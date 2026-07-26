import { defineConfig } from "vite";

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || "http://localhost:8000";
const orchestratorProxyTarget = process.env.VITE_ORCHESTRATOR_PROXY_TARGET || "http://localhost:8006";

export default defineConfig({
  server: {
    proxy: {
      "/api": { target: apiProxyTarget, changeOrigin: true, rewrite: (path) => path.replace(/^\/api/, "") },
      "/orchestrator": { target: orchestratorProxyTarget, changeOrigin: true, rewrite: (path) => path.replace(/^\/orchestrator/, "") },
    },
  },
});
