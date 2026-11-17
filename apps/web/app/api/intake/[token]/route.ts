import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE = { "Cache-Control": "no-store" };
const TOKEN = /^[A-Za-z0-9_-]{20,128}$/;

/**
 * Public: what the client's intake link shows. The token in the path is the only credential,
 * and no office session is sent upstream.
 */
export async function GET(_request: Request, context: { params: Promise<{ token: string }> }) {
  const { token } = await context.params;
  if (!TOKEN.test(token)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: NO_STORE });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  try {
    const upstream = await fetch(`${base}/intake/${token}`, { cache: "no-store" });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { ...NO_STORE, "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return NextResponse.json({ detail: "לא ניתן להגיע לשירות." }, { status: 502, headers: NO_STORE });
  }
}
