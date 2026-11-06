import type { NextConfig } from "next";

const privateHeaders = [
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "X-Robots-Tag", value: "noindex" },
  { key: "Cache-Control", value: "no-store" },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@docketai/shared-types"],
  serverExternalPackages: ["pdfjs-dist"],
  async headers() {
    return [
      { source: "/sign/:path*", headers: privateHeaders },
      { source: "/api/portal/:path*", headers: privateHeaders },
      { source: "/login", headers: privateHeaders },
      { source: "/api/office/:path*", headers: privateHeaders },
      { source: "/api/auth/:path*", headers: privateHeaders },
    ];
  },
};

export default nextConfig;
