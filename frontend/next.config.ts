import type { NextConfig } from "next";

const apiBackend = process.env.API_BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  experimental: {
    cpus: 1,
    proxyClientMaxBodySize: "60mb",
    workerThreads: true,
  },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${apiBackend}/api/v1/:path*` }];
  },
};

export default nextConfig;
