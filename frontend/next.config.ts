import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Required for Docker deployment — produces a standalone Node.js server
  // that doesn't need node_modules at runtime.
  output: "standalone",
  // Disable the bottom-left Next.js build indicator in development
  devIndicators: {
    appIsrStatus: false,
    buildActivity: false,
  },
};

export default nextConfig;
