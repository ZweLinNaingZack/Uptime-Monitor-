import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The Docker image sets NEXT_OUTPUT=standalone. The build then copies only the files the
  // server really needs into .next/standalone, so the image doesn't ship all of
  // node_modules. Local builds skip it: `next start` doesn't use it, and on Windows it may
  // need extra permissions to create symlinks.
  output: process.env.NEXT_OUTPUT === "standalone" ? "standalone" : undefined,
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
