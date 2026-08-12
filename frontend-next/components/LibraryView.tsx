"use client";

import { useRef, useState } from "react";
import { ArtEmptyLibrary, IconTrash, IconUpload } from "./icons";
import type { DocumentSummary } from "@/lib/types";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export function LibraryView({
  docs,
  uploading,
  onUpload,
  onDelete,
  onOpen,
}: {
  docs: DocumentSummary[];
  uploading: string[];
  onUpload: (files: FileList | File[]) => void;
  onDelete: (docId: string) => void;
  onOpen: (docId: string) => void;
}) {
  const [dragging, setDragging] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

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
      <div className="mx-auto w-full max-w-[860px] px-6 py-8">
        <header className="mb-5 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-[20px] font-semibold tracking-tight text-ink">Library</h1>
            <p className="mt-1 text-[13px] text-ink-2">
              Documents in this workspace. Uploading parses the file, extracts its tables and
              figures, and indexes it for questions.
            </p>
          </div>
          <button
            type="button"
            onClick={() => fileInput.current?.click()}
            className="flex shrink-0 items-center gap-1.5 rounded-xl bg-accent px-3.5 py-2 text-[12.5px] font-medium text-white transition-opacity hover:opacity-90"
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
        </header>

        <div
          className={`mb-4 rounded-xl border border-dashed px-4 py-6 text-center transition-colors ${
            dragging ? "border-accent bg-accent-soft" : "border-rule-2 bg-panel-2"
          }`}
        >
          <p className="flex items-center justify-center gap-2 text-[13px] text-ink-2">
            <IconUpload size={15} />
            Drop PDFs or Word documents anywhere on this page
          </p>
        </div>

        <ul className="flex flex-col gap-2">
          {uploading.map((name) => (
            <li
              key={name}
              className="flex items-center gap-3 rounded-xl border border-rule bg-panel px-4 py-3"
            >
              <span className="pulse h-2 w-2 shrink-0 rounded-full bg-accent" />
              <span className="min-w-0 flex-1 truncate text-[13.5px] text-ink-2">{name}</span>
              <span className="shrink-0 text-[12px] text-ink-3">
                parsing · extracting tables · indexing
              </span>
            </li>
          ))}

          {docs.map((d) => (
            <li
              key={d.doc_id}
              className="group flex items-center gap-4 rounded-xl border border-rule bg-panel px-4 py-3"
            >
              <button
                type="button"
                onClick={() => onOpen(d.doc_id)}
                className="min-w-0 flex-1 text-left"
              >
                <span className="block truncate text-[13.5px] font-medium text-ink">
                  {d.filename}
                </span>
                <span className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[12px] text-ink-3">
                  <span>{plural(d.chunk_count, "passage", "passages")}</span>
                  <span className={d.structured_fact_count > 0 ? "text-exact" : undefined}>
                    {plural(d.structured_fact_count, "spec value", "spec values")}
                  </span>
                  <span className={d.figure_count > 0 ? "text-accent" : undefined}>
                    {plural(d.figure_count, "figure", "figures")}
                  </span>
                </span>
              </button>

              {confirming === d.doc_id ? (
                <span className="flex shrink-0 items-center gap-2">
                  <span className="text-[12px] text-ink-2">Remove it?</span>
                  <button
                    type="button"
                    onClick={() => {
                      onDelete(d.doc_id);
                      setConfirming(null);
                    }}
                    className="rounded-lg bg-risk px-2.5 py-1 text-[12px] font-medium text-white"
                  >
                    Remove
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirming(null)}
                    className="rounded-lg px-2 py-1 text-[12px] text-ink-2 hover:bg-panel-2"
                  >
                    Cancel
                  </button>
                </span>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirming(d.doc_id)}
                  className="shrink-0 rounded-lg p-1.5 text-ink-3 opacity-0 transition-opacity hover:bg-panel-2 hover:text-risk focus-visible:opacity-100 group-hover:opacity-100"
                  title="Remove this document"
                  aria-label={`Remove ${d.filename}`}
                >
                  <IconTrash size={15} />
                </button>
              )}
            </li>
          ))}

          {!docs.length && !uploading.length && (
            <li className="flex flex-col items-center rounded-xl border border-rule bg-panel px-4 py-10 text-center">
              <ArtEmptyLibrary className="mb-3" />
              <p className="text-[13.5px] text-ink-2">Nothing here yet</p>
              <p className="mx-auto mt-1 max-w-[44ch] text-[12.5px] leading-relaxed text-ink-3">
                Documents are scoped to this user and project — switch workspace from the account
                block at the bottom of the sidebar to see a different set.
              </p>
            </li>
          )}
        </ul>

        {docs.length > 0 && (
          <p className="mt-4 text-[12px] leading-relaxed text-ink-3">
            Removing a document deletes its passages, its extracted spec values and its figures
            together, so it stops answering questions immediately.
          </p>
        )}
      </div>
    </div>
  );
}
