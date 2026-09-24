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
    # Let the model propose job-document fields the table and text rules missed.
    # Its values are only kept when they appear verbatim in the document.
    extraction_model_fallback: bool = True
    # Who the answers are for; added to the answer prompt. Set DOMAIN_CONTEXT to
    # retarget the assistant, or to an empty string for a general document tool.
    domain_context: str = (
        "The readers are welding and fabrication engineers, inspectors and welders, mostly working to "
        "Indian (IS), ASME, AWS and ISO codes. Use SI units (mm, kJ/mm, °C, MPa) and give the imperial value "
        "only when the source uses it. When an excerpt comes from a code or standard, name the document and "
        "clause. Never present a welding parameter, limit or classification as fact unless the excerpts state "
        "it. Do not calculate heat input, carbon equivalent or preheat yourself; point the reader to the "
        "Calculators page instead."
    )
    ollama_timeout_seconds: int = 180


settings = Settings()
