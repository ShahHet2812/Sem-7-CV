/**
 * Centralized API client.
 *
 * VITE_API_BASE_URL is the backend origin as seen by the browser. Leave it
 * empty to use same-origin requests (Vite dev proxy / nginx in Docker).
 */
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  code: string
  details: unknown

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

type Query = Record<string, string | number | boolean | null | undefined | string[]>

export function apiUrl(path: string, query?: Query): string {
  const url = `${API_BASE_URL}${path}`
  if (!query) return url
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((item) => params.append(k, item))
    else params.append(k, String(v))
  }
  const qs = params.toString()
  return qs ? `${url}?${qs}` : url
}

/** Resolve server-relative resource URLs (e.g. stream_url) against the API base. */
export function resourceUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined
  return path.startsWith('http') ? path : `${API_BASE_URL}${path}`
}

function describeValidation(details: unknown): string | null {
  if (!Array.isArray(details) || details.length === 0) return null
  const first = details[0] as { loc?: string[]; msg?: string }
  const field = first.loc?.filter((p) => p !== 'body' && p !== 'query').join('.')
  const msg = (first.msg ?? '').replace(/^Value error, /, '')
  return field ? `${field}: ${msg}` : msg
}

export async function parseError(res: Response): Promise<ApiError> {
  let code = 'http_error'
  let message = `Request failed (${res.status})`
  let details: unknown
  try {
    const body = await res.json()
    if (body?.error) {
      code = body.error.code ?? code
      message = body.error.message ?? message
      details = body.error.details
      if (code === 'validation_error') message = describeValidation(details) ?? message
    }
  } catch {
    // non-JSON error body (e.g. proxy error page)
  }
  if (res.status === 502 || res.status === 504) {
    message = 'The API server is not reachable. Is the backend running?'
    code = 'backend_unreachable'
  }
  return new ApiError(res.status, code, message, details)
}

export async function request<T>(
  method: string,
  path: string,
  options: { query?: Query; body?: unknown; signal?: AbortSignal } = {},
): Promise<T> {
  let res: Response
  try {
    res = await fetch(apiUrl(path, options.query), {
      method,
      signal: options.signal,
      headers: options.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw err
    throw new ApiError(0, 'network_error', 'Cannot reach the ZoneVision API. Check that the backend is running.')
  }
  if (!res.ok) throw await parseError(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>('GET', path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, { body }),
  delete: (path: string) => request<void>('DELETE', path),
}

/** Multipart upload with progress (fetch has no upload progress events). */
export function uploadWithProgress<T>(
  path: string,
  form: FormData,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', apiUrl(path))
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total)
    }
    xhr.onload = async () => {
      const res = new Response(xhr.responseText, { status: xhr.status })
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText) as T)
      else reject(await parseError(res))
    }
    xhr.onerror = () => reject(new ApiError(0, 'network_error', 'Upload failed: the API is not reachable.'))
    xhr.onabort = () => reject(new ApiError(0, 'aborted', 'Upload cancelled.'))
    signal?.addEventListener('abort', () => xhr.abort())
    xhr.send(form)
  })
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return 'Something went wrong.'
}
