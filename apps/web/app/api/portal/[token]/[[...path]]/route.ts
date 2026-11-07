import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ALLOWED: Record<string, Set<string>> = {
  GET: new Set(["", "preview", "signed-document", "certificate"]),
  POST: new Set(["fields", "chat/stream", "sign"]),
};

async function proxy(request: Request, context: { params: Promise<{ token: string; path?: string[] }> }) {
  const { token, path } = await context.params;
  const joined = (path ?? []).join("/");
  if (!ALLOWED[request.method]?.has(joined)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const target = joined ? `${base}/portal/${joined}` : `${base}/portal`;
  try {
    const headers = new Headers();
    headers.set("Authorization", `Bearer ${token}`);
    headers.set("X-Portal-Client-Ip", rightmostForwarded(request.headers.get("x-forwarded-for")));
    headers.set("X-Portal-User-Agent", request.headers.get("user-agent") ?? "");
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers,
      cache: "no-store",
    };
    if (request.method !== "GET" && request.method !== "HEAD") {
      init.body = request.body;
      init.duplex = "half";
    }
    const upstream = await fetch(target, init);
    const responseHeaders = new Headers();
    const type = upstream.headers.get("content-type");
    if (type) responseHeaders.set("Content-Type", type);
    const disposition = upstream.headers.get("content-disposition");
    if (disposition) responseHeaders.set("Content-Disposition", disposition);
    responseHeaders.set("Cache-Control", "no-store");
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return NextResponse.json(
      { detail: "The signing service could not be reached." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}

function rightmostForwarded(header: string | null): string {
  const parts = (header ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return parts.length > 0 ? parts[parts.length - 1] : "";
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
export const HEAD = proxy;
