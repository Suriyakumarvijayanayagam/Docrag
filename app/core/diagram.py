"""
Diagrams are generated as Mermaid syntax (text), never as pixels.
This keeps a 2B-class model within its actual competence (structured text
generation) instead of asking it to do something it's bad at (drawing).
Client renders with mermaid.js.
"""
from app.core.llm_client import ollama

# A 2-3B model knows *of* Mermaid but improvises its keywords - observed
# failures include `auto id1 as ID1` in place of `participant id1 as ID1`, and
# arrows pointing at participants that were never declared. Both produce a
# parse error client-side, so the syntax rules are spelled out with worked
# examples rather than left to the model's recall.
_DIAGRAM_SYSTEM = """You convert technical descriptions into Mermaid diagram syntax.

Pick ONE diagram type and follow its syntax exactly:

graph TD                          <- block / architecture / power diagrams
    A[24V Input] --> B[Regulator]
    B --> C[3V3 Rail]

sequenceDiagram                   <- handshakes, protocols, boot flows
    participant MCU
    participant Regulator
    MCU->>Regulator: Enable
    Regulator-->>MCU: Power Good

flowchart TD                      <- decision logic
    A[Start] --> B{Over 150C?}
    B -->|yes| C[Shut down]
    B -->|no| D[Continue]

Hard rules:
- In sequenceDiagram, EVERY actor must be declared with `participant Name` \
before it is used. The keyword is `participant` - never `auto`, `actor id`, or \
anything else.
- Only use arrows between declared participants. Never invent `self`.
- Node ids are single words; put any spaces inside the brackets: A[Power Rail].
- Output ONLY the diagram. No code fences, no prose before or after it, no \
explanation of what the diagram shows."""


async def generate_diagram(context_text: str, request: str) -> str:
    prompt = f"Context from documents:\n{context_text}\n\nDiagram request: {request}"
    raw = await ollama.chat(_DIAGRAM_SYSTEM, prompt, temperature=0.2)
    # strip markdown fences if present, keep raw mermaid source
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        cleaned = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
    return cleaned.strip()
