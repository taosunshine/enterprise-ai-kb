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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
