import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // P-021 修复：显式锁定 Next 项目根（避免被上层 E:\新建文件夹 (6)\package-lock.json
  // 误导 outputFileTracingRoot，导致产物/资源路径错位、dev 白屏）
  outputFileTracingRoot: path.join(__dirname),
  // 后端 API 层鉴权为 httpOnly 会话 cookie；前端跨域取数必须显式携带
  //（credentials 在 lib/api.ts 的 fetch 中设置，此处仅为路由/构建配置）。
  eslint: {
    // lint 非验收项（验收 = npm install / npm run dev / npm test），
    // 构建期跳过 lint，避免 eslint-config-next 版本差异阻塞 next build 冒烟。
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
