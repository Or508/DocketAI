import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PROCESS = /^[a-z0-9_]{1,64}$/;
const MAX_BODY_BYTES = 1024;

/** Open a new case for an existing client, reusing the documents the office already holds. */
export async function POST(request: Request) {
  const token = (await cookies()).get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: NO_STORE });
  }
  if (!sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: NO_STORE });
  }
  const raw = await request.text();
  let payload: { source_case_id?: unknown; process_type?: unknown } = {};
  try {
    if (raw.length <= MAX_BODY_BYTES) payload = JSON.parse(raw) as typeof payload;
  } catch {
    payload = {};
  }
  const source = typeof payload.source_case_id === "string" ? payload.source_case_id : "";
  const processType = typeof payload.process_type === "string" ? payload.process_type : "";
  if (!UUID.test(source) || !PROCESS.test(processType)) {
    return NextResponse.json({ detail: "הבקשה אינה תקינה." }, { status: 400, headers: NO_STORE });
  }

  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/clients/quick-case`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      // Only the two known fields go upstream.
      body: JSON.stringify({ source_case_id: source, process_type: processType }),
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
