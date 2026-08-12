"use client";

import { ConfidenceMeter } from "./Confidence";
import { SourceChips } from "./Sources";
import { DiagramCard } from "./DiagramCard";
import type { Exchange } from "@/lib/types";

/**
 * The grounded/insight split is the product's core claim, so it is rendered
 * structurally - two labelled zones - rather than left as prose the model
 * happens to have formatted. While streaming, text before the marker arrives
 * is shown as grounded, then re-splits the moment the marker lands.
 */
function splitAnswer(text: string): { grounded: string; insight: string } {
  const idx = text.toUpperCase().indexOf("ADDITIONAL INSIGHT");
  if (idx === -1) {
    return { grounded: text.replace(/FROM THE DOCUMENTS:?/i, "").trim(), insight: "" };
  }
  return {
    grounded: text
      .slice(0, idx)
      .replace(/FROM THE DOCUMENTS:?/i, "")
      .trim(),
    insight: text
      .slice(idx)
      .replace(/ADDITIONAL INSIGHT:?/i, "")
      .trim(),
  };
}

function Zone({
  kind,
  body,
  streaming,
}: {
  kind: "grounded" | "insight";
  body: string;
  streaming: boolean;
}) {
  const grounded = kind === "grounded";
  return (
    <div
      className={`rounded-xl px-3.5 py-3 ${grounded ? "bg-ok-soft" : "bg-note-soft"}`}
    >
      <div
        className={`mb-1.5 flex items-center gap-1.5 text-[11px] font-medium ${
          grounded ? "text-ok" : "text-note"
        }`}
      >
        {/* marked as well as coloured, so the split survives a projector or a
            colourblind viewer rather than relying on hue alone */}
        <span aria-hidden>{grounded ? "◆" : "✎"}</span>
        {grounded ? "From the documents" : "Added by the model"}
      </div>
      <p
        className={`whitespace-pre-wrap text-[14px] leading-[1.65] ${
          grounded ? "text-ink" : "text-ink-2"
        } ${streaming ? "caret" : ""}`}
      >
        {body}
      </p>
    </div>
  );
}

export function AnswerCard({
  ex,
  onOpenSource,
}: {
  ex: Exchange;
  onOpenSource?: (file: string, page: number, snippet?: string | null) => void;
}) {
  const { grounded, insight } = splitAnswer(ex.answer);
  const streaming = ex.status === "streaming";

  return (
    <article className="rise flex flex-col gap-3">
      {/* the question, as the reader's own turn */}
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-2xl rounded-br-md bg-accent-soft px-3.5 py-2 text-[13.5px] leading-snug text-ink">
          {ex.question}
        </p>
      </div>

      <div className="flex flex-col gap-2.5">
        {ex.status === "pending" && (
          <div className="flex items-center gap-2 text-[12.5px] text-ink-3">
            <span className="pulse h-1.5 w-1.5 rounded-full bg-accent" />
            {ex.kind === "diagram"
              ? "looking for a matching figure…"
              : "searching the documents…"}
          </div>
        )}

        {ex.status === "error" && (
          <div className="rounded-xl bg-risk-soft px-3.5 py-3">
            <div className="mb-1 text-[11px] font-medium text-risk">Something went wrong</div>
            <p className="text-[13px] leading-relaxed text-ink">{ex.error}</p>
          </div>
        )}

        {ex.kind === "diagram" && ex.diagram && <DiagramCard data={ex.diagram} />}

        {ex.kind === "answer" && ex.answer && (
          <>
            <Zone kind="grounded" body={grounded} streaming={streaming && !insight} />
            {insight && <Zone kind="insight" body={insight} streaming={streaming} />}
          </>
        )}

        {ex.status !== "pending" && ex.sources.length > 0 && (
          <SourceChips sources={ex.sources} onOpen={onOpenSource} />
        )}

        {ex.status === "done" && ex.kind === "answer" && (
          <div className="flex items-center gap-3 text-[11px] text-ink-3">
            <ConfidenceMeter level={ex.confidence} />
            {ex.elapsedMs !== undefined && (
              <span className="tabular-nums">
                {(ex.elapsedMs / 1000).toFixed(1)}s
                {ex.ttftMs !== undefined && ` · first words in ${(ex.ttftMs / 1000).toFixed(1)}s`}
              </span>
            )}
          </div>
        )}
      </div>
    </article>
  );
}
