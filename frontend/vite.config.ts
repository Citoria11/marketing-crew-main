import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In local development the FastAPI backend runs on port 8080.
// In Docker, the backend container's port 8080 is mapped to host port 8000,
// but the Vite dev server is only used outside Docker.
const BACKEND = process.env.VITE_API_BASE ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/upload":    BACKEND,
      "/process":   BACKEND,
      "/resume":    BACKEND,
      "/state":     BACKEND,
      "/campaigns": BACKEND,
    },
  },
});
