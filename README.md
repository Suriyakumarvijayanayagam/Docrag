# Datum

Ask technical questions of your datasheets, specs and design documents, and
get answers that point to the page they came from. Everything runs on your
own machine: a small local model through Ollama, PostgreSQL with pgvector, and
your files in a Docker volume. Nothing is sent to a cloud service.

Built for welding and fabrication engineers, inspectors and welders working
to IS, ASME, AWS and ISO codes, reviewing WPS/PQRs, standards, consumable
datasheets and design documents. It is not a general chatbot over files.

- **Answers tied to pages.** Every claim carries a `[n]` citation. Clicking it
  opens the PDF beside the answer, scrolled to the page, with the cited passage
  highlighted.
- **What the documents say is kept apart from what the model adds.** The
  model's own reasoning is shown in a separate, labelled block.
- **Grounding you can see.** Each answer reports strong, partial or weak
  grounding, based on how relevant the reranker judged the best passage.
- **Exact spec values.** Tables in PDFs, Word and PowerPoint files are
  extracted as label/value pairs, so "what's the max input voltage" returns the
  number from the table instead of a paraphrase.
- **Figures.** Start a question with `diagram:` to get a figure that already
  exists in the documents, or a Mermaid diagram drawn by the model if none matches.
- **Job files with cross-document checks.** Put a job's WPS, PQR, welder
  qualifications, consumable certificates and weld log together, and Datum
  reads the key fields from each and checks them against each other: a WPS
  thickness range beyond its PQR coupon, a certificate for the wrong electrode,
  a welder on a joint they aren't qualified for (process, position), a
  qualification lapsed through inactivity, a joint thicker than its WPS allows.
  Every finding cites the page or log row on both sides, every extracted field
  can be corrected by hand, and the findings print as an inspection-readiness
  report. The checks are code, not the model.
- **Reference libraries.** Standards, codes and consumable catalogues loaded
  once by the server operator, readable by every account, and searched
  alongside each team's own documents (switchable per thread).
- **Welding calculators.** Arc energy / heat input, carbon equivalent (IIW CE,
  CET, Pcm) and an EN 1011-2 preheat estimate, computed in code with the
  formula, reference and validity range shown. Ask "what's the heat input
  for 24 V, 160 A at 150 mm/min with SMAW?" in a thread and the calculator
  answers, not the model; missing inputs are named rather than guessed.
- **Project memory.** Facts and decisions from earlier questions in a library
  are distilled and given to the model as context in later threads.
- **Accounts and shared libraries.** Local sign-in; a library's owner can
  invite other accounts on the same server.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for how it works.

## Run it (macOS)

1. Install [Ollama](https://ollama.com/download) and pull the models. Ollama
   runs natively so it can use the GPU; the rest runs in Docker.

   ```bash
   ollama serve
   ollama pull qwen2.5:3b
   ollama pull nomic-embed-text
   ```

2. Configure and start:

   ```bash
   cp .env.example .env
   docker compose up --build
   ```

3. Open http://localhost:3000, create an account, create a library and add
   documents. Indexing runs in the background; a document is used for answers
   once it shows **Ready**.

`JWT_SECRET` can stay blank: a random secret is generated on first start and
kept in the uploads volume. The 3B model is a practical default for an 8 GB
Mac; set `CHAT_MODEL` to use a larger one. If you change the embedding model,
set `EMBEDDING_DIM` to match and start with a fresh database volume.

```bash
docker compose logs -f api worker   # follow indexing and answers
docker compose down                 # stop
docker compose down -v              # stop and delete ALL data, files and embeddings
```

API docs are served at http://localhost:3000/api/docs.

## Job files

**Jobs → New job**, then upload the job's documents. Each file's type (WPS,
PQR, welder qualification, consumable certificate, weld log) is guessed from
its name and first page; change it if it's wrong. Open a document to see the
fields read from it, where each came from, and correct any value. **Run
checks** lists findings by severity; click any evidence line to open that page
with the value highlighted. **Report** prints the findings.

Weld logs are spreadsheets (XLSX or CSV) with at least welder and WPS columns;
joint, date, position, process and thickness columns are used when present.
`sample-docs/job-2025-118/` is a fictional job with seven planted problems for
trying it out.

## Reference libraries

Load documents everyone on the server should be able to search (standards,
codes, electrode and wire catalogues) into a read-only reference library:

```bash
docker compose cp ./standards api:/tmp/standards
docker compose exec api python -m scripts.load_reference \
    --name "Welding reference" --description "Codes, standards and consumable data" /tmp/standards
docker compose exec api python -m scripts.load_reference --list
docker compose exec api python -m scripts.load_reference --name "Welding reference" --remove
```

Re-running a load adds new files and skips ones already there. BIS, ASME,
AWS and ISO documents are licensed: only load copies your organisation may
share with everyone who has an account. `sample-docs/Sample_WPS-SMAW-017.docx`
is a fictional WPS for trying this out.

## Supported files

PDF (with OCR for image-only pages), DOCX, PPTX, XLSX, Markdown, plain text,
HTML, and PNG/JPEG/TIFF/BMP images (OCR), up to 50 MB each. Files can go into a
library, or be attached to a single thread.

## Development

Backend (Python 3.10+; the Docker image uses 3.12). Needs PostgreSQL with
pgvector and Ollama; the defaults point at `localhost`.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000   # API
python -m app.worker                        # indexing worker, second terminal
python -m pytest                            # unit tests
```

Frontend (Vite, React 18, TypeScript). The dev server proxies `/api` to
`localhost:8000`.

```bash
cd frontend
npm install
npm run dev
```

### End-to-end tests

`backend/tests/e2e/run.py` drives a throwaway stack through the API: accounts
and access control, uploads and indexing, answers and citations, figures,
memory, reference libraries, calculators and job checks. It uses Python's
standard library only and creates its own named test accounts, so never
point it at a stack whose data you care about.

```bash
APP_PORT=3107 docker compose -p datum-e2e -f compose.yaml -f compose.fake-llm.yaml up --build -d
python3 backend/tests/e2e/run.py core welding jobs     # 58 checks, stand-in model
APP_PORT=3107 docker compose -p datum-e2e -f compose.yaml up -d --remove-orphans
python3 backend/tests/e2e/run.py real                  # answer quality on the real model
docker compose -p datum-e2e down -v
```

`real` checks that answers state the right values from the right document,
cite them, keep the two-part layout, say so when the documents don't cover a
question, and hand calculations to the calculator. On an M1 with 8 GB and
`qwen2.5:3b`, answers take 5-20 s. Keep the Mac awake while it runs
(`caffeinate -dimsu python3 ...`): idle sleep pauses Docker and Ollama.

`docs/demo/record_demo.py` records a captioned walkthrough video of the app
with Playwright (see its docstring).

### Without a model

`backend/tests/fake_ollama.py` stands in for Ollama with deterministic
responses, so upload, indexing, retrieval, reranking, answers and memory can
all be exercised without downloading a model. It checks that data flows end to
end, not that answers are any good.

```bash
docker compose -f compose.yaml -f compose.fake-llm.yaml up --build
```

### Retrieval evaluation

Measure hit rates on known question/answer-location pairs, both after fusion
and after reranking:

```bash
docker compose exec api python -m scripts.eval_retrieval \
    --knowledge_base_id <library id> --eval_file scripts/eval_set_example.json
```

The example set targets the documents in `sample-docs/`
(regenerate them with `cd backend && python -m scripts.make_sample_docs`).
Build a set from your own documents before trusting the numbers.

## Configuration

| Variable | Default | |
|---|---|---|
| `CHAT_MODEL` | `qwen2.5:3b` | Ollama model for answers, reranking, memory and diagrams |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `nomic-embed-text` / `768` | Must match each other |
| `CHUNK_TOKENS` / `CHUNK_OVERLAP` | `420` / `60` | Passage size, in an estimated token count |
| `RETRIEVAL_MIN_SIMILARITY` | `0.28` | Vector matches below this are dropped |
| `RETRIEVAL_CANDIDATES` / `RETRIEVAL_TOP_K` | `12` / `5` | Fused candidates reranked, and passages kept |
| `RERANK_ENABLED` | `true` | `false` is faster, but grounding then never reads "strong" |
| `MEMORY_ENABLED` | `true` | Distil questions into library memory |
| `EXTRACTION_MODEL_FALLBACK` | `true` | Let the model propose job fields the table/text rules missed (kept only if found verbatim) |
| `DOMAIN_CONTEXT` | welding text | Who answers are for; added to the prompt. Empty string for a general document tool |
| `REGISTRATION_ENABLED` | `true` | Turn off once everyone has an account |

## Limits

- Small local models make mistakes. Check citations, especially when
  grounding reads partial or weak. Nothing here replaces a qualified WPS or
  the governing code; calculator results are estimates to check against them.
- Table extraction handles typical spec tables; merged-cell and nested tables
  are not reliably flattened. Non-English documents are untested.
- Keep it bound to localhost (the default) unless you put it behind TLS.
