// round-99 真实 handler 全写入口封禁探针（R98-1）
// 用 Python helper 创建有效 org/admin/viewer/invitation；随后用真实 IdP Cookie 调 handler：
//   active 未授权写全 403（插件层 + 路由层双层）；disabled 旧 Cookie 全写 403；零副作用。
// 唯一 fixture 名 + finally 精确清理；连续两次可重放。
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const frontend = path.join(root, "frontend");
const require = createRequire(path.join(frontend, "package.json"));
const { Pool } = require("pg");
const { auth, handler } = await import(pathToFileURL(path.join(frontend, "auth.config.ts")));
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const base = auth.options.baseURL;
const emails = [0, 1, 2].map(() => `cdx-r99-${randomUUID()}@example.invalid`);
const users = [];
let tid, oid, memberId, invitationId;
const emit = (k, v) => console.log(k + "=" + JSON.stringify(v));

async function request(route, body, cookie) {
  const headers = { origin: base };
  if (body) headers["content-type"] = "application/json";
  if (cookie) headers.cookie = cookie;
  const response = await handler(new Request(base + "/api/auth" + route, {
    method: body ? "POST" : "GET", headers,
    ...(body ? { body: JSON.stringify(body) } : {}),
  }));
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  return { status: response.status, headers: response.headers, data };
}

try {
  for (const email of emails) {
    const up = await request("/sign-up/email", { email, password: "R99-Fixture-Pass-2026!", name: "cdx-r99" });
    assert.equal(up.status, 200);
    const login = await request("/sign-in/email", { email, password: "R99-Fixture-Pass-2026!" });
    assert.equal(login.status, 200);
    users.push({ id: up.data.user.id, cookie: login.headers.getSetCookie().map(s => s.split(";")[0]).join("; ") });
  }
  tid = (await pool.query("INSERT INTO app.tenants(name,scope) VALUES ($1,'internal') RETURNING public_id", [`cdx-r99-${randomUUID()}`])).rows[0].public_id;
  // Python helper 建立有效组织：user0=admin，user1=viewer（生产路径，2 条审计）
  const setup = spawnSync("python", ["-c", `
import json,os,sys
from sqlalchemy import create_engine
from infra.auth import PgUserDirectory,bind_tenant_organization,set_member_role
e=create_engine(os.environ['DATABASE_URL'])
with e.begin() as c:
 d=PgUserDirectory(c)
 o=bind_tenant_organization(c,actor_id='a9a79363-609b-5848-a4b3-33982797cfb8',tenant_public_id=sys.argv[1],organization_name='cdx-r99',first_admin_user_id=sys.argv[2],request_id='cdx-r99-setup',worker_scope_tenant_public_id=sys.argv[1],user_directory=d)
 set_member_role(c,operator_actor_id='a9a79363-609b-5848-a4b3-33982797cfb8',tenant_public_id=sys.argv[1],target_actor_id=sys.argv[3],new_role='viewer',request_id='cdx-r99-setup',operator_scope_tenant_public_id=sys.argv[1],user_directory=d)
 print(json.dumps({'orgId':o}))
e.dispose()
`, tid, users[0].id, users[1].id], {
    cwd: path.join(root, "backend"), encoding: "utf8",
    env: { ...process.env, DATABASE_URL: process.env.DATABASE_URL.replace(/^postgres(?:ql)?:/, "postgresql+psycopg2:"), PYTHONIOENCODING: "utf-8" },
  });
  assert.equal(setup.status, 0, setup.stderr);
  oid = JSON.parse(setup.stdout.trim()).orgId;
  memberId = (await pool.query("SELECT id FROM auth.member WHERE organization_id=$1 AND user_id=$2", [oid, users[1].id])).rows[0].id;
  emit("HELPER_SETUP_AUDIT_ROWS", Number((await pool.query("SELECT count(*) FROM app.audit_events WHERE request_id='cdx-r99-setup' AND tenant_id=(SELECT id FROM app.tenants WHERE public_id=$1)", [tid])).rows[0].count));
  emit("HELPER_ASSIGNED_ROLES", (await pool.query("SELECT role FROM auth.member WHERE organization_id=$1 ORDER BY role", [oid])).rows.map(r => r.role));

  // active 未授权 user（user1 viewer，非 admin）：改角色/邀请/leave 均 403（路由层）
  const viewerUpdateRole = await request("/organization/update-member-role", { organizationId: oid, memberId, role: "admin" }, users[1].cookie);
  emit("ACTIVE_VIEWER_UPDATE_ROLE_HTTP", viewerUpdateRole.status);
  const viewerInvite = await request("/organization/invite-member", { organizationId: oid, email: `cdx-r99-inv@example.invalid`, role: "member" }, users[1].cookie);
  emit("ACTIVE_VIEWER_INVITE_HTTP", viewerInvite.status);
  const viewerLeave = await request("/organization/leave", { organizationId: oid }, users[1].cookie);
  emit("ACTIVE_VIEWER_LEAVE_HTTP", viewerLeave.status);

  // disabled 旧 Cookie：update/role/invite/accept/cancel/leave 全 403
  await pool.query("UPDATE auth.user SET status='disabled' WHERE id=ANY($1::uuid[])", [users.map(u => u.id)]);
  const disabledUpdate = await request("/organization/update", { organizationId: oid, data: { name: "x" } }, users[0].cookie);
  emit("DISABLED_UPDATE_HTTP", disabledUpdate.status);
  const disabledRole = await request("/organization/update-member-role", { organizationId: oid, memberId, role: "member" }, users[0].cookie);
  emit("DISABLED_ROLE_UPDATE_HTTP", disabledRole.status);
  const disabledInvite = await request("/organization/invite-member", { organizationId: oid, email: `cdx-r99-i2@example.invalid`, role: "member" }, users[0].cookie);
  emit("DISABLED_INVITE_HTTP", disabledInvite.status);
  const disabledLeave = await request("/organization/leave", { organizationId: oid }, users[1].cookie);
  emit("DISABLED_LEAVE_HTTP", disabledLeave.status);
  const disabledNewLogin = await request("/sign-in/email", { email: emails[0], password: "R99-Fixture-Pass-2026!" });
  emit("DISABLED_NEW_LOGIN_HTTP", disabledNewLogin.status);

  // 零副作用断言
  emit("ROLE_UNCHANGED", (await pool.query("SELECT role FROM auth.member WHERE id=$1", [memberId])).rows[0]?.role);
  emit("INVITATION_ROWS", Number((await pool.query("SELECT count(*) FROM auth.invitation WHERE organization_id=$1", [oid])).rows[0].count));
  emit("MEMBER_ROWS", Number((await pool.query("SELECT count(*) FROM auth.member WHERE organization_id=$1", [oid])).rows[0].count));
  emit("PLUGIN_ACTOR_AUDIT_ROWS", Number((await pool.query("SELECT count(*) FROM app.audit_events WHERE actor_id=ANY($1::uuid[])", [users.map(u => u.id)])).rows[0].count));
} finally {
  if (tid) {
    await pool.query("DELETE FROM app.audit_events WHERE tenant_id=(SELECT id FROM app.tenants WHERE public_id=$1)", [tid]);
    await pool.query("DELETE FROM auth.organization WHERE slug=$1", [tid]);
  }
  await pool.query("DELETE FROM auth.user WHERE email=ANY($1::text[])", [emails]);
  if (tid) await pool.query("DELETE FROM app.tenants WHERE public_id=$1", [tid]);
  emit("PROBE_USER_ROWS", Number((await pool.query("SELECT count(*) FROM auth.user WHERE email=ANY($1::text[])", [emails])).rows[0].count));
  emit("PROBE_TENANT_ROWS", Number((await pool.query("SELECT count(*) FROM app.tenants WHERE public_id=$1", [tid ?? randomUUID()])).rows[0].count));
  await pool.end();
}
