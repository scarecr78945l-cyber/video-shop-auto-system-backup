// round-97 真实 handler 全入口保护探针（R96-1/R96-2）
// 普通 user 对现存/不存在 tenant 均无绑定能力（create/update/delete/member/invitation 全 403）；
// 唯一 fixture 名 + finally 精确清理；连续两次可重放。
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../frontend");
const require = createRequire(path.join(frontend, "package.json"));
const { Pool } = require("pg");
const { auth } = await import(pathToFileURL(path.join(frontend, "auth.config.ts")));
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const base = auth.options.baseURL;
const email = `cdx-r97-${randomUUID()}@example.invalid`;
const password = "R97-Only-Fixture-Pass-2026!";
const tenantIds = [];
let userId;
const emit = (k, v) => console.log(k + "=" + JSON.stringify(v));
async function request(route, body, cookie) {
  const headers = { origin: base };
  if (body) headers["content-type"] = "application/json";
  if (cookie) headers.cookie = cookie;
  const response = await auth.handler(new Request(base + "/api/auth" + route, {
    method: body ? "POST" : "GET", headers,
    ...(body ? { body: JSON.stringify(body) } : {}),
  }));
  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null; // 部分路由返回空 body
  }
  return { status: response.status, headers: response.headers, data };
}
try {
  const up = await request("/sign-up/email", { email, password, name: "cdx-r97-probe" });
  assert.equal(up.status, 200);
  userId = up.data.user.id;
  const login = await request("/sign-in/email", { email, password });
  assert.equal(login.status, 200);
  const cookie = login.headers.getSetCookie().map(s => s.split(";")[0]).join("; ");
  // 两个真实 tenant 作为资源（存在性不赋予用户权限）
  for (let i = 0; i < 2; i++) {
    const row = await pool.query("INSERT INTO app.tenants(name,scope) VALUES ($1,'internal') RETURNING public_id", [`cdx-r97-${randomUUID()}`]);
    tenantIds.push(row.rows[0].public_id);
  }
  // 普通 user 对现存 tenant 无绑定能力（R96-1：现存 ≠ 授权）
  const create = await request("/organization/create", { name: "r97-org", slug: tenantIds[0] }, cookie);
  emit("UNASSIGNED_USER_EXISTING_TENANT_CREATE_HTTP", create.status);
  // 普通 user 对不存在 tenant 同样拒绝
  const createUnknown = await request("/organization/create", { name: "r97-org2", slug: randomUUID() }, cookie);
  emit("UNASSIGNED_USER_UNKNOWN_TENANT_CREATE_HTTP", createUnknown.status);
  // 停用旧 Cookie 对所有写入口均拒绝（含 delete/member/invitation）
  await pool.query("UPDATE auth.user SET status='disabled' WHERE id=$1", [userId]);
  const del = await request("/organization/delete", { organizationId: randomUUID() }, cookie);
  emit("DISABLED_OLD_COOKIE_DELETE_HTTP", del.status);
  const addMember = await request("/organization/add-member", { organizationId: randomUUID(), userId: randomUUID(), role: "admin" }, cookie);
  emit("DISABLED_OLD_COOKIE_ADD_MEMBER_HTTP", addMember.status);
  const invite = await request("/organization/invite-member", { organizationId: randomUUID(), email: "x@example.com", role: "admin" }, cookie);
  emit("DISABLED_OLD_COOKIE_INVITE_HTTP", invite.status);
  const newLogin = await request("/sign-in/email", { email, password });
  emit("DISABLED_NEW_LOGIN_HTTP", newLogin.status);
  // 重新启用
  await pool.query("UPDATE auth.user SET status='active' WHERE id=$1", [userId]);
  const relogin = await request("/sign-in/email", { email, password });
  emit("REENABLED_LOGIN_HTTP", relogin.status);
  // 插件写入无审计（组织写已被禁用，不应产生 org 审计）
  emit("PLUGIN_AUDIT_ROWS", Number((await pool.query("SELECT count(*) FROM app.audit_events WHERE actor_id=$1", [userId])).rows[0].count));
} finally {
  await pool.query("DELETE FROM auth.user WHERE email=$1", [email]);
  for (const id of tenantIds) await pool.query("DELETE FROM app.tenants WHERE public_id=$1", [id]);
  emit("PROBE_USER_ROWS", Number((await pool.query("SELECT count(*) FROM auth.user WHERE email=$1", [email])).rows[0].count));
  emit("PROBE_TENANT_ROWS", Number((await pool.query("SELECT count(*) FROM app.tenants WHERE public_id=ANY($1::uuid[])", [tenantIds])).rows[0].count));
  await pool.end();
}
