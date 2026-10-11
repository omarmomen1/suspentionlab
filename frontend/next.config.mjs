/** @type {import('next').NextConfig} */
const nextConfig = {
  async redirects() {
    return [
      {
        source: "/login",
        destination: "/auth/login",
        permanent: false,
      },
    ];
  },

  // Rewrites: /api/* +' backend (avoids CORS issues in same-origin deployments)
  async rewrites() {
    const apiBase = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
    ];
  },

  // Allow images only from trusted external hostnames.
  // FIXED: Wildcard hostname "**" was an SSRF vector — the Next.js image optimizer
  // would proxy requests to any HTTPS host including internal network addresses.
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "avatars.githubusercontent.com" },
      { protocol: "https", hostname: "lh3.googleusercontent.com" },
      { protocol: "https", hostname: "www.gravatar.com" },
      { protocol: "https", hostname: "assets.lemonsqueezy.com" },
    ],
  },

  // Strict React mode for better error catching in dev
  reactStrictMode: true,
  swcMinify: true,

  // Zero Source Map Exposure in production builds
  productionBrowserSourceMaps: false,
  output: "standalone",

  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion", "three"],
  },
};

export default nextConfig;
