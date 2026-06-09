# server/ai_module.py
import logging
from config import settings
from ollama_deep_researcher.internet_block import internet_research

logger = logging.getLogger("AI-Search-Module")


def ask_ai(question: str):
    """Run web-grounded research and return an answer plus frontend sources."""

    try:
        logger.info(f"AI Module: Processing question: {question}")
        result = internet_research(
            question,
            model=settings.model_name,
            max_loops=0,
            fetch_full_page=True,
        )

        sources = []
        for source in result.source_details:
            sources.append(
                {
                    "title": source.get("title") or "Знайдене джерело",
                    "url": source.get("url"),
                    "source": "Internet",
                    "content": source.get("snippet") or "",
                    "id": source.get("id"),
                    "fetched_at": source.get("fetched_at"),
                }
            )

        if not sources:
            for source in result.sources:
                sources.append(
                    {
                        "title": "Знайдене джерело",
                        "url": source,
                        "source": "Internet",
                        "content": "",
                    }
                )

        return result.answer, sources

    except Exception as e:
        logger.error(f"AI Module Integration Error: {e}", exc_info=True)
        return f"Помилка інтеграції з інтернет-модулем: {str(e)}", []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info("--- Тестовий запуск інтегрованого AI модуля ---")
    test_q = "Які останні новини про мову програмування Mojo?"
    answer, sources = ask_ai(test_q)
    logger.info(f"\nAI: {answer}")
    logger.info(f"\nДжерела ({len(sources)}):")
    for source in sources:
        logger.info(f"- [{source.get('id')}] {source.get('title')}: {source.get('url')}")
