import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/health": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://api:8000",
        changeOrigin: true,
      },
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET ?? "http://api:8000",
        changeOrigin: true,
      },
    },
  },
});
