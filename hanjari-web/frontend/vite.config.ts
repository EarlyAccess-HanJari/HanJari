import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_TARGET || "http://127.0.0.1:8000";  // 같은 레포의 backend/
  return {
    plugins: [react()],
    server: {
      proxy: {
        "/api": { target, changeOrigin: true },
      },
    },
  };
});