import { useEffect, useId, useState } from 'react'
import type { Diagram } from '../types'

const DIAGRAM_START = /^\s*(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram(-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart)\b/i
/** Tokens that mark a line as diagram syntax rather than an English sentence. */
const DIAGRAM_TOKEN = /(-->|->>|--x|---|\|\||:::|\bparticipant\b|\bsubgraph\b|\bNote\b|\bend\b|\[|\()/

/**
 * Pulls the diagram out of whatever a 3B model wrapped it in: a closing fence
 * with no opening one, or a sentence explaining the diagram after it. Either
 * makes mermaid throw on output that contains a perfectly good diagram.
 */
function cleanMermaid(raw: string): string {
  const fenced = raw.match(/```(?:mermaid)?\s*([\s\S]*?)```/i)
  if (fenced?.[1]?.trim()) return fenced[1].trim()
  const lines = raw.replace(/```(?:mermaid)?/gi, '').split('\n')
  const start = lines.findIndex(line => DIAGRAM_START.test(line))
  if (start === -1) return raw.trim()
  const body: string[] = []
  for (let i = start; i < lines.length; i++) {
    if (i > start && !lines[i].trim()) {
      const next = lines.slice(i + 1).find(line => line.trim())
      if (!next || (!/^\s+\S/.test(next) && !DIAGRAM_TOKEN.test(next))) break
    }
    body.push(lines[i])
  }
  return body.join('\n').trim()
}

/** Repairs the arrow malformations this model reliably produces; anything else is left alone. */
function repairMermaid(source: string): string {
  return source
    .replace(/--\s*([A-Za-z0-9 _]+?)\s*-->/g, '-->|$1|') // "B --yes--> C" -> "B -->|yes| C"
    .replace(/--\s*([A-Za-z0-9 _]+?)\s*--\s+>/g, '-->|$1|')
    .replace(/--\s+>/g, '-->')
    .replace(/-\s+->/g, '-->')
}

/** Mermaid is bundled, not fetched from a CDN, and loaded only once a diagram is on screen. */
function MermaidView({ source }: { source: string }) {
  const [svg, setSvg] = useState<string | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const id = `mmd-${useId().replace(/[^a-zA-Z0-9]/g, '')}`

  useEffect(() => {
    let alive = true
    setSvg(null)
    setFailed(null)
    void (async () => {
      try {
        const mermaid = (await import('mermaid')).default
        const dark = window.matchMedia('(prefers-color-scheme: dark)').matches
        mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'neutral', fontFamily: '-apple-system, "Segoe UI", sans-serif' })
        const rendered = await mermaid.render(id, source)
        if (alive) setSvg(rendered.svg)
      } catch (error) {
        if (alive) setFailed(error instanceof Error ? error.message : String(error))
      }
    })()
    return () => { alive = false }
  }, [source, id])

  if (svg) return <div className="mermaid-host" dangerouslySetInnerHTML={{ __html: svg }} />
  if (failed) return <div className="diagram-failed"><strong>The model's diagram didn't parse. Raw output:</strong><pre>{source}</pre></div>
  return <div className="diagram-rendering">Rendering diagram…</div>
}

export function DiagramCard({ diagram, onOpenPage }: { diagram: Diagram; onOpenPage?: (documentId: string, filename: string, page: number) => void }) {
  if (diagram.kind === 'figure') {
    return <figure className="diagram-card">
      <figcaption><span>Figure found in document</span>{diagram.page && onOpenPage
        ? <button type="button" onClick={() => onOpenPage(diagram.document_id, diagram.filename, diagram.page!)}>{diagram.source}</button>
        : <small>{diagram.source}</small>}</figcaption>
      <img src={diagram.url} alt={diagram.caption} />
      <p className="diagram-caption">{diagram.caption}</p>
    </figure>
  }
  return <figure className="diagram-card">
    <figcaption><span>Drawn by the model</span><small>No matching figure in the documents</small></figcaption>
    <MermaidView source={repairMermaid(cleanMermaid(diagram.mermaid))} />
  </figure>
}
