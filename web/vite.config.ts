import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/ui/",
  build: {
    outDir: "../src/knoarbor/ui/dist",
    emptyOutDir: true,
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          const normalizedId = id.replace(/\\/g, "/");
          if (normalizedId.includes("node_modules/cytoscape")) {
            return "graph-engine";
          }
          if (
            normalizedId.includes("node_modules/react/") ||
            normalizedId.includes("node_modules/react-dom/") ||
            normalizedId.includes("node_modules/scheduler/")
          ) {
            return "vendor-react";
          }
          if (
            normalizedId.includes("node_modules/react-markdown/") ||
            normalizedId.includes("node_modules/remark-") ||
            normalizedId.includes("node_modules/rehype-") ||
            normalizedId.includes("node_modules/unified/") ||
            normalizedId.includes("node_modules/mdast-") ||
            normalizedId.includes("node_modules/hast-")
          ) {
            return "vendor-markdown";
          }
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/health": "http://127.0.0.1:8000",
      "/ingest": "http://127.0.0.1:8000",
      "/run_lint_maintenance": "http://127.0.0.1:8000",
      "/query": "http://127.0.0.1:8000",
      "/ui/api": "http://127.0.0.1:8000",
    },
  },
});
