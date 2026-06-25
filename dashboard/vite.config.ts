import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      "/admin": { target: "http://localhost:8070", changeOrigin: true },
      "/health": { target: "http://localhost:8070", changeOrigin: true },
    },
  },
  base: "/admin/",
  build: { outDir: "dist" },
});
