import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const ACTION = /^[a-z_]{1,64}$/;

/** The office's audit trail across its cases. Only the three known filters go upstream. */
export async function GET(request: Request) {
  const token = (await cookies()).get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: NO_STORE });
  }
  const incoming = new URL(request.url).searchParams;
  const outgoing = new URLSearchParams();
  const action = incoming.get("action") ?? "";
  if (ACTION.test(action)) outgoing.set("action", action);
  const q = (incoming.get("q") ?? "").trim().slice(0, 120);
  if (q) outgoing.set("q", q);
  const limit = Number.parseInt(incoming.get("limit") ?? "", 10);
  if (Number.isInteger(limit) && limit >= 1 && limit <= 500) outgoing.set("limit", String(limit));

  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const query = outgoing.toString();
  try {
    const upstream = await fetch(`${base}/audit${query ? `?${query}` : ""}`, {
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
