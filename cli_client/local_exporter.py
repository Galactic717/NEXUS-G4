import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from . import config


def _export_dir() -> Path:
    return config.EXPORT_DIR


def export_markdown(
    query: str,
    answer: str,
    sources: List[Dict[str, Any]],
    output_path: Optional[str] = None,
) -> str:
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in query[:30])
        output_path = str(_export_dir() / f"report_{safe_name}_{ts}.md")

    lines = []
    lines.append(f"# {query}")
    lines.append("")
    lines.append(f"_Generated: {datetime.now().isoformat()}_")
    lines.append("")
    lines.append("## Answer")
    lines.append("")
    lines.append(answer)
    lines.append("")
    lines.append("## Sources")
    lines.append("")
    for i, s in enumerate(sources, 1):
        title = s.get("title", "Untitled")
        url = s.get("url", "")
        snippet = s.get("snippet", "")
        relevance = s.get("relevance_score", "N/A")
        lines.append(f"### [{i}] {title}")
        lines.append(f"- **URL:** {url}")
        lines.append(f"- **Relevance:** {relevance}")
        if snippet:
            lines.append(f"- **Snippet:** {snippet}")
        lines.append("")

    content = "\n".join(lines)
    Path(output_path).write_text(content, encoding="utf-8")
    return output_path


def export_json(
    data: Dict[str, Any],
    output_path: Optional[str] = None,
) -> str:
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in data.get("query", "export")[:30])
        output_path = str(_export_dir() / f"data_{safe_name}_{ts}.json")

    Path(output_path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def export_cached_bundle(
    entries: List[Dict[str, Any]],
    output_path: Optional[str] = None,
) -> str:
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(_export_dir() / f"cache_bundle_{ts}.json")

    bundle = {
        "exported_at": datetime.now().isoformat(),
        "count": len(entries),
        "entries": entries,
    }
    Path(output_path).write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output_path


def export_txt_concise(
    query: str,
    answer: str,
    sources: List[Dict[str, Any]],
    output_path: Optional[str] = None,
) -> str:
    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() else "_" for c in query[:30])
        output_path = str(_export_dir() / f"concise_{safe_name}_{ts}.txt")

    lines = []
    lines.append(f"Query: {query}")
    lines.append(f"Date: {datetime.now().isoformat()}")
    lines.append("")
    lines.append(answer)
    lines.append("")
    lines.append("--- Sources ---")
    for i, s in enumerate(sources, 1):
        lines.append(f"{i}. {s.get('title', '')} - {s.get('url', '')}")

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    return output_path
