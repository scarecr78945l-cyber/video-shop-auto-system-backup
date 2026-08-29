import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  test: {
    // 口径转换/状态机映射/API 客户端均为纯函数，node 环境即可（无需 DOM/jsdom）
    environment: "node",
    include: ["tests/**/*.test.ts"],
    globals: false,
  },
  resolve: {
    alias: {
      "@": path.resolve(process.cwd(), "."),
    },
  },
});
