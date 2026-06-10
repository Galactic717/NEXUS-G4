# Deep Researcher PRO: Enterprise Autonomous Search System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-State_Machine-red.svg)](https://github.com/langchain-ai/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Deep Researcher PRO** — це передова система автономного дослідження, побудована на базі циклічних графів (LangGraph) та локальних LLM (Ollama). Вона імітує роботу аналітика-людини: шукає інформацію, аналізує її, знаходить прогалини в знаннях і проводить уточнюючі пошуки до повного вичерпання теми.

## 🚀 Ключові особливості

*   **Agentic Workflow (LangGraph):** Використання повноцінного державного автомата для керування циклом дослідження.
*   **Агресивний Дата-Майнінг:** Кастомні промпти для витягування жорстких фактів, цифр та бенчмарків.
*   **Multi-Provider Search:** Паралельний пошук через DuckDuckGo, Tavily, Google Search API, Shodan та Darknet (Tor).
*   **Enterprise Reporting:** Генерація професійних PDF та HTML звітів з інтерактивними посиланнями та цитуванням джерел.
*   **Privacy First:** Повна підтримка локальних моделей (Gemma 4, Llama 3) через Ollama.
*   **Smart Retry Logic:** Автоматичне коригування пошукових запитів при нульових результатах.

## 🛠 Технологічний стек

*   **Backend:** FastAPI, Python 3.11+
*   **AI Framework:** LangChain, LangGraph
*   **Database:** SQLite + SQLAlchemy (з підтримкою retry-механізмів для високого навантаження)
*   **Frontend:** Vanilla JS (Premium Glassmorphism UI), Lucide Icons
*   **OSINT Tools:** Tor Proxy, Shodan API, Jina Reader bypass

## 📦 Встановлення та запуск

1.  **Клонуйте репозиторій:**
    ```bash
    git clone https://github.com/your-username/Deep_Researcher_PRO.git
    cd Deep_Researcher_PRO
    ```

2.  **Налаштуйте середовище:**
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```

3.  **Конфігурація:** Скопіюйте `.env.example` у `.env` та додайте свої ключі (Tavily, Shodan).

4.  **Запуск:**
    ```bash
    python run_app.py
    ```

## 📊 Презентація для інженерів

Проект демонструє глибоке розуміння **Agentic AI**:
1.  **Циклічне мислення:** Система не просто відповідає на запит, а будує план дослідження.
2.  **Валідація джерел:** Автоматичне оцінювання релевантності кожного знайденого сайту (Scoring Algorithm).
3.  **Стійкість:** Реалізовано обхід Cloudflare через Stealth-заголовки та Jina Reader.

---
*Розроблено як демонстрація можливостей сучасних AI-агентів у сфері інформаційної безпеки та технічного аналізу.*
