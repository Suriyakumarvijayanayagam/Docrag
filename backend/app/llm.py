"""
The only module that talks to Ollama. Everything else calls embed / chat /
chat_stream, so moving to another local backend (llama.cpp server, vLLM) means
changing this file and nothing else. tests/fake_ollama.py serves the same
three endpoints for running the stack without a model.
"""
import json
from typing import Iterator

import httpx

from app.config import settings

EMBED_BATCH = 24


def _url(path: str) -> str:
    return f"{settings.ollama_base_url.rstrip('/')}{path}"


def embed(texts: list[str]) -> list[list[float]]:
    """Embeds in batches; raises if the model's output doesn't match EMBEDDING_DIM."""
    results: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        response = httpx.post(
            _url("/api/embed"),
            json={"model": settings.embedding_model, "input": batch},
            timeout=settings.ollama_timeout_seconds,
        )
        response.raise_for_status()
        embeddings = response.json().get("embeddings", [])
        if len(embeddings) != len(batch):
            raise ValueError("Ollama returned an unexpected number of embeddings")
        for embedding in embeddings:
            if len(embedding) != settings.embedding_dim:
                raise ValueError(
                    f"Embedding model returned {len(embedding)} dimensions, but EMBEDDING_DIM is {settings.embedding_dim}"
                )
        results.extend(embeddings)
    return results


def embed_query(text: str) -> list[float] | None:
    """Query-time embedding. None on failure so retrieval can fall back to full-text only."""
    try:
        return embed([text])[0]
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        return None


def chat(system: str, user: str, temperature: float = 0.2, num_ctx: int = 4096) -> str:
    """Blocking single-turn call, for the reranker, memory distillation and diagrams."""
    response = httpx.post(
        _url("/api/chat"),
        json={
            "model": settings.chat_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "options": {"temperature": temperature, "num_ctx": num_ctx},
        },
        timeout=settings.ollama_timeout_seconds,
    )
    response.raise_for_status()
    return response.json().get("message", {}).get("content", "")


def chat_stream(messages: list[dict], temperature: float = 0.2, num_ctx: int = 4096) -> Iterator[str]:
    """Yields answer tokens as Ollama generates them."""
    with httpx.Client(timeout=None) as client:
        with client.stream(
            "POST", _url("/api/chat"),
            json={"model": settings.chat_model, "messages": messages, "stream": True,
                  "options": {"temperature": temperature, "num_ctx": num_ctx}},
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = payload.get("message", {}).get("content", "")
                if text:
                    yield text
                if payload.get("done"):
                    break


def available() -> bool:
    try:
        return httpx.get(_url("/api/tags"), timeout=2).is_success
    except httpx.HTTPError:
        return False
