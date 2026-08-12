"use client";

import dynamic from "next/dynamic";
import { useEffect, useLayoutEffect, useRef } from "react";
import { AnswerCard } from "./AnswerCard";
import type { ViewerTarget } from "./PdfViewer";
import type { DocumentSummary, Exchange, Scope } from "@/lib/types";

// pdf.js touches DOM APIs (DOMMatrix) at module scope, which don't exist during
// the static prerender - so the viewer is loaded in the browser only.
const PdfViewer = dynamic(() => import("./PdfViewer").then((m) => m.PdfViewer), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center bg-sunk">
      <p className="text-[13px] text-ink-3">Loading viewer…</p>
    </div>
  ),
});

export function ChatView({
  scope,
  docs,
  exchanges,
  input,
  onInput,
  onSubmit,
  busy,
  viewer,
  onOpenSource,
  onPickDoc,
}: {
  scope: Scope;
  docs: DocumentSummary[];
  exchanges: Exchange[];
  input: string;
  onInput: (v: string) => void;
  onSubmit: (text: string) => void;
  busy: boolean;
  viewer: ViewerTarget | null;
  onOpenSource: (file: string, page: number, snippet?: string | null) => void;
  onPickDoc: (docId: string) => void;
}) {
  const composer = useRef<HTMLTextAreaElement>(null);
  const streamEnd = useRef<HTMLDivElement>(null);
  const isDiagram = input.trim().toLowerCase().startsWith("diagram:");

  useEffect(() => {
    streamEnd.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [exchanges]);

  // Grow the composer to fit its content. Driven by the value rather than the
  // change event so pasting, prefills and clearing after send all resize too.
  useLayoutEffect(() => {
    const el = composer.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, window.innerHeight * 0.4)}px`;
  }, [input]);

  useEffect(() => {
    composer.current?.focus();
  }, []);

  return (
    <div className="flex h-full min-h-0">
      {/* the document itself */}
      <section className="hidden min-w-0 flex-1 border-r border-rule md:flex">
        <PdfViewer scope={scope} docs={docs} target={viewer} onPickDoc={onPickDoc} />
      </section>

      {/* the conversation */}
      <section className="flex w-full min-w-0 flex-col bg-panel md:w-[460px] lg:w-[540px]">
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-5">
          {exchanges.length === 0 ? (
            <div className="pt-4">
              <h2 className="text-[15px] font-semibold text-ink">Ask about these documents</h2>
              <p className="mt-1.5 max-w-[44ch] text-[13px] leading-relaxed text-ink-2">
                Answers keep what came from the documents separate from what the model added. Every
                citation opens the page it came from and highlights the passage.
              </p>
              {docs.length === 0 && (
                <p className="mt-3 rounded-xl bg-note-soft px-3.5 py-2.5 text-[12.5px] leading-relaxed text-note">
                  This workspace has no documents yet, so there is nothing to ground an answer in.
                  Add one from the Library first.
                </p>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-7">
              {exchanges.map((ex) => (
                <AnswerCard key={ex.id} ex={ex} onOpenSource={onOpenSource} />
              ))}
              <div ref={streamEnd} />
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-rule px-5 py-3">
          <div
            className={`flex items-end gap-2 rounded-2xl border bg-panel-2 px-3.5 py-2.5 transition-colors ${
              isDiagram ? "border-accent" : "border-rule focus-within:border-rule-2"
            }`}
          >
            <textarea
              ref={composer}
              rows={1}
              value={input}
              placeholder="Ask anything about these documents…"
              onChange={(e) => onInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  onSubmit(input);
                }
              }}
              className="min-h-[24px] flex-1 resize-none overflow-y-auto bg-transparent text-[14px] leading-relaxed text-ink outline-none placeholder:text-ink-3"
              style={{ maxHeight: "40vh" }}
            />
            <button
              type="button"
              onClick={() => onSubmit(input)}
              disabled={busy || !input.trim()}
              className="shrink-0 rounded-xl bg-accent px-3 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-35"
            >
              {busy ? "…" : "Send"}
            </button>
          </div>
          <p className="mt-1.5 text-[11.5px] text-ink-3">
            {isDiagram
              ? "Diagram request — an existing figure wins over a generated one"
              : busy
                ? "Answering — keep typing, then press ↵ once it finishes"
                : "↵ to send · shift + ↵ for a new line · start with diagram: for a figure"}
          </p>
        </div>
      </section>
    </div>
  );
}
