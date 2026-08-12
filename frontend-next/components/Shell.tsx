"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CommandPalette, type Command } from "./CommandPalette";
import { Sidebar } from "./Sidebar";
import { useWorkspace } from "./WorkspaceProvider";

/** Chrome that persists across routes: sidebar, command palette, toasts. */
export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const {
    exchanges,
    memory,
    newChat,
    refreshAll,
    refreshMemory,
    setStreamMode,
    setTheme,
    setToast,
    streamMode,
    theme,
    toast,
  } = useWorkspace();
  const [collapsed, setCollapsed] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  const commands = useMemo<Command[]>(
    () => [
      { id: "home", label: "Go home", keys: "", run: () => router.push("/") },
      { id: "chat", label: "Go to the conversation", run: () => router.push("/chat") },
      { id: "library", label: "Open the library", run: () => router.push("/library") },
      {
        id: "memory",
        label: "Open project memory",
        hint: memory.length ? `${memory.length} entries` : undefined,
        run: () => {
          refreshMemory();
          router.push("/memory");
        },
      },
      { id: "new", label: "Start a new chat", run: newChat },
      {
        id: "stream",
        label: streamMode ? "Turn streaming off" : "Turn streaming on",
        hint: streamMode ? "answers arrive word by word" : "answers arrive all at once",
        run: () => setStreamMode((s) => !s),
      },
      {
        id: "theme",
        label:
          theme === "dark"
            ? "Switch to light"
            : theme === "light"
              ? "Match the system theme"
              : "Switch to dark",
        run: () => setTheme(theme === "dark" ? "light" : theme === "light" ? "system" : "dark"),
      },
      {
        id: "sidebar",
        label: collapsed ? "Expand the sidebar" : "Collapse the sidebar",
        run: () => setCollapsed((c) => !c),
      },
      { id: "refresh", label: "Reload documents, status and memory", run: refreshAll },
      {
        id: "copy",
        label: "Copy the last answer",
        run: () => {
          const last = [...exchanges].reverse().find((e) => e.answer);
          if (last) {
            navigator.clipboard.writeText(last.answer);
            setToast("Answer copied");
          }
        },
      },
    ],
    [
      collapsed,
      exchanges,
      memory.length,
      newChat,
      refreshAll,
      refreshMemory,
      router,
      setStreamMode,
      setTheme,
      setToast,
      streamMode,
      theme,
    ],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((o) => !o);
      }
      if (e.key === "Escape") setPaletteOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="flex h-full bg-ground">
      <Sidebar collapsed={collapsed} onToggleCollapsed={() => setCollapsed((c) => !c)} />
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} commands={commands} />

      {toast && (
        <div
          role="status"
          className="rise fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-ink px-3.5 py-2 text-[12.5px] text-panel shadow-[var(--shadow-md)]"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
