import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:5000";

const nextConfig: NextConfig = {
  output: "standalone",
  // Browser calls /api/* on the same origin; Next forwards them to Flask, so session
  // cookies stay first-party and no CORS is needed in the browser.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  poweredByHeader: false,
};

export default nextConfig;
