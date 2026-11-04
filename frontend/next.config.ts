import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Bundles just what the server needs, so the Docker image stays small.
  output: "standalone",
};

export default nextConfig;
