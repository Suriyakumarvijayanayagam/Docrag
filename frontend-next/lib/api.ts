import type {
  AnswerResponse,
  DocumentSummary,
  DiagramResponse,
  IngestResponse,
  MemoryEntry,
  ProjectStatus,
  Scope,
  SourceRef,
} from "./types";

/**
 * Empty string means same-origin, which is the case when FastAPI serves the
 * exported console at /ui. In `npm run dev` the console runs on :3000 and
 * NEXT_PUBLIC_API_BASE points at the backend on :8000.
 */
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

/** Resolve a backend-relative path (e.g. a /figures/... image) to a full URL. */
export function apiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(apiUrl(path), init);
  } catch {
    // fetch only rejects on network-level failure - the backend being down
    throw new ApiError(
      `Cannot reach the DocRAG backend at ${API_BASE || window.location.origin}. Is uvicorn running?`,
      0,
    );
  }

  const body = await res.text();
  let parsed: unknown = null;
  try {
    parsed = body ? JSON.parse(body) : null;
  } catch {
    /* non-JSON error body - fall through to the status-based message */
  }

  if (!res.ok) {
    const detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? String((parsed as { detail: unknown }).detail)
        : body.slice(0, 300) || `Request failed (${res.status})`;
    throw new ApiError(detail, res.status);
  }
  return parsed as T;
}

export function health(): Promise<{ status: string }> {
  return request("/health");
}

export function projectStatus({
  userId,
  projectId,
}: Scope): Promise<ProjectStatus> {
  return request(
    `/projects/status?user_id=${encodeURIComponent(userId)}&project_id=${encodeURIComponent(projectId)}`,
  );
}

export function projectMemory({
  userId,
  projectId,
}: Scope): Promise<{ entries: MemoryEntry[] }> {
  return request(
    `/projects/memory?user_id=${encodeURIComponent(userId)}&project_id=${encodeURIComponent(projectId)}`,
  );
}

export function listDocuments({
  userId,
  projectId,
}: Scope): Promise<DocumentSummary[]> {
  return request(
    `/documents/list?user_id=${encodeURIComponent(userId)}&project_id=${encodeURIComponent(projectId)}`,
  );
}

export function uploadDocument(
  scope: Scope,
  file: File,
): Promise<IngestResponse> {
  const form = new FormData();
  form.append("user_id", scope.userId);
  form.append("project_id", scope.projectId);
  form.append("file", file);
  return request("/documents/upload", { method: "POST", body: form });
}

export function deleteDocument(
  scope: Scope,
  docId: string,
): Promise<{ status: string }> {
  return request(
    `/documents/${encodeURIComponent(docId)}?user_id=${encodeURIComponent(scope.userId)}&project_id=${encodeURIComponent(scope.projectId)}`,
    { method: "DELETE" },
  );
}

export function ask(scope: Scope, question: string): Promise<AnswerResponse> {
  return request("/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: scope.userId,
      project_id: scope.projectId,
      question,
    }),
  });
}

export function diagram(
  scope: Scope,
  requestText: string,
): Promise<DiagramResponse> {
  return request("/diagram", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: scope.userId,
      project_id: scope.projectId,
      request: requestText,
    }),
  });
}

interface StreamHandlers {
  onMeta: (meta: {
    sources: SourceRef[];
    confidence: AnswerResponse["confidence"];
  }) => void;
  onToken: (token: string) => void;
}

/**
 * /ask/stream emits one JSON metadata line (sources + confidence) and then
 * raw answer tokens. The backend reports model-backend failures *inside* the
 * stream once headers are sent, so a body starting with "[error]" is surfaced
 * as a real error rather than rendered as answer text.
 */
export async function askStream(
  scope: Scope,
  question: string,
  { onMeta, onToken }: StreamHandlers,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch(apiUrl("/ask/stream"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: scope.userId,
        project_id: scope.projectId,
        question,
      }),
    });
  } catch {
    throw new ApiError(
      `Cannot reach the DocRAG backend at ${API_BASE || window.location.origin}. Is uvicorn running?`,
      0,
    );
  }

  if (!res.ok || !res.body) {
    const text = await res.text();
    throw new ApiError(
      text.slice(0, 300) || `Stream failed (${res.status})`,
      res.status,
    );
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sawMeta = false;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    if (!sawMeta) {
      const nl = buffer.indexOf("\n");
      if (nl === -1) continue;
      try {
        onMeta(JSON.parse(buffer.slice(0, nl)));
      } catch {
        /* malformed meta line - keep streaming the answer anyway */
      }
      buffer = buffer.slice(nl + 1);
      sawMeta = true;
    }

    if (buffer) {
      if (buffer.trimStart().startsWith("[error]")) {
        throw new ApiError(buffer.trim().replace(/^\[error\]\s*/, ""), 503);
      }
      onToken(buffer);
      buffer = "";
    }
  }
}
