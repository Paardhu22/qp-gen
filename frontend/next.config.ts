import path from "node:path";
import type { NextConfig } from "next";

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
