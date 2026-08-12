"""
Thin async wrapper around Ollama's REST API. Keeps the rest of the app
decoupled from Ollama specifics - swap this file if you move to llama.cpp
server or vLLM later.
"""
import httpx
from app.config import settings


class OllamaClient:
    def __init__(self, host: str = None):
        self.host = host or settings.ollama_host

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.host}/api/embeddings",
                json={"model": settings.embedding_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        # Ollama's embeddings endpoint is single-prompt; parallelize client-side.
        import asyncio
        return await asyncio.gather(*(self.embed(t) for t in texts))

    async def chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                f"{self.host}/api/chat",
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature},
                },
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"]

    async def chat_stream(self, system: str, user: str, temperature: float = 0.3):
        """Yields response tokens as they're generated, via Ollama's NDJSON stream."""
        import json
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                f"{self.host}/api/chat",
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": True,
                    "options": {"temperature": temperature},
                },
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield content
                    if chunk.get("done"):
                        break


ollama = OllamaClient()
