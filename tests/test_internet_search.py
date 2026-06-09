import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).parent.parent))

from ai_module import ask_ai
from ollama_deep_researcher.graph import _parse_json_model_output
from ollama_deep_researcher.internet_block import (
    _clean_search_query,
    _prepare_search_query,
    internet_research,
)
from ollama_deep_researcher.utils import (
    _jina_reader_url,
    _normalize_bing_url,
    annotate_source_relevance,
    assign_source_ids,
    filter_search_results,
)


def test_empty_query():
    with pytest.raises(ValueError, match="query must not be empty"):
        internet_research("")

    with pytest.raises(ValueError, match="query must not be empty"):
        internet_research("   ")


def test_quick_research(mock_duckduckgo_search, mock_chat_ollama):
    query_text = "Які новини про ШІ?"

    result = internet_research(
        query_text,
        model="gemma4:e4b",
        max_loops=0,
        fetch_full_page=False,
    )

    assert result.query == query_text
    assert "<think>" not in result.answer
    assert "</think>" not in result.answer
    assert "Результати розумного пошуку" in result.answer
    assert "[S1]" in result.answer

    assert len(result.sources) == 1
    assert "[S1]" in result.sources[0]
    assert "https://example.com/ai-news" in result.sources[0]

    assert len(result.gathered_text) == 1
    assert "[S1] Source: Штучний інтелект сьогодні" in result.gathered_text[0]

    assert result.source_details[0]["id"] == "S1"
    assert result.source_details[0]["title"] == "Штучний інтелект сьогодні"
    assert result.source_details[0]["url"] == "https://example.com/ai-news"
    assert result.source_details[0]["fetched_at"] == "2026-05-26T12:00:00+00:00"
    assert result.source_details[0]["content_chars"] == len(
        "Останні розробки у сфері ШІ показують стрімке зростання."
    )
    assert result.source_details[0]["relevance_score"] > 0


def test_search_only_mode(mock_duckduckgo_search):
    result = internet_research(
        "Тестовий пошук без ШІ",
        search_only=True,
        fetch_full_page=False,
    )

    assert "Search-only mode" in result.answer
    assert len(result.sources) == 1
    assert "[S1]" in result.sources[0]
    assert "https://example.com/ai-news" in result.sources[0]
    assert result.source_details[0]["url"] == "https://example.com/ai-news"


def test_ai_module_ask_ai_integration(mock_duckduckgo_search, mock_chat_ollama):
    answer, sources = ask_ai("Які останні новини про Mojo?")

    assert answer is not None
    assert "<think>" not in answer
    assert "Результати розумного пошуку" in answer

    assert len(sources) == 1
    assert sources[0]["id"] == "S1"
    assert sources[0]["url"] == "https://example.com/ai-news"
    assert sources[0]["source"] == "Internet"
    assert sources[0]["title"] == "Штучний інтелект сьогодні"
    assert sources[0]["fetched_at"] == "2026-05-26T12:00:00+00:00"


def test_thinking_model_json_output_is_parsed_after_cleanup():
    content = (
        "<think>I should create a focused search query.</think>\n"
        '{"query": "latest AI coding agents 2026", "rationale": "fresh topic"}'
    )

    parsed = _parse_json_model_output(content, strip_thinking=True)

    assert parsed["query"] == "latest AI coding agents 2026"


def test_jina_reader_url_keeps_original_scheme_valid():
    assert (
        _jina_reader_url("https://example.com/page?q=ai")
        == "https://r.jina.ai/http://example.com/page?q=ai"
    )
    assert (
        _jina_reader_url("http://example.com/page?q=ai")
        == "https://r.jina.ai/http://example.com/page?q=ai"
    )


def test_search_query_cleanup_removes_answer_instructions():
    cleaned = _clean_search_query(
        "Коротко: які AI новини за сьогодні, 26 травня 2026? "
        "Відповідай українською і цитуй джерела."
    )

    assert cleaned == "AI новини за сьогодні, 26 травня 2026"
    assert "Коротко" not in cleaned
    assert "Відповідай" not in cleaned


def test_prepared_ai_news_query_removes_question_words_and_adds_domain_terms(monkeypatch):
    # Mock datetime to ensure the temporal query adds the expected date regardless of when the test runs
    import datetime as dt_module
    class MockDatetime:
        @staticmethod
        def now():
            class MockNow:
                @staticmethod
                def strftime(fmt):
                    return "2026-05-26"
            return MockNow()
    monkeypatch.setattr("ollama_deep_researcher.internet_block.datetime", MockDatetime)

    prepared = _prepare_search_query(
        "Коротко: які AI новини за сьогодні, 26 травня 2026? "
        "Відповідай українською і цитуй джерела."
    )

    assert not prepared.lower().startswith("які")
    assert "штучний інтелект" in prepared
    assert "artificial intelligence" in prepared
    assert "2026-05-26" in prepared


def test_source_ids_can_be_assigned_globally_across_research_steps():
    first = {"results": [{"title": "A", "url": "https://a.test", "content": "AI news"}]}
    second = {"results": [{"title": "B", "url": "https://b.test", "content": "AI agents"}]}

    assign_source_ids(first, start_index=1)
    assign_source_ids(second, start_index=2)

    assert first["results"][0]["source_id"] == "S1"
    assert second["results"][0]["source_id"] == "S2"


def test_relevance_score_is_added_to_sources():
    search_response = {
        "results": [
            {
                "title": "AI coding agents update",
                "url": "https://example.com/ai-coding-agents",
                "content": "AI coding agents are changing software engineering.",
            }
        ]
    }

    annotate_source_relevance(search_response, "AI coding agents latest")

    assert search_response["results"][0]["relevance_score"] > 0


def test_bing_redirect_url_is_decoded():
    decoded = _normalize_bing_url(
        "https://www.bing.com/ck/a?!&&u=a1aHR0cHM6Ly9haXRvb2xseS5jb20vYWktbmV3cy8yMDI2LTA1LTI2"
    )

    assert decoded == "https://aitoolly.com/ai-news/2026-05-26"


def test_filter_search_results_passthrough():
    search_response = {
        "results": [
            {"title": "A", "url": "https://a.com", "content": "a", "relevance_score": 0.0},
            {"title": "B", "url": "https://b.com", "content": "b", "relevance_score": 1.0},
        ]
    }
    result = filter_search_results(search_response)
    assert len(result["results"]) == 2


def test_no_sources_skips_llm_call(monkeypatch):
    monkeypatch.setattr(
        "ollama_deep_researcher.utils.duckduckgo_search",
        lambda *args, **kwargs: {"results": []},
    )
    monkeypatch.setattr(
        "ollama_deep_researcher.utils.bing_reader_search",
        lambda *args, **kwargs: {"results": []},
    )
    monkeypatch.setattr(
        "ollama_deep_researcher.utils.google_reader_search",
        lambda *args, **kwargs: {"results": []},
    )

    def fail_if_called(self, messages):
        raise AssertionError("LLM should not be called when no sources are available")

    monkeypatch.setattr("langchain_ollama.ChatOllama.invoke", fail_if_called)

    result = internet_research("AI news today", max_loops=0, search_only=False)

    assert "could not find relevant web sources" in result.answer
    assert result.source_details == []
