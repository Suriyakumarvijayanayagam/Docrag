import { useCallback, useEffect, useState } from 'react'
import { RotateCw, Trash2 } from 'lucide-react'
import { api } from '../api'
import type { MemoryEntry } from '../types'

/**
 * What this library has learned in conversation, as distinct from what any
 * one document says. Each answered question is distilled into one durable
 * fact, decision or preference (or dropped) and fed back into later answers.
 */
export function MemoryPanel({ knowledgeBaseId, onError }: { knowledgeBaseId: string; onError: (message: string) => void }) {
  const [entries, setEntries] = useState<MemoryEntry[] | null>(null)

  const load = useCallback(() => api<{ entries: MemoryEntry[] }>(`/knowledge-bases/${knowledgeBaseId}/memory`)
    .then(result => setEntries(result.entries))
    .catch(error => onError(error instanceof Error ? error.message : 'Could not load memory')), [knowledgeBaseId, onError])

  useEffect(() => { setEntries(null); void load() }, [load])

  async function forget(entry: MemoryEntry) {
    try {
      await api(`/knowledge-bases/${knowledgeBaseId}/memory/${entry.id}`, { method: 'DELETE' })
      setEntries(current => current?.filter(item => item.id !== entry.id) ?? null)
    } catch (error) { onError(error instanceof Error ? error.message : 'Could not remove memory entry') }
  }

  return <section className="panel">
    <header className="panel-header">
      <div>
        <h2>Project memory <span className="count">{entries?.length ?? ''}</span></h2>
        <p>Facts and decisions distilled from earlier questions in this library. Given to the model as context, never cited as a source.</p>
      </div>
      <button className="btn btn-ghost btn-icon" onClick={() => void load()} title="Refresh"><RotateCw size={14} /></button>
    </header>
    {entries === null ? <div className="panel-empty">Loading…</div>
      : entries.length === 0 ? <div className="panel-empty">Nothing yet. Entries appear here after questions that establish something worth keeping.</div>
      : <ul className="memory-list">{entries.map(entry => <li key={entry.id}>
        <span className={`tag tag-${entry.entry_type}`}>{entry.entry_type}</span>
        <p>{entry.content}</p>
        <time>{new Date(entry.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</time>
        <button className="btn btn-ghost btn-icon danger" onClick={() => void forget(entry)} title="Forget"><Trash2 size={14} /></button>
      </li>)}</ul>}
  </section>
}
