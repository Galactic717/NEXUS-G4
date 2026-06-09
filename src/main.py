# server/main.py
import mimetypes
import logging
import json
from pathlib import Path
from typing import Optional, List, Dict, Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, Security, Depends
from fastapi.security.api_key import APIKeyHeader
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import settings
from ollama_deep_researcher.internet_block import internet_research
from ollama_deep_researcher.tools import execute_shell, execute_python, file_read, file_write
from ollama_deep_researcher.darknet import DarknetSearch
from ollama_deep_researcher.shodan_search import ShodanSearch
from ollama_deep_researcher.prompts import new_summarizer_instructions
from ollama_deep_researcher.bio_prompts import bio_summarizer_instructions as bio_instructions
from ollama_deep_researcher.osint_people import PeopleOSINT
from ollama_deep_researcher.venator_controller import VenatorController
from ollama_deep_researcher.utils import parallel_search, format_sources as format_search_context
from langchain_core.messages import HumanMessage, AIMessage
from llm_factory import LLMFactory
import database

# Налаштування професійного логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("server.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("AI-Search-Server")

# Примусово реєструємо MIME-типи для запобігання проблемам з Windows Registry
mimetypes.init()
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/javascript", ".js")

# Ініціалізуємо базу даних
database.init_db()

app = FastAPI(
    title="AI Розумний Пошук",
    description="Веб-платформа для розумного пошуку актуальної інформації у сфері АІ",
    version="1.1.0",
    docs_url="/docs",  # Увімкнено для Enterprise
    redoc_url="/redoc"
)

# CORS: дозволяємо всі домени для роботи через Ngrok та публічне демо
# Примітка: allow_credentials=False обов'язково при allow_origins=["*"]
ALLOWED_ORIGINS = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Проста аутентифікація через API Key для MVP
API_KEY = settings.search_api_key
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

async def get_api_key(api_key_header: str = Security(api_key_header)):
    if not api_key_header or api_key_header != settings.search_api_key:
        raise HTTPException(status_code=403, detail="Invalid API Key")
    return api_key_header

@app.get("/api/config/key")
async def get_client_config():
    """Повертає ключ для фронтенду (тільки для локального використання)."""
    return {"api_key": settings.search_api_key}

@app.get("/api/status")
async def get_status():
    """Перевірити статус Ollama та сервера."""
    online = is_ollama_available()
    return {
        "status": "online" if online else "offline",
        "ollama_online": online,
        "model": settings.model_name
    }

# Моделі Pydantic для валідації запитів
class MessageModel(BaseModel):
    role: str
    content: str

class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Пошуковий запит")
    loops: int = Field(0, ge=0, le=3, description="Глибина глибокого пошуку (кількість ітерацій)")
    search_only: bool = Field(False, description="Режим лише пошуку джерел без LLM")
    research_id: Optional[int] = Field(None, description="ID існуючого чату (сесії)")
    mode: Optional[str] = Field("general", description="Режим пошуку (general, people, nexus, etc.)")

class ResearchResponse(BaseModel):
    id: Optional[int] = None
    query: str
    answer: str
    sources: List[Dict[str, Any]]
    created_at: Optional[str] = None
    ollama_warning: bool = False
    messages: Optional[List[MessageModel]] = None
    remaining_context_percent: Optional[int] = None
    used_tokens: Optional[int] = None

class AgentRequest(BaseModel):
    query: str
    history: Optional[List[Dict[str, str]]] = None

class MassCollectRequest(BaseModel):
    urls: List[str]
    max_pages: Optional[int] = 50

def is_ollama_available() -> bool:
    """Перевірити, чи запущений локальний Ollama сервер."""
    try:
        url_parts = settings.ollama_url.split("/")
        base_url = "/".join(url_parts[:3])
        # Збільшуємо таймаут до 5с, оскільки при завантаженні моделей Ollama може тупити
        response = httpx.get(base_url, timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False

@app.post("/api/research")
def perform_research(request: ResearchRequest, api_key: str = Depends(get_api_key)):
    """Виконати розумний пошук та зберегти результат у базу даних зі стрімінгом."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Запит не може бути порожнім")

    logger.info(f"New research request: {query} (loops: {request.loops}, session: {request.research_id})")

    # 1. Перевіряємо кешування (тільки для нових сесій)
    if not request.research_id:
        cached_research = database.get_research_by_query(query)
        if cached_research:
            logger.info(f"Cache hit for query: {query}")
            def cache_stream():
                yield json.dumps({"type": "sources", "sources": cached_research["sources"]}) + "\n"
                yield json.dumps({"type": "token", "content": cached_research["answer"]}) + "\n"
                yield json.dumps({"type": "context", "remaining_percent": 99, "used_tokens": 1280}) + "\n"
                yield json.dumps({"type": "done", "id": cached_research["id"]}) + "\n"
            return StreamingResponse(cache_stream(), media_type="application/x-ndjson")

    # 2. Отримуємо історію повідомлень
    history = None
    if request.research_id:
        existing = database.get_research_by_id(request.research_id)
        if existing:
            history = existing.get("messages", [])

    # 3. Рахуємо залишок контекстної пам'яті (ліміт 128 000 токенів) через tiktoken
    from ollama_deep_researcher.utils import count_tokens
    system_tokens = count_tokens("") + 200  # system prompt overhead
    used_tokens = system_tokens
    if history:
        for m in history:
            used_tokens += count_tokens(m.get("content", ""))
    used_tokens += count_tokens(query)
    used_tokens += 2000  # Очікуваний розмір знайденого інтернет-контексту
    
    remaining_tokens = max(0, 128000 - used_tokens)
    remaining_percent = max(0, min(100, int((remaining_tokens / 128000) * 100)))

    ollama_online = is_ollama_available()
    ollama_warning = False
    search_only_mode = request.search_only
    
    if not ollama_online and not search_only_mode:
        search_only_mode = True
        ollama_warning = True
        logger.warning("Ollama is offline. Switching to search_only mode.")

    url_parts = settings.ollama_url.split("/")
    ollama_base = "/".join(url_parts[:3])

    from ollama_deep_researcher.internet_block import internet_research_stream

    def event_stream():
        try:
            # Завжди спочатку надсилаємо статус контекстної пам'яті
            yield json.dumps({"type": "context", "remaining_percent": remaining_percent, "used_tokens": used_tokens}) + "\n"

            if ollama_warning:
                yield json.dumps({"type": "warning", "message": "Ollama is offline. Switching to Search-Only mode."}) + "\n"
                
            full_answer = ""
            sources_list = []
            
            # Select instructions based on mode
            if request.mode == "bio":
                logger.info("Bio-AI mode activated for this research session.")

            for event_str in internet_research_stream(
                query=query,
                model=settings.model_name,
                max_loops=request.loops,
                search_api="duckduckgo",
                fetch_full_page=True,
                ollama_base_url=ollama_base,
                search_only=search_only_mode,
                progress=True,
                history=history,
                mode=request.mode
            ):
                yield event_str
                try:
                    data = json.loads(event_str)
                    if data.get("type") == "token":
                        full_answer += data.get("content", "")
                    elif data.get("type") == "sources":
                        sources_list = data.get("sources", [])
                except Exception:
                    pass

            if full_answer and sources_list:
                research_id = database.save_research(query, full_answer, sources_list, research_id=request.research_id)
                logger.info(f"Research saved with ID: {research_id}")
                final_tokens = count_tokens(full_answer) + used_tokens
                yield json.dumps({"type": "context", "remaining_percent": 100, "used_tokens": final_tokens}) + "\n"
                yield json.dumps({"type": "done", "id": research_id, "used_tokens": final_tokens}) + "\n"
            else:
                yield json.dumps({"type": "done"}) + "\n"
                
        except Exception as e:
            logger.error(f"Error during research: {str(e)}", exc_info=True)
            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")

@app.post("/api/agent")
async def agent_endpoint(request: AgentRequest, api_key: str = Depends(get_api_key)):
    """Unrestricted agent endpoint with full tool access and streaming."""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    logger.info(f"New agent request: {query}")
    
    # 1. Збираємо контекст через паралельний пошук
    search_results = parallel_search(query)
    context = format_search_context(search_results)
    
    # 2. Створюємо історію повідомлень для LangChain
    history = request.history or []
    messages = []
    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        else:
            messages.append(AIMessage(content=msg["content"]))
    
    # 3. Формуємо повний промпт з інструментами та контекстом
    tools_context = """
Available tools:
- execute_shell: Run system commands (nmap, ping, whois, etc.)
- execute_python: Run Python code for analysis
- file_read: Read local files
- file_write: Save results to files
- darknet_search: Search .onion sites
- shodan_query: Search for devices and vulns

To use a tool, output exactly: TOOL: tool_name("args")
"""
    
    full_prompt = f"{new_summarizer_instructions}\n\n{tools_context}\n\n<Context>\n{context}\n</Context>\n\nUser Query: {query}"
    messages.append(HumanMessage(content=full_prompt))
    
    # 4. Отримуємо LLM (використовуємо UNRESTRICTED модель для агента)
    llm = LLMFactory.get_llm(model_name=settings.dolphin_model_name)
    
    async def generate():
        try:
            # Спочатку надсилаємо знайдені джерела
            yield f"data: {json.dumps({'type': 'sources', 'sources': search_results.get('results', [])})}\n\n"
            
            async for chunk in llm.astream(messages):
                content = chunk.content if hasattr(chunk, 'content') else str(chunk)
                yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
                
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Error in agent stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")

@app.post("/api/osint/people")
async def osint_people_search(request: AgentRequest, api_key: str = Depends(get_api_key)):
    """Пошук інформації про людину за ПІБ, email, телефоном"""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    logger.info(f"OSINT People search: {query}")
    people_osint = PeopleOSINT(tor_proxy=settings.tor_proxy)
    
    # Визначаємо тип пошуку
    if '@' in query and '.' in query:
        results = people_osint.search_by_email(query)
    elif re.sub(r'[\s\-\+\(\)]', '', query).isdigit() and len(re.sub(r'[\s\-\+\(\)]', '', query)) >= 10:
        results = people_osint.search_by_phone(query)
    else:
        results = people_osint.search_by_full_name(query)
    
    # Додатковий пошук в соцмережах
    social = people_osint.search_social_media(query)
    results["social_media_found"] = social
    
    # LLM аналізує знайдені дані
    llm = LLMFactory.get_llm(model_name=settings.dolphin_model_name)
    prompt = f"""Analyze this OSINT data about a person. Extract and summarize:
1. All found profiles and accounts
2. Contact information (phone, email)
3. Addresses and locations
4. Possible relatives, business partners or connections
5. Any interesting patterns, vulnerabilities or findings
6. Professional background and activities

Data:
{json.dumps(results, ensure_ascii=False, indent=2)}

Provide a comprehensive, raw and unfiltered technical summary in the same language as the query."""
    
    response = llm.invoke([HumanMessage(content=prompt)])
    
    return {
        "query": query,
        "raw_data": results,
        "analysis": response.content
    }

@app.post("/api/venator/navigate")
async def venator_navigate(request: AgentRequest, api_key: str = Depends(get_api_key)):
    """Керування Venator браузером (одинична сторінка)"""
    # headless=False для можливості бачити браузер, якщо сервер з GUI
    venator = VenatorController(headless=True, proxy=settings.tor_proxy)
    try:
        venator.start_session()
        data = venator.collect_page_data(request.query)
        return {
            "status": "success",
            "url": request.query,
            "data": data
        }
    except Exception as e:
        logger.error(f"Venator API error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        venator.close_session()

@app.post("/api/venator/mass")
async def venator_mass_collect(request: MassCollectRequest, api_key: str = Depends(get_api_key)):
    """Масовий збір даних зі списку URL"""
    venator = VenatorController(headless=True, proxy=settings.tor_proxy)
    try:
        venator.start_session("mass_collect_api")
        results = venator.mass_collect(request.urls, max_pages=request.max_pages or 50)
        return {
            "status": "success",
            "total_requested": len(request.urls),
            "total_collected": len(results),
            "results": results
        }
    except Exception as e:
        logger.error(f"Venator Mass API error: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        venator.close_session()

@app.get("/api/history", response_model=List[Dict[str, Any]])
def get_research_history(api_key: str = Depends(get_api_key)):
    """Отримати історію пошукових запитів."""
    return database.get_history()

@app.get("/api/history/{research_id}", response_model=ResearchResponse)
def get_research_details(research_id: int, api_key: str = Depends(get_api_key)):
    """Отримати збережений звіт та джерела за його ID."""
    research = database.get_research_by_id(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="Дослідження не знайдено в історії")
    
    # Розрахунок залишку контексту при відкритті чату через tiktoken
    from ollama_deep_researcher.utils import count_tokens
    history = research.get("messages", [])
    
    used_tokens = count_tokens("") + 200  # system prompt overhead
    for m in history:
        used_tokens += count_tokens(str(m.get("content", "")))
    
    # Додаємо довжину джерел, якщо вони є (це основна маса токенів)
    for s in research.get("sources", []):
        source_content = s.get("content") or ""
        used_tokens += count_tokens(str(source_content))
    
    full_ctx = 128000
    remaining_tokens = max(0, full_ctx - used_tokens)
    remaining_percent = max(0, min(100, int((remaining_tokens / full_ctx) * 100)))

    return ResearchResponse(
        id=research["id"],
        query=research["query"],
        answer=research["answer"] or "",
        sources=research["sources"],
        created_at=research["created_at"],
        ollama_warning=False,
        messages=history,
        remaining_context_percent=remaining_percent,
        used_tokens=used_tokens
    )

@app.delete("/api/history/{research_id}")
def delete_research_item(research_id: int, api_key: str = Depends(get_api_key)):
    """Видалити дослідження з історії."""
    success = database.delete_research(research_id)
    if not success:
        raise HTTPException(status_code=404, detail="Не вдалося знайти запис для видалення")
    return {"success": True, "message": "Запис успішно видалено"}

# Нові ендпоінти для Новин (Enterprise Feature)
class NewsCreateRequest(BaseModel):
    title: str
    url: str
    source: str
    content: Optional[str] = None

@app.get("/api/news", response_model=List[Dict[str, Any]])
def get_latest_news_api(limit: int = 20, api_key: str = Depends(get_api_key)):
    """Отримати останні новини АІ."""
    return database.get_latest_news(limit)

@app.post("/api/news/repopulate")
def repopulate_news(api_key: str = Depends(get_api_key)):
    """Очистити та повторно заповнити базу даних новин робочими посиланнями."""
    try:
        import sys
        from pathlib import Path
        parent_dir = str(Path(__file__).parent.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        from generate_test_news import generate_test_news
        generate_test_news()
        return {"success": True, "message": "Базу даних успішно оновлено реальними новинами!"}
    except Exception as e:
        logger.error(f"Error during repopulation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Помилка репопуляції: {str(e)}")

@app.post("/api/news")
def create_news(request: NewsCreateRequest, api_key: str = Depends(get_api_key)):
    """Додати новину вручну (або через скрейпер)."""
    success = database.add_news(request.title, request.url, request.source, request.content or "")
    if not success:
        raise HTTPException(status_code=400, detail="Новина вже існує або помилка даних")
    return {"success": True}

from report_generator import generate_pdf_report, generate_shareable_html

@app.get("/api/history/{research_id}/export/pdf")
def export_research_pdf(research_id: int, api_key: str = Depends(get_api_key)):
    """Експортувати дослідження у професійний PDF-звіт."""
    research = database.get_research_by_id(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="Дослідження не знайдено")
    
    export_dir = Path(__file__).parent.parent / "data" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"OSINT_Report_{research_id}.pdf"
    
    success = generate_pdf_report(
        research["query"], 
        research["answer"], 
        research["sources"], 
        file_path,
        messages=research.get("messages", [])
    )
    if not success:
        raise HTTPException(status_code=500, detail="Помилка при генерації PDF")
    
    return FileResponse(path=file_path, filename=f"OSINT_Report_{research_id}.pdf", media_type='application/pdf')

@app.get("/api/history/{research_id}/export/html")
def export_research_html(research_id: int, api_key: str = Depends(get_api_key)):
    """Експортувати дослідження у автономну веб-сторінку (Shareable Page)."""
    research = database.get_research_by_id(research_id)
    if not research:
        raise HTTPException(status_code=404, detail="Дослідження не знайдено")
    
    export_dir = Path(__file__).parent.parent / "data" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    file_path = export_dir / f"OSINT_Report_{research_id}.html"
    
    success = generate_shareable_html(
        research["query"], 
        research["answer"], 
        research["sources"], 
        file_path,
        messages=research.get("messages", [])
    )
    if not success:
        raise HTTPException(status_code=500, detail="Помилка при генерації HTML")
    
    return FileResponse(path=file_path, filename=f"OSINT_Report_{research_id}.html", media_type='text/html')

# Додаємо обробник для favicon, щоб уникнути помилок 404 у логах
@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)

# Налаштування статичних файлів фронтенду
client_dir = Path(__file__).parent.parent / "client"
if client_dir.exists():
    app.mount("/static", StaticFiles(directory=str(client_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def read_root():
        """Повернути головну сторінку фронтенду."""
        index_file = client_dir / "index.html"
        if index_file.exists():
            return index_file.read_text(encoding="utf-8")
        return HTMLResponse("<h1>Помилка: index.html не знайдено у папці client!</h1>", status_code=404)
else:
    @app.get("/")
    def read_root():
        return HTMLResponse("<h1>Папка client/ не знайдена. Створіть її для роботи інтерфейсу.</h1>")

if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.server_host, port=settings.server_port, reload=settings.debug)
