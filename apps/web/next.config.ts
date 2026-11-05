import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@docketai/shared-types"],
  serverExternalPackages: ["pdfjs-dist"],
};

export default nextConfig;
