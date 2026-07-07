import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  build: {
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      input: {
        main: "index.html",
        keybindings: "keybindings.html",
        splash: "tauri-splash.html"
      }
    }
  },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.PORT) || 5173,
    strictPort: true
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true
  },
  test: {
    include: ["src/**/*.{test,spec}.?(c|m)[jt]s?(x)"],
    globals: true,
    environment: "node"
  }
});
