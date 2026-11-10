// better-auth 实际配置（T7 gate 交付，round-85 R84-1；round-87 R86-1；round-89 R88-1；
// round-93 R92-1；round-95 R94-1/R94-2/R94-3；round-97 R96-1；round-99 R98-1 定稿）
// 依据：auth-gate.md 锁定 better-auth 1.7.2；auth-boundary.md §四/§五/§六 冻结契约。
//
// round-99 定稿（R98-1）：
// - R94-3：drizzle 使用 auth-runtime-schema（timestamp withTimezone:true，timestamptz 解码一致）；
// - R94-1：新会话仅 active 可建（disabled/未知拒绝）；
// - R96-1/R98-1：organization 插件**全部原生写入口禁用**——修正实际 hook 键名
//   （beforeUpdateMemberRole/beforeCreateInvitation，round-98 指正），覆盖邀请 accept/reject/cancel，
//   并对无 hook 的 leave 等路径用导出 handler 包裹在路由层统一拒绝（GET 读取除外）。
//   组织生命周期统一由 Python helper（organization.py）管理：service/worker 专属 + 角色白名单
//   + UUID canonical + 不可变绑定 + 事务审计。
import { betterAuth } from "better-auth";
import { APIError } from "better-auth/api";
import { drizzleAdapter } from "@better-auth/drizzle-adapter";
import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import { organization } from "better-auth/plugins";
import * as schema from "./auth-runtime-schema.ts";

const pool = new Pool({
  connectionString:
    process.env.DATABASE_URL ?? "postgresql://dsh:dsh@127.0.0.1:5432/dsh_test",
});
pool.on("connect", (client) => {
  client.query("SET search_path TO auth");
});

const db = drizzle(pool, { schema });

const orgWriteForbidden = () => {
  throw new APIError("FORBIDDEN", {
    message: "组织写操作仅限 service/worker 服务端 actor（走 Python helper）",
  });
};

// R98-1：organization 插件全部写 hook 封禁（键名对照 better-auth 1.7.2 实际调用点）
const organizationHooks = {
  beforeCreateOrganization: orgWriteForbidden,
  beforeUpdateOrganization: orgWriteForbidden,
  beforeDeleteOrganization: orgWriteForbidden,
  beforeAddMember: orgWriteForbidden,
  beforeUpdateMemberRole: orgWriteForbidden, // 实际键（crud-members.mjs:340）
  beforeRemoveMember: orgWriteForbidden,
  beforeCreateInvitation: orgWriteForbidden, // 实际键（crud-invites.mjs:207）
  beforeAcceptInvitation: orgWriteForbidden,
  beforeRejectInvitation: orgWriteForbidden,
  beforeCancelInvitation: orgWriteForbidden,
};

export const auth = betterAuth({
  appName: "wechat-shop-automation-console",
  baseURL: process.env.BETTER_AUTH_URL ?? "http://127.0.0.1:43120",
  database: drizzleAdapter(db, { provider: "pg" }),
  emailAndPassword: {
    enabled: true,
  },
  advanced: {
    database: {
      generateId: "uuid",
    },
  },
  user: {
    additionalFields: {
      status: {
        type: "string",
        required: true,
        defaultValue: "active",
        input: false,
      },
    },
  },
  databaseHooks: {
    session: {
      create: {
        before: async (session) => {
          // 新会话：仅 active 可建（disabled/未知拒绝）
          const rows = await pool.query("SELECT status FROM auth.user WHERE id=$1", [session.userId]);
          const status = rows.rows[0]?.status;
          if (status !== "active") return false;
          return { data: session };
        },
      },
    },
  },
  plugins: [
    organization({ organizationHooks }),
  ],
});

// R98-1：导出 handler 包裹——路由层拦截 organization 全部写路径（含无 hook 的 leave），GET 读取放行。
// 依据 organization.mjs 端点注册：create/update/delete/set-active/create-invitation/cancel-invitation/
// accept-invitation/reject-invitation/add-member/update-member-role/remove-member/leave/team-* 等。
const orgWritePrefixes = [
  "/api/auth/organization/create",
  "/api/auth/organization/update",
  "/api/auth/organization/delete",
  "/api/auth/organization/set-active",
  "/api/auth/organization/invite-member",
  "/api/auth/organization/cancel-invitation",
  "/api/auth/organization/accept-invitation",
  "/api/auth/organization/reject-invitation",
  "/api/auth/organization/add-member",
  "/api/auth/organization/update-member-role",
  "/api/auth/organization/remove-member",
  "/api/auth/organization/leave",
  "/api/auth/organization/create-team",
  "/api/auth/organization/update-team",
  "/api/auth/organization/remove-team",
  "/api/auth/organization/add-team-member",
  "/api/auth/organization/remove-team-member",
];

export const orgWriteGuard = (request: Request) => {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method.toUpperCase();
  if (method === "GET" || method === "HEAD" || method === "OPTIONS") return false;
  return orgWritePrefixes.some((p) => path === p || path.startsWith(p + "/"));
};

export async function handler(request: Request): Promise<Response> {
  if (orgWriteGuard(request)) {
    return new Response(JSON.stringify({ error: { code: "FORBIDDEN", message: "组织写操作仅限 service/worker 服务端 actor（走 Python helper）" } }), {
      status: 403,
      headers: { "content-type": "application/json" },
    });
  }
  return auth.handler(request);
}
