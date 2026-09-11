import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build estático servido pelo FastAPI. Em dev, proxia /api para o backend na 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
