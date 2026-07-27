import path from "node:path";
import type { NextConfig } from "next";

// `NEXT_PUBLIC_*` values are inlined into the client bundle at BUILD time, so a
// production build that runs without NEXT_PUBLIC_API_BASE_URL bakes in the
// development fallback (localhost) permanently — setting the variable on the
// server afterwards changes nothing. The failure mode is silent and total:
// every API call from the deployed page goes to an origin that isn't there.
//
// Fail the build instead. This is the only point where the mistake is
// recoverable.
if (process.env.NODE_ENV === "production" && !process.env.NEXT_PUBLIC_API_BASE_URL) {
  throw new Error(
    "NEXT_PUBLIC_API_BASE_URL must be set for a production build.\n" +
      "It is inlined into the client bundle at build time, so it cannot be " +
      "supplied later at runtime.\n" +
      "Example: NEXT_PUBLIC_API_BASE_URL=https://api.hsatedu.in npm run build",
  );
}

const nextConfig: NextConfig = {
  // Pin the Turbopack workspace root to this directory.
  // Without this, Next infers the root by walking up to the outermost
  // lockfile. A stray package-lock.json in the repo root made it infer
  // /home/paardhu/Projects/qp-gen, so the file watcher covered backend/,
  // .git/ and every node_modules in the monorepo (~69k files) instead of
  // just the frontend — producing sustained ~200% CPU and ~26 MB/s of
  // cache rewrites while the dev server sat idle.
  turbopack: {
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
