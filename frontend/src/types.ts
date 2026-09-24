export type User = { id: string; email: string; display_name: string }
export type KnowledgeBase = {
  id: string; name: string; description: string; role?: string; document_count?: number
  /** readable by every account; loaded by the server operator */
  is_reference?: boolean
}
export type Chat = {
  id: string; title: string; knowledge_base_id: string | null; knowledge_base_name?: string | null
  first_message?: string | null; updated_at: string
  /** also search the reference libraries */
  use_reference?: boolean
}
export type Document = {
  id: string; filename: string; content_type?: string; byte_size?: number; status: string
  error_message?: string | null; page_count?: number; chunk_count?: number
  fact_count?: number; figure_count?: number; created_at: string
}
export type Citation = {
  index: number; kind?: 'passage' | 'fact'; document_id: string; chunk_id: number | null; filename: string
  page_start: number | null; page_end: number | null; section: string; location: string; snippet: string
  /** reranker relevance, 0-10; null for exact table values */
  score: number | null; exact?: boolean
}
export type Confidence = 'high' | 'medium' | 'low' | 'none'
export type Diagram =
  | { kind: 'figure'; figure_id: number; url: string; caption: string; document_id: string; filename: string; page: number | null; source: string }
  | { kind: 'mermaid'; mermaid: string; source: string }
export type Message = {
  id: string; role: 'user' | 'assistant'; content: string; citations: Citation[]; created_at: string
  confidence?: Confidence | null; diagram?: Diagram | null
  /** client-side only: the request failed */
  error?: string
}
export type MemoryEntry = {
  id: number; entry_type: 'fact' | 'decision' | 'preference'; content: string; created_at: string
}
