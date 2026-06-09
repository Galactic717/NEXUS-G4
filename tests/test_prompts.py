import pytest
from src.ollama_deep_researcher.prompts import summarizer_instructions, query_writer_instructions, reflection_instructions

def test_prompts_loaded():
    """Verify that essential LangGraph prompts are loaded and not empty."""
    assert summarizer_instructions is not None
    assert len(summarizer_instructions) > 50
    
    assert query_writer_instructions is not None
    assert "{current_date}" in query_writer_instructions
    
    assert reflection_instructions is not None
    assert "Apex-Auditor" in reflection_instructions

def test_corporate_compliance():
    """Ensure the prompts adhere to enterprise compliance (no darknet/exploit mentions)."""
    assert "darknet" not in summarizer_instructions.lower()
    assert "exploit" not in summarizer_instructions.lower()
    assert "unrestricted" not in summarizer_instructions.lower()
