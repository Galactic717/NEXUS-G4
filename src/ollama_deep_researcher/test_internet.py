from ollama_deep_researcher.internet_block import internet_research

result = internet_research(
    "What is LangGraph used for?",
    model="gemma4:e4b",
    max_loops=0,
    fetch_full_page=False,
)

print(result.answer)