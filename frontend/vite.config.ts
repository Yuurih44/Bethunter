import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/")) {
            if (
              /recharts|d3-|victory-vendor|react-smooth|decimal.js|lodash/.test(
                id,
              )
            )
              return "charts";
            if (/react-dom|\/react\/|scheduler/.test(id)) return "react";
          }
        },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  preview: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
