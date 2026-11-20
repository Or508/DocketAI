import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { OFFICE_COOKIE, officeCookieOptions, sameOrigin } from "@/lib/server/office-session";

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
  if (
    joined === "auth/me" ||
    joined === "auth/security" ||
    joined === "auth/password" ||
    joined === "auth/mfa/setup" ||
    joined === "auth/mfa/enable" ||
    joined === "auth/mfa/disable" ||
    joined === "auth/mfa/recovery-codes" ||
    joined === "organization" ||
    joined === "organization/profession" ||
    joined === "organization/ai-reading" ||
    // WhatsApp reminders that are due, for the office to send by hand.
    joined === "outreach/due"
  ) {
    return true;
  }
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
  if (request.method !== "GET" && request.method !== "HEAD" && !sameOrigin(request)) {
    return NextResponse.json({ detail: "Forbidden", code: "forbidden" }, { status: 403, headers: { "Cache-Control": "no-store" } });
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
    if (disposition) {
      const inline = new URL(request.url).searchParams.get("view") === "1";
      responseHeaders.set("Content-Disposition", inline ? disposition.replace(/^attachment/i, "inline") : disposition);
    }
    responseHeaders.set("Cache-Control", "no-store");
    if (upstream.status === 401) {
      const text = await upstream.text();
      let clearCookie = true;
      try {
        const parsed = JSON.parse(text) as { detail?: unknown };
        if (parsed.detail === "The current password is incorrect.") clearCookie = false;
      } catch {
        clearCookie = true;
      }
      const response = new NextResponse(text, { status: 401, headers: responseHeaders });
      if (clearCookie) response.cookies.set(OFFICE_COOKIE, "", officeCookieOptions(0));
      return response;
    }
    const response = new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders });
    return response;
  } catch {
    return NextResponse.json(
      { detail: "לא ניתן להגיע לשירות המשרד." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
