# Deep Researcher PRO: Enterprise Autonomous Search System

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![LangGraph](https://img.shields.io/badge/LangGraph-State_Machine-orange.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

An advanced, multi-agent autonomous research system designed for deep information retrieval, data aggregation, and factual synthesis. Built with a focus on modular architecture, local LLM execution, and verifiable output.

## 🏗 System Architecture (Multi-Agent State Machine)

Deep Researcher PRO leverages **LangGraph** to implement cyclic reflection loops. Rather than performing a single linear search, the system continuously evaluates its findings against the user's query, identifies knowledge gaps, and dynamically generates follow-up queries until comprehensive coverage is achieved.

- **Orchestrator Node:** Manages the state graph and controls the execution flow.
- **Search Node:** Interfaces with external APIs (DuckDuckGo, Tavily) with concurrent asynchronous execution.
- **Analysis Node:** Evaluates retrieved HTML/text, extracting relevant facts and citing sources.
- **Reflection Node (Apex-Auditor):** Analyzes the current knowledge state to determine if further iterations are required.

## 🌟 Engineering Highlights

1. **Stateful Multi-Agent Workflows:** Uses LangChain's `StateGraph` to maintain context across complex, multi-step research operations.
2. **Enterprise API Design:** Backend built with **FastAPI**, featuring Server-Sent Events (SSE) for real-time token streaming and status updates.
3. **Local Privacy-First Execution:** Fully integrated with the Ollama ecosystem (Gemma 4, Llama 3) to ensure sensitive queries remain on-device.
4. **Persistent Vector Memory:** Utilizes an SQLite FTS5 backend to index past research, creating a searchable local knowledge base.

## 🚀 Quick Start

1. **Environment Setup:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configuration:**
   ```bash
   cp .env.example .env
   # Add optional API keys (Tavily, etc.)
   ```

3. **Launch Server & UI:**
   ```bash
   python run_app.py
   ```
   *The system provides an interactive CLI to choose between Local Web UI, Headless Server, or Electron Desktop modes.*

## 🧪 Testing
The project includes a comprehensive Pytest suite covering API endpoints, data processing, and external integrations.
```bash
pytest tests/
```

---
*Designed for scalable, verifiable, and private data intelligence.*
