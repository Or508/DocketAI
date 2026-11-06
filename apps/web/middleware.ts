import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import { OFFICE_COOKIE } from "@/lib/server/office-session";

export function middleware(request: NextRequest) {
  if (request.cookies.get(OFFICE_COOKIE)?.value) return NextResponse.next();
  const next = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  const login = new URL("/login", request.url);
  login.searchParams.set("next", next);
  return NextResponse.redirect(login);
}

export const config = {
  matcher: ["/", "/cases/:path*"],
};
