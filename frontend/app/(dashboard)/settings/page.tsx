import type { Metadata } from "next";
import { PagePlaceholder } from "@/components/PagePlaceholder";

export const metadata: Metadata = {
  title: "系统设置",
};

export default function SettingsPage() {
  return (
    <PagePlaceholder
      title="系统设置"
      description="提供商配置（masked 密钥展示，密钥永不落前端）/ 类目白名单 / 预算上限 / 一键全停（对接 /api/app-config、/api/kill-switch）"
      module="系统设置"
    />
  );
}
