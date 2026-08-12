"use client";

import { useLayoutEffect, useRef, useState } from "react";
import {
  IconArrow,
  IconChat,
  IconLibrary,
  IconMemory,
  IconSearchDoc,
  IconShield,
  IconUpload,
} from "./icons";
import type { DocumentSummary, ProjectStatus } from "@/lib/types";

const QUICK = [
  { label: "Look up a spec", text: "What is the thermal shutdown threshold?" },
  { label: "Check a requirement", text: "Does this part meet the output ripple requirement?" },
  { label: "Find a diagram", text: "diagram: block diagram of the power subsystem" },
  { label: "Probe the gaps", text: "What isn't covered in these documents?" },
];

const ABOUT = [
  {
    Icon: IconChat,
    title: "Grounded and added, kept apart",
    body: "Every answer is split in two: what the documents actually say, and what the model added on top. You always know which half you're reading.",
  },
  {
    Icon: IconSearchDoc,
    title: "Citations you can follow",
    body: "Each citation opens the source PDF at that page and highlights the passage the answer came from — so a claim can be checked, not just trusted.",
  },
  {
    Icon: IconLibrary,
    title: "Tables get exact answers",
    body: "Spec tables are extracted at upload into an exact-lookup store, so “what's the max voltage” reads the value out of the table instead of guessing semantically.",
  },
  {
    Icon: IconShield,
    title: "Nothing leaves this machine",
    body: "Parsing, embeddings, reranking and generation all run locally through Ollama. No cloud calls, no document ever uploaded anywhere.",
  },
  {
    Icon: IconUpload,
    title: "Separate by user and project",
    body: "Each user + project pair gets its own physical store. There is no query path that spans them, so one workspace can't surface another's documents.",
  },
  {
    Icon: IconMemory,
    title: "It remembers the project",
    body: "Exchanges are distilled into durable facts and decisions rather than raw chat logs, so context survives across sessions without a growing transcript.",
  },
];

export function HomeView({
  docs,
  status,
  onAsk,
  onUpload,
  onOpenLibrary,
}: {
  docs: DocumentSummary[];
  status: ProjectStatus | null;
  onAsk: (question: string) => void;
  onUpload: (files: FileList | File[]) => void;
  onOpenLibrary: () => void;
}) {
  const [draft, setDraft] = useState("");
  const [dragging, setDragging] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, window.innerHeight * 0.35)}px`;
  }, [draft]);

  const facts = docs.reduce((n, d) => n + d.structured_fact_count, 0);
  const figures = docs.reduce((n, d) => n + d.figure_count, 0);

  return (
    <div
      className="h-full overflow-y-auto"
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (e.dataTransfer.files.length) onUpload(e.dataTransfer.files);
      }}
    >
      <div className="mx-auto flex w-full max-w-[760px] flex-col px-6 py-14">
        <div className="text-center">
          <p className="label mb-3">Local document intelligence</p>
          <h1 className="text-[30px] font-semibold leading-tight tracking-tight text-ink">
            What do you need from these documents?
          </h1>
          <p className="mx-auto mt-3 max-w-[52ch] text-[14px] leading-relaxed text-ink-2">
            Upload spec sheets, datasheets or design docs and ask technical questions about them.
            Answers cite the page they came from, and run entirely on a model on this machine.
          </p>
        </div>

        {/* the composer is the primary action, so it leads */}
        <div
          className={`mt-7 rounded-2xl border bg-panel p-2 shadow-[var(--shadow-sm)] transition-colors ${
            dragging ? "border-accent" : "border-rule"
          }`}
        >
          <textarea
            ref={box}
            rows={2}
            value={draft}
            placeholder="Ask a question, or drop a PDF anywhere on this page…"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                if (draft.trim()) onAsk(draft.trim());
              }
            }}
            className="w-full resize-none bg-transparent px-3 pt-2.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-3"
            style={{ maxHeight: "35vh" }}
          />
          <div className="flex items-center gap-2 px-2 pb-1 pt-1">
            <button
              type="button"
              onClick={() => fileInput.current?.click()}
              className="flex items-center gap-1.5 rounded-lg border border-rule px-2.5 py-1.5 text-[12.5px] text-ink-2 hover:border-accent hover:text-accent"
            >
              <IconUpload size={14} />
              Add document
            </button>
            <input
              ref={fileInput}
              type="file"
              accept=".pdf,.docx"
              multiple
              hidden
              onChange={(e) => {
                if (e.target.files?.length) onUpload(e.target.files);
                e.target.value = "";
              }}
            />
            <span className="text-[11.5px] text-ink-3">PDF or DOCX</span>
            <button
              type="button"
              onClick={() => draft.trim() && onAsk(draft.trim())}
              disabled={!draft.trim()}
              className="ml-auto rounded-xl bg-accent px-3.5 py-1.5 text-[12.5px] font-medium text-white disabled:opacity-35"
            >
              Ask
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap justify-center gap-1.5">
          {QUICK.map((q) => (
            <button
              key={q.label}
              type="button"
              onClick={() => onAsk(q.text)}
              title={q.text}
              className="rounded-full border border-rule bg-panel px-3 py-1.5 text-[12.5px] text-ink-2 transition-colors hover:border-accent hover:text-accent"
            >
              {q.label}
            </button>
          ))}
        </div>

        {/* what's actually loaded right now */}
        <button
          type="button"
          onClick={onOpenLibrary}
          className="mt-8 flex items-center gap-4 rounded-xl border border-rule bg-panel px-4 py-3 text-left hover:border-accent"
        >
          <span className="flex-1">
            <span className="block text-[13.5px] font-medium text-ink">
              {docs.length === 0
                ? "No documents in this workspace yet"
                : `${docs.length} ${docs.length === 1 ? "document" : "documents"} ready`}
            </span>
            <span className="mt-0.5 block text-[12.5px] text-ink-3">
              {docs.length === 0
                ? "Drop a PDF or DOCX to get started — parsing takes about a second."
                : `${facts} spec ${facts === 1 ? "value" : "values"} from tables · ${figures} ${figures === 1 ? "figure" : "figures"} found · ${status?.memory_entry_count ?? 0} remembered`}
            </span>
          </span>
          <span className="flex shrink-0 items-center gap-1.5 text-[12.5px] text-accent">
            Library
            <IconArrow size={14} />
          </span>
        </button>

        <div className="mt-10">
          <h2 className="text-[13px] font-semibold text-ink">How it works</h2>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {ABOUT.map((a) => (
              <div key={a.title} className="rounded-xl border border-rule bg-panel px-4 py-3.5 transition-colors hover:border-rule-2">
                <h3 className="flex items-center gap-2 text-[13px] font-medium text-ink">
                  <span className="grid h-6 w-6 place-items-center rounded-lg bg-accent-soft text-accent">
                    <a.Icon size={14} />
                  </span>
                  {a.title}
                </h3>
                <p className="mt-1 text-[12.5px] leading-relaxed text-ink-2">{a.body}</p>
              </div>
            ))}
          </div>
        </div>

        <p className="mt-8 text-center text-[11.5px] leading-relaxed text-ink-3">
          Runs on a small local model, so answers take a few seconds and complex multi-part
          comparisons are worth double-checking against the cited pages.
        </p>
      </div>
    </div>
  );
}
