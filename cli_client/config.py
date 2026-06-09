import json
import os
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "ai-osint-cli"
CONFIG_FILE = CONFIG_DIR / "config.json"
CACHE_DIR = CONFIG_DIR / "cache"
EXPORT_DIR = CONFIG_DIR / "exports"

DEFAULT_CONFIG = {
    "server_url": "http://127.0.0.1:8000",
    "api_key": "dev-secret-key",
    "default_loops": 0,
    "default_search_only": False,
    "theme": "dark",
    "default_limit": 10,
    "timeout": 120,
}


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return {**DEFAULT_CONFIG, **json.load(f)}
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(config: dict):
    ensure_dirs()
    merged = {**DEFAULT_CONFIG, **config}
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False)


def get(key: str, default=None):
    return load_config().get(key, default)


def set_key(key: str, value):
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
