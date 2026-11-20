import type { NextConfig } from "next";

const privateHeaders = [
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Robots-Tag", value: "noindex" },
  { key: "Cache-Control", value: "no-store" },
];

// Every page and route. Another site may not frame these pages, so it cannot lay a decoy over the
// signing screen (clickjacking). Same-origin frames stay allowed: the office previews PDFs in one.
const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: "frame-ancestors 'self'; base-uri 'self'; object-src 'none'; form-action 'self'",
  },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()" },
  // Browsers honour this only over HTTPS, so it is inert on a local http run.
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
];

const nextConfig: NextConfig = {
  // A second server (a preview beside `next start`) builds into its own folder, never over .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactStrictMode: true,
  transpilePackages: ["@docketai/shared-types"],
  serverExternalPackages: ["pdfjs-dist"],
  async headers() {
    // Later entries win for the same header, so the private routes keep `no-referrer`.
    return [
      { source: "/:path*", headers: securityHeaders },
      { source: "/sign/:path*", headers: privateHeaders },
      { source: "/api/portal/:path*", headers: privateHeaders },
      { source: "/login", headers: privateHeaders },
      { source: "/api/office/:path*", headers: privateHeaders },
      { source: "/api/auth/:path*", headers: privateHeaders },
    ];
  },
};

export default nextConfig;
