from ollama_deep_researcher.internet_block import internet_research

while True:
    user_question = input("Ти: ")

    if user_question.lower() in ["exit", "quit", "вихід"]:
        break

    result = internet_research(
        user_question,
        model="gemma4:e4b",
        max_loops=0,
        fetch_full_page=False,
    )

    print("\nAI:")
    print(result.answer)
    print()