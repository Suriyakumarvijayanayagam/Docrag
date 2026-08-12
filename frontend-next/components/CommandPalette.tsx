"use client";

import { useEffect, useMemo, useRef, useState } from "react";

export interface Command {
  id: string;
  label: string;
  hint?: string;
  keys?: string;
  run: () => void;
}

/**
 * Mounted only while open, so query and cursor start fresh from useState
 * rather than being reset by an effect (which would cascade a second render
 * every time the palette opens).
 */
export function CommandPalette({
  open,
  onClose,
  commands,
}: {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}) {
  if (!open) return null;
  return <PaletteBody onClose={onClose} commands={commands} />;
}

function PaletteBody({
  onClose,
  commands,
}: {
  onClose: () => void;
  commands: Command[];
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter((c) =>
      `${c.label} ${c.hint ?? ""}`.toLowerCase().includes(q),
    );
  }, [commands, query]);

  useEffect(() => {
    // focus after paint so the input exists
    requestAnimationFrame(() => inputRef.current?.focus());
  }, []);

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/55 pt-[14vh]"
      onMouseDown={onClose}
      role="presentation"
    >
      <div
        className="w-[min(560px,92vw)] overflow-hidden border border-rule-2 bg-panel shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          value={query}
          placeholder="Run a command…"
          onChange={(e) => {
            setQuery(e.target.value);
            setCursor(0); // reset the highlight as the result set changes
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") onClose();
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setCursor((c) => Math.min(c + 1, matches.length - 1));
            }
            if (e.key === "ArrowUp") {
              e.preventDefault();
              setCursor((c) => Math.max(c - 1, 0));
            }
            if (e.key === "Enter" && matches[cursor]) {
              e.preventDefault();
              matches[cursor].run();
              onClose();
            }
          }}
          className="w-full border-b border-rule bg-transparent px-4 py-3 font-mono text-[13px] text-ink outline-none placeholder:text-ink-3"
        />
        <ul className="max-h-[320px] overflow-y-auto py-1">
          {matches.map((c, i) => (
            <li key={c.id}>
              <button
                type="button"
                onMouseEnter={() => setCursor(i)}
                onClick={() => {
                  c.run();
                  onClose();
                }}
                className={`flex w-full items-center gap-3 px-4 py-2 text-left ${
                  i === cursor ? "bg-accent-dim" : ""
                }`}
              >
                <span className="flex-1 text-[13px] text-ink">{c.label}</span>
                {c.hint && (
                  <span className="font-mono text-[10.5px] text-ink-3">
                    {c.hint}
                  </span>
                )}
                {c.keys && (
                  <kbd className="border border-rule bg-sunk px-1.5 py-[1px] font-mono text-[10px] text-ink-3">
                    {c.keys}
                  </kbd>
                )}
              </button>
            </li>
          ))}
          {!matches.length && (
            <li className="px-4 py-3 font-mono text-[12px] text-ink-3">
              No matching command
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}
