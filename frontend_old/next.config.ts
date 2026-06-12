import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Rewrites: /api/* → backend (avoids CORS issues in same-origin deployments)
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/:path*`,
      },
    ];
  },

  // Allow images from any https source (charts, user avatars, etc.)
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**" },
    ],
  },

  // Strict React mode for better error catching in dev
  reactStrictMode: true,
};

export default nextConfig;
