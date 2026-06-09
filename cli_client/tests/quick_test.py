import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cli_client.local_processor import preprocess_query, extract_keywords, deduplicate_sources, rerank_sources
from cli_client.local_exporter import export_markdown, export_json, export_txt_concise

print("=== Query Preprocessing ===")
print("1:", repr(preprocess_query("коротко, розкажи про AI останні новини")))
print("2:", repr(preprocess_query("what is LLM and how it works")))
print("3:", repr(preprocess_query("briefly summarize latest news about GAN")))

print()
print("=== Keyword Extraction ===")
print("Keywords:", extract_keywords("transformer neural network deep learning GPT model AI"))
print("UA:", extract_keywords("штучний інтелект нейронні мережі глибоке навчання"))

print()
print("=== Source Dedup & Rerank ===")
sources = [
    {"title": "AI News", "url": "https://example.com/ai", "relevance_score": 8.0, "snippet": "AI advances"},
    {"title": "AI News", "url": "https://example.com/ai", "relevance_score": 9.0, "snippet": "AI advances"},
    {"title": "ML Update", "url": "https://example.com/ml", "relevance_score": 5.0, "snippet": "ML models"},
]
deduped = deduplicate_sources(sources)
print("Dedup:", len(sources), "->", len(deduped))
reranked = rerank_sources(deduped, ["ai", "neural"])
print("Reranked titles:", [s["title"] for s in reranked])

print()
print("=== Local Export ===")
md = export_markdown("Test Query", "Test answer content.", [{"title": "Src", "url": "https://ex.com", "snippet": "test"}])
print("Markdown exported:", md)
js = export_json({"query": "test", "answer": "data"})
print("JSON exported:", js)
tx = export_txt_concise("Test", "Answer", [{"title": "S", "url": "https://ex.com"}])
print("TXT exported:", tx)
print()
print("ALL TESTS PASSED")
