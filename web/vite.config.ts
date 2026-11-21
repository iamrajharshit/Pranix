// SPDX-License-Identifier: AGPL-3.0-only
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// In development the API runs on :8000 (uvicorn); Vite proxies API calls to it.
const api = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/v1": api, "/version": api, "/healthz": api, "/readyz": api },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 400 },
  test: { environment: "jsdom", globals: true, exclude: ["e2e/**", "node_modules/**"] },
});
