// ESLint 9 扁平配置：兼容 eslint-config-next 15.1.3（eslintrc 格式经 FlatCompat 桥接）。
// lint 非本项目验收项（验收 = npm install / npm run dev / npm test），仅保证可运行。
import { FlatCompat } from "@eslint/eslintrc";
import path from "node:path";
import { fileURLToPath } from "node:url";

const compat = new FlatCompat({
  baseDirectory: path.dirname(fileURLToPath(import.meta.url)),
});

export default [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [".next/**", "node_modules/**", "coverage/**"],
  },
];
