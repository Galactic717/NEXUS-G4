# Venator: Autonomous Intelligence Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-State_Machine-red.svg)](https://github.com/langchain-ai/langgraph)
[![Biomedical](https://img.shields.io/badge/Domain-Biomedical_Research-green.svg)](#)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Venator** is an advanced autonomous research system engineered for deep information retrieval, technical analysis, and biomedical synthesis. Powered by **LangGraph** and local **LLMs (Gemma 4)**, it functions as an artificial analyst capable of multi-step reasoning, gap identification, and specialized data mining.

## 🚀 Key Features

*   **Agentic Intelligence (LangGraph):** Employs a sophisticated state machine to manage complex research cycles, ensuring exhaustive coverage of topics.
*   **Specialized Search Engines:**
    *   **Biomedical:** Direct integration with **NCBI PubMed** for peer-reviewed medical research.
    *   **OSINT:** Deep people search and registry analysis.
    *   **Cybersecurity:** Integrated **Shodan** and **Darknet (Tor)** search capabilities.
    *   **Technical:** Parallel querying across Google, DuckDuckGo, and Tavily with stealth-bypass technology.
*   **Enterprise Reporting:** Generates professional-grade analytical reports with verifiable citations and structured synthesis.
*   **Venator Browser:** A custom headless browser controller for bypassing Cloudflare and collecting deep-page data (HTML, screenshots, state).
*   **Privacy-First:** Optimized for high-performance local execution using **Ollama** and **Gemma 4**.

## 🛠 Technology Stack

*   **Backend:** FastAPI, Python 3.11+
*   **AI Framework:** LangChain, LangGraph
*   **Search Protocols:** Entrez (PubMed), Shodan API, Tor Proxy, Jina Reader.
*   **Data Handling:** SQLAlchemy with high-concurrency retry logic.
*   **Frontend:** Premium Glassmorphism UI (Vanilla JS & React).

## 📦 Quick Start

1.  **Clone & Setup:**
    ```bash
    git clone https://github.com/your-username/Venator.git
    cd Venator
    python -m venv .venv
    .\.venv\Scripts\activate
    pip install -r requirements.txt
    ```

2.  **Configuration:** Configure `.env` with your API keys (PubMed/Entrez email, Shodan, etc.).

3.  **Launch:**
    ```bash
    python run_app.py
    ```

## 📊 Technical Presentation

Venator demonstrates proficiency in:
1.  **Stateful Multi-Agent Systems:** Handling long-running research loops without state drift.
2.  **Specialized Data Acquisition:** Fetching and processing data from non-standard sources (Darknet, PubMed).
3.  **Advanced RAG:** Local vector memory for session-long context persistence.

---
*Developed by Гліб Сергійович Степанов as a demonstration of next-generation autonomous research agents.*
