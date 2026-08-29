/**
 * 环境开关（v0.4 批次1）
 *
 * NEXT_PUBLIC_USE_MOCK：演示数据开关保留位（context 环境变量注册表）。
 * 当前版本**不注入任何 mock 数据**，页面始终直连真实 API（硬性要求）；
 * 置 1/true 时页面仅展示「演示模式保留位」提示条（后续迭代可在该开关下挂载
 * 演示数据层，不改变页面取数代码结构）。
 */
export function isMockMode(): boolean {
  const value = process.env.NEXT_PUBLIC_USE_MOCK;
  return value === "1" || value === "true";
}
