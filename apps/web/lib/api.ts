import type {
  CaseRead,
  CaseWorkspace,
  ChatRequest,
  DocumentRoleRead,
  FieldUpdateRequest,
  FillReport,
  IntakeSummary,
  ProcessRead,
  SigningLinkCreated,
  SigningLinkRead,
  StreamError,
  UploadResult,
} from "@docketai/shared-types";

const base = "/api/office";

function redirectToLogin() {
  if (typeof window === "undefined") return;
  const next = `${window.location.pathname}${window.location.search}`;
  window.location.assign(`/login?next=${encodeURIComponent(next)}`);
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function detailFrom(body: unknown): string {
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
    if (response.status === 401 && message !== "The current password is incorrect.") redirectToLogin();
    throw new ApiError(message || "Request failed", response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface OfficeProfile {
  id: string;
  email: string;
  display_name: string;
  organization_id: string;
  organization_name: string;
  profession: string;
  profession_label_he: string;
  client_term_he: string;
  case_term_he: string;
}

export interface ProfessionOption {
  key: string;
  label_he: string;
  client_term_he: string;
  case_term_he: string;
}

export interface OrganizationProfile {
  name: string;
  profession: ProfessionOption;
  ai_reading_enabled: boolean;
  professions: ProfessionOption[];
}

export interface SecurityStatus {
  mfa_enabled: boolean;
  recovery_codes_left: number;
  min_password_length: number;
}

export interface MfaSetup {
  secret: string;
  otpauth_uri: string;
}

export type OutreachPurpose = "intake" | "signing";
export type OutreachChannel = "email" | "whatsapp";

export interface OutreachMessage {
  id: string;
  purpose: OutreachPurpose;
  kind: "first" | "reminder";
  channel: OutreachChannel;
  recipient: string;
  status: "sent" | "failed" | "handed_to_office";
  error: string | null;
  created_at: string;
}

export interface OutreachSent {
  message: OutreachMessage;
  url: string;
  whatsapp_url: string | null;
  next_reminder_at: string | null;
}

export interface OutreachState {
  email: string | null;
  phone: string | null;
  phone_display: string | null;
  purpose: OutreachPurpose | null;
  channel: OutreachChannel | null;
  reminders_enabled: boolean;
  reminders_sent: number;
  next_reminder_at: string | null;
  stopped_reason: string | null;
  email_available: boolean;
  messages: OutreachMessage[];
}

export interface DueReminder {
  case_id: string;
  case_name: string;
  client_name: string | null;
  purpose: OutreachPurpose;
  phone_display: string;
  due_at: string;
}

export interface OutreachSendBody {
  purpose: OutreachPurpose;
  channel: OutreachChannel;
  email?: string;
  phone?: string;
  reminders: boolean;
}

export const api = {
  me: () => request<OfficeProfile>("/auth/me"),
  organization: () => request<OrganizationProfile>("/organization"),
  setProfession: (profession: string) =>
    request<OrganizationProfile>("/organization/profession", { method: "PUT", body: JSON.stringify({ profession }) }),
  setAiReading: (enabled: boolean) =>
    request<OrganizationProfile>("/organization/ai-reading", { method: "PUT", body: JSON.stringify({ enabled }) }),
  security: () => request<SecurityStatus>("/auth/security"),
  changePassword: (current_password: string, new_password: string) =>
    request<void>("/auth/password", { method: "POST", body: JSON.stringify({ current_password, new_password }) }),
  mfaSetup: () => request<MfaSetup>("/auth/mfa/setup", { method: "POST" }),
  mfaEnable: (code: string) =>
    request<{ recovery_codes: string[] }>("/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) }),
  mfaDisable: (password: string, code: string) =>
    request<void>("/auth/mfa/disable", { method: "POST", body: JSON.stringify({ password, code }) }),
  mfaRecoveryCodes: (password: string, code: string) =>
    request<{ recovery_codes: string[] }>("/auth/mfa/recovery-codes", { method: "POST", body: JSON.stringify({ password, code }) }),
  processes: (profession?: string) =>
    request<ProcessRead[]>(profession ? `/processes?profession=${encodeURIComponent(profession)}` : "/processes"),
  cases: () => request<CaseRead[]>("/cases"),
  createCase: (body: { name: string; process_key: string; client_name?: string }) =>
    request<CaseRead>("/cases", { method: "POST", body: JSON.stringify(body) }),
  workspace: (caseId: string) => request<CaseWorkspace>(`/cases/${caseId}`),
  upload: (
    caseId: string,
    files: File[],
    options?: { documentType?: string; role?: "form" | "evidence"; replaceExisting?: boolean },
  ) => {
    const body = new FormData();
    for (const file of files) body.append("files", file, file.name);
    if (options?.documentType) body.append("document_type", options.documentType);
    if (options?.role) body.append("role", options.role);
    body.append("replace_existing", options?.replaceExisting ? "true" : "false");
    return request<UploadResult>(`/cases/${caseId}/upload`, { method: "POST", body });
  },
  deleteDocument: (caseId: string, documentId: string) =>
    request<CaseWorkspace>(`/cases/${caseId}/documents/${documentId}`, { method: "DELETE" }),
  classify: (caseId: string, documentId: string, documentType: string) =>
    request<CaseWorkspace>(`/cases/${caseId}/classify-manual`, {
      method: "POST",
      body: JSON.stringify({ document_id: documentId, document_type: documentType }),
    }),
  chat: (caseId: string, message: string) => {
    const body: ChatRequest = { message };
    return request<CaseWorkspace>(`/cases/${caseId}/chat`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  streamChat: (caseId: string, message: string, onDelta: (text: string) => void) =>
    readChatStream(caseId, message, onDelta),
  setField: (caseId: string, key: string, value: string) => {
    const body: FieldUpdateRequest = { key, value };
    return request<CaseWorkspace>(`/cases/${caseId}/fields`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },
  sign: (caseId: string, signaturePngBase64: string) =>
    request<CaseWorkspace>(`/cases/${caseId}/fill-and-sign`, {
      method: "POST",
      body: JSON.stringify({ signature_png_base64: signaturePngBase64, field_values: {}, consent: true }),
    }),
  createSigningLink: (caseId: string) =>
    request<SigningLinkCreated>(`/cases/${caseId}/signing-links`, { method: "POST" }),
  signingLink: (caseId: string) => request<SigningLinkRead>(`/cases/${caseId}/signing-link`),
  revokeSigningLink: (caseId: string) =>
    request<void>(`/cases/${caseId}/signing-link`, { method: "DELETE" }),
  reopenCase: (caseId: string) => request<CaseWorkspace>(`/cases/${caseId}/reopen`, { method: "POST" }),
  loadDefaultForm: (caseId: string) => request<CaseWorkspace>(`/cases/${caseId}/load-default-form`, { method: "POST" }),
  timeline: (caseId: string) => request<unknown>(`/cases/${caseId}/timeline`),
  intake: (caseId: string) => request<IntakeSummary>(`/cases/${caseId}/intake`),
  outreach: (caseId: string) => request<OutreachState>(`/cases/${caseId}/outreach`),
  sendOutreach: (caseId: string, body: OutreachSendBody) =>
    request<OutreachSent>(`/cases/${caseId}/outreach/send`, { method: "POST", body: JSON.stringify(body) }),
  setOutreachReminders: (caseId: string, enabled: boolean) =>
    request<OutreachState>(`/cases/${caseId}/outreach/reminders`, {
      method: "PUT",
      body: JSON.stringify({ enabled }),
    }),
  remindOutreach: (caseId: string) => request<OutreachSent>(`/cases/${caseId}/outreach/remind`, { method: "POST" }),
  dueOutreach: () => request<DueReminder[]>("/outreach/due"),
  fillReport: (caseId: string, documentId: string) =>
    request<FillReport>(`/cases/${caseId}/documents/${documentId}/fill-report`),
  setDocumentRole: (caseId: string, documentId: string, role: "evidence" | "form", displayTitle?: string) =>
    request<DocumentRoleRead>(`/cases/${caseId}/documents/${documentId}/role`, {
      method: "PUT",
      body: JSON.stringify({ role, display_title: displayTitle ?? null }),
    }),
};

export function signedDocumentUrl(caseId: string) {
  return `${base}/cases/${caseId}/signed-document`;
}

export function certificateUrl(caseId: string) {
  return `${base}/cases/${caseId}/certificate`;
}

export async function downloadCaseArchive(caseId: string, filename: string) {
  const response = await fetch(`${base}/cases/${caseId}/archive`, { cache: "no-store" });
  if (response.status === 401) redirectToLogin();
  if (!response.ok) {
    let message = response.statusText;
    try {
      message = detailFrom(await response.json());
    } catch {
      message = response.statusText;
    }
    throw new ApiError(message || "Request failed", response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function documentFileUrl(caseId: string, documentId: string) {
  return `${base}/cases/${caseId}/documents/${documentId}/file`;
}

export function filledFormUrl(caseId: string, documentId: string) {
  return `${base}/cases/${caseId}/documents/${documentId}/filled-preview`;
}

async function readChatStream(
  caseId: string,
  message: string,
  onDelta: (text: string) => void,
): Promise<CaseWorkspace> {
  const body: ChatRequest = { message };
  try {
    return await readEventStream<CaseWorkspace>(`${base}/cases/${caseId}/chat/stream`, body, onDelta);
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) redirectToLogin();
    throw error;
  }
}

export async function readEventStream<T>(
  url: string,
  body: unknown,
  onDelta: (text: string) => void,
): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
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
  let result: T | null = null;
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
      if (event === "replace") {
        assembled = JSON.parse(data) as string;
        onDelta(assembled);
      }
      if (event === "error") {
        throw new ApiError((JSON.parse(data) as StreamError).detail, 502);
      }
      if (event === "workspace") result = JSON.parse(data) as T;
    }
  }
  if (!result) throw new ApiError("The clerk did not finish the reply.", 502);
  return result;
}
