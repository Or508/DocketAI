import { NextResponse } from "next/server";

import { clientIpHeaders } from "@/lib/server/client-ip";
import { sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Public account links: joining an office by invitation and choosing a new password.
// No office session is needed or sent. The link's token travels in the JSON body.
const ALLOWED = new Set(["link", "invite/accept", "password/forgot", "password/reset"]);
const NO_STORE = { "Cache-Control": "no-store" };

export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const joined = (path ?? []).join("/");
  if (!ALLOWED.has(joined)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
  }
  if (!sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: NO_STORE });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/account/${joined}`, {
      method: "POST",
      headers: clientIpHeaders(request, { "Content-Type": "application/json" }),
      body: await request.text(),
      cache: "no-store",
    });
    const headers = new Headers(NO_STORE);
    const type = upstream.headers.get("content-type");
    if (type) headers.set("Content-Type", type);
    return new NextResponse(upstream.status === 204 ? null : upstream.body, { status: upstream.status, headers });
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות המשרד." }, { status: 502, headers: NO_STORE });
  }
}
