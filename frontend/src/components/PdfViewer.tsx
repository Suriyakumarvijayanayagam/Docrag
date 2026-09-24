import { useCallback, useEffect, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import { ExternalLink, X } from 'lucide-react'

// Bundled by Vite and served from our own origin, so the viewer works offline.
pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString()

export type ViewerTarget = {
  documentId: string
  filename: string
  page: number
  /** the cited passage, highlighted on the page */
  snippet?: string | null
  /** bumped on every citation click so re-clicking the same page re-scrolls */
  nonce: number
}

/** PDF text runs and the stored chunk differ in line breaks and spacing, not in words. */
function normalise(text: string): string {
  return text.toLowerCase().replace(/\s+/g, ' ').trim()
}

function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!))
}

export function PdfViewer({ target, onClose }: { target: ViewerTarget; onClose: () => void }) {
  const [numPages, setNumPages] = useState(0)
  const [width, setWidth] = useState(560)
  const [error, setError] = useState<string | null>(null)
  const [visiblePage, setVisiblePage] = useState(target.page)
  const observer = useRef<ResizeObserver | null>(null)
  const pageRefs = useRef(new Map<number, HTMLDivElement>())
  const fileUrl = `/api/documents/${target.documentId}/file`

  const attachShell = useCallback((element: HTMLDivElement | null) => {
    observer.current?.disconnect()
    if (!element) return
    const measure = (w: number) => setWidth(Math.min(900, Math.max(260, w - 36)))
    measure(element.clientWidth)
    observer.current = new ResizeObserver(([entry]) => measure(entry.contentRect.width))
    observer.current.observe(element)
  }, [])

  const cited = target.snippet ? normalise(target.snippet) : null

  /**
   * pdf.js hands over one text run at a time while a citation spans many, so
   * each run is tested for membership in the cited chunk rather than trying to
   * locate the chunk in the page. Runs under four characters are skipped:
   * lighting up every "the" would tell the reader nothing.
   */
  const highlightRun = useCallback(({ str }: { str: string }) => {
    const run = normalise(str)
    if (!cited || run.length < 4 || !cited.includes(run)) return escapeHtml(str)
    return `<mark class="cited">${escapeHtml(str)}</mark>`
  }, [cited])

  const focusCitation = useCallback((pageNumber: number) => {
    if (pageNumber !== target.page) return
    const container = pageRefs.current.get(pageNumber)
    if (!container) return
    // wait a frame or two: pages above are still swapping placeholders for
    // rendered canvases, and scrolling now would land short of the passage
    window.setTimeout(() => {
      const mark = container.querySelector('mark.cited')
      ;(mark ?? container).scrollIntoView({ behavior: 'smooth', block: mark ? 'center' : 'start' })
    }, 120)
  }, [target])

  // jump (not animate) to the cited page first, so its text layer renders in view
  useEffect(() => {
    if (!numPages) return
    pageRefs.current.get(target.page)?.scrollIntoView({ block: 'start' })
    setVisiblePage(target.page)
  }, [target, numPages])

  return <aside className="viewer-pane">
    <header className="viewer-header">
      <div className="viewer-title"><strong title={target.filename}>{target.filename}</strong>{numPages > 0 && <span>page {visiblePage} of {numPages}</span>}</div>
      <a className="btn btn-ghost btn-icon" href={fileUrl} target="_blank" rel="noreferrer" title="Open in a new tab"><ExternalLink size={15} /></a>
      <button className="btn btn-ghost btn-icon" onClick={onClose} title="Close viewer"><X size={16} /></button>
    </header>
    <div className="viewer-scroll" ref={attachShell} onScroll={event => {
      // the page under the middle of the pane is the one being read
      const pane = event.currentTarget.getBoundingClientRect()
      const middle = pane.top + pane.height / 2
      for (const [n, element] of pageRefs.current) {
        const rect = element.getBoundingClientRect()
        if (rect.top <= middle && rect.bottom >= middle) { setVisiblePage(n); break }
      }
    }}>
      {error ? <p className="viewer-message">{error}</p> : <Document
        key={fileUrl}
        file={fileUrl}
        onLoadSuccess={({ numPages: n }) => { setNumPages(n); setError(null) }}
        onLoadError={event => setError(`Could not open this PDF: ${event.message}`)}
        loading={<p className="viewer-message">Opening document…</p>}
      >
        {Array.from({ length: numPages }, (_, i) => i + 1).map(n => <div key={n} className="viewer-page" ref={element => { if (element) pageRefs.current.set(n, element); else pageRefs.current.delete(n) }}>
          <Page
            pageNumber={n}
            width={width}
            renderAnnotationLayer={false}
            customTextRenderer={n === target.page ? highlightRun : undefined}
            onRenderTextLayerSuccess={() => focusCitation(n)}
            loading={<div className="viewer-page-placeholder" style={{ width, height: width * 1.29 }} />}
          />
        </div>)}
      </Document>}
    </div>
  </aside>
}
