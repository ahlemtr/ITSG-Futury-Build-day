import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // 127.0.0.1 instead of "localhost": on Windows, localhost can resolve to IPv6 only
  server: {
    host: "127.0.0.1",
    port: 5173,
    open: true,
    // api mode: /api/* goes to the FastAPI backend (uvicorn api.main:app --port 8000), so no CORS is needed
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
