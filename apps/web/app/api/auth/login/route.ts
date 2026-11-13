import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: await request.text(),
      cache: "no-store",
    });
    if (!upstream.ok) {
      return NextResponse.json(
        { detail: "Email or password is incorrect." },
        { status: upstream.status, headers: { "Cache-Control": "no-store" } },
      );
    }
    const data = (await upstream.json()) as { token: string; expires_at: string; user: unknown };
    const maxAge = Math.max(0, Math.floor((new Date(data.expires_at).getTime() - Date.now()) / 1000));
    const response = NextResponse.json({ user: data.user }, { headers: { "Cache-Control": "no-store" } });
    response.cookies.set(OFFICE_COOKIE, data.token, officeCookieOptions(maxAge));
    return response;
  } catch {
    return NextResponse.json(
      { detail: "לא ניתן להגיע לשירות המשרד." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
