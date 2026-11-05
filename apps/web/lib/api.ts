import type {
  CaseRead,
  CaseWorkspace,
  ProcessRead,
  UploadResult,
} from "@docketai/shared-types";

const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function detailFrom(body: unknown): string {
  if (!body || typeof body !== "object" || !("detail" in body)) return "Request failed";
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) return String(item.msg);
        return String(item);
      })
      .join(" ");
  }
  return "Request failed";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${base}${path}`, { ...init, headers, cache: "no-store" });
  if (!response.ok) {
    let message = response.statusText;
    try {
      message = detailFrom(await response.json());
    } catch {
      message = response.statusText;
    }
    throw new ApiError(message || "Request failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  processes: () => request<ProcessRead[]>("/processes"),
  cases: () => request<CaseRead[]>("/cases"),
  createCase: (body: { name: string; process_key: string; client_name?: string }) =>
    request<CaseRead>("/cases", { method: "POST", body: JSON.stringify(body) }),
  workspace: (caseId: string) => request<CaseWorkspace>(`/cases/${caseId}`),
  upload: (caseId: string, files: File[]) => {
    const body = new FormData();
    for (const file of files) body.append("files", file, file.name);
    return request<UploadResult>(`/cases/${caseId}/upload`, { method: "POST", body });
  },
  classify: (caseId: string, documentId: string, documentType: string) =>
    request<CaseWorkspace>(`/cases/${caseId}/classify-manual`, {
      method: "POST",
      body: JSON.stringify({ document_id: documentId, document_type: documentType }),
    }),
  chat: (caseId: string, message: string) =>
    request<CaseWorkspace>(`/cases/${caseId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  streamChat: (caseId: string, message: string, onDelta: (text: string) => void) =>
    readChatStream(caseId, message, onDelta),
  setField: (caseId: string, key: string, value: string) =>
    request<CaseWorkspace>(`/cases/${caseId}/fields`, {
      method: "POST",
      body: JSON.stringify({ key, value }),
    }),
  sign: (caseId: string, signaturePngBase64: string) =>
    request<CaseWorkspace>(`/cases/${caseId}/fill-and-sign`, {
      method: "POST",
      body: JSON.stringify({ signature_png_base64: signaturePngBase64, field_values: {} }),
    }),
};

export function signedDocumentUrl(caseId: string) {
  return `${base}/cases/${caseId}/signed-document`;
}

export function documentFileUrl(caseId: string, documentId: string) {
  return `${base}/cases/${caseId}/documents/${documentId}/file`;
}

async function readChatStream(
  caseId: string,
  message: string,
  onDelta: (text: string) => void,
): Promise<CaseWorkspace> {
  const response = await fetch(`${base}/cases/${caseId}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    cache: "no-store",
  });
  if (!response.ok) {
    let text = response.statusText;
    try {
      text = detailFrom(await response.json());
    } catch {
      text = response.statusText;
    }
    throw new ApiError(text || "Request failed", response.status);
  }
  if (!response.body) throw new ApiError("The clerk stream is empty.", 502);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assembled = "";
  let workspace: CaseWorkspace | null = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      if (!part.trim() || part.startsWith(":")) continue;
      const lines = part.split("\n");
      const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (event === "delta") {
        assembled += JSON.parse(data) as string;
        onDelta(assembled);
      }
      if (event === "workspace") workspace = JSON.parse(data) as CaseWorkspace;
    }
  }
  if (!workspace) throw new ApiError("The clerk did not finish the reply.", 502);
  return workspace;
}

export const apiBaseUrl = base;
