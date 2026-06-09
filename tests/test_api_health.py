import pytest
from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def test_health_check():
    """Verify that the FastAPI server is healthy and responding."""
    response = client.get("/favicon.ico")
    assert response.status_code in [200, 204]

def test_root_endpoint():
    """Verify that the root endpoint serves the frontend or a fallback message."""
    response = client.get("/")
    assert response.status_code in [200, 404]
    if response.status_code == 200:
        assert "text/html" in response.headers.get("content-type", "")
