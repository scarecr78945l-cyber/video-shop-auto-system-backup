import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "管理控制台 · 视频号小店全自动系统",
    template: "%s · 管理控制台",
  },
  description: "视频号小店全自动系统管理控制台（选品 / 素材 / 优化 / 上架 / 托管 / 人工闸门）",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
