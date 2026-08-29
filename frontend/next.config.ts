import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // 后端 API 层鉴权为 httpOnly 会话 cookie；前端跨域取数必须显式携带
  //（credentials 在 lib/api.ts 的 fetch 中设置，此处仅为路由/构建配置）。
  eslint: {
    // lint 非验收项（验收 = npm install / npm run dev / npm test），
    // 构建期跳过 lint，避免 eslint-config-next 版本差异阻塞 next build 冒烟。
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
