from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://rag:rag-local-password@localhost:5432/localrag"
    ollama_base_url: str = "http://localhost:11434"
    chat_model: str = "qwen2.5:3b"
    embedding_model: str = "nomic-embed-text"
    embedding_dim: int = 768
    # Left blank (or at a known placeholder), a random secret is generated and
    # kept in the data volume - see security._resolve_jwt_secret.
    jwt_secret: str = ""
    jwt_expire_hours: int = 168
    registration_enabled: bool = True
    max_upload_mb: int = 50
    upload_dir: str = "./data/uploads"
    chunk_tokens: int = 420
    chunk_overlap: int = 60
    retrieval_min_similarity: float = 0.28
    # Fused candidates handed to the reranker, and how many survive it into the prompt.
    retrieval_candidates: int = 12
    retrieval_top_k: int = 5
    # Set false to skip the LLM rerank pass (faster, no confidence verification).
    rerank_enabled: bool = True
    # Set false to stop distilling chat exchanges into knowledge-base memory.
    memory_enabled: bool = True
    ollama_timeout_seconds: int = 180


settings = Settings()
