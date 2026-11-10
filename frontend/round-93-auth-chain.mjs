// round-93 真实 better-auth 链路集成探针（R92-1；round-95 R94-4 清理加固）——置于 frontend/ 目录
// 注册 -> 登录 -> session 落库（可信 actor 来自 IdP 会话）-> 服务端 disabled -> 登录拒绝
// 会话有效性以 auth.session 表真实行为准（Python 生产目录读同一库验证）。
// R94-4：finally 精确清理本次生成的 user（email 唯一），FK CASCADE 清 session/account；
// 输出固定 UTF-8。
// 运行：cd frontend && node --experimental-strip-types round-93-auth-chain.mjs
import { auth } from "./auth.config.ts";
import { Pool } from "pg";

// R98-2：支持外部预生成唯一 email（测试可提前定位 fixture，失败时也能精确清理）
const email = process.env.FIXTURE_EMAIL ||
  `it-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
const password = "T7-Integration-Pass-2026!";
const name = "t7-integration-user";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL ?? "postgresql://dsh:dsh@127.0.0.1:5432/dsh_test",
});
let userId = null;

async function main() {
  // 1) 注册（IdP 写入 auth.user）
  const signUp = await auth.api.signUpEmail({ body: { email, password, name } });
  console.log("SIGNUP_OK=" + Boolean(signUp && signUp.user && signUp.user.id));
  userId = signUp.user.id;
  console.log("USER_ID=" + userId);
  console.log("USER_STATUS_DEFAULT=" + (signUp.user.status ?? "active"));

  // 2) 登录（IdP 写入 auth.session；signIn 返回 token）
  const signIn = await auth.api.signInEmail({ body: { email, password } });
  const token = signIn?.token;
  console.log("SIGNIN_TOKEN_PRESENT=" + Boolean(token));

  // 3) session 落库验证（可信 actor 来源）：auth.session 行存在且 user_id 匹配
  const sess = await pool.query(
    "SELECT id, token, user_id FROM auth.session WHERE user_id=$1 ORDER BY created_at DESC LIMIT 1",
    [userId]);
  const row = sess.rows[0];
  console.log("SESSION_ROW_PRESENT=" + Boolean(row));
  console.log("SESSION_USER_ID_MATCH=" + String(row?.user_id === userId));
  console.log("SESSION_TOKEN_MATCH=" + String(row?.token === token));

  // 4) 服务端停用（生产路径由服务端控制 auth.user.status）
  await pool.query("UPDATE auth.user SET status='disabled' WHERE id=$1", [userId]);
  console.log("SERVER_DISABLED=true");

  // 5) 停用后登录拒绝（约定行为：disabled 用户不能建立新会话）
  let blocked = false;
  try {
    await auth.api.signInEmail({ body: { email, password } });
  } catch {
    blocked = true;
  }
  console.log("DISABLED_LOGIN_BLOCKED=" + blocked);
}

try {
  await main();
} finally {
  // R94-4：默认精确清理本次生成 user（email 唯一），FK CASCADE 级联 session/account；
  // KEEP_USER=1 时保留（供 Python 侧同源读取验证，由测试 teardown 清理）
  if (userId && process.env.KEEP_USER !== "1") {
    await pool.query("DELETE FROM auth.user WHERE id=$1", [userId]);
  } else if (userId) {
    console.log("KEPT_USER_ID=" + userId);
  }
  await pool.end();
}
console.log("CHAIN_DONE=true");
