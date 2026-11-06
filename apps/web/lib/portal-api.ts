import type { ChatRequest, FieldUpdateRequest, PortalSignRequest, PortalView } from "@docketai/shared-types";

import { ApiError, detailFrom, readEventStream } from "@/lib/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers, cache: "no-store" });
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

function root(token: string) {
  return `/api/portal/${encodeURIComponent(token)}`;
}

export const portalApi = {
  view: (token: string) => request<PortalView>(root(token)),
  setField: (token: string, key: string, value: string) => {
    const body: FieldUpdateRequest = { key, value };
    return request<PortalView>(`${root(token)}/fields`, { method: "POST", body: JSON.stringify(body) });
  },
  streamChat: (token: string, message: string, onDelta: (text: string) => void) => {
    const body: ChatRequest = { message };
    return readEventStream<PortalView>(`${root(token)}/chat/stream`, body, onDelta);
  },
  sign: (token: string, body: PortalSignRequest) =>
    request<PortalView>(`${root(token)}/sign`, { method: "POST", body: JSON.stringify(body) }),
};

export function portalPreviewUrl(token: string) {
  return `${root(token)}/preview`;
}

export function portalDownloadUrl(token: string) {
  return `${root(token)}/signed-document`;
}
