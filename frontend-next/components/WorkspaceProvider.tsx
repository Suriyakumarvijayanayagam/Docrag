"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import * as api from "@/lib/api";
import { ApiError } from "@/lib/api";
import type { ViewerTarget } from "./PdfViewer";
import type { DocumentSummary, Exchange, MemoryEntry, ProjectStatus, Scope } from "@/lib/types";

const SCOPE_KEY = "docrag.scope";
const THEME_KEY = "docrag.theme";
const DIAGRAM_PREFIX = "diagram:";

export type ThemeChoice = "light" | "dark" | "system";

/**
 * Workspace state lives above the routes so navigating between Home, Ask,
 * Library and Memory doesn't discard the conversation or refetch everything -
 * the provider sits in the root layout, which Next keeps mounted across
 * client-side navigation.
 */
interface WorkspaceValue {
  scope: Scope;
  setScope: (s: Scope) => void;
  docs: DocumentSummary[];
  uploading: string[];
  status: ProjectStatus | null;
  memory: MemoryEntry[];
  exchanges: Exchange[];
  input: string;
  setInput: (v: string) => void;
  busy: boolean;
  online: boolean | null;
  streamMode: boolean;
  setStreamMode: (fn: (s: boolean) => boolean) => void;
  theme: ThemeChoice;
  setTheme: (t: ThemeChoice) => void;
  viewer: ViewerTarget | null;
  toast: string | null;
  setToast: (t: string | null) => void;
  submit: (text: string) => void;
  newChat: () => void;
  upload: (files: FileList | File[]) => void;
  remove: (docId: string) => void;
  openSource: (file: string, page: number, snippet?: string | null) => void;
  openDoc: (docId: string) => void;
  pickDoc: (docId: string) => void;
  refreshAll: () => void;
  refreshMemory: () => void;
}

const Ctx = createContext<WorkspaceValue | null>(null);

export function useWorkspace(): WorkspaceValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return v;
}

function useDebounced<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(t);
  }, [value, delayMs]);
  return settled;
}

function newId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [scope, setScopeState] = useState<Scope>({ userId: "demo", projectId: "demo" });
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [uploading, setUploading] = useState<string[]>([]);
  const [status, setStatus] = useState<ProjectStatus | null>(null);
  const [memory, setMemory] = useState<MemoryEntry[]>([]);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [input, setInput] = useState("");
  const [streamMode, setStreamModeState] = useState(true);
  const [busy, setBusy] = useState(false);
  const [online, setOnline] = useState<boolean | null>(null);
  const [theme, setThemeState] = useState<ThemeChoice>("system");
  const [toast, setToast] = useState<string | null>(null);
  const [viewer, setViewer] = useState<ViewerTarget | null>(null);
  const hydrated = useRef(false);

  const loadScope = useDebounced(scope, 450);

  /* ---------- persistence ---------- */

  useEffect(() => {
    const saved = localStorage.getItem(SCOPE_KEY);
    const savedTheme = localStorage.getItem(THEME_KEY) as ThemeChoice | null;
    hydrated.current = true;
    if (saved) {
      try {
        // localStorage doesn't exist during the static prerender, so restoring
        // after mount is correct - a lazy initialiser would break hydration.
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setScopeState(JSON.parse(saved));
      } catch {
        /* ignore malformed value */
      }
    }
    if (savedTheme === "light" || savedTheme === "dark") setThemeState(savedTheme);
  }, []);

  useEffect(() => {
    if (hydrated.current) localStorage.setItem(SCOPE_KEY, JSON.stringify(scope));
  }, [scope]);

  // "system" follows the OS and keeps following it while it's selected
  useEffect(() => {
    localStorage.setItem(THEME_KEY, theme);
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      document.documentElement.classList.toggle(
        "theme-dark",
        theme === "dark" || (theme === "system" && mq.matches),
      );
    apply();
    if (theme !== "system") return;
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, [theme]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 3200);
    return () => clearTimeout(t);
  }, [toast]);

  /* ---------- backend ---------- */

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(await api.projectStatus(loadScope));
      setOnline(true);
    } catch {
      setStatus(null);
      setOnline(false);
    }
  }, [loadScope]);

  const refreshDocs = useCallback(async () => {
    try {
      setDocs(await api.listDocuments(loadScope));
    } catch {
      setDocs([]);
    }
  }, [loadScope]);

  const refreshMemory = useCallback(async () => {
    try {
      setMemory((await api.projectMemory(loadScope)).entries);
    } catch {
      setMemory([]);
    }
  }, [loadScope]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- async fetches
    refreshStatus();
    refreshMemory();
    refreshDocs();
  }, [refreshStatus, refreshMemory, refreshDocs]);

  useEffect(() => {
    const t = setInterval(refreshStatus, 15000);
    return () => clearInterval(t);
  }, [refreshStatus]);

  /**
   * Switching workspace clears everything on screen. Done at the point of
   * change rather than in an effect: showing one workspace's documents or
   * answers while scoped to another would undercut the isolation guarantee.
   */
  const setScope = useCallback((next: Scope) => {
    setScopeState(next);
    setDocs([]);
    setExchanges([]);
    setMemory([]);
    setViewer(null);
  }, []);

  const setStreamMode = useCallback((fn: (s: boolean) => boolean) => setStreamModeState(fn), []);
  const setTheme = useCallback((t: ThemeChoice) => setThemeState(t), []);

  /* ---------- documents ---------- */

  const upload = useCallback(
    async (files: FileList | File[]) => {
      const list = Array.from(files).filter((f) => /\.(pdf|docx)$/i.test(f.name));
      if (!list.length) {
        setToast("Only PDF and Word documents can be added");
        return;
      }
      setUploading((u) => [...u, ...list.map((f) => f.name)]);
      for (const file of list) {
        try {
          await api.uploadDocument(scope, file);
        } catch (e) {
          setToast(
            e instanceof ApiError ? `${file.name}: ${e.message}` : `${file.name}: upload failed`,
          );
        } finally {
          setUploading((u) => u.filter((n) => n !== file.name));
        }
      }
      refreshDocs();
      refreshStatus();
    },
    [scope, refreshDocs, refreshStatus],
  );

  const remove = useCallback(
    async (docId: string) => {
      try {
        await api.deleteDocument(scope, docId);
        setViewer((v) => (v?.docId === docId ? null : v));
        refreshDocs();
        refreshStatus();
      } catch (e) {
        setToast(e instanceof ApiError ? e.message : "Delete failed");
      }
    },
    [scope, refreshDocs, refreshStatus],
  );

  const pickDoc = useCallback((docId: string) => {
    setViewer((v) => ({ docId, page: 1, snippet: null, nonce: (v?.nonce ?? 0) + 1 }));
  }, []);

  const openDoc = useCallback(
    (docId: string) => {
      pickDoc(docId);
      router.push("/chat");
    },
    [pickDoc, router],
  );

  /** Follow a citation: open that document at the cited page and highlight it. */
  const openSource = useCallback(
    (file: string, page: number, snippet?: string | null) => {
      const doc = docs.find((d) => d.filename === file);
      if (!doc) return;
      if (!doc.filename.toLowerCase().endsWith(".pdf")) {
        setToast("Only PDFs can be previewed — this citation points at a Word document");
        return;
      }
      setViewer((v) => ({
        docId: doc.doc_id,
        page,
        snippet: snippet ?? null,
        nonce: (v?.nonce ?? 0) + 1,
      }));
    },
    [docs],
  );

  /* ---------- asking ---------- */

  const patch = useCallback((id: string, next: Partial<Exchange>) => {
    setExchanges((list) => list.map((e) => (e.id === id ? { ...e, ...next } : e)));
  }, []);

  const submit = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;

      const isDiagram = text.toLowerCase().startsWith(DIAGRAM_PREFIX);
      const id = newId();
      const started = performance.now();

      router.push("/chat");
      setExchanges((list) => [
        ...list,
        {
          id,
          question: text,
          kind: isDiagram ? "diagram" : "answer",
          status: "pending",
          answer: "",
          sources: [],
          confidence: "none",
        },
      ]);
      setInput("");
      setBusy(true);

      try {
        if (isDiagram) {
          const data = await api.diagram(scope, text.slice(DIAGRAM_PREFIX.length).trim());
          patch(id, { status: "done", diagram: data, elapsedMs: performance.now() - started });
        } else if (streamMode) {
          let acc = "";
          let ttft: number | undefined;
          patch(id, { status: "streaming" });
          await api.askStream(scope, text, {
            onMeta: (meta) => patch(id, { sources: meta.sources, confidence: meta.confidence }),
            onToken: (tok) => {
              if (ttft === undefined) ttft = performance.now() - started;
              acc += tok;
              patch(id, { answer: acc });
            },
          });
          patch(id, { status: "done", ttftMs: ttft, elapsedMs: performance.now() - started });
        } else {
          const res = await api.ask(scope, text);
          patch(id, {
            status: "done",
            answer: res.answer,
            sources: res.sources,
            confidence: res.confidence,
            elapsedMs: performance.now() - started,
          });
        }
        refreshMemory();
        refreshStatus();
      } catch (e) {
        patch(id, {
          status: "error",
          error: e instanceof ApiError ? e.message : "Something went wrong",
          elapsedMs: performance.now() - started,
        });
        if (e instanceof ApiError && e.status === 0) setOnline(false);
      } finally {
        setBusy(false);
      }
    },
    [busy, patch, refreshMemory, refreshStatus, router, scope, streamMode],
  );

  const newChat = useCallback(() => {
    setExchanges([]);
    setInput("");
    router.push("/");
  }, [router]);

  const refreshAll = useCallback(() => {
    refreshDocs();
    refreshStatus();
    refreshMemory();
  }, [refreshDocs, refreshStatus, refreshMemory]);

  const value = useMemo<WorkspaceValue>(
    () => ({
      scope,
      setScope,
      docs,
      uploading,
      status,
      memory,
      exchanges,
      input,
      setInput,
      busy,
      online,
      streamMode,
      setStreamMode,
      theme,
      setTheme,
      viewer,
      toast,
      setToast,
      submit,
      newChat,
      upload,
      remove,
      openSource,
      openDoc,
      pickDoc,
      refreshAll,
      refreshMemory,
    }),
    [
      busy,
      docs,
      exchanges,
      input,
      memory,
      newChat,
      online,
      openDoc,
      openSource,
      pickDoc,
      refreshAll,
      refreshMemory,
      remove,
      scope,
      setScope,
      setStreamMode,
      setTheme,
      status,
      streamMode,
      submit,
      theme,
      toast,
      upload,
      uploading,
      viewer,
    ],
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
