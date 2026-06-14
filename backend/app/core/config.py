from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Enterprise AI Knowledge Base"
    database_url: str = "sqlite:///./data/app.db"
    secret_key: str = "change-this-in-production"
    access_token_expire_minutes: int = 1440
    upload_dir: Path = Path("./data/uploads")
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dimensions: int = 512
    retrieval_top_k: int = 8
    retrieval_candidate_multiplier: int = 4
    rerank_top_k: int = 3
    retrieval_min_score: float = 0.25
    evidence_min_score: float = 0.38
    evidence_min_lexical_score: float = 0.08
    chunk_size: int = 700
    chunk_overlap: int = 100
    chat_history_messages: int = 8
    rerank_provider: str = "llm"
    rerank_api_key: str = ""
    rerank_base_url: str = ""
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    task_poll_interval_seconds: float = 2.0
    task_max_attempts: int = 3
    task_retry_base_seconds: int = 15
    task_stale_after_seconds: int = 900
    task_eager: bool = False
    upload_max_bytes: int = 25 * 1024 * 1024
    upload_max_documents_per_kb: int = 100
    auth_rate_limit: int = 10
    auth_rate_window_seconds: int = 60
    upload_rate_limit: int = 30
    upload_rate_window_seconds: int = 60
    chat_rate_limit: int = 30
    chat_rate_window_seconds: int = 60
    database_url_file: Path | None = None
    secret_key_file: Path | None = None
    llm_api_key_file: Path | None = None
    rerank_api_key_file: Path | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context: object) -> None:
        for value_field, file_field in (
            ("database_url", "database_url_file"),
            ("secret_key", "secret_key_file"),
            ("llm_api_key", "llm_api_key_file"),
            ("rerank_api_key", "rerank_api_key_file"),
        ):
            path = getattr(self, file_field)
            if path and path.is_file():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    object.__setattr__(self, value_field, value)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
