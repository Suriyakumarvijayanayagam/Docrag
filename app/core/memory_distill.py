"""
Raw question logging (the original approach) gets noisy fast - after 50
questions, the memory block is mostly clutter. This distills a Q&A exchange
down to what's actually worth remembering: a fact established, a decision
made, or a stated preference. Skips exchanges that added nothing durable.
"""
from app.core.llm_client import ollama
from app.core.memory import add_entry

_DISTILL_SYSTEM = """You extract durable project memory from a single Q&A exchange.
Respond with ONLY a JSON object: {"worth_remembering": true/false, "entry_type": \
"fact"|"decision"|"preference", "content": "one sentence, third person, dense"}.
Set worth_remembering to false for exchanges that are just information lookups with \
no lasting relevance (e.g. "what page is X on"). Set it true for things that would \
matter in a later session: established facts about the system, decisions taken, \
stated preferences or constraints."""


async def distill_exchange(user_id: str, project_id: str, question: str, answer: str):
    import json
    prompt = f"Question: {question}\n\nAnswer: {answer}"
    try:
        raw = await ollama.chat(_DISTILL_SYSTEM, prompt, temperature=0.0)
        parsed = json.loads(raw.strip())
    except Exception:
        return  # fail silent - distillation is best-effort, never blocks the answer

    if parsed.get("worth_remembering") and parsed.get("content"):
        add_entry(user_id, project_id, parsed.get("entry_type", "fact"), parsed["content"])
