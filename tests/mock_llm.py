"""
STAND-IN FOR TESTING ONLY. Not part of the shipped app.

Implements the same interface as OllamaClient (embed, embed_batch, chat,
chat_stream) so the real pipeline code runs completely unmodified. This
proves data flows correctly through every stage - ingestion, hybrid
retrieval, structured facts, figures, reranking, confidence, memory
distillation - without needing a downloadable model in this sandbox.

The "chat" responses here are template-based, not generated - they exist
only to keep the real pipeline's control flow exercised end-to-end.
"""
import hashlib
import json


class MockLLMClient:
    async def embed(self, text: str) -> list[float]:
        # deterministic pseudo-embedding: hash-based, but words that share
        # tokens produce closer vectors than unrelated text (crude TF hashing)
        dim = 32
        vec = [0.0] * dim
        for word in text.lower().split():
            h = int(hashlib.md5(word.encode()).hexdigest(), 16)
            vec[h % dim] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]

    async def chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        if "score how relevant" in system.lower():
            # reranker prompt - count naive keyword overlap as a fake relevance score
            import re
            passages = re.findall(r"\[(\d+)\]\s*(.*?)(?=\[\d+\]|$)", user.split("Passages:")[-1], re.S)
            query = user.split("Query:")[1].split("Passages:")[0].strip().lower()
            q_tokens = set(query.split())
            scores = []
            for _, text in passages:
                overlap = len(q_tokens & set(text.lower().split()))
                scores.append(min(10, overlap * 3))
            return json.dumps(scores)

        if "worth_remembering" in system:
            return json.dumps({
                "worth_remembering": True,
                "entry_type": "fact",
                "content": "[MOCK DISTILLATION] " + user.split("Question:")[-1][:80].strip(),
            })

        if "mermaid" in system.lower():
            return "```mermaid\ngraph TD\n  A[Input] --> B[LM317 Regulator] --> C[Output Rail]\n```"

        # main answer prompt
        return (
            "[MOCK MODEL RESPONSE - real Ollama model would generate this]\n\n"
            "FROM THE DOCUMENTS: Based on the retrieved passages/facts above, "
            "this is where a real 2-3B local model would synthesize a grounded answer "
            "and cite page/section locators.\n\n"
            "ADDITIONAL INSIGHT: This is where the model would add analysis beyond "
            "the source text."
        )

    async def chat_stream(self, system: str, user: str, temperature: float = 0.3):
        full = await self.chat(system, user, temperature)
        for word in full.split(" "):
            yield word + " "
