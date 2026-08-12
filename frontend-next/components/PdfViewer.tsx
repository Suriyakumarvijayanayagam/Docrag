"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { apiUrl } from "@/lib/api";
import type { DocumentSummary, Scope } from "@/lib/types";

// Worker is served from our own origin (copied into public/ at setup) rather
// than a CDN, so the viewer works offline like the rest of the stack.
pdfjs.GlobalWorkerOptions.workerSrc = "/ui/pdf.worker.min.mjs";

export interface ViewerTarget {
  docId: string;
  page: number;
  /** the cited passage, highlighted on the page when present */
  snippet?: string | null;
  /** bumped on every citation click so re-clicking the same page re-scrolls */
  nonce: number;
}

/** Lowercased, whitespace-collapsed - PDF text runs and the stored chunk
 *  differ in line breaks and spacing, not in words. */
function normalise(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

export function PdfViewer({
  scope,
  docs,
  target,
  onPickDoc,
}: {
  scope: Scope;
  docs: DocumentSummary[];
  target: ViewerTarget | null;
  onPickDoc: (docId: string) => void;
}) {
  const [numPages, setNumPages] = useState(0);
  const [width, setWidth] = useState(680);
  const [error, setError] = useState<string | null>(null);
  const [visiblePage, setVisiblePage] = useState(1);
  const observerRef = useRef<ResizeObserver | null>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  const active = docs.find((d) => d.doc_id === target?.docId) ?? docs[0] ?? null;
  const isPdf = active?.filename.toLowerCase().endsWith(".pdf") ?? false;

  const fileUrl = active
    ? apiUrl(
        `/documents/${encodeURIComponent(active.doc_id)}/file?user_id=${encodeURIComponent(
          scope.userId,
        )}&project_id=${encodeURIComponent(scope.projectId)}`,
      )
    : null;

  // Fit pages to the pane. Attached by callback ref rather than an effect: the
  // scroll shell only mounts once this tenant has a document, which is after
  // the component's first render, so a []-deps effect would never see it.
  const attachShell = useCallback((el: HTMLDivElement | null) => {
    observerRef.current?.disconnect();
    if (!el) return;
    const measure = (w: number) =>
      setWidth(Math.min(940, Math.max(320, w - 48)));
    measure(el.clientWidth);
    const ro = new ResizeObserver(([entry]) => measure(entry.contentRect.width));
    ro.observe(el);
    observerRef.current = ro;
  }, []);

  const citedText = target?.snippet ? normalise(target.snippet) : null;

  /**
   * Highlights the cited passage inside the page's text layer.
   *
   * pdf.js hands us one text run at a time, while a citation covers a whole
   * chunk spanning many runs - so rather than trying to locate the chunk in
   * the page, each run is tested for membership in the chunk. Runs shorter
   * than four characters are skipped: matching "the" or "of" would light up
   * the entire page and tell the reader nothing.
   */
  const highlightRun = useCallback(
    ({ str }: { str: string }) => {
      const run = normalise(str);
      if (!citedText || run.length < 4 || !citedText.includes(run)) return str;
      return `<mark class="cited">${str}</mark>`;
    },
    [citedText],
  );

  /** Land on the highlighted sentence, not merely the top of the page. */
  const focusCitation = useCallback(
    (pageNumber: number) => {
      if (!target || pageNumber !== target.page) return;
      const container = pageRefs.current.get(pageNumber);
      if (!container) return;
      const firstMark = container.querySelector("mark.cited");
      (firstMark ?? container).scrollIntoView({
        behavior: "smooth",
        block: firstMark ? "center" : "start",
      });
      setVisiblePage(pageNumber);
    },
    [target],
  );

  // scroll to the cited page as soon as it exists; once its text layer has
  // rendered, focusCitation re-centres on the highlight itself
  useEffect(() => {
    if (!target || !numPages) return;
    const el = pageRefs.current.get(target.page);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    setVisiblePage(target.page);
  }, [target, numPages]);

  const registerPage = useCallback((n: number, el: HTMLDivElement | null) => {
    if (el) pageRefs.current.set(n, el);
    else pageRefs.current.delete(n);
  }, []);

  if (!docs.length) {
    return (
      <div className="flex h-full w-full flex-1 flex-col items-center justify-center gap-2 bg-sunk px-8 text-center">
        <p className="text-[14px] text-ink-2">No document open</p>
        <p className="max-w-[300px] text-[13px] leading-relaxed text-ink-3">
          Upload a PDF and it appears here. Answers cite it by page, and clicking a citation jumps
          straight to that page.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full min-w-0 flex-1 flex-col bg-sunk">
      {/* document tabs */}
      <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-rule bg-panel px-2 py-1.5">
        {docs.map((d) => (
          <button
            key={d.doc_id}
            type="button"
            onClick={() => onPickDoc(d.doc_id)}
            title={d.filename}
            className={`max-w-[190px] shrink-0 truncate rounded-md px-2.5 py-1 text-[12px] transition-colors ${
              d.doc_id === active?.doc_id
                ? "bg-accent-soft text-accent"
                : "text-ink-3 hover:bg-panel-2 hover:text-ink-2"
            }`}
          >
            {d.filename}
          </button>
        ))}
        {numPages > 0 && (
          <span className="ml-auto shrink-0 pl-2 font-mono text-[11px] tabular-nums text-ink-3">
            page {visiblePage} / {numPages}
          </span>
        )}
      </div>

      <div ref={attachShell} className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
        {!isPdf ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <p className="text-[13.5px] text-ink-2">{active?.filename}</p>
            <p className="max-w-[320px] text-[12.5px] leading-relaxed text-ink-3">
              Word documents can&apos;t be previewed here yet — answers still cite them by section.
            </p>
          </div>
        ) : error ? (
          <div className="flex h-full items-center justify-center">
            <p className="max-w-[340px] text-center text-[13px] leading-relaxed text-ink-3">{error}</p>
          </div>
        ) : (
          <Document
            key={fileUrl}
            file={fileUrl}
            onLoadSuccess={({ numPages: n }) => {
              setNumPages(n);
              setError(null);
            }}
            onLoadError={(e) => setError(`Could not open this PDF — ${e.message}`)}
            loading={<p className="py-8 text-center text-[13px] text-ink-3">Opening document…</p>}
          >
            <div className="flex flex-col items-center gap-4">
              {Array.from({ length: numPages }, (_, i) => i + 1).map((n) => (
                <div
                  key={n}
                  ref={(el) => registerPage(n, el)}
                  className="overflow-hidden rounded-lg bg-white shadow-sm ring-1 ring-black/5"
                >
                  <Page
                    pageNumber={n}
                    width={width}
                    renderAnnotationLayer={false}
                    customTextRenderer={n === target?.page ? highlightRun : undefined}
                    onRenderTextLayerSuccess={() => focusCitation(n)}
                    loading={
                      <div style={{ width, height: width * 1.29 }} className="animate-pulse bg-panel-2" />
                    }
                  />
                </div>
              ))}
            </div>
          </Document>
        )}
      </div>
    </div>
  );
}
