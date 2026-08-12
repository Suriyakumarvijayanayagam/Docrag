# DocRAG — Project Memory for Claude Code

Read this first, every session. See `docs/ARCHITECTURE.md` for the full
stack/flow explanation if more depth is needed.

## What this is

A standalone, self-hosted, multi-tenant document intelligence system.
Upload PDF/DOCX, ask technical questions, get answers grounded in the
documents (kept visibly separate from AI-added insight), generate or find
diagrams. Runs on a small local LLM (~2-3B params) via Ollama — nothing
leaves the machine, no cloud API calls for inference.

Target user: a technical/engineering audience reviewing spec sheets, design
docs, datasheets. Not a generic chatbot-over-files product.

## Stack

- **App layer:** FastAPI (`app/main.py`)
- **Model layer:** Ollama, running separately (`localhost:11434` by default)
  - LLM: `qwen2.5:3b` (configurable in `app/config.py`)
  - Embeddings: `nomic-embed-text`
- **Storage:** all local
  - ChromaDB — one physical collection per `(user_id, project_id)` — see Isolation below
  - SQLite — structured facts, figures, persistent project memory (`data/memory.sqlite3`)
  - Filesystem — uploaded originals + extracted figure images
- **Frontend:** two, both served by FastAPI itself
  - `frontend-next/` — the console. Next.js 16 + React 19 + Tailwind 4,
    TypeScript. Static export (`output: "export"`, `basePath: "/ui"`), so there
    is still only one process at runtime: `npm run build` writes
    `frontend-next/out`, FastAPI mounts it at `/ui`. Split view: the PDF itself
    on the left (pdf.js via react-pdf), chat on the right, and citations that
    scroll the viewer to the cited page and highlight the passage there. The
    highlight works because `/ask` returns each source's `snippet` (the
    retrieved chunk, capped at `query_pipeline.SNIPPET_CHARS`); the viewer
    tests each pdf.js text run for membership in that chunk rather than trying
    to locate the chunk in the page. Mermaid and the pdf.js worker are both
    bundled/self-hosted — nothing leaves the machine, and both work offline.
    The worker lives at `frontend-next/public/pdf.worker.min.mjs`, copied from
    `node_modules/pdfjs-dist/build/` — re-copy it after upgrading pdfjs-dist.
    `PdfViewer` is imported via `next/dynamic` with `ssr: false`; pdf.js touches
    `DOMMatrix` at module scope and breaks the static prerender otherwise.
    Four exported routes (`/`, `/chat`, `/library`, `/memory`) with workspace
    state in `WorkspaceProvider` in the root layout - keep new shared state
    there, not in a page, or it resets on every navigation. `trailingSlash` is
    on, so links must end in `/`; FastAPI 307s the un-slashed form.
  - `frontend/index.html` — the original single-file UI, kept as a no-build
    fallback and served at `/ui-basic`. If `frontend-next/out` is missing,
    `/ui` falls back to this one rather than 404ing.

## Run it

```bash
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
pip install -r requirements.txt

# console (only needed after changing frontend-next/)
cd frontend-next && npm install && npm run build && cd ..

uvicorn app.main:app --reload
```

Console: `http://localhost:8000/ui`
Fallback UI: `http://localhost:8000/ui-basic`
API docs: `http://localhost:8000/docs`

Iterating on the console: `cd frontend-next && npm run dev` serves it at
`http://localhost:3000/ui` with hot reload. It needs the backend's origin,
so create `frontend-next/.env.local` with
`NEXT_PUBLIC_API_BASE=http://localhost:8000`. Leave that unset for the
static build — same-origin is correct when FastAPI serves it.

**Python 3.10+ is not assumed.** The codebase runs on 3.9, so use
`Optional[X]` / `Union[X, Y]` rather than `X | None` in annotations that get
evaluated at runtime (Pydantic models especially).

## Non-obvious design decisions (don't "fix" these without asking)

1. **Multi-tenant isolation is physical, not filtered.** Every user/project
   pair gets its own Chroma collection (`app/core/vectorstore.py:_collection_name`).
   There is intentionally no query path that spans collections. If you're
   tempted to add a "search across all projects" feature, that needs a new
   explicit function, not a loosened filter on the existing one.

2. **Reranker is LLM-prompted, not a cross-encoder** (`app/core/reranker.py`).
   Deliberate — avoids a torch dependency to keep the whole stack installable
   in seconds. Swap in `bge-reranker-base` only if answer quality demands it;
   the `rerank(query, candidates, top_k)` interface is designed not to change.

3. **Hybrid retrieval = vector (Chroma) + BM25, fused with Reciprocal Rank
   Fusion** (`app/core/hybrid_search.py`). BM25 index is rebuilt from the full
   tenant collection on every query — fine at prototype scale, needs caching
   or a proper hybrid vector store (Qdrant/Weaviate) past a few thousand
   chunks per project.

4. **Structured facts and figures are separate SQLite tables**, not part of
   the RAG chunk flow (`app/core/structured_facts.py`, `app/core/figures.py`).
   Table data gets exact lookups instead of fuzzy semantic search. Figures
   already in source docs are extracted and preferred over LLM-generated
   Mermaid diagrams (`app/core/diagram.py`) — only generate a new diagram if
   nothing existing matches.

5. **Memory is LLM-distilled, not raw logging** (`app/core/memory_distill.py`).
   Every Q&A exchange gets summarized down to "worth remembering or not" —
   don't revert to logging raw questions, it makes the memory block noisy
   over a long project.

6. **Confidence score comes from the reranker's own relevance scores**
   (`app/core/query_pipeline.py:_confidence_label`), not from vector distance.
   high ≥7, medium ≥4, else low, on the 0-10 LLM-assigned scale.

## Known gaps (expected next work, not bugs)

- No auth layer — `user_id` is client-supplied. Fine for local/prototype use,
  not for anything exposed beyond localhost.
- `scripts/eval_set_example.json` has only 2 toy cases — build a real eval
  set from actual test documents before trusting the hit-rate numbers.
- Reranker and structured-fact-extraction heuristics are both "good enough
  for typical technical docs," not exhaustive — complex nested/merged-cell
  tables and non-English documents haven't been tested.

## Testing without a live model

`tests/mock_llm.py` implements the same interface as `OllamaClient`
(`embed`, `embed_batch`, `chat`, `chat_stream`) with deterministic
template/hash-based responses. Useful for exercising the full pipeline
(ingestion → retrieval → fusion → facts → figures → confidence → memory)
without needing Ollama running. Not meant to validate answer *quality* —
only that data flows correctly end to end.

## Conventions

- Every new storage read/write must be scoped by `(user_id, project_id)` —
  no exceptions, this is the isolation guarantee the whole system depends on.
- Keep `OllamaClient`'s interface stable (`embed`, `embed_batch`, `chat`,
  `chat_stream`) — several modules and the mock depend on it staying exactly
  as-is if the model backend ever changes.
- New API routes go in `app/api/`, get included in `app/main.py`, and get a
  matching Pydantic schema in `app/models/schemas.py`.
- A document exists in three stores — chunks in Chroma, facts and figures in
  SQLite. Anything that creates or destroys a document must touch all three
  (see `routes_documents.remove_document`), or deleted documents keep
  answering questions through the fact/figure fast-paths.
