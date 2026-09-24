export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { credentials: 'include', ...options })
  if (!response.ok) {
    let detail = `Request failed (${response.status})`
    try {
      const body = await response.json()
      detail = body.detail || detail
    } catch { /* response had no JSON body */ }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function formatBytes(bytes?: number): string {
  if (!bytes) return '—'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
