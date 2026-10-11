import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The FastAPI backend (backend/) — run `uvicorn app.main:app --port 8000`.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
      // Sanity's content API, so local dev needs no CORS setup.
      "/sanity": { target: "https://1lvtpppu.apicdn.sanity.io", changeOrigin: true, rewrite: (p) => p.replace(/^\/sanity/, "") },
    },
  },
});
