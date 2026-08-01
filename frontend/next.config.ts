import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Emits .next/standalone with only the traced dependencies, so the Docker
  // runtime image ships the server bundle instead of all of node_modules.
  output: "standalone",
};

export default nextConfig;
