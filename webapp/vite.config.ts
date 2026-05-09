import { defineConfig, type PluginOption } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = fileURLToPath(new URL(".", import.meta.url));

function stripBundleBlankLineWhitespace(): PluginOption {
  return {
    name: "strip-bundle-blank-line-whitespace",
    generateBundle(_options, bundle) {
      for (const chunkOrAsset of Object.values(bundle)) {
        if (chunkOrAsset.type === "chunk") {
          chunkOrAsset.code = chunkOrAsset.code.replace(/^[\t ]+$/gm, "");
        } else if (typeof chunkOrAsset.source === "string") {
          chunkOrAsset.source = chunkOrAsset.source.replace(/^[\t ]+$/gm, "");
        }
      }
    },
  };
}

export default defineConfig({
  root: resolve(rootDir),
  plugins: [react(), tailwindcss(), stripBundleBlankLineWhitespace()],
  resolve: {
    alias: {
      "@": resolve(rootDir, "./src"),
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        ws: true,
      },
      "/logo.jpg": {
        target: "http://127.0.0.1:8000",
      },
      "/logo.png": {
        target: "http://127.0.0.1:8000",
      },
      "/favicon.ico": {
        target: "http://127.0.0.1:8000",
      },
      "/favicon.png": {
        target: "http://127.0.0.1:8000",
      },
    },
  },
  build: {
    outDir: resolve(rootDir, "../src/pbi_agent/web/static/app"),
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("node_modules/react-dom") || id.includes("node_modules/react/") || id.includes("node_modules/react-router")) {
            return "vendor";
          }
          if (id.includes("node_modules/@tanstack/react-query")) {
            return "query";
          }
          if (id.includes("node_modules/react-markdown") || id.includes("node_modules/remark-") || id.includes("node_modules/rehype-") || id.includes("node_modules/unified") || id.includes("node_modules/mdast") || id.includes("node_modules/micromark")) {
            return "markdown";
          }
        },
      },
    },
  },
});
