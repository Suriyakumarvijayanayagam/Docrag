import type { SourceRef } from "@/lib/types";

function locatorLabel(loc: SourceRef["locator"]): string {
  if (loc === null || loc === undefined) return "—";
  return typeof loc === "number" ? `page ${loc}` : String(loc);
}

/**
 * Citations are the point of the product, so they are controls, not labels:
 * clicking one opens that document at that page in the viewer. A citation you
 * can't follow is just a claim - landing on the page is what lets a reviewer
 * actually check the answer.
 */
export function SourceChips({
  sources,
  onOpen,
}: {
  sources: SourceRef[];
  onOpen?: (file: string, page: number, snippet?: string | null) => void;
}) {
  if (!sources.length) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="label mr-0.5">Cited</span>
      {sources.map((s, i) => {
        const exact = s.relevance === "exact_match";
        const page = typeof s.locator === "number" ? s.locator : null;
        const followable = Boolean(onOpen && s.file && page);

        return (
          <button
            key={`${s.file}-${s.locator}-${i}`}
            type="button"
            disabled={!followable}
            onClick={() => followable && onOpen!(s.file!, page!, s.snippet)}
            title={
              followable
                ? `Open ${s.file} at page ${page}`
                : exact
                  ? "Exact value read from a table"
                  : `Relevance ${s.relevance} / 10`
            }
            className={`inline-flex max-w-[260px] items-center gap-1.5 rounded-full border px-2.5 py-[3px] text-[11.5px] transition-colors ${
              exact
                ? "border-exact-soft bg-exact-soft text-exact"
                : "border-rule bg-panel-2 text-ink-2"
            } ${followable ? "cursor-pointer hover:border-accent hover:text-accent" : "cursor-default"}`}
          >
            <span className="truncate">{s.file ?? "unknown"}</span>
            <span className="shrink-0 opacity-70">{locatorLabel(s.locator)}</span>
            {exact && <span className="shrink-0 text-[10px] uppercase tracking-wide">exact</span>}
          </button>
        );
      })}
    </div>
  );
}

/** Full-width rows with a relevance bar, for the detail panel. */
export function SourceRows({
  sources,
  onOpen,
}: {
  sources: SourceRef[];
  onOpen?: (file: string, page: number, snippet?: string | null) => void;
}) {
  if (!sources.length) {
    return <p className="px-4 py-5 text-[13px] text-ink-3">No sources for this answer yet.</p>;
  }
  return (
    <ul className="flex flex-col">
      {sources.map((s, i) => {
        const exact = s.relevance === "exact_match";
        const score = exact ? 10 : Number(s.relevance) || 0;
        const page = typeof s.locator === "number" ? s.locator : null;
        const followable = Boolean(onOpen && s.file && page);
        return (
          <li key={`${s.file}-${s.locator}-${i}`} className="border-b border-rule last:border-b-0">
            <button
              type="button"
              disabled={!followable}
              onClick={() => followable && onOpen!(s.file!, page!, s.snippet)}
              className={`w-full px-4 py-3 text-left ${followable ? "hover:bg-panel-2" : "cursor-default"}`}
            >
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-[12.5px] text-ink">{s.file ?? "unknown"}</span>
                <span className="shrink-0 text-[11.5px] text-ink-3">{locatorLabel(s.locator)}</span>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <div className="h-[4px] flex-1 overflow-hidden rounded-full bg-sunk">
                  <div
                    className={`h-full rounded-full ${exact ? "bg-exact" : "bg-accent"}`}
                    style={{ width: `${Math.min(100, score * 10)}%` }}
                  />
                </div>
                <span className={`text-[11px] tabular-nums ${exact ? "text-exact" : "text-ink-3"}`}>
                  {exact ? "exact" : score.toFixed(1)}
                </span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
