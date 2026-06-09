import pytest
import os
from src import database

def test_database_initialization():
    """Verify that the database initializes correctly and the tables are created."""
    # Ensure the init_db function doesn't crash
    database.init_db()
    
    # Test simple insert and retrieval
    query = "Test Query"
    answer = "Test Answer"
    sources = [{"url": "http://test.com"}]
    
    research_id = database.save_research(query, answer, sources)
    assert research_id is not None
    assert isinstance(research_id, int)
    
    # Retrieve and verify
    record = database.get_research_by_id(research_id)
    assert record is not None
    assert record["query"] == query
    assert record["answer"] == answer
    
    # Cleanup (optional but good practice)
    # Note: A real test DB should be used, but this is a minimal viable test.
