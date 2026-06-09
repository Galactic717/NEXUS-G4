import sys
import os
from pathlib import Path

# Додаємо шлях до папки server, щоб Python бачив пакет ollama_deep_researcher
sys.path.append(str(Path(__file__).parent))

from ollama_deep_researcher.internet_block import internet_research

print("Запуск інтегрованого тесту пошуку...")
try:
    result = internet_research(
        "Останні новини про ШІ на сьогодні",
        model="gemma4:e4b",
        max_loops=0,
        fetch_full_page=False,
    )
    print("\nРезультат від AI:")
    print(result.answer)
except Exception as e:
    print(f"\nСталася помилка: {e}")

