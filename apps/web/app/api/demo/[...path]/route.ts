import { NextResponse } from "next/server";

import { clientIpHeaders } from "@/lib/server/client-ip";
import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

function apiBase() {
  return process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if ((path ?? []).join("/") !== "info") {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
  }
  try {
    const upstream = await fetch(`${apiBase()}/demo/info`, {
      headers: clientIpHeaders(request),
      cache: "no-store",
    });
    const headers = new Headers(NO_STORE);
    const type = upstream.headers.get("content-type");
    if (type) headers.set("Content-Type", type);
    return new NextResponse(upstream.body, { status: upstream.status, headers });
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות המשרד." }, { status: 502, headers: NO_STORE });
  }
}

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if ((path ?? []).join("/") !== "start") {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
  }
  if (!sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: NO_STORE });
  }
  try {
    const upstream = await fetch(`${apiBase()}/demo/start`, {
      method: "POST",
      headers: clientIpHeaders(request, { "Content-Type": "application/json" }),
      body: await request.text(),
      cache: "no-store",
    });
    const failure = (await upstream.json().catch(() => null)) as {
      token?: string;
      expires_at?: string;
      user?: unknown;
      detail?: unknown;
    } | null;
    if (!upstream.ok || !failure?.token || !failure.expires_at) {
      const detail = typeof failure?.detail === "string" ? failure.detail : "הפעולה לא הצליחה. נסו שוב.";
      return NextResponse.json({ detail }, { status: upstream.ok ? 502 : upstream.status, headers: NO_STORE });
    }
    const maxAge = Math.max(0, Math.floor((new Date(failure.expires_at).getTime() - Date.now()) / 1000));
    const response = NextResponse.json({ user: failure.user }, { headers: NO_STORE });
    response.cookies.set(OFFICE_COOKIE, failure.token, officeCookieOptions(maxAge));
    return response;
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות המשרד." }, { status: 502, headers: NO_STORE });
  }
}
