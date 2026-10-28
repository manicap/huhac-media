import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ mode }) => {
  const apiTarget = loadEnv(mode, ".", "").HUHAC_STUDIO_API_TARGET
    || "http://127.0.0.1:8878";
  if (!/^http:\/\/(?:127\.0\.0\.1|localhost|\[::1\])(?::\d+)?\/?$/.test(apiTarget)) {
    throw new Error("HUHAC_STUDIO_API_TARGET must be a loopback HTTP URL");
  }
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
          headers: { Origin: apiTarget },
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
      css: true,
    },
  };
});
