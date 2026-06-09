from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_duckduckgo_search(monkeypatch):
    """Mock DuckDuckGo so tests do not make real network requests."""

    def fake_search(query, max_results=3, fetch_full_page=False):
        raw_content = (
            "Останні розробки у сфері ШІ показують стрімке зростання. "
            "Нові моделі Gemma та Llama вражають своїми можливостями."
        )
        return {
            "results": [
                {
                    "source_id": "S1",
                    "fetched_at": "2026-05-26T12:00:00+00:00",
                    "title": "Штучний інтелект сьогодні",
                    "url": "https://example.com/ai-news",
                    "content": "Останні розробки у сфері ШІ показують стрімке зростання.",
                    "raw_content": raw_content if fetch_full_page else "Останні розробки у сфері ШІ показують стрімке зростання.",
                }
            ]
        }

    monkeypatch.setattr("ollama_deep_researcher.utils.duckduckgo_search", fake_search)
    return fake_search


@pytest.fixture
def mock_chat_ollama(monkeypatch):
    """Mock local LLM calls so tests do not require Ollama."""

    mock_response = MagicMock()
    mock_response.content = (
        "<think>draft</think>"
        "## Результати розумного пошуку:\n"
        "Технології ШІ активно розвиваються у 2026 році [S1]."
    )

    def fake_invoke(self, messages):
        return mock_response

    monkeypatch.setattr("langchain_ollama.ChatOllama.invoke", fake_invoke)
    return fake_invoke
