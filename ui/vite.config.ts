import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { resolve } from "node:path";

const marketDataApiUrl =
  process.env.MARKET_DATA_API_URL || "http://127.0.0.1:8010";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
  server: {
    port: 3020,
    proxy: {
      "/api": {
        target: marketDataApiUrl,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  preview: {
    port: 3020,
  },
});
