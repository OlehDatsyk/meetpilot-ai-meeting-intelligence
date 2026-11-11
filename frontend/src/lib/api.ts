/** API client. The bearer token lives in localStorage; no secrets or provider keys ever reach the browser. */

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "meetpilot.token";

export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode); the session lasts for this tab only */
  }
}

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: (() => void) | null) {
  onUnauthorized = fn;
}

async function parseError(res: Response): Promise<ApiError> {
  let code = "error";
  let message = `Request failed (HTTP ${res.status}).`;
  let details: unknown;
  try {
    const body = await res.json();
    if (body?.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
      if (code === "validation_error" && Array.isArray(details) && details.length) {
        const fields = (details as { field: string; message: string }[])
          .map((d) => `${d.field.split(".").pop() || "value"}: ${d.message.replace(/^Value error, /, "")}`);
        message = `${message} ${fields.join("; ")}`;
      }
    }
  } catch {
    if (res.status >= 500) message = "The server is unavailable. Please try again shortly.";
  }
  return new ApiError(res.status, code, message, details);
}

export function url(path: string) {
  return `${API_BASE}${path}`;
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  let res: Response;
  try {
    res = await fetch(url(path), { ...init, headers, body });
  } catch {
    throw new ApiError(0, "network_error", "Cannot reach the MeetPilot AI server. Check your connection.");
  }
  if (res.status === 401 && token) onUnauthorized?.();
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, json?: unknown) => api<T>(path, { method: "POST", json: json ?? {} });
export const patch = <T>(path: string, json: unknown) => api<T>(path, { method: "PATCH", json });
export const del = <T>(path: string, json?: unknown) => api<T>(path, { method: "DELETE", json });

export function qs(params: Record<string, string | number | boolean | null | undefined>) {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Upload with real progress events (fetch has no upload progress). */
export function uploadFile<T>(path: string, form: FormData, onProgress: (fraction: number) => void,
                              signal?: AbortSignal): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url(path));
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    xhr.onload = () => {
      let body: any = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        /* non-JSON error page */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as T);
      else reject(new ApiError(xhr.status, body?.error?.code ?? "upload_failed",
        body?.error?.message ?? (xhr.status === 413 ? "The file is too large." : `Upload failed (HTTP ${xhr.status}).`)));
    };
    xhr.onerror = () => reject(new ApiError(0, "network_error", "The upload was interrupted. Check your connection."));
    xhr.onabort = () => reject(new ApiError(0, "aborted", "Upload cancelled."));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(form);
  });
}

/** Download an authenticated file and hand it to the browser. */
export async function download(path: string, fallbackName: string) {
  const headers = new Headers();
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const res = await fetch(url(path), { headers });
  if (!res.ok) throw await parseError(res);
  const blob = await res.blob();
  const cd = res.headers.get("Content-Disposition") || "";
  const match = /filename="([^"]+)"/.exec(cd);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = match?.[1] || fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
