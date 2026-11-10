// Real Request-handler probes; fixtures are scoped to unique IDs and cleaned.
import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const frontend = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../frontend");
const require = createRequire(path.join(frontend, "package.json"));
const { Pool } = require("pg");
const { auth } = await import(pathToFileURL(path.join(frontend, "auth.config.ts")));
const { drizzle } = await import(pathToFileURL(path.join(frontend, "node_modules/drizzle-orm/node-postgres/index.js")));
const { eq } = await import(pathToFileURL(path.join(frontend, "node_modules/drizzle-orm/index.js")));
const schema = await import(pathToFileURL(path.join(frontend, "auth-runtime-schema.ts")));
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const base = auth.options.baseURL;
const email = `cdx-r96-${randomUUID()}@example.invalid`;
const password = "R96-Only-Fixture-Pass-2026!";
const orgIds = [], tenantIds = [];
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
  return { status: response.status, headers: response.headers, data: await response.json() };
}
async function createOrg(slug, cookie) {
  const result = await request("/organization/create", { name: "cdx-r96-org", slug }, cookie);
  if (result.data?.id) orgIds.push(result.data.id);
  return result;
}
try {
  const up = await request("/sign-up/email", { email, password, name: "cdx-r96-probe" });
  assert.equal(up.status, 200);
  userId = up.data.user.id;
  const login = await request("/sign-in/email", { email, password });
  assert.equal(login.status, 200);
  const cookie = login.headers.getSetCookie().map(s => s.split(";")[0]).join("; ");
  assert.ok(cookie);
  emit("UNKNOWN_TENANT_CREATE_HTTP", (await createOrg(randomUUID(), cookie)).status);
  for (let i = 0; i < 2; i++) {
    const row = await pool.query("INSERT INTO app.tenants(name,scope) VALUES ($1,'internal') RETURNING public_id", [`cdx-r96-${randomUUID()}`]);
    tenantIds.push(row.rows[0].public_id);
  }
  emit("PRIOR_MEMBERSHIP_COUNT", Number((await pool.query("SELECT count(*) FROM auth.member WHERE user_id=$1", [userId])).rows[0].count));
  const org = await createOrg(tenantIds[0], cookie);
  emit("UNASSIGNED_USER_EXISTING_TENANT_CREATE_HTTP", org.status);
  assert.ok(org.data?.id);
  const oid = org.data.id;
  emit("CREATOR_ROLE", (await pool.query("SELECT role FROM auth.member WHERE organization_id=$1 AND user_id=$2", [oid, userId])).rows[0]?.role);
  const rebind = await request("/organization/update", { organizationId: oid, data: { slug: tenantIds[1] } }, cookie);
  emit("ACTIVE_CROSS_TENANT_REBIND_HTTP", rebind.status);
  emit("ACTIVE_SLUG_MOVED", (await pool.query("SELECT slug FROM auth.organization WHERE id=$1", [oid])).rows[0]?.slug === tenantIds[1]);
  const compact = await createOrg(tenantIds[1].replaceAll("-", ""), cookie);
  emit("COMPACT_SAME_TENANT_CREATE_HTTP", compact.status);
  emit("SAME_CANONICAL_TENANT_ORG_COUNT", Number((await pool.query("SELECT count(*) FROM auth.organization WHERE replace(slug,'-','')=$1", [tenantIds[1].replaceAll("-", "")])).rows[0].count));
  await pool.query("UPDATE auth.user SET updated_at='2001-01-01T00:00:00Z' WHERE id=$1", [userId]);
  const updated = await request("/update-user", { name: "cdx-r96-updated" }, cookie);
  emit("PROFILE_UPDATE_HTTP", updated.status);
  emit("PROFILE_UPDATED_AT", (await pool.query("SELECT updated_at FROM auth.user WHERE id=$1", [userId])).rows[0].updated_at.toISOString());
  await pool.query("UPDATE auth.user SET status='disabled' WHERE id=$1", [userId]);
  const disabledUpdate = await request("/organization/update", { organizationId: oid, data: { name: "disabled-edit" } }, cookie);
  emit("DISABLED_UPDATE_HTTP", disabledUpdate.status);
  emit("DISABLED_NEW_LOGIN_HTTP", (await request("/sign-in/email", { email, password })).status);
  const deleted = await request("/organization/delete", { organizationId: oid }, cookie);
  emit("DISABLED_OLD_COOKIE_DELETE_HTTP", deleted.status);
  emit("ORG_ROWS_AFTER_DISABLED_DELETE", Number((await pool.query("SELECT count(*) FROM auth.organization WHERE id=$1", [oid])).rows[0].count));
  emit("PLUGIN_AUDIT_ROWS", Number((await pool.query("SELECT count(*) FROM app.audit_events WHERE actor_id=$1", [userId])).rows[0].count));
  await pool.query("UPDATE auth.user SET status='unknown-r96' WHERE id=$1", [userId]);
  emit("UNKNOWN_NEW_LOGIN_HTTP", (await request("/sign-in/email", { email, password })).status);
  await pool.query("UPDATE auth.user SET status='active' WHERE id=$1", [userId]);
  emit("REENABLED_LOGIN_HTTP", (await request("/sign-in/email", { email, password })).status);
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query("SET LOCAL search_path TO auth");
    const db = drizzle(client, { schema });
    const matrix = [];
    for (const zone of ["UTC", "Asia/Shanghai", "America/New_York"]) {
      await client.query("SELECT set_config('TimeZone',$1,true)", [zone]);
      const epoch = Date.parse("2026-09-06T02:03:04.567Z");
      await db.update(schema.user).set({ createdAt: new Date(epoch) }).where(eq(schema.user.id, userId));
      const actual = (await db.select().from(schema.user).where(eq(schema.user.id, userId)))[0].createdAt.getTime();
      const stored = Number((await client.query("SELECT extract(epoch FROM created_at)*1000 AS epoch FROM auth.user WHERE id=$1", [userId])).rows[0].epoch);
      const session = (await db.select().from(schema.session).where(eq(schema.session.userId, userId)))[0];
      const databaseExpired = (await client.query("SELECT expires_at<=now() AS expired FROM auth.session WHERE id=$1", [session.id])).rows[0].expired;
      matrix.push({ zone, writeDeltaMs: stored - epoch, readDeltaMs: actual - epoch, expiryAgreement: (session.expiresAt.getTime() <= Date.now()) === databaseExpired });
    }
    emit("RUNTIME_TIMEZONE_MATRIX", matrix);
  } finally {
    await client.query("ROLLBACK");
    client.release();
  }
} finally {
  for (const id of orgIds) await pool.query("DELETE FROM auth.organization WHERE id=$1", [id]);
  await pool.query("DELETE FROM auth.user WHERE email=$1", [email]);
  for (const id of tenantIds) await pool.query("DELETE FROM app.tenants WHERE public_id=$1", [id]);
  emit("PROBE_USER_ROWS", Number((await pool.query("SELECT count(*) FROM auth.user WHERE email=$1", [email])).rows[0].count));
  emit("PROBE_TENANT_ROWS", Number((await pool.query("SELECT count(*) FROM app.tenants WHERE public_id=ANY($1::uuid[])", [tenantIds])).rows[0].count));
  await pool.end();
}
