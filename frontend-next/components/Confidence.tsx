import type { Confidence } from "@/lib/types";

const SPEC: Record<Confidence, { text: string; tone: string; hint: string }> = {
  high: {
    text: "Well grounded",
    tone: "bg-ok-soft text-ok",
    hint: "A retrieved passage scored 7 or above out of 10 — the answer is well supported by the documents.",
  },
  medium: {
    text: "Partly grounded",
    tone: "bg-note-soft text-note",
    hint: "Scored between 4 and 7, or grounded by an exact table lookup with weaker surrounding text.",
  },
  low: {
    text: "Check the sources",
    tone: "bg-risk-soft text-risk",
    hint: "Nothing retrieved scored above 4 — the model may be filling gaps. Follow the citations before trusting this.",
  },
  none: {
    text: "Nothing retrieved",
    tone: "bg-panel-2 text-ink-3",
    hint: "No matching content in this project.",
  },
};

/**
 * Says what it means in words rather than making the reader decode a meter.
 * The underlying 0-10 score is still in the tooltip and on every source row.
 */
export function ConfidenceMeter({ level }: { level: Confidence }) {
  const spec = SPEC[level];
  return (
    <span
      title={spec.hint}
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-[3px] text-[11px] font-medium ${spec.tone}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />
      {spec.text}
    </span>
  );
}
