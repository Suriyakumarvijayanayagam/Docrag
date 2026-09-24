"""
A stand-in for Ollama that serves the endpoints app.llm uses (/api/embed,
/api/chat, /api/tags) with deterministic output, so the whole stack -
upload -> worker -> retrieval -> rerank -> answer -> memory - can run without
a model. It proves data flows end to end, not that answers are any good.

    docker compose -f compose.yaml -f compose.fake-llm.yaml up --build

Embeddings are hashed bags of words, so texts sharing words are similar.
Chat replies are picked by recognising which prompt is asking.
"""
import hashlib
import json
import math
import re

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

app = FastAPI()
DIM = 768


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-]*", text.lower())


def _embed(text: str) -> list[float]:
    vector = [0.0] * DIM
    for word in _words(text):
        vector[int(hashlib.sha1(word.encode()).hexdigest(), 16) % DIM] += 1.0
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _rerank(prompt: str) -> str:
    query = set(_words(prompt.split("\n", 1)[0]))
    passages = re.findall(r"^\[(\d+)\] (.*)$", prompt, re.M)
    return json.dumps([min(10, 3 * len(query & set(_words(text)))) for _, text in passages])


def _answer(system: str, question: str) -> str:
    first = re.search(r"^\[(\d+)\] .*\n(.+)$", system.split("DOCUMENT EXCERPTS AND FACTS:", 1)[-1], re.M)
    if not first:
        return "FROM THE DOCUMENTS:\nThe selected documents do not cover this.\n\nADDITIONAL INSIGHT:\nNone."
    return (
        f"FROM THE DOCUMENTS:\n{first.group(2)[:200]} [{first.group(1)}]\n\n"
        f"ADDITIONAL INSIGHT:\nFake-model insight about: {question[:80]}"
    )


def _reply(messages: list[dict]) -> str:
    system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
    user = messages[-1]["content"] if messages else ""
    if system.startswith("You rate how useful"):
        return _rerank(user)
    if system.startswith("You extract durable project memory"):
        return json.dumps({"worth_remembering": True, "entry_type": "fact", "content": f"Asked: {user[10:90]}"})
    if system.startswith("You convert technical descriptions into Mermaid"):
        return "graph TD\n    A[Input] --> B[Regulator]\n    B --> C[Output]"
    return _answer(system, user)


@app.get("/api/tags")
def tags():
    return {"models": [{"name": "fake"}]}


@app.post("/api/embed")
async def embed(request: Request):
    body = await request.json()
    inputs = body["input"] if isinstance(body["input"], list) else [body["input"]]
    return {"embeddings": [_embed(text) for text in inputs]}


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    reply = _reply(body.get("messages", []))
    if not body.get("stream"):
        return {"message": {"role": "assistant", "content": reply}, "done": True}

    def stream():
        for piece in re.findall(r"\S+\s*", reply):
            yield json.dumps({"message": {"role": "assistant", "content": piece}, "done": False}) + "\n"
        yield json.dumps({"message": {"role": "assistant", "content": ""}, "done": True}) + "\n"
    return StreamingResponse(stream(), media_type="application/x-ndjson")
