// Exercise the actual auth Request handler; delete only this probe's fixtures.
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
const schema = await import(pathToFileURL(path.join(frontend, "auth-schema.ts")));
const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const base = auth.options.baseURL;
const email = `cdx-r94-${randomUUID()}@example.invalid`;
const password = "R94-Only-Fixture-Pass-2026!";
let userId, orgId;
const emit = (k, v) => console.log(k + "=" + JSON.stringify(v));
async function request(route, body, cookie) {
  const headers = { origin: base };
  if (body) headers["content-type"] = "application/json";
  if (cookie) headers.cookie = cookie;
  const response = await auth.handler(new Request(base + "/api/auth" + route, {
    method: body ? "POST" : "GET", headers,
    ...(body ? { body: JSON.stringify(body) } : {}),
  }));
  const data = await response.json();
  return { response, data };
}
try {
  const up = await request("/sign-up/email", { email, password, name: "cdx-r94-probe" });
  assert.equal(up.response.status, 200);
  userId = up.data.user.id;
  const login = await request("/sign-in/email", { email, password });
  assert.equal(login.response.status, 200);
  const cookie = login.response.headers.getSetCookie().map(s => s.split(";")[0]).join("; ");
  assert.ok(cookie);
  const initial = await request("/get-session", null, cookie);
  emit("REAL_COOKIE_SESSION_USER_MATCH", initial.data?.user?.id === userId);
  const orphanSlug = randomUUID();
  const org = await request("/organization/create", { name: "cdx-r94-org", slug: orphanSlug }, cookie);
  orgId = org.data?.id;
  emit("ORDINARY_USER_CREATE_ORG_HTTP", org.response.status);
  emit("ORG_TENANT_EXISTS", Number((await pool.query("SELECT count(*) FROM app.tenants WHERE public_id=$1", [orphanSlug])).rows[0].count));
  if (orgId) {
    emit("CREATOR_ROLE", (await pool.query("SELECT role FROM auth.member WHERE organization_id=$1 AND user_id=$2", [orgId, userId])).rows[0]?.role);
  }
  await pool.query("UPDATE auth.user SET status='disabled' WHERE id=$1", [userId]);
  const disabledSession = await request("/get-session", null, cookie);
  emit("DISABLED_EXISTING_SESSION", { http: disabledSession.response.status, userPresent: !!disabledSession.data?.user, status: disabledSession.data?.user?.status });
  const newLogin = await request("/sign-in/email", { email, password });
  emit("DISABLED_NEW_LOGIN_HTTP", newLogin.response.status);
  if (orgId) {
    const newSlug = randomUUID();
    const changed = await request("/organization/update", { organizationId: orgId, data: { slug: newSlug } }, cookie);
    emit("DISABLED_USER_REBIND_HTTP", changed.response.status);
    emit("SLUG_CHANGED", (await pool.query("SELECT slug FROM auth.organization WHERE id=$1", [orgId])).rows[0]?.slug === newSlug);
  }
  emit("IDP_ORG_AUDIT_ROWS", Number((await pool.query("SELECT count(*) FROM app.audit_events WHERE actor_id=$1", [userId])).rows[0].count));
  await pool.query("UPDATE auth.user SET status='unknown-r94' WHERE id=$1", [userId]);
  const unknown = await request("/sign-in/email", { email, password });
  emit("UNKNOWN_STATUS_NEW_LOGIN_HTTP", unknown.response.status);
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    await client.query("SET LOCAL search_path TO auth");
    const db = drizzle(client, { schema });
    const times = [];
    for (const zone of ["UTC", "Asia/Shanghai", "America/New_York"]) {
      await client.query("SELECT set_config('TimeZone',$1,true)", [zone]);
      const actual = (await db.select().from(schema.user).where(eq(schema.user.id, userId)))[0];
      const expected = (await client.query("SELECT extract(epoch FROM created_at)*1000 AS epoch FROM auth.user WHERE id=$1", [userId])).rows[0].epoch;
      times.push({ zone, expectedMs: Number(expected), actualMs: actual.createdAt.getTime(), deltaMs: actual.createdAt.getTime() - Number(expected) });
    }
    emit("ADAPTER_TIMEZONE_MATRIX", times);
  } finally {
    await client.query("ROLLBACK");
    client.release();
  }
} finally {
  if (orgId) await pool.query("DELETE FROM auth.organization WHERE id=$1", [orgId]);
  // The email is unique to this invocation, including a partial signup failure.
  await pool.query("DELETE FROM auth.user WHERE email=$1", [email]);
  emit("PROBE_USERS_REMAINING", Number((await pool.query("SELECT count(*) FROM auth.user WHERE email=$1", [email])).rows[0].count));
  await pool.end();
}
