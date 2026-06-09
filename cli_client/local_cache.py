import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from . import config


def _get_db_path() -> Path:
    return config.CACHE_DIR / "cli_cache.db"


def _conn() -> sqlite3.Connection:
    db_path = _get_db_path()
    config.ensure_dirs()
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_cache():
    conn = _conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cached_researches (
            id INTEGER PRIMARY KEY,
            query TEXT NOT NULL,
            answer TEXT NOT NULL DEFAULT '',
            sources_json TEXT NOT NULL DEFAULT '[]',
            messages_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            cached_at REAL NOT NULL,
            server_id INTEGER,
            tags TEXT NOT NULL DEFAULT ''
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS cache_fts USING fts5(
            query, answer, tags,
            content='cached_researches',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TABLE IF NOT EXISTS cache_triggers (
            name TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1
        );

        INSERT OR IGNORE INTO cache_triggers (name, enabled) VALUES ('fts_sync', 1);
    """)

    conn.commit()
    conn.close()


def _ensure_fts_triggers(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS cache_fts_insert AFTER INSERT ON cached_researches BEGIN
            INSERT INTO cache_fts(rowid, query, answer, tags)
            VALUES (new.id, new.query, new.answer, new.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS cache_fts_delete AFTER DELETE ON cached_researches BEGIN
            INSERT INTO cache_fts(cache_fts, rowid, query, answer, tags)
            VALUES ('delete', old.id, old.query, old.answer, old.tags);
        END;

        CREATE TRIGGER IF NOT EXISTS cache_fts_update AFTER UPDATE ON cached_researches BEGIN
            INSERT INTO cache_fts(cache_fts, rowid, query, answer, tags)
            VALUES ('delete', old.id, old.query, old.answer, old.tags);
            INSERT INTO cache_fts(rowid, query, answer, tags)
            VALUES (new.id, new.query, new.answer, new.tags);
        END;
    """)


def save_to_cache(
    query: str,
    answer: str,
    sources: List[Dict[str, Any]],
    messages: Optional[List[Dict[str, Any]]] = None,
    server_id: Optional[int] = None,
    tags: str = "",
) -> int:
    conn = _conn()
    _ensure_fts_triggers(conn)
    created_at = datetime.now().isoformat()
    cached_at = time.time()
    sources_json = json.dumps(sources, ensure_ascii=False)
    messages_json = json.dumps(messages or [], ensure_ascii=False)

    cur = conn.execute(
        """INSERT INTO cached_researches
           (query, answer, sources_json, messages_json, created_at, cached_at, server_id, tags)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (query, answer, sources_json, messages_json, created_at, cached_at, server_id, tags),
    )
    row_id = cur.lastrowid
    conn.commit()
    conn.close()
    return row_id


def search_cache(query: str, limit: int = 20) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        """SELECT cr.*, rank
           FROM cache_fts
           JOIN cached_researches cr ON cr.id = cache_fts.rowid
           WHERE cache_fts MATCH ?
           ORDER BY rank
           LIMIT ?""",
        (query, limit),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_all_cached(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM cached_researches ORDER BY cached_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_cached_by_id(cache_id: int) -> Optional[Dict[str, Any]]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM cached_researches WHERE id = ?", (cache_id,)
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def get_cached_by_server_id(server_id: int) -> Optional[Dict[str, Any]]:
    conn = _conn()
    row = conn.execute(
        "SELECT * FROM cached_researches WHERE server_id = ? ORDER BY cached_at DESC LIMIT 1",
        (server_id,),
    ).fetchone()
    conn.close()
    return _row_to_dict(row) if row else None


def update_tags(cache_id: int, tags: str):
    conn = _conn()
    conn.execute("UPDATE cached_researches SET tags = ? WHERE id = ?", (tags, cache_id))
    conn.commit()
    conn.close()


def delete_from_cache(cache_id: int) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM cached_researches WHERE id = ?", (cache_id,))
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def clear_cache():
    conn = _conn()
    conn.executescript("DELETE FROM cached_researches; DELETE FROM cache_fts;")
    conn.commit()
    conn.close()


def get_cache_stats() -> Dict[str, Any]:
    conn = _conn()
    count = conn.execute("SELECT COUNT(*) as cnt FROM cached_researches").fetchone()["cnt"]
    oldest = conn.execute("SELECT MIN(cached_at) as t FROM cached_researches").fetchone()["t"]
    newest = conn.execute("SELECT MAX(cached_at) as t FROM cached_researches").fetchone()["t"]
    total_chars = conn.execute(
        "SELECT SUM(LENGTH(answer)) as total FROM cached_researches"
    ).fetchone()["total"]
    conn.close()

    def ts(epoch):
        return datetime.fromtimestamp(epoch).isoformat() if epoch else None

    return {
        "total_entries": count,
        "oldest": ts(oldest),
        "newest": ts(newest),
        "total_chars": total_chars or 0,
    }


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    try:
        d["sources"] = json.loads(d.pop("sources_json", "[]"))
    except (json.JSONDecodeError, KeyError):
        d["sources"] = []
    try:
        d["messages"] = json.loads(d.pop("messages_json", "[]"))
    except (json.JSONDecodeError, KeyError):
        d["messages"] = []
    return d
