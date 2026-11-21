// The visitor's address, which the API uses for rate limits, login lockouts and the signing certificate.
//
// Default: the rightmost X-Forwarded-For entry. That is right behind a proxy that appends the real
// visitor last (Caddy in deploy/, nginx). On Render, Cloudflare sits in front and the rightmost entry is a
// Cloudflare address, so set CLIENT_IP_HEADER=cf-connecting-ip there: Cloudflare always overwrites that header.
function clientIpHeaderName(): string | null {
  const name = (process.env.CLIENT_IP_HEADER ?? "").trim().toLowerCase();
  return name.length > 0 ? name : null;
}

export function rightmostForwarded(header: string | null): string {
  const parts = (header ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => item.length > 0);
  return parts.length > 0 ? parts[parts.length - 1] : "";
}

export function forwardedClientIp(request: Request): string {
  const name = clientIpHeaderName();
  if (name) {
    // A single address is expected; keep only the first if a proxy ever sends a list.
    return (request.headers.get(name) ?? "").split(",")[0].trim();
  }
  return rightmostForwarded(request.headers.get("x-forwarded-for"));
}

/** Headers for an upstream API call that carry the visitor's address and nothing the browser chose. */
export function clientIpHeaders(request: Request, extra: Record<string, string> = {}): Record<string, string> {
  return { ...extra, "X-Client-Ip": forwardedClientIp(request) };
}
