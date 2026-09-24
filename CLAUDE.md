# Datum — Project Memory for Claude Code

Read this first, every session. `docs/ARCHITECTURE.md` has the full flow.

## What this is

A self-hosted document question-answering tool for welding and fabrication
engineers in India (IS / ASME / AWS / ISO codes), reviewing WPS/PQRs,
standards, consumable datasheets and design docs. Answers cite the page each claim comes
from, keep the model's own reasoning visibly separate, and report how well
grounded they are. Runs on a small local model (~3B) via Ollama; nothing
leaves the machine.

Previously two codebases (DocRAG: Chroma/SQLite/Next.js; LocalRAG:
Postgres/auth/Vite). They were merged in Sept 2026 on DocRAG 2's foundation;
the old code is in git history before the merge commit.

## Layout

- `backend/app/` — FastAPI (Python 3.10+, image uses 3.12)
  - `main.py` routes · `streaming.py` SSE answer/diagram streams
  - `answer.py` pipeline + prompt + confidence · `retrieval.py` hybrid search, scope, spreadsheet counts
  - `reranker.py` · `facts.py` table values · `figures.py` figures + Mermaid · `memory.py`
  - `ingestion.py` text extraction · `chunking.py` · `worker.py` background indexing
  - `llm.py` the only module that calls Ollama · `db.py` schema + migrations
  - `security.py` auth, JWT secret, library roles · `storage.py` storing uploads, files on disk
  - `welding.py` heat input, carbon equivalent, preheat (pure functions)
  - `job_fields.py` field extraction for job documents · `job_checks.py` cross-document checks
  - `routes_jobs.py` job API (APIRouter) · `uploads.py` upload validation
- `backend/tests/` — pytest unit tests; `fake_ollama.py` stand-in model
- `backend/scripts/` — `load_reference.py` (operator loads reference libraries),
  `eval_retrieval.py`, `make_sample_docs.py`
- `frontend/src/` — Vite + React 18 + TS. `App.tsx` (workspace state and
  views), `components/` (AnswerBody, PdfViewer, DiagramCard, MemoryPanel,
  Calculators, JobsView, Dialog, Logo), `styles.css` (single stylesheet, tokens + dark mode)
- `compose.yaml` postgres, api, worker, web · `compose.fake-llm.yaml` swaps in the fake model
- `sample-docs/` fixtures used by the eval set; `sample-docs/job-2025-118/` is a
  fictional job file with seven planted problems, used by the job tests

## Run

```bash
cp .env.example .env && docker compose up --build   # http://localhost:3000
docker compose -f compose.yaml -f compose.fake-llm.yaml up --build   # no model needed
cd backend && python -m pytest                      # unit tests (needs 3.10+)
```

The host's system Python is 3.9, which can't run the backend. Run tests in
the image: `docker run --rm -v "$PWD":/src -w /src -u root <api image> sh -c
"pip install -q pytest && python -m pytest"` from `backend/`.

## Non-obvious decisions (don't "fix" these without asking)

1. **Retrieval scope is one SQL fragment.** `retrieval.SCOPE_SQL` limits every
   query to ready documents in the chat's library plus the chat's own
   attachments. Any new retrieval query must use it; the API checks library
   membership before retrieval runs.
2. **Every per-document table cascades from `documents`.** Chunks, table
   values and figures use `ON DELETE CASCADE`. Files on disk don't cascade:
   anything that deletes documents must call `storage.remove_document_files`.
3. **The reranker is LLM-prompted, not a cross-encoder** (no torch). Its 0-10
   scores are the grounding signal: strong ≥7, partial ≥4 or an exact table
   value, else weak. Retrieval-only scores are capped at 6.5 so they can never
   read "strong". Keep `rerank(query, candidates, top_k)` stable.
4. **Answers have two parts** (`FROM THE DOCUMENTS` / `ADDITIONAL INSIGHT`);
   the frontend splits on those headings in `AnswerBody.splitAnswer`. Change
   both sides together.
5. **Memory is distilled, per library, and never evidence.** Don't revert to
   logging raw questions. Distillation runs in a background thread after the
   answer streams.
6. **Count/list questions take a different path**: the whole best-matching
   document (≤24 chunks), no rerank, spreadsheet counts computed in code.
7. **Existing figures beat generated diagrams**, with strict caption matching
   (≥2 shared content words).
8. **Bump `db.PARSER_VERSION`** when extraction output changes; stale
   documents are re-queued on startup.
9. **Schema changes go in `db.SCHEMA` as idempotent statements**
   (`IF NOT EXISTS`); there's no migration tool. Startup takes an advisory
   lock because api and worker both run it.
10. **JWT secret**: blank or placeholder values are replaced by a generated
    secret stored at `$UPLOAD_DIR/.jwt_secret`.
11. **nginx must serve `.mjs` as JavaScript** or the pdf.js worker fails to load.
12. **Reference libraries** (`knowledge_bases.is_reference`) have no owner or
    members; everyone gets the virtual role `reader`. Anything that writes to
    a library must go through `security.require_kb_write`, and memory must
    never be written into a reference library.
13. **Welding numbers come from `welding.py`, never the model.** The domain
    prompt (`settings.domain_context`) tells the model not to calculate. Any
    new formula needs its reference, validity range and a test with a
    hand-checked value.
14. **Job checks are code; the model only proposes fields, and a proposed
    value is dropped unless it appears verbatim in the document.** Code-rule
    findings are the only place code requirements live; each names its clause
    and says to verify against the governing edition. Consistency findings
    need no code knowledge - prefer adding those.
15. **Bump `job_fields.EXTRACTOR_VERSION`** when extraction output changes, so
    cached job extractions are re-read.

## Conventions

- Only `llm.py` talks to Ollama; keep `embed`, `embed_query`, `chat`,
  `chat_stream`, `available` stable (the fake model serves the same endpoints).
- Model output is untrusted: prompts say so, and every parser of it
  (scores, memory JSON, Mermaid, PDF text in the highlighter) must tolerate
  garbage without raising or injecting HTML.
- UI copy is plain and specific: say what something does, no marketing
  phrasing, no decorative icons. Numbers, pages and filenames use the mono
  font. Colours come from the tokens at the top of `styles.css`.
- The Postgres database and user are still named `localrag`/`rag`; renaming
  them would orphan existing volumes.

## Welding content

No standards ship with the repo: BIS/ASME/AWS/ISO documents are licensed and
must be supplied by the user. `sample-docs/Sample_WPS-SMAW-017.docx` is a
fictional WPS for testing. Don't add real standards text to the repo or state
code requirements from memory in prompts or UI copy.

## Known gaps

- Answer quality has only been checked against the fake model; run the eval
  set against `qwen2.5:3b` with real documents.
- Full-text search has no stemming (`simple` config).
- No per-member roles beyond owner/member; no audit log.
- Planned welding work not yet built: shop-floor QR logging of actual weld
  parameters into the job, a qualification-range engine driven by reviewed
  rule tables, calculator results usable inside answers, change-password UI,
  and an eval set from real welding documents.
- Job field extraction is tuned on the fictional samples; real WPS/PQR forms
  vary a lot and will need more label synonyms.
