import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/v1": proxyTarget(),
      "/docs": proxyTarget(),
      "/redoc": proxyTarget(),
      "/openapi.json": proxyTarget(),
    },
  },
});

function proxyTarget() {
  return {
    target: process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000",
    changeOrigin: true,
  };
}
