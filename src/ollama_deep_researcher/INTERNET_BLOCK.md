# Internet Block for `gemma4:e4b`

This repository was cloned from `langchain-ai/ollama-deep-researcher` and adapted as a callable internet module for a local Ollama model:

- model: `gemma4:e4b`
- provider: Ollama at `http://localhost:11434`
- default search: DuckDuckGo, no API key required
- research style: iterative query generation, source reading, summary, reflection, follow-up search, final answer

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
ollama pull gemma4:e4b
```

Ollama must be running locally before calling the module.

## Function API

```python
from ollama_deep_researcher.internet_block import internet_research

result = internet_research(
    "What are the best current approaches for extracting article text from web pages?",
    model="gemma4:e4b",
    max_loops=2,
)

print(result.answer)
print(result.sources)
print(result.gathered_text)
```

`result.gathered_text` contains the formatted source text: title, URL, snippet, and fetched page content when available. `result.answer` is the model's final analyzed answer with sources.

## CLI

Fast smoke test without the LLM:

```powershell
python -m ollama_deep_researcher.internet_block "що таке LangGraph?" --search-only --no-fetch-full-page --out result.json
```

Fast one-pass answer with the LLM:

```powershell
python -m ollama_deep_researcher.internet_block "your research question" --loops 0 --no-fetch-full-page --out result.json
```

After `pip install -e .`, this shortcut is also available:

```powershell
internet-block "your research question" --loops 0 --no-fetch-full-page --out result.json
```

For deeper research, increase `--loops` to `1` or `2`. The default model `gemma4:e4b` is large, so deeper runs can take several minutes on CPU-heavy setups.

## How Your AI Should Use It

Call `internet_research(user_question)` whenever the AI needs fresh information. Feed `result.answer`, `result.sources`, and optionally `result.gathered_text` back into the main AI context so it can produce the final user-facing response.
