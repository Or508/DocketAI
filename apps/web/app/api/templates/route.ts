import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };

export async function GET() {
  const token = (await cookies()).get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: NO_STORE });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/templates`, {
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
