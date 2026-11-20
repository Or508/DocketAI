// The reverse proxy in front of this app appends the visitor's address last, so only the
// rightmost X-Forwarded-For entry is trusted. The API limits requests per this address.
export function forwardedClientIp(request: Request): string {
  const parts = (request.headers.get("x-forwarded-for") ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return parts.length > 0 ? parts[parts.length - 1] : "";
}

/** Headers for an upstream API call that carry the visitor's address and nothing the browser chose. */
export function clientIpHeaders(request: Request, extra: Record<string, string> = {}): Record<string, string> {
  return { ...extra, "X-Client-Ip": forwardedClientIp(request) };
}
