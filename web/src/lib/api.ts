// Talking to the AfriSearch API: sign-in token, current workspace, streaming and uploads.
import { readLines } from "./ndjson";
import type { StreamEvent, UploadResult } from "./types";

let getToken: () => Promise<string | null> = async () => null;
let workspaceId: string | null = null;

/** Called by the auth provider: how to get the current access token. */
export function setTokenGetter(getter: () => Promise<string | null>) {
  getToken = getter;
}

/** Called by the workspace provider: every request is scoped to this workspace. */
export function setWorkspaceId(id: string | null) {
  workspaceId = id;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export async function authHeaders(): Promise<Record<string, string>> {
  const headers: Record<string, string> = {};
  const token = await getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (workspaceId) headers["X-Workspace-Id"] = workspaceId;
  return headers;
}

async function errorFrom(response: Response): Promise<ApiError> {
  let detail = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) detail = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    // not JSON; keep the status text
  }
  return new ApiError(detail, response.status);
}

export async function api<T>(path: string, options: { method?: string; json?: unknown; signal?: AbortSignal } = {}): Promise<T> {
  const headers = await authHeaders();
  if (options.json !== undefined) headers["Content-Type"] = "application/json";
  let response: Response;
  try {
    response = await fetch(`/api${path}`, {
      method: options.method ?? (options.json !== undefined ? "POST" : "GET"),
      headers,
      body: options.json !== undefined ? JSON.stringify(options.json) : undefined,
      signal: options.signal,
    });
  } catch (error) {
    if ((error as Error).name === "AbortError") throw error;
    throw new ApiError("Can't reach the AfriSearch server. Check your connection.", 0);
  }
  if (!response.ok) throw await errorFrom(response);
  return response.json() as Promise<T>;
}

/** POST /api/ask/stream and yield its events as they arrive. */
export async function* streamAsk(body: Record<string, unknown>, signal: AbortSignal): AsyncGenerator<StreamEvent> {
  const headers = { ...(await authHeaders()), "Content-Type": "application/json" };
  const response = await fetch("/api/ask/stream", { method: "POST", headers, body: JSON.stringify(body), signal });
  if (!response.ok || !response.body) throw await errorFrom(response);
  for await (const line of readLines(response.body)) {
    yield JSON.parse(line) as StreamEvent;
  }
}

/** Upload files with progress (fetch can't report upload progress, XHR can). */
export async function uploadFiles(files: File[], onProgress: (fraction: number) => void): Promise<UploadResult> {
  const headers = await authHeaders();
  const form = new FormData();
  files.forEach((file) => form.append("files", file, file.name));
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/documents/upload");
    Object.entries(headers).forEach(([name, value]) => xhr.setRequestHeader(name, value));
    xhr.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total);
    xhr.onload = () => {
      let body: { detail?: string } & UploadResult;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        return reject(new ApiError(`Upload failed (${xhr.status}).`, xhr.status));
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new ApiError(typeof body.detail === "string" ? body.detail : `Upload failed (${xhr.status}).`, xhr.status));
    };
    xhr.onerror = () => reject(new ApiError("Upload failed: can't reach the server.", 0));
    xhr.send(form);
  });
}

/** Download a file from the API (with the sign-in token) under the given name. */
export async function downloadFile(path: string, filename: string) {
  const response = await fetch(`/api${path}`, { headers: await authHeaders() });
  if (!response.ok) throw await errorFrom(response);
  const url = URL.createObjectURL(await response.blob());
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Open an uploaded document in a new tab, at a page for PDFs. */
export async function openDocument(sourceId: string, page?: number | null) {
  // Open the tab right away (inside the click), or popup blockers stop it.
  const tab = window.open("about:blank", "_blank");
  try {
    const response = await fetch(`/api/documents/${encodeURIComponent(sourceId)}/file`, { headers: await authHeaders() });
    if (!response.ok) throw await errorFrom(response);
    const url = URL.createObjectURL(await response.blob());
    const target = page ? `${url}#page=${page}` : url;
    if (tab) tab.location.href = target;
    else window.open(target, "_blank");
  } catch (error) {
    tab?.close();
    throw error;
  }
}
