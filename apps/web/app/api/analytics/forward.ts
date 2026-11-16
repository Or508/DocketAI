import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions } from "@/lib/server/office-session";

const NO_STORE = { "Cache-Control": "no-store" };

/** Read one office analytics resource from the API with the caller's office session. */
export async function forwardAnalytics(path: "summary" | "export.csv"): Promise<Response> {
  const token = (await cookies()).get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: NO_STORE });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/analytics/${path}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    });
    const headers = new Headers(NO_STORE);
    headers.set("Content-Type", upstream.headers.get("content-type") ?? "application/json");
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) headers.set("Content-Disposition", disposition);
    // Bytes, not text: the report starts with a BOM that must reach the browser untouched.
    const response = new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers });
    if (upstream.status === 401) response.cookies.set(OFFICE_COOKIE, "", officeCookieOptions(0));
    return response;
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות המשרד." }, { status: 502, headers: NO_STORE });
  }
}
