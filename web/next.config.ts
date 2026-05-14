import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "**.primor.eu" },
      { protocol: "https", hostname: "**.sephora.fr" },
      { protocol: "https", hostname: "**.nocibe.fr" },
      { protocol: "https", hostname: "rcm.frizbit.com" },
      { protocol: "https", hostname: "**.ltwebstatic.com" },
      { protocol: "https", hostname: "image.nocibe.com" },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
