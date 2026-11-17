import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Open a document intake link for the client of an unsigned case.
 * A new link replaces the one before it. The API answers 409 for a signed case.
 */
export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!UUID.test(id)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
  }
  const token = (await cookies()).get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: NO_STORE });
  }
  if (!sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: NO_STORE });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/cases/${id}/intake-link`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
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
