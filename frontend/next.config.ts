import type { NextConfig } from "next";

// Vercel sets VERCEL=1 during its builds and packages the app itself. The
// standalone output and pinned tracing root exist for the Docker image
// (frontend/Dockerfile copies .next/standalone); forcing them on Vercel breaks
// its packaging step after an otherwise successful build.
const onVercel = Boolean(process.env.VERCEL);

const nextConfig: NextConfig = {
  ...(onVercel
    ? {}
    : {
        output: "standalone" as const,
        outputFileTracingRoot: process.cwd(),
        turbopack: { root: process.cwd() },
      }),
  poweredByHeader: false,
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
