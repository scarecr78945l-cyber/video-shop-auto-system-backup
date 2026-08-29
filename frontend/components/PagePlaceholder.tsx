/**
 * 占位页（v0.4+ 页面建设中用）：标题 + 说明 + 建设中提示。
 * 后续子代理开发真实页面时替换本组件调用即可。
 */
import { Hammer } from "lucide-react";

type Props = {
  title: string;
  description: string;
  module: string;
};

export function PagePlaceholder({ title, description, module }: Props) {
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-zinc-900">{title}</h1>
        <p className="mt-1 text-sm text-zinc-500">{description}</p>
      </div>
      <div className="rounded-lg border border-dashed border-zinc-300 bg-white p-12 text-center">
        <span className="mx-auto mb-3 grid size-12 place-items-center rounded-full bg-zinc-100 text-zinc-400">
          <Hammer size={22} />
        </span>
        <p className="text-sm font-medium text-zinc-600">{module} · v0.4+ 建设中</p>
        <p className="mt-1 text-xs text-zinc-400">工程底座已就绪，业务页面由后续迭代交付</p>
      </div>
    </div>
  );
}
