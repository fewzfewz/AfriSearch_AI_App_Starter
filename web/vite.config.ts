/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs separately (uvicorn on :8000); Vite forwards /api to it.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.AFRISEARCH_API_URL ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  test: { environment: "node" },
});
