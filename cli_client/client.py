import json
import sys
import requests
from typing import Optional, Dict, Any, List, Generator

from . import config


def _headers() -> Dict[str, str]:
    return {
        "X-API-KEY": config.get("api_key", "dev-secret-key"),
        "Content-Type": "application/json",
    }


def _url(path: str) -> str:
    base = config.get("server_url", "http://127.0.0.1:8000")
    return f"{base.rstrip('/')}{path}"


def check_server() -> bool:
    try:
        resp = requests.get(_url("/"), timeout=3)
        return resp.status_code == 200
    except requests.RequestException:
        return False


def research_stream(
    query: str,
    loops: int = 0,
    search_only: bool = False,
    research_id: Optional[int] = None,
) -> Generator[Dict[str, Any], None, None]:
    timeout_val = config.get("timeout", 120)
    payload = {
        "query": query,
        "loops": loops,
        "search_only": search_only,
        "research_id": research_id,
    }
    with requests.post(
        _url("/api/research"),
        json=payload,
        headers=_headers(),
        stream=True,
        timeout=timeout_val,
    ) as resp:
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail", "")
            except Exception:
                detail = resp.text
            yield {"type": "error", "message": f"HTTP {resp.status_code}: {detail}"}
            return

        buffer = ""
        for chunk in resp.iter_content(chunk_size=1, decode_unicode=True):
            if chunk:
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        yield data
                    except json.JSONDecodeError:
                        yield {"type": "token", "content": line}


def get_history() -> List[Dict[str, Any]]:
    resp = requests.get(_url("/api/history"), headers=_headers(), timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return []


def get_research_detail(research_id: int) -> Optional[Dict[str, Any]]:
    resp = requests.get(_url(f"/api/history/{research_id}"), headers=_headers(), timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return None


def delete_research(research_id: int) -> bool:
    resp = requests.delete(_url(f"/api/history/{research_id}"), headers=_headers(), timeout=10)
    return resp.status_code == 200


def get_news(limit: int = 20) -> List[Dict[str, Any]]:
    resp = requests.get(_url(f"/api/news?limit={limit}"), headers=_headers(), timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return []


def repopulate_news() -> bool:
    resp = requests.post(_url("/api/news/repopulate"), headers=_headers(), timeout=30)
    return resp.status_code == 200


def export_pdf(research_id: int, output_path: str) -> bool:
    resp = requests.get(_url(f"/api/history/{research_id}/export/pdf"), headers=_headers(), timeout=30)
    if resp.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    return False


def export_html(research_id: int, output_path: str) -> bool:
    resp = requests.get(_url(f"/api/history/{research_id}/export/html"), headers=_headers(), timeout=30)
    if resp.status_code == 200:
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    return False
