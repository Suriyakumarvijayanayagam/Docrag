# How Datum works

Plain terms first, then the technical detail. No prior knowledge of RAG or
LLMs assumed.

---

## In one sentence

You put documents into a library; Datum reads them, indexes them on your
machine, and answers questions using what is actually in them, with every
claim pointing at its page and anything the model adds kept visibly separate.

---

## What runs

```
 Browser ──► web (nginx)  ──  serves the React app, forwards /api/*
                │
                ▼
            api (FastAPI) ──  accounts, libraries, threads, questions (streamed)
                │
   ┌────────────┼──────────────────────────────┐
   ▼            ▼                              ▼
 PostgreSQL   uploads volume              Ollama (native on the host)
 + pgvector   originals + figure images   chat model + embedding model
   ▲
   │
 worker ──  picks up queued documents: extract → chunk → embed → store
```

| Piece | Job |
|---|---|
| **web** | nginx serving the built frontend; proxies `/api/` to the API with buffering off so answers stream |
| **api** | FastAPI. Sign-in, access checks, uploads, and the answer pipeline |
| **worker** | Background indexing, so a 200-page PDF never blocks a request. Retries a failed document up to 3 times |
| **PostgreSQL + pgvector** | One database for everything: users, libraries, documents, passages and their embeddings, full-text index, table values, figures, memory, threads |
| **Ollama** | The model, running outside Docker so it can use the Mac's GPU. Only `backend/app/llm.py` talks to it |

Nothing in the stack calls a cloud service at runtime.

---

## Who can see what

Every document belongs to exactly one of:

- a **library** (knowledge base), visible to its members, or
- a **thread**, as an attachment, visible only to the thread's owner.

A question searches the thread's library plus the thread's own attachments,
nothing else. That scope is one SQL fragment (`retrieval.SCOPE_SQL`) used by
every retrieval query, and the API checks membership before retrieval runs.
Table values, figures and passages all hang off `documents` with
`ON DELETE CASCADE`, so deleting a document removes everything indexed from
it; the files on disk are removed by `storage.remove_document_files`.

Library owners can invite other accounts, delete the library, and remove any
document. Members can read, ask, upload, and remove what they uploaded.

---

## Flow 1: adding a document

```
 Upload (PDF, DOCX, PPTX, XLSX, MD, TXT, HTML, image)
   │   saved under a random name; SHA-256 checked for duplicates in the library
   ▼
 Queued job  ──►  worker claims it (FOR UPDATE SKIP LOCKED)
                    │
        ┌───────────┼─────────────────────┬──────────────────────┐
        ▼           ▼                     ▼                      ▼
   Extract text   Tables → exact         Embedded images →     (OCR for image-only
   with page and  label/value pairs      figure files,          pages and images)
   heading info   ("Vin.Max" → "40 V")   captioned from the
        │                                page text
        ▼
   Chunk (~420 tokens, overlap 60; spreadsheet rows kept whole)
        │
        ▼
   Embed each chunk (Ollama)  ──►  one transaction writes passages,
                                   table values and figures, then marks the
                                   document Ready
```

If table or figure extraction fails, the document still indexes its text.
When extraction changes, `db.PARSER_VERSION` is bumped and existing documents
are re-indexed on the next start.

---

## Flow 2: asking a question

```
 "What is the thermal shutdown temperature of the PC-42?"
   │
   ├─► Exact table values whose labels share the most words with the question
   │
   ├─► Hybrid search, top 12
   │     meaning (pgvector cosine)  +  exact words (PostgreSQL full text)
   │     fused with Reciprocal Rank Fusion, weighted 0.7 / 0.3
   │
   ├─► "Compare X and Y"?  interleave documents so each one is represented
   │
   ├─► Rerank: the model scores each passage 0-10; keep the best 5
   │     grounding = strong (best ≥ 7) · partial (≥ 4, or an exact table value)
   │                 · weak · none
   │
   ├─► Prompt = instructions + library memory + numbered passages and values
   │     the model must answer in two parts:
   │       FROM THE DOCUMENTS   every claim cited [n]
   │       ADDITIONAL INSIGHT   its own reasoning, uncited
   │
   ├─► Stream to the browser: sources → tokens → saved message
   │
   └─► After the answer: distil it into one memory entry, or nothing
```

Count and list questions ("how many rows", "list all parts") skip reranking
and put the whole best-matching document in the prompt, since a top-5 sample
would produce a wrong total. Spreadsheet row counts are computed in code and
handed to the model rather than left to it.

The browser renders the two parts as separate blocks, turns `[n]` into
buttons, and opens PDFs in a pdf.js viewer that highlights the cited passage
by matching each text run on the page against the stored chunk.

---

## Flow 3: `diagram:` requests

```
 "diagram: PC-42 block diagram"
   │
   ▼
 A figure in this scope whose caption shares ≥ 2 real words with the request?
   │
  yes ──► return that image, with a link to its page
   │
  no  ──► retrieve passages, ask the model for Mermaid, render it in the browser
```

A real figure from the document always wins over a drawn one. Matching is
deliberately strict: an unrelated figure is worse than a generated diagram.

---

## Decisions worth knowing before changing things

- **The reranker is a prompted LLM, not a cross-encoder.** That avoids a torch
  dependency. Its scores are also the grounding signal, so `reranker.py` works
  hard to keep them on the 0-10 scale; without it, retrieval-only scores are
  capped below "strong" so an unverified answer never looks certain.
- **Memory is distilled, not logged.** Raw questions turn the memory block into
  noise. Memory is context, never evidence: the prompt forbids citing it.
- **Table values are a separate store,** not more chunks, because spec
  questions need the exact cell, not a nearby paragraph.
- **One database.** The earlier version split Chroma, SQLite and files, and
  every delete had to remember all three. Cascading foreign keys make that
  impossible to get wrong.
- **Small model assumed.** Prompts spell out formats with examples, and every
  parser of model output (scores, memory JSON, Mermaid) tolerates the ways a
  3B model gets them wrong.

## Known limits

- The full-text index uses PostgreSQL's `simple` configuration: no stemming,
  English or otherwise.
- Table flattening is heuristic (two columns = label/value, otherwise header
  row × first column). Merged cells aren't handled.
- The example eval set covers three questions on the sample documents. Build
  one from real documents before tuning retrieval settings.
