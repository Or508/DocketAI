import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: { "Cache-Control": "no-store" } });
  }
  const jar = await cookies();
  const token = jar.get(OFFICE_COOKIE)?.value;
  if (token) {
    const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
    try {
      await fetch(`${base}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
      });
    } catch {
      // The cookie is cleared even when the API cannot be reached.
    }
  }
  const response = new NextResponse(null, { status: 204, headers: { "Cache-Control": "no-store" } });
  response.cookies.set(OFFICE_COOKIE, "", officeCookieOptions(0));
  return response;
}
