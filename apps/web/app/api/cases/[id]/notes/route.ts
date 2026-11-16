import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
// A note holds 2,000 characters; anything far past that is not a note.
const MAX_BODY_BYTES = 32 * 1024;

type Context = { params: Promise<{ id: string }> };

/** Internal office notes. Only an office session reaches these; there is no signer-side route. */
async function forward(request: Request, context: Context, body: string | null) {
  const { id } = await context.params;
  if (!UUID.test(id)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
  }
  const token = (await cookies()).get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: NO_STORE });
  }
  if (request.method !== "GET" && !sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: NO_STORE });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
    if (body !== null) headers["Content-Type"] = "application/json";
    const upstream = await fetch(`${base}/cases/${id}/notes`, {
      method: request.method,
      headers,
      body: body ?? undefined,
      cache: "no-store",
    });
    const response = new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { ...NO_STORE, "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
    if (upstream.status === 401) response.cookies.set(OFFICE_COOKIE, "", officeCookieOptions(0));
    return response;
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות המשרד." }, { status: 502, headers: NO_STORE });
  }
}

export async function GET(request: Request, context: Context) {
  return forward(request, context, null);
}

export async function POST(request: Request, context: Context) {
  const body = await request.text();
  if (body.length > MAX_BODY_BYTES) {
    return NextResponse.json({ detail: "ההערה ארוכה מדי." }, { status: 413, headers: NO_STORE });
  }
  return forward(request, context, body);
}
