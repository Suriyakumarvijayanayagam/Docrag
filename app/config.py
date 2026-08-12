"""
Central configuration. Reads from environment with sane local-dev defaults.
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Model serving (Ollama) ---
    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:3b"          # swap to qwen3.5:2b etc once pulled in ollama
    embedding_model: str = "nomic-embed-text"  # served via ollama for zero extra deps

    # --- Storage ---
    chroma_path: str = "./data/chroma"
    memory_db_path: str = "./data/memory.sqlite3"
    upload_dir: str = "./data/uploads"

    # --- Chunking ---
    chunk_size_tokens: int = 700
    chunk_overlap_tokens: int = 100

    # --- Retrieval ---
    top_k_retrieval: int = 12
    top_k_after_rerank: int = 5

    class Config:
        env_prefix = "DOCRAG_"


settings = Settings()
