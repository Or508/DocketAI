import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions } from "@/lib/server/office-session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function rightmostForwarded(header: string | null): string {
  const parts = (header ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return parts.length > 0 ? parts[parts.length - 1] : "";
}

function encodedSegments(raw: string[]): string[] | null {
  const decoded: string[] = [];
  for (const segment of raw) {
    try {
      decoded.push(decodeURIComponent(segment));
    } catch {
      return null;
    }
  }
  for (const segment of decoded) {
    if (segment === ".." || segment === "." || segment.includes("/") || segment.includes("\\")) return null;
  }
  return decoded.map((segment) => encodeURIComponent(segment));
}

function allowed(segments: string[]): boolean {
  const joined = segments.join("/");
  if (joined === "auth/me") return true;
  return segments[0] === "cases" || segments[0] === "processes";
}

export async function GET(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
export async function POST(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
export async function PUT(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
export async function PATCH(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
export async function DELETE(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
export async function HEAD(request: Request, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

async function proxy(request: Request, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const segments = encodedSegments(path ?? []);
  if (segments === null || !allowed(segments)) {
    return NextResponse.json({ detail: "Not found" }, { status: 404, headers: { "Cache-Control": "no-store" } });
  }
  const jar = await cookies();
  const token = jar.get(OFFICE_COOKIE)?.value;
  if (!token) {
    return NextResponse.json({ detail: "Sign in required.", code: "unauthenticated" }, { status: 401, headers: { "Cache-Control": "no-store" } });
  }
  if (request.method === "POST" || request.method === "PUT" || request.method === "PATCH" || request.method === "DELETE") {
    const origin = request.headers.get("origin");
    if (origin) {
      const expected = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
      let originHost = "";
      try {
        originHost = new URL(origin).host;
      } catch {
        originHost = "";
      }
      if (!expected || originHost !== expected) {
        return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: { "Cache-Control": "no-store" } });
      }
    }
  }
  const base = process.env.API_INTERNAL_URL ?? "http://127.0.0.1:8000";
  const search = new URL(request.url).search;
  const target = `${base}/${segments.join("/")}${search}`;
  try {
    const headers = new Headers();
    headers.set("Authorization", `Bearer ${token}`);
    const contentType = request.headers.get("content-type");
    if (contentType) headers.set("Content-Type", contentType);
    headers.set("X-Office-Client-Ip", rightmostForwarded(request.headers.get("x-forwarded-for")));
    headers.set("X-Office-User-Agent", request.headers.get("user-agent") ?? "");
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
    const response = new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
    if (upstream.status === 401) response.cookies.set(OFFICE_COOKIE, "", officeCookieOptions(0));
    return response;
  } catch {
    return NextResponse.json(
      { detail: "The office service could not be reached." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
