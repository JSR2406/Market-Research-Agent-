import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Pin the tracing root to this frontend, ignoring a stray lockfile one level up.
  outputFileTracingRoot: path.join(process.cwd()),
};

export default nextConfig;
