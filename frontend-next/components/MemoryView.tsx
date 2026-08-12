"use client";

import type { MemoryEntry } from "@/lib/types";

const TONE: Record<string, string> = {
  fact: "bg-accent-soft text-accent",
  decision: "bg-exact-soft text-exact",
  preference: "bg-note-soft text-note",
};

export function MemoryView({ entries }: { entries: MemoryEntry[] }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-[720px] px-6 py-8">
        <h1 className="text-[20px] font-semibold tracking-tight text-ink">Project memory</h1>
        <p className="mt-1 max-w-[62ch] text-[13px] leading-relaxed text-ink-2">
          What this project knows, as distinct from what any one document says. Each exchange is
          distilled into a durable fact or decision — or dropped if it wasn&apos;t worth keeping —
          so context carries across sessions without a growing transcript.
        </p>

        {entries.length === 0 ? (
          <div className="mt-6 rounded-xl border border-rule bg-panel px-4 py-8 text-center">
            <p className="text-[13.5px] text-ink-2">Nothing remembered yet</p>
            <p className="mt-1 text-[12.5px] text-ink-3">
              Ask a few questions and the durable parts will collect here.
            </p>
          </div>
        ) : (
          <ul className="mt-6 flex flex-col gap-2">
            {entries.map((e, i) => (
              <li key={i} className="rounded-xl border border-rule bg-panel px-4 py-3.5">
                <span
                  className={`inline-block rounded-full px-2 py-[2px] text-[10.5px] font-medium ${
                    TONE[e.entry_type] ?? "bg-panel-2 text-ink-3"
                  }`}
                >
                  {e.entry_type}
                </span>
                <p className="mt-1.5 text-[13px] leading-relaxed text-ink-2">{e.content}</p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
