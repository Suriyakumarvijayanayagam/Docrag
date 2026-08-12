"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  IconAuto,
  IconChat,
  IconHome,
  IconLibrary,
  IconMemory,
  IconMoon,
  IconPanel,
  IconPlus,
  IconSun,
} from "./icons";
import { useWorkspace, type ThemeChoice } from "./WorkspaceProvider";

const NAV = [
  { href: "/", label: "Home", hint: "What this is and how to use it", Icon: IconHome },
  { href: "/chat", label: "Ask documents", hint: "Chat beside the source PDF", Icon: IconChat },
  { href: "/library", label: "Library", hint: "Uploaded documents", Icon: IconLibrary },
  { href: "/memory", label: "Project memory", hint: "What this project has learned", Icon: IconMemory },
] as const;

const THEMES: { id: ThemeChoice; label: string; Icon: typeof IconSun }[] = [
  { id: "light", label: "Light", Icon: IconSun },
  { id: "dark", label: "Dark", Icon: IconMoon },
  { id: "system", label: "Match system", Icon: IconAuto },
];

export function Sidebar({
  collapsed,
  onToggleCollapsed,
}: {
  collapsed: boolean;
  onToggleCollapsed: () => void;
}) {
  const path = usePathname();
  const { scope, setScope, status, docs, memory, online, newChat, theme, setTheme } = useWorkspace();
  const [idOpen, setIdOpen] = useState(false);
  const idRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!idOpen) return;
    const away = (e: MouseEvent) => {
      if (idRef.current && !idRef.current.contains(e.target as Node)) setIdOpen(false);
    };
    document.addEventListener("mousedown", away);
    return () => document.removeEventListener("mousedown", away);
  }, [idOpen]);

  const countFor = (href: string) =>
    href === "/library" ? docs.length : href === "/memory" ? memory.length : 0;

  return (
    <nav
      className={`flex h-full shrink-0 flex-col border-r border-rule bg-panel-2 transition-[width] duration-200 ${
        collapsed ? "w-[64px]" : "w-[248px]"
      }`}
    >
      <div className="flex items-center gap-2 px-3 py-3">
        <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-accent text-[13px] font-bold text-white">
          D
        </span>
        {!collapsed && (
          <span className="flex-1 truncate text-[14px] font-semibold tracking-tight text-ink">
            DocRAG
          </span>
        )}
        <button
          type="button"
          onClick={onToggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="rounded-md p-1.5 text-ink-3 transition-colors hover:bg-panel hover:text-ink-2"
        >
          <IconPanel />
        </button>
      </div>

      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={newChat}
          title="Start a new conversation"
          className={`flex w-full items-center gap-2 rounded-xl border border-rule bg-panel py-2 text-[13px] font-medium text-ink shadow-[var(--shadow-sm)] transition-colors hover:border-accent hover:text-accent ${
            collapsed ? "justify-center px-0" : "px-3"
          }`}
        >
          <IconPlus />
          {!collapsed && "New chat"}
        </button>
      </div>

      <ul className="flex flex-1 flex-col gap-0.5 px-2 py-2">
        {NAV.map(({ href, label, hint, Icon }) => {
          const active = path === href;
          const count = countFor(href);
          return (
            <li key={href}>
              <Link
                href={href}
                title={collapsed ? label : hint}
                aria-current={active ? "page" : undefined}
                className={`relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] transition-colors ${
                  active
                    ? "bg-accent-soft font-medium text-accent"
                    : "text-ink-2 hover:bg-panel hover:text-ink"
                } ${collapsed ? "justify-center" : ""}`}
              >
                {/* a short bar marks the current page even when collapsed */}
                {active && (
                  <span className="absolute -left-2 top-1/2 h-4 w-[3px] -translate-y-1/2 rounded-r bg-accent" />
                )}
                <Icon />
                {!collapsed && (
                  <>
                    <span className="flex-1 truncate">{label}</span>
                    {count > 0 && (
                      <span className="shrink-0 text-[11.5px] tabular-nums text-ink-3">{count}</span>
                    )}
                  </>
                )}
              </Link>
            </li>
          );
        })}
      </ul>

      {!collapsed && (
        <div className="px-3 pb-2">
          <div className="flex gap-0.5 rounded-lg bg-panel p-0.5">
            {THEMES.map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => setTheme(id)}
                title={label}
                aria-label={label}
                aria-pressed={theme === id}
                className={`flex flex-1 items-center justify-center rounded-md py-1.5 transition-colors ${
                  theme === id ? "bg-accent-soft text-accent" : "text-ink-3 hover:text-ink-2"
                }`}
              >
                <Icon size={14} />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Who you are. There is no auth layer in this system - identity is
          whatever the client sends - so this says exactly that rather than
          dressing an unauthenticated field up as a signed-in account. */}
      <div ref={idRef} className="relative border-t border-rule p-2">
        <button
          type="button"
          onClick={() => setIdOpen((o) => !o)}
          className={`flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left transition-colors hover:bg-panel ${
            collapsed ? "justify-center" : ""
          }`}
          title={`${scope.userId} · ${scope.projectId}`}
        >
          <span className="relative grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-[12px] font-semibold uppercase text-accent">
            {scope.userId.slice(0, 2)}
            {collapsed && (
              <span
                className={`absolute -bottom-0.5 -right-0.5 h-2 w-2 rounded-full border-2 border-panel-2 ${
                  online === null ? "bg-ink-3" : online ? "bg-ok" : "pulse bg-risk"
                }`}
              />
            )}
          </span>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-[13px] text-ink">{scope.userId}</span>
                <span className="block truncate text-[11.5px] text-ink-3">{scope.projectId}</span>
              </span>
              <span
                title={online ? "Backend reachable" : "Cannot reach the backend"}
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  online === null ? "bg-ink-3" : online ? "bg-ok" : "pulse bg-risk"
                }`}
              />
            </>
          )}
        </button>

        {idOpen && (
          <div className="rise absolute bottom-[calc(100%+6px)] left-2 z-40 w-[268px] rounded-xl border border-rule bg-panel p-3 shadow-[var(--shadow-md)]">
            <p className="mb-2 text-[11.5px] leading-snug text-ink-3">
              No sign-in yet — a workspace is just a user and project name, and each pair keeps its
              own separate documents and memory.
            </p>
            <label className="mb-2 flex flex-col gap-1">
              <span className="label">User</span>
              <input
                value={scope.userId}
                onChange={(e) => setScope({ ...scope, userId: e.target.value })}
                spellCheck={false}
                className="rounded-md border border-rule bg-panel-2 px-2 py-1.5 font-mono text-[12px] text-ink outline-none focus:border-accent"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="label">Project</span>
              <input
                value={scope.projectId}
                onChange={(e) => setScope({ ...scope, projectId: e.target.value })}
                spellCheck={false}
                className="rounded-md border border-rule bg-panel-2 px-2 py-1.5 font-mono text-[12px] text-ink outline-none focus:border-accent"
              />
            </label>
            <p className="mt-2 text-[11.5px] text-ink-3">
              {status?.document_count ?? 0} documents · {status?.memory_entry_count ?? 0} memory
              entries
            </p>
          </div>
        )}
      </div>
    </nav>
  );
}
