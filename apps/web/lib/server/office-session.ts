export const OFFICE_COOKIE = "docket_session";

// Browsers send Origin on cross-site POSTs, so a request without one is not a cross-site form.
export function sameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  if (!origin) return true;
  const expected = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  try {
    return Boolean(expected) && new URL(origin).host === expected;
  } catch {
    return false;
  }
}

export function officeCookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    path: "/",
    secure: process.env.NODE_ENV === "production",
    maxAge,
  };
}
