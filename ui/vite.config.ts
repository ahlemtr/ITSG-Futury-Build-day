import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // 127.0.0.1 instead of "localhost": on Windows, localhost can resolve to IPv6 only
  server: { host: "127.0.0.1", port: 5173, open: true },
});
