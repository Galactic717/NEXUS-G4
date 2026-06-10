"""Small callable internet-research block for a local Ollama model.

The public function in this module is intentionally simple: pass a user/AI
question in, get back the final answer, sources, and gathered article text.
"""

from __future__ import annotations

from config import settings
import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, List, Dict

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_ollama import ChatOllama

from ollama_deep_researcher.graph import graph
from ollama_deep_researcher.prompts import summarizer_instructions
from .bio_prompts import bio_summarizer_instructions
from ollama_deep_researcher import utils
from memory_module import search_memory, save_to_memory, consolidate_memory
from llm_factory import LLMFactory
import logging

logger = logging.getLogger("AI-Search-InternetBlock")

DEFAULT_MODEL = "gemma4:unrestricted"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
TEMPORAL_QUERY_RE = re.compile(
    r"\b(today|latest|recent|current|now)\b|сьогодні|сегодня|останні|последние|актуальн|новин",
    re.IGNORECASE,
)
LEADING_INSTRUCTION_RE = re.compile(
    r"^\s*(коротко|стисло|будь ласка|будь-ласка|знайди|поясни|розкажи|"
    r"shortly|briefly|please|find|search|tell me|explain)\s*[:\-–—,]?\s+",
    re.IGNORECASE,
)
ANSWER_INSTRUCTION_RE = re.compile(
    r"(?i)(?:^|[.!?]\s+)(відповідай|дай відповідь|напиши|answer|respond|reply)"
    r".*$",
    re.DOTALL,
)
LEADING_QUESTION_RE = re.compile(
    r"^\s*(які|яка|яке|який|що|чому|як|де|коли|чи|"
    r"what|which|why|how|where|when)\s+",
    re.IGNORECASE,
)


def detect_search_type(query: str) -> str:
    """Визначає тип запиту: людина, email, телефон, загальний"""
    # Перевірка на ПІБ (3 слова, українські/російські літери)
    name_pattern = re.compile(r'^[А-ЯІЇЄҐа-яіїєґ\']+\s+[А-ЯІЇЄҐа-яіїєґ\']+\s+[А-ЯІЇЄҐа-яіїєґ\']+$')
    if name_pattern.match(query.strip()):
        return "person"
    
    # Перевірка на email
    if '@' in query and '.' in query:
        return "email"
    
    # Перевірка на телефон
    phone_clean = re.sub(r'[\s\-\+\(\)]', '', query)
    if phone_clean.isdigit() and len(phone_clean) >= 10:
        return "phone"
    
    return "general"


@dataclass
class InternetResearchResult:
    query: str
    answer: str
    sources: list[str]
    gathered_text: list[str]
    source_details: list[dict[str, Any]]


def internet_research(
    query: str,
    *,
    model: str = DEFAULT_MODEL,
    max_loops: int = 2,
    search_api: str = "duckduckgo",
    fetch_full_page: bool = True,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    search_only: bool = False,
    progress: bool = False,
) -> InternetResearchResult:
    if not query.strip():
        raise ValueError("query must not be empty")

    load_dotenv()

    # Пошук у власній пам'яті для використання накопичених знань
    memory_context = search_memory(query)

    if search_only or max_loops <= 0:
        return _single_pass_research(
            query,
            model=model,
            search_api=search_api,
            fetch_full_page=fetch_full_page,
            ollama_base_url=ollama_base_url,
            search_only=search_only,
            progress=progress,
        )

    config: dict[str, Any] = {
        "configurable": {
            "llm_provider": "ollama",
            "local_llm": os.getenv("MODEL_NAME", "qwen2.5-coder:14b"),
            "dolphin_llm": model,  # Passed from arguments, usually dolphin-free
            "ollama_base_url": ollama_base_url,
            "search_api": search_api,
            "fetch_full_page": fetch_full_page,
            "max_web_research_loops": max_loops,
            "strip_thinking_tokens": True,
            "use_tool_calling": False,
        }
    }

    _log("Starting deep research graph with memory context...", progress)
    output = _invoke_graph_with_progress(query, config, progress=progress, memory_context=memory_context)

    return InternetResearchResult(
        query=query,
        answer=output.get("running_summary", ""),
        sources=output.get("sources_gathered", []),
        gathered_text=output.get("web_research_results", []),
        source_details=output.get("source_details", []),
    )


def internet_research_stream(
    query: str,
    *,
    model: str = DEFAULT_MODEL,
    max_loops: int = 2,
    search_api: str = "duckduckgo",
    fetch_full_page: bool = True,
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL,
    search_only: bool = False,
    progress: bool = False,
    history: Optional[List[Dict[str, str]]] = None,
    mode: str = "general"
):
    if not query.strip():
        raise ValueError("query must not be empty")

    load_dotenv()
    
    # Максимальна кількість джерел (включно з усіма провайдерами)
    # 0 loops = Швидкий пошук (40 джерел) 
    # 1+ loops = Глибокий пошук (60 джерел)
    search_limit = 40 if max_loops == 0 else 60
    mode_name = "Швидкий" if max_loops == 0 else "Глибокий"
    
    yield json.dumps({"type": "progress", "message": f"{mode_name} пошук в Інтернеті ({search_limit} сайтів)..."}) + "\n"

    from memory_module import search_memory, save_to_memory, consolidate_memory
    
    # Пошук у власній пам'яті для використання накопичених знань
    past_knowledge = search_memory(query)
    if past_knowledge:
        yield json.dumps({"type": "progress", "message": "Знайдено релевантні знання у власній пам'яті... Використовую для глибшого аналізу."}) + "\n"

    # Використовуємо фабрику для ініціалізації LLM з ПОВНИМ 128K контекстом
    llm = LLMFactory.get_llm(model_name=model)

    # Автоматичне "очищення" та перетворення довгого промту в пошуковий запит через ШІ
    search_query = query
    if len(query.split()) > 8:
        yield json.dumps({"type": "progress", "message": "Оптимізація пошукового запиту..."}) + "\n"
        from ollama_deep_researcher.prompts import query_writer_instructions
        
        try:
            from ollama_deep_researcher.utils import get_current_date, get_current_year
            refine_msg = llm.invoke([
                SystemMessage(content=query_writer_instructions.format(
                    current_date=get_current_date(), 
                    current_year=get_current_year(),
                    research_topic=query
                )),
                HumanMessage(content="Згенеруй ОДИН короткий технічний пошуковий запит для Google/DuckDuckGo на основі мого тексту. Видай ТІЛЬКИ JSON.")
            ])
            content = refine_msg.content
            if "{" in content:
                data = json.loads(content[content.find("{"):content.rfind("}")+1])
                search_query = data.get("query", query)
            else:
                search_query = content.strip()
        except Exception as e:
            logger.error(f"Failed to refine query: {e}")
            search_query = query

    # AI-powered розширення запиту синонімами для кращого покриття
    expanded_query = _expand_query_with_synonyms(search_query)
    if expanded_query != search_query:
        yield json.dumps({"type": "progress", "message": f"Розширено запит: '{search_query}' → '{expanded_query}'"}) + "\n"
        search_query = expanded_query

    # ── OSINT People Integration ──
    osint_context = ""
    search_type = detect_search_type(query)
    
    # Режим NEXUS або виявлений спеціальний тип
    if mode == "nexus" or search_type != "general":
        targets = []
        if mode == "nexus":
            yield json.dumps({"type": "progress", "message": "🌀 Активовано режим NEXUS: Повномасштабний збір даних..."}) + "\n"
            targets = ["people", "darknet", "shodan"]
        else:
            targets = [search_type]

        from config import settings
        special_results = {}

        # 1. People OSINT
        if "person" in targets or "people" in targets:
            yield json.dumps({"type": "progress", "message": "🔍 Шукаємо профілі та зв'язки особи..."}) + "\n"
            from .osint_people import PeopleOSINT
            try:
                people_searcher = PeopleOSINT(tor_proxy=settings.tor_proxy)
                p_data = people_searcher.search_by_full_name(query)
                special_results["people"] = p_data
                if p_data.get("profiles"):
                    yield json.dumps({"type": "sources", "sources": [{"title": f"Profile: {p['platform']}", "url": p['url'], "source": "OSINT_People"} for p in p_data["profiles"]]}) + "\n"
            except Exception as e: logger.error(f"Nexus People error: {e}")

        # 2. Darknet
        if "darknet" in targets:
            yield json.dumps({"type": "progress", "message": "🌑 Скануємо Darknet (.onion)..."}) + "\n"
            from .darknet import DarknetSearch
            try:
                darknet = DarknetSearch(tor_proxy=settings.tor_proxy)
                d_data = darknet.ahmia_search(query)
                special_results["darknet"] = d_data
            except Exception as e: logger.error(f"Nexus Darknet error: {e}")

        # 3. Shodan
        if "shodan" in targets:
            yield json.dumps({"type": "progress", "message": "📡 Перевірка мережевої інфраструктури (Shodan)..."}) + "\n"
            from .shodan_search import ShodanSearch
            try:
                shodan = ShodanSearch(api_key=settings.shodan_api_key)
                s_data = shodan.search(query, limit=5)
                special_results["shodan"] = s_data
            except Exception as e: logger.error(f"Nexus Shodan error: {e}")

        osint_context = f"\n## NEXUS ENRICHED DATA\n{json.dumps(special_results, ensure_ascii=False, indent=2)}\n"

    search_results, gathered_text, sources = _search_web(
        search_query,
        search_api=search_api,
        fetch_full_page=fetch_full_page,
        progress=progress,
        max_results=search_limit,
    )
    
    # Додаємо старі знання та OSINT дані до нового контексту
    full_context = ""
    if past_knowledge:
        full_context += f"## Local Memory Context\n{past_knowledge}\n\n"
    if osint_context:
        full_context += osint_context + "\n"
    
    full_context += f"## Internet Search Results\n{gathered_text}"

    source_details_list = _source_details(search_results)
    
    yield json.dumps({"type": "sources", "sources": source_details_list}) + "\n"

    if search_only:
        yield json.dumps({"type": "token", "content": "Search-only mode: gathered sources without LLM analysis."}) + "\n"
        return

    if not search_results.get("results"):
        yield json.dumps({"type": "token", "content": "## Summary\nI could not find relevant web sources for this request.\n"}) + "\n"
        return

    yield json.dumps({"type": "progress", "message": "Генерація глибокої аналітичної відповіді..."}) + "\n"
    
    # Вибір інструкцій залежно від режиму
    current_summarizer_instr = summarizer_instructions
    if mode == "bio":
        current_summarizer_instr = bio_summarizer_instructions
    
    # Створюємо ланцюжок повідомлень з історією діалогу
    messages_chain = [SystemMessage(content=current_summarizer_instr)]
    
    if history:
        for msg in history:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "user":
                messages_chain.append(HumanMessage(content=content))
            elif role == "assistant":
                messages_chain.append(AIMessage(content=content))
                
    messages_chain.append(
        HumanMessage(
            content=(
                f"Current date: {datetime.now().strftime('%Y-%m-%d')}.\n"
                f"<Context>\n{full_context}\n</Context>\n\n"
                f"Проведи ГЛИБОКИЙ АНАЛІЗ за наступним запитом. Використовуй ANALYSIS_FRAMEWORK з інструкцій:\n"
                f"1) Ключові факти та цифри\n"
                f"2) Порівняння та контрасти між джерелами\n"
                f"3) Тренди та закономірності\n"
                f"4) Протиріччя та застереження\n"
                f"5) Висновки\n\n"
                f"Запит: {query}"
            )
        )
    )
    
    stream = llm.stream(messages_chain)

    think_mode = False
    think_buffer = ""
    full_answer = ""
    for chunk in stream:
        content = chunk.content
        if not content:
            continue
            
        # Покращена фільтрація think-токенів з буферизацією
        if "<think" in content:
            think_mode = True
            before_think = content.split("<think")[0]
            if before_think:
                full_answer += before_think
                yield json.dumps({"type": "token", "content": before_think}) + "\n"
            think_buffer = ""
            continue
            
        if think_mode:
            think_buffer += content
            if "</think>" in content:
                think_mode = False
                after_think = content.split("</think>")[-1]
                if after_think:
                    full_answer += after_think
                    yield json.dumps({"type": "token", "content": after_think}) + "\n"
            continue
            
        if content:
            full_answer += content
            yield json.dumps({"type": "token", "content": content}) + "\n"
    
    # Якщо think-режим так і не закрився, все одно використовуємо накопичене
    if think_mode and think_buffer:
        full_answer += " " + think_buffer
        yield json.dumps({"type": "token", "content": " " + think_buffer}) + "\n"
            
    # Збереження нових знань після завершення генерації + консолідація
    if full_answer:
        save_to_memory(query, full_answer)
        consolidate_memory(query)

    yield json.dumps({"type": "token", "content": f"\n\n### Sources:\n{sources}"}) + "\n"



def _log(message: str, enabled: bool) -> None:
    if enabled:
        logger.info(message)


def _expand_query_with_synonyms(query: str) -> str:
    """Розширює пошуковий запит синонімами для кращого покриття."""
    synonyms = {
        r'\bAI\b': 'AI artificial intelligence machine learning',
        r'\bLLM\b': 'LLM large language model',
        r'\bML\b': 'ML machine learning',
        r'\bNLP\b': 'NLP natural language processing',
        r'\bNN\b': 'NN neural network',
        r'\bGPU\b': 'GPU graphics card',
        r'\bRAG\b': 'RAG retrieval augmented generation',
        r'\bAGI\b': 'AGI artificial general intelligence',
        r'\bCNN\b': 'CNN convolutional neural network',
        r'\bRNN\b': 'RNN recurrent neural network',
        r'\bGAN\b': 'GAN generative adversarial network',
        r'\bVAE\b': 'VAE variational autoencoder',
        r'\bRL\b': 'RL reinforcement learning',
        r'\bDL\b': 'DL deep learning',
        r'\bSOTA\b': 'SOTA state of the art',
        r'\bMCP\b': 'MCP model context protocol',
    }
    expanded = query
    for pattern, replacement in synonyms.items():
        if re.search(pattern, query, re.IGNORECASE):
            if replacement not in expanded:
                expanded = expanded + " " + replacement
    return expanded


def _search_web(
    query: str,
    *,
    search_api: str,
    fetch_full_page: bool,
    progress: bool,
    max_results: int = 15,
) -> tuple[dict[str, Any], str, str]:
    search_query = _prepare_search_query(query)
    _log(f"Searching web via {search_api} (limit {max_results}): {search_query}", progress)

    # Паралельний пошук через ВСІ доступні провайдери одночасно
    if search_api == "duckduckgo":
        # Паралельний пошук через ВСІ загальні пошукові системи (DuckDuckGo, Tavily, Bing, Google)
        search_results = utils.parallel_search(
            search_query,
            max_results=max_results,
            fetch_full_page=fetch_full_page,
        )
    elif search_api == "tavily":
        search_results = utils.tavily_search(
            search_query,
            max_results=max_results,
            fetch_full_page=fetch_full_page,
        )
    elif search_api == "perplexity":
        search_results = utils.perplexity_search(search_query)
    elif search_api == "searxng":
        search_results = utils.searxng_search(
            search_query,
            max_results=max_results,
            fetch_full_page=fetch_full_page,
        )
    else:
        raise ValueError(f"Unsupported search API: {search_api}")

    # Fallback: якщо результатів 0, а в запиті був доданий рік — пробуємо БЕЗ року
    if not search_results.get("results") and search_query != query:
        _log(f"No results with year. Retrying with original query: {query}", progress)
        search_results = utils.parallel_search(
            query,
            max_results=max_results,
            fetch_full_page=fetch_full_page,
        )
        search_query = query

    utils.annotate_source_relevance(search_results, search_query)
    utils.assign_source_ids(search_results)
    
    # AI аналізує ВСІ знайдені джерела
    gathered_text = utils.deduplicate_and_format_sources(
        search_results,
        max_tokens_per_source=1000000,
        fetch_full_page=fetch_full_page,
    )
    
    # Для візуалізації залишаємо ТОП 20 релевантних (було 15)
    display_results = {
        "results": search_results.get("results", [])[:20]
    }
    sources = utils.format_sources(display_results)
    
    _log(f"Found {len(search_results.get('results', []))} source(s). AI will analyze all, but UI will show top 20.", progress)
    return search_results, gathered_text, sources


def _prepare_search_query(query: str) -> str:
    cleaned = _clean_search_query(query)
    cleaned = _expand_ai_query(cleaned)
    return _add_current_date_for_temporal_query(cleaned)


def _clean_search_query(query: str) -> str:
    cleaned = " ".join(query.strip().split())
    cleaned = LEADING_INSTRUCTION_RE.sub("", cleaned)
    cleaned = ANSWER_INSTRUCTION_RE.sub("", cleaned).strip()
    cleaned = LEADING_QUESTION_RE.sub("", cleaned)
    cleaned = cleaned.strip(" :-–—,.;")
    return cleaned or query.strip()


def _expand_ai_query(query: str) -> str:
    lowered = query.lower()
    has_ai_marker = any(marker in lowered for marker in (" ai", "ai ", "шi", "ші"))
    has_news_marker = any(marker in lowered for marker in ("новин", "news", "latest", "останні"))

    if has_ai_marker and has_news_marker and "штуч" not in lowered:
        return f"{query} штучний інтелект artificial intelligence"
    return query


def _add_current_date_for_temporal_query(query: str) -> str:
    if not TEMPORAL_QUERY_RE.search(query):
        return query

    current_year = datetime.now().strftime("%Y")
    if current_year in query:
        return query
    return f"{query} {current_year}"


def _source_details(search_results: dict[str, Any]) -> list[dict[str, Any]]:
    details = []
    for source in search_results.get("results", [])[:15]:
        details.append(
            {
                "id": source.get("source_id"),
                "title": source.get("title"),
                "url": source.get("url"),
                "snippet": source.get("content"),
                "fetched_at": source.get("fetched_at"),
                "content_chars": len(source.get("raw_content") or ""),
                "relevance_score": source.get("relevance_score", 0.0),
            }
        )
    return details


def _single_pass_research(
    query: str,
    *,
    model: str,
    search_api: str,
    fetch_full_page: bool,
    ollama_base_url: str,
    search_only: bool,
    progress: bool,
) -> InternetResearchResult:
    search_results, gathered_text, sources = _search_web(
        query,
        search_api=search_api,
        fetch_full_page=fetch_full_page,
        progress=progress,
        max_results=50,
    )

    if search_only:
        return InternetResearchResult(
            query=query,
            answer="Search-only mode: gathered sources without LLM analysis.",
            sources=[sources],
            gathered_text=[gathered_text],
            source_details=_source_details(search_results),
        )

    if not search_results.get("results"):
        return InternetResearchResult(
            query=query,
            answer=(
                "## Summary\n"
                "I could not find relevant web sources for this request, so I cannot "
                "produce a source-grounded answer.\n\n"
                "### Sources:\n"
            ),
            sources=[],
            gathered_text=[],
            source_details=[],
        )

    _log(f"Summarizing with Ollama model {model} ({settings.context_size // 1024}K context)...", progress)
    # Використовуємо фабрику з оптимізованим контекстом
    llm = LLMFactory.get_llm(
        model_name=model,
        temperature=0,
        num_ctx=settings.context_size,
        base_url=ollama_base_url,
    )
    response = llm.invoke(
        [
            SystemMessage(content=summarizer_instructions),
            HumanMessage(
                content=(
                    f"Current date: {datetime.now().strftime('%Y-%m-%d')}.\n"
                    f"<Context>\n{gathered_text}\n</Context>\n\n"
                    f"Проведи ГЛИБОКИЙ АНАЛІЗ за наступним запитом. Використовуй ANALYSIS_FRAMEWORK:\n"
                    f"1) Ключові факти та цифри\n"
                    f"2) Порівняння та контрасти\n"
                    f"3) Тренди та закономірності\n"
                    f"4) Протиріччя\n"
                    f"5) Висновки\n\n"
                    f"Запит: {query}"
                )
            ),
        ]
    )
    logger.info("Raw LLM Response (first 200 chars): %s", response.content[:200].replace("\n", " "))
    answer = utils.strip_thinking_tokens(response.content)

    return InternetResearchResult(
        query=query,
        answer=f"## Summary\n{answer}\n\n### Sources:\n{sources}",
        sources=[sources],
        gathered_text=[gathered_text],
        source_details=_source_details(search_results),
    )


def _invoke_graph_with_progress(
    query: str,
    config: dict[str, Any],
    *,
    progress: bool,
    memory_context: str = "",
) -> dict[str, Any]:
    invoke_input = {"research_topic": query}
    if memory_context:
        invoke_input["memory_context"] = memory_context

    if not progress:
        return graph.invoke(invoke_input, config=config)

    state: dict[str, Any] = {
        "research_topic": query,
        "sources_gathered": [],
        "web_research_results": [],
        "source_details": [],
        "memory_context": memory_context or None,
    }
    for update in graph.stream(
        {"research_topic": query},
        config=config,
        stream_mode="updates",
    ):
        for node_name, node_update in update.items():
            _log(f"Completed step: {node_name}", progress)
            if not node_update:
                continue
            for key, value in node_update.items():
                if key in {"sources_gathered", "web_research_results", "source_details"} and isinstance(
                    value, list
                ):
                    state.setdefault(key, []).extend(value)
                else:
                    state[key] = value
    return state


def _main() -> None:
    parser = argparse.ArgumentParser(description="Run local internet research with Ollama.")
    parser.add_argument("query", help="Research question or search topic")
    parser.add_argument("--model", default=os.getenv("LOCAL_LLM", DEFAULT_MODEL))
    parser.add_argument("--loops", type=int, default=int(os.getenv("MAX_WEB_RESEARCH_LOOPS", "2")))
    parser.add_argument("--search-api", default=os.getenv("SEARCH_API", "duckduckgo"))
    parser.add_argument(
        "--fetch-full-page",
        action=argparse.BooleanOptionalAction,
        default=os.getenv("FETCH_FULL_PAGE", "true").lower() == "true",
    )
    parser.add_argument(
        "--search-only",
        action="store_true",
        help="Only search and collect source text; skip Ollama summarization.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print progress messages to stderr.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show full Python traceback on errors.",
    )
    parser.add_argument("--out", type=Path, help="Optional JSON output file")
    args = parser.parse_args()

    try:
        result = internet_research(
            args.query,
            model=args.model,
            max_loops=args.loops,
            search_api=args.search_api,
            fetch_full_page=args.fetch_full_page,
            search_only=args.search_only,
            progress=not args.quiet,
        )
    except KeyboardInterrupt:
        logger.warning("Stopped by user.")
        raise SystemExit(130) from None
    except Exception as exc:
        logger.error("internet_research error: %s", exc)
        if args.debug:
            raise
        raise SystemExit(1) from None

    payload = json.dumps(asdict(result), ensure_ascii=False, indent=2)

    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    sys.stdout.buffer.write(payload.encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    _main()
