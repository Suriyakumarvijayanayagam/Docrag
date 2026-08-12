export type Confidence = "high" | "medium" | "low" | "none";

export interface SourceRef {
  file: string | null;
  locator: number | string | null;
  /** 0-10 reranker score, or the string "exact_match" for structured-fact hits */
  relevance: number | "exact_match";
  /** the cited passage, highlighted in the source document when followed */
  snippet?: string | null;
}

export interface AnswerResponse {
  answer: string;
  sources: SourceRef[];
  confidence: Confidence;
}

export interface IngestResponse {
  doc_id: string;
  filename: string;
  chunk_count: number;
  unit_type: string;
  unit_count: number;
  structured_fact_count: number;
  figure_count: number;
}

export interface DiagramResponse {
  mermaid: string;
  existing_figure_path: string | null;
  existing_figure_caption: string | null;
  source: string;
}

export interface ProjectStatus {
  user_id: string;
  project_id: string;
  document_count: number;
  memory_entry_count: number;
}

export interface MemoryEntry {
  entry_type: string;
  content: string;
  created_at: number;
}

/** A document already in the tenant, recovered from the backend on load. */
export interface DocumentSummary {
  doc_id: string;
  filename: string;
  chunk_count: number;
  structured_fact_count: number;
  figure_count: number;
}

/** One row in the conversation stream. */
export interface Exchange {
  id: string;
  question: string;
  kind: "answer" | "diagram";
  status: "pending" | "streaming" | "done" | "error";
  answer: string;
  sources: SourceRef[];
  confidence: Confidence;
  diagram?: DiagramResponse;
  error?: string;
  /** wall-clock ms for the whole request */
  elapsedMs?: number;
  /** ms until the first streamed token arrived */
  ttftMs?: number;
}

export interface Scope {
  userId: string;
  projectId: string;
}
