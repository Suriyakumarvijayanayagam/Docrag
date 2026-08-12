# How DocRAG Works

This explains the system in plain terms first, then with technical detail.
No prior knowledge of RAG or LLMs assumed.

---

## In one sentence

You upload documents, the system reads and remembers them privately per
project, and you ask questions — it answers using what's actually in your
documents (clearly separated from anything the AI adds on its own).

---

## The stack (what's running, and why)

```
┌─────────────────────────────────────────────────────────┐
│  YOUR APP (FastAPI)                                      │
│  Handles uploads, questions, and coordinates everything   │
├─────────────────────────────────────────────────────────┤
│  THE MODEL (Ollama, running a small local LLM)            │
│  Reads text, writes answers, generates diagrams           │
├─────────────────────────────────────────────────────────┤
│  STORAGE (all on your machine, nothing sent to the cloud) │
│  ├─ ChromaDB    → document meaning, for "find related"    │
│  ├─ SQLite      → exact facts, figures, project memory    │
│  └─ Filesystem  → the original uploaded files              │
└─────────────────────────────────────────────────────────┘
```

| Layer | Tool | Plain-English job |
|---|---|---|
| App | FastAPI | Traffic controller — routes every request to the right piece of code |
| Model | Ollama + small LLM (~2-3B params) | The "brain" — reads and writes language |
| Meaning search | ChromaDB | Finds passages that *mean* the same thing as your question, even with different words |
| Keyword search | BM25 | Finds passages with the *exact* words from your question (part numbers, model names) |
| Exact facts | SQLite table | Table data (spec sheets) stored as precise lookups, not fuzzy guesses |
| Figures | SQLite + file storage | Diagrams already inside your documents, extracted and reused |
| Project memory | SQLite table | A running, self-editing summary of what's been learned in this project |

---

## Flow 1 — Uploading a document

```
 You upload a PDF or DOCX
          │
          ▼
 ┌──────────────────┐
 │ Read the text     │  (page by page for PDF, section by section for DOCX)
 └──────────────────┘
          │
          ▼
 ┌──────────────────┐
 │ Split into chunks │  (~700 words each, slightly overlapping so no
 └──────────────────┘   sentence gets cut in half)
          │
          ├─────────────────────┬─────────────────────┐
          ▼                     ▼                     ▼
 ┌────────────────┐   ┌──────────────────┐   ┌──────────────────┐
 │ Turn each chunk │   │ Pull out tables   │   │ Pull out existing│
 │ into a "meaning │   │ as exact facts    │   │ diagrams/images  │
 │ fingerprint"    │   │ (label → value)   │   │ already in the   │
 │ (embedding)     │   │                   │   │ document         │
 └────────────────┘   └──────────────────┘   └──────────────────┘
          │                     │                     │
          ▼                     ▼                     ▼
 ┌────────────────┐   ┌──────────────────┐   ┌──────────────────┐
 │   ChromaDB      │   │  SQLite (facts)  │   │  SQLite (figures)│
 │  (this project  │   │  (this project   │   │  (this project   │
 │   only)         │   │   only)          │   │   only)          │
 └────────────────┘   └──────────────────┘   └──────────────────┘
```

**The important part:** every one of those three storage boxes is scoped to
*one specific user and one specific project*. There is no query in the whole
system that can reach across that boundary — User A's documents are
physically stored separately from User B's, not just hidden behind a filter
that could someday be forgotten.

---

## Flow 2 — Asking a question

```
 You ask: "what's the max voltage of the regulator?"
          │
          ▼
 ┌─────────────────────────┐
 │ Check exact facts first  │  → if it's a spec/number question, this
 │ (fast path)               │    often already has the precise answer
 └─────────────────────────┘
          │
          ▼
 ┌─────────────────────────┐
 │ Search two ways at once  │
 │ ┌───────────┐ ┌────────┐ │
 │ │  Meaning   │ │Keyword │ │  → combined, because meaning-search alone
 │ │  search    │ │ search │ │    can miss exact terms, and keyword-search
 │ └───────────┘ └────────┘ │    alone can miss reworded questions
 └─────────────────────────┘
          │
          ▼
 ┌─────────────────────────┐
 │ If comparing multiple    │
 │ documents, make sure     │  → e.g. "compare X vs Y" pulls from both
 │ each one is represented  │    documents, not just whichever scored highest
 └─────────────────────────┘
          │
          ▼
 ┌─────────────────────────┐
 │ Re-rank what was found   │  → double-check which passages are actually
 │ for real relevance        │    relevant, and score confidence: high/medium/low
 └─────────────────────────┘
          │
          ▼
 ┌─────────────────────────┐
 │ The model writes the     │  → answer is split into two clearly labeled
 │ answer                    │    parts: what the documents say, vs. what the
 │                            │    AI is adding on top
 └─────────────────────────┘
          │
          ▼
 ┌─────────────────────────┐
 │ Was this worth            │  → the model decides if anything from this
 │ remembering?               │    exchange should become permanent project
 │                            │    memory (not every question is - keeps it
 │                            │    from getting cluttered over time)
 └─────────────────────────┘
          │
          ▼
   Answer + sources + confidence level, shown to you
```

---

## Flow 3 — Asking for a diagram

```
 You ask: "show me the block diagram of the power subsystem"
          │
          ▼
 ┌─────────────────────────┐
 │ Does a matching diagram   │
 │ already exist in the      │  → prefer the real thing already in your
 │ uploaded documents?       │    documents over an invented one
 └─────────────────────────┘
          │
     ┌────┴────┐
    yes        no
     │          │
     ▼          ▼
 Return the   Ask the model to generate one as text-based
 real image   diagram code (Mermaid), rendered as a diagram
 + its page   in your browser — because a small model is
 reference    good at writing structured text, not at
              actually drawing pixels
```

---

## Why it's built this way (the short version)

- **Isolation is physical, not a checkbox** — separate storage per user/project,
  so there's no code path that could leak one person's documents into another's answer.
- **Two search methods, not one** — catches both "the exact term" and "the same
  idea worded differently."
- **Facts vs. insight, always separated** — so you can tell what's actually in
  your documents vs. what the AI is adding.
- **Reuses real diagrams instead of inventing new ones** whenever possible.
- **Memory is curated, not a dumping ground** — it only keeps what's actually
  worth remembering, so it stays useful even after hundreds of questions.
- **Everything runs locally** — no document ever leaves your machine.
