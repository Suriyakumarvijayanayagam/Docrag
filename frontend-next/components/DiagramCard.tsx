"use client";

import { useEffect, useId, useRef, useState } from "react";
import { apiUrl } from "@/lib/api";
import type { DiagramResponse } from "@/lib/types";

/**
 * Mermaid is bundled, not pulled from a CDN - the whole point of this stack is
 * that nothing leaves the machine, and a CDN script also means diagrams stop
 * rendering on a firewalled or offline network. Imported dynamically so it
 * stays out of the initial bundle until a diagram is actually requested.
 */
function useMermaid(source: string, enabled: boolean) {
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const id = useId().replace(/[^a-zA-Z0-9]/g, "");
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    if (!enabled || !source.trim()) return;

    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark =
          !document.documentElement.classList.contains("theme-light");
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: dark ? "dark" : "neutral",
          themeVariables: {
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
            fontSize: "13px",
          },
        });
        const { svg: rendered } = await mermaid.render(
          `mmd-${id}`,
          source.trim(),
        );
        if (alive.current) setSvg(rendered);
      } catch (err) {
        if (alive.current)
          setFailed(err instanceof Error ? err.message : String(err));
      }
    })();

    return () => {
      alive.current = false;
    };
  }, [source, enabled, id]);

  return { svg, failed };
}

const DIAGRAM_START =
  /^\s*(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram(-v2)?|erDiagram|journey|gantt|pie|mindmap|timeline|gitGraph|quadrantChart)\b/i;

/** Tokens that mark a line as diagram syntax rather than an English sentence. */
const DIAGRAM_TOKEN =
  /(-->|->>|--x|---|\|\||:::|\bparticipant\b|\bsubgraph\b|\bNote\b|\bend\b|\[|\()/;

/**
 * Pull the diagram out of whatever the model wrapped it in.
 *
 * A 3B model is inconsistent here in ways that matter: it emits a closing ```
 * with no opening one, or appends a sentence explaining the diagram after it.
 * Feeding either to mermaid throws a parse error, so the console would show
 *"syntax not valid" on output that actually contained a perfectly good
 * diagram. Take the fenced block when there is a real pair, otherwise start at
 * the diagram-type line and stop when the content stops looking like syntax.
 */
function cleanMermaid(raw: string): string {
  const fenced = raw.match(/```(?:mermaid)?\s*([\s\S]*?)```/i);
  if (fenced?.[1]?.trim()) return fenced[1].trim();

  const lines = raw.replace(/```(?:mermaid)?/gi, "").split("\n");
  const start = lines.findIndex((l) => DIAGRAM_START.test(l));
  if (start === -1) return raw.trim();

  const body: string[] = [];
  for (let i = start; i < lines.length; i++) {
    const line = lines[i];
    if (i > start && !line.trim()) {
      // a blank line ends the diagram unless what follows is still syntax
      const next = lines.slice(i + 1).find((l) => l.trim());
      if (!next || (!/^\s+\S/.test(next) && !DIAGRAM_TOKEN.test(next))) break;
    }
    body.push(line);
  }
  return body.join("\n").trim();
}

/**
 * Repair the two arrow malformations this model reliably produces. Both are
 * unambiguous, so fixing them client-side turns a parse error into a rendered
 * diagram; anything we don't recognise is left alone and falls through to the
 * raw-output view rather than being guessed at.
 */
function repairMermaid(src: string): string {
  return (
    src
      //"B --yes--> C" ->"B -->|yes| C" (label wants pipes, not dashes)
      .replace(/--\s*([A-Za-z0-9 _]+?)\s*-->/g, "-->|$1|")
      //"B --no-- > D" ->"B --> D" (space split the arrow head)
      .replace(/--\s*([A-Za-z0-9 _]+?)\s*--\s+>/g, "-->|$1|")
      .replace(/--\s+>/g, "-->")
      .replace(/-\s+->/g, "-->")
  );
}

export function DiagramCard({ data }: { data: DiagramResponse }) {
  const isFigure = Boolean(data.existing_figure_path);
  const source = repairMermaid(cleanMermaid(data.mermaid || ""));
  const { svg, failed } = useMermaid(source, !isFigure);

  return (
    <figure className="overflow-hidden border border-rule bg-panel-2">
      <figcaption className="flex items-center justify-between gap-3 border-b border-rule bg-sunk px-3 py-1.5">
        <span className="label">
          {isFigure
            ? "Figure extracted from the document"
            : "Generated diagram — no matching figure found"}
        </span>
        <span className="font-mono text-[10px] text-ink-3">{data.source}</span>
      </figcaption>

      {isFigure ? (
        <div className="flex flex-col gap-2 p-3">
          {/* eslint-disable-next-line @next/next/no-img-element -- backend-served file, not a Next asset */}
          <img
            src={apiUrl(data.existing_figure_path!)}
            alt={data.existing_figure_caption ?? "Figure from source document"}
            className="max-h-[440px] w-full bg-white object-contain"
          />
          {data.existing_figure_caption && (
            <p className="font-mono text-[11px] text-ink-2">
              {data.existing_figure_caption}
            </p>
          )}
        </div>
      ) : (
        <div className="mermaid-host overflow-x-auto p-3">
          {svg ? (
            <div dangerouslySetInnerHTML={{ __html: svg }} />
          ) : failed ? (
            <div className="flex flex-col gap-1.5">
              <span className="label text-note">
                Diagram syntax was not valid — showing raw output
              </span>
              <span className="font-mono text-[10.5px] leading-snug text-ink-3">
                {failed}
              </span>
              <pre className="overflow-x-auto font-mono text-[11.5px] text-ink-2">
                {source}
              </pre>
            </div>
          ) : (
            <span className="font-mono text-[11.5px] text-ink-3">
              rendering…
            </span>
          )}
        </div>
      )}
    </figure>
  );
}
