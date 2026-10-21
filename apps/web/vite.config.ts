import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const env = (globalThis as { process?: { env?: Record<string, string | undefined> } }).process
  ?.env;

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: env?.VITE_API_PROXY_TARGET ?? "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
