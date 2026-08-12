# DocRAG — Local Multi-Tenant Document Intelligence

A standalone, self-hosted system: upload PDFs/DOCX, ask technical questions,
get answers with document-grounded facts separated from AI-added insight,
generate diagrams from document content, and never lose project context —
all running on a small local model (Qwen3.5-2B class), fully isolated per
user/project.

**→ See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the stack and flow
diagrams — written to be understandable by anyone, not just engineers.**

## Console

A split-view console (Next.js 16 + React 19 + TypeScript + Tailwind 4) lives in
`frontend-next/` and is served at `http://localhost:8000/ui`. It builds to a
**static export**, so runtime is still a single process — FastAPI serves the
built files; there is no Node server in production.

```bash
cd frontend-next
npm install
cp node_modules/pdfjs-dist/build/pdf.worker.min.mjs public/   # PDF viewer worker
npm run build                                                 # writes ./out, served at /ui
```

The pdf.js worker is served from your own origin rather than a CDN, so the
viewer works offline like the rest of the stack.

- **Sidebar** — Home, Ask documents, Library and Project memory, each a real
  route (`/ui/`, `/ui/chat/`, `/ui/library/`, `/ui/memory/`) so refreshing or
  bookmarking keeps the page you were on. Shared state lives in a provider in
  the root layout, so moving between routes never drops the conversation or
  refetches. Also holds the light / dark / match-system theme switcher, a
  collapse toggle, and the current workspace at the bottom. There is no
  sign-in: a workspace is just a user + project name, and switching it swaps to
  a completely separate set of documents and memory.
- **Home** — what the system is and what it can do, a composer to start from,
  quick-start prompts, and a live summary of what's loaded.
- **Ask documents** — the split view. The left pane renders the actual PDF;
  clicking a citation scrolls the viewer to that page and **highlights the
  exact passage the answer was drawn from**, so a reviewer checks the claim
  against the source instead of taking it on trust. Every answer is split into
  **from the documents** and **added by the model**, with a plain-English
  confidence reading and per-answer latency plus time-to-first-token.
- **Library** — every document with its passage / spec-value / figure counts,
  drag-and-drop upload, and removal (which clears passages, spec values and
  figures together).
- **Project memory** — the distilled facts and decisions carried across
  sessions.
- **Keyboard-first** — `⌘K` command palette, `/` to focus the composer, `⌘↵` to
  send from anywhere, `diagram: …` to request a figure.
- **Diagrams** render with a **bundled** Mermaid — no CDN, so they work offline
  and on firewalled networks.
- Light by default — a PDF page is white — with a dark theme via the command palette.

The original single-file UI is still there, needs no build step, and is served
at `http://localhost:8000/ui-basic`. If `frontend-next/out` doesn't exist on a
machine, `/ui` falls back to it automatically.

## Architecture

```
Client
  │
  ▼
FastAPI (app layer)
  ├── /documents/upload   → parse → chunk → embed → store (Chroma)
  ├── /ask                → embed query → retrieve → rerank → answer
  ├── /diagram            → retrieve context → generate Mermaid syntax
  └── /projects/*         → status, persistent memory inspection
  │
  ▼
Ollama (model layer, runs separately)
  ├── LLM: qwen2.5:3b (swap to qwen3.5:2b once available in your Ollama build)
  └── Embeddings: nomic-embed-text
  │
  ▼
Storage
  ├── ChromaDB — one physical collection per (user_id, project_id) — hard isolation
  ├── SQLite — persistent project memory (facts/decisions, not raw chat logs)
  └── Filesystem — uploaded source files
```

## Why it's built this way

- **Multi-tenant isolation is structural, not a filter.** Each user+project pair
  gets its own Chroma collection. There's no query path that can cross collections —
  you can't accidentally leak User B's documents into User A's answer.
- **Grounded facts vs AI insight are kept visibly separate** in every answer,
  so a technical reviewer can tell what came from their documents vs what the
  model added.
- **Diagrams are generated as Mermaid text**, not images — small models are
  competent at structured text generation, bad at actually drawing.
- **Persistent memory is a separate, curated store from RAG.** RAG answers
  "what does the document say." Memory answers "what do we already know about
  this project," and survives across sessions without relying on a growing
  context window.
- **No heavy ML deps (torch/sentence-transformers).** Embeddings and reranking
  route through Ollama, keeping the whole stack installable in seconds and the
  model swap-in swap-out (change one line in `config.py`).

## Setup

```bash
# 1. Install Ollama, then pull the models
ollama pull qwen2.5:3b        # or your chosen small model
ollama pull nomic-embed-text

# 2. Install app deps
pip install -r requirements.txt

# 3. Run
uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs.

## API surface

| Endpoint | Purpose |
|---|---|
| `POST /documents/upload` | Upload a PDF/DOCX — parses, chunks, embeds, extracts tables + figures |
| `GET /documents/list` | Documents in this tenant, with chunk/fact/figure counts |
| `DELETE /documents/{doc_id}` | Remove a document — chunks, structured facts, and figures |
| `GET /documents/{doc_id}/file` | The original uploaded file, for the viewer |
| `POST /ask` | Ask a question, grounded in that project's documents, blocking |
| `POST /ask/stream` | Same as `/ask` but streams tokens as they generate |
| `POST /diagram` | Returns an existing figure from the docs if one matches, else generates Mermaid |
| `GET /projects/status` | Document count + memory entry count |
| `GET /projects/memory` | Inspect the distilled persistent memory entries |

## Upgrades over the base prototype

1. **Hybrid retrieval** (`app/core/hybrid_search.py`) — vector search (Chroma) fused
   with BM25 keyword search via Reciprocal Rank Fusion. Catches exact terms
   (part numbers, model names) that pure embedding similarity can miss.
2. **Cross-document reasoning** (`query_pipeline._ensure_doc_diversity`) — comparison-style
   questions ("compare X vs Y") are detected and retrieval is rebalanced so multiple
   source documents are represented, not just whichever one scored highest.
3. **Structured fact extraction** (`app/core/structured_facts.py`) — tables from PDF/DOCX
   are pulled into an exact-lookup key/value store at ingest time. Spec questions
   ("what's the max voltage") get a precise answer, not a semantic guess.
4. **Existing figure extraction** (`app/core/figures.py`) — diagrams/schematics already
   embedded in the source documents are extracted, captioned, and returned directly
   when relevant — `/diagram` only generates a new Mermaid diagram if nothing matches.
5. **Confidence scoring** (`query_pipeline._confidence_label`) — every answer reports
   high/medium/low/none confidence based on the reranker's actual relevance scores,
   so a technical reviewer can see when the system is unsure instead of it silently
   guessing.
6. **Streaming responses** (`llm_client.chat_stream`, `/ask/stream`) — tokens stream
   as they're generated instead of blocking for the full response.
7. **LLM-distilled memory** (`app/core/memory_distill.py`) — instead of logging every
   raw question, each exchange is distilled by the LLM into a durable fact/decision/
   preference, or discarded if it wasn't worth remembering. Keeps the memory block
   dense over a long project instead of accumulating noise.
8. **Retrieval evaluation harness** (`scripts/eval_retrieval.py`) — run against a
   known question set to measure hit rate, and specifically shows where hybrid
   fusion rescues a miss that vector-only or BM25-only would have had. Proves
   retrieval quality with numbers instead of demo vibes.

```bash
python -m scripts.eval_retrieval --user_id demo --project_id demo \
    --eval_file scripts/eval_set_example.json
```

## What's tested vs what needs Ollama running

Verified in this environment (no live model needed):
- PDF/DOCX parsing (including tables)
- Recursive chunking with overlap
- Multi-tenant Chroma isolation (confirmed User A/User B never cross-contaminate)
- Full FastAPI route registration

Needs Ollama running locally to test end-to-end:
- Embedding generation
- Answer generation (grounded + insight split)
- LLM-prompted reranking
- Mermaid diagram generation

## Known trade-offs to revisit as you scale

- **Reranker** currently uses LLM-prompted scoring instead of a dedicated
  cross-encoder (to avoid a torch dependency). Swap in `bge-reranker-base`
  in `app/core/reranker.py` if answer quality needs it — interface won't change.
- **BM25 index is rebuilt on every query** from the tenant's full collection.
  Fine at prototype scale; cache it (or move to a proper hybrid store like
  Weaviate/Qdrant with native BM25) once a single project has thousands of chunks.
- **Structured fact extraction** uses simple table-shape heuristics (2-column =
  label/value, else header-row + row-entity flattening). Works well for typical
  spec sheets; complex nested/merged-cell tables will need custom handling.
- **No auth layer yet** — `user_id` is passed by the client. Fine for a
  prototype/demo, not for anything public-facing.
