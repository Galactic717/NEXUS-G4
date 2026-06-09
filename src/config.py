from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    server_host: str = Field(default="127.0.0.1", alias="HOST")
    server_port: int = Field(default=8000, alias="PORT")
    debug: bool = Field(default=True, alias="DEBUG")

    ollama_url: str = Field(
        default="http://localhost:11434/api/generate",
        alias="OLLAMA_URL",
    )
    model_name: str = Field(default="qwen2.5-coder:14b", alias="MODEL_NAME")
    dolphin_model_name: str = Field(default="dolphin-free", alias="DOLPHIN_MODEL_NAME")
    temperature: float = Field(default=0.85, alias="TEMPERATURE")
    top_p: float = Field(default=0.92, alias="TOP_P")
    max_tokens: int = Field(default=8192, alias="MAX_TOKENS")
    context_size: int = Field(default=8192, alias="CONTEXT_SIZE")

    database_path: str = Field(default="../data/news.db", alias="DATABASE_PATH")
    news_limit: int = Field(default=20, alias="NEWS_LIMIT")
    max_search_results: int = Field(default=30, alias="MAX_SEARCH_RESULTS")

    search_api_key: str = Field(default="dev-secret-key", alias="SEARCH_API_KEY")

    enable_proxy: bool = Field(default=False, alias="ENABLE_PROXY")
    proxy_url: str = Field(default="socks5://127.0.0.1:9050", alias="PROXY_URL")
    stealth_mode: bool = Field(default=True, alias="STEALTH_MODE")
    search_depth: str = Field(default="aggressive", alias="SEARCH_DEPTH")

    tavily_api_key: Optional[str] = Field(default=None, alias="TAVILY_API_KEY")
    perplexity_api_key: Optional[str] = Field(default=None, alias="PERPLEXITY_API_KEY")
    google_api_key: Optional[str] = Field(default=None, alias="GOOGLE_API_KEY")
    google_cse_id: Optional[str] = Field(default=None, alias="GOOGLE_CSE_ID")
    shodan_api_key: Optional[str] = Field(default=None, alias="SHODAN_API_KEY")
    telegram_bot_token: Optional[str] = Field(default=None, alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: Optional[str] = Field(default=None, alias="TELEGRAM_CHAT_ID")
    tor_proxy: str = Field(default="socks5h://127.0.0.1:9050", alias="TOR_PROXY")
    tor_control_port: int = Field(default=9051, alias="TOR_CONTROL_PORT")

    @field_validator("server_port")
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError(f"port must be 1..65535, got {v}")
        return v

    @field_validator("search_depth")
    @classmethod
    def valid_depth(cls, v: str) -> str:
        allowed = {"quick", "normal", "aggressive"}
        if v.lower() not in allowed:
            raise ValueError(f"search_depth must be one of {allowed}, got {v}")
        return v.lower()


settings = Settings()
