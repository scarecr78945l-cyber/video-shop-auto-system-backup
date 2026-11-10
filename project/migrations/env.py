"""P0-1 T1 migration env：ddl-order.md 契约落地（round-47 R46-1 回修）。

- business_schema = app；search_path = app, pg_catalog（每次迁移显式 SET）
- migration_role = ${MIGRATION_ROLE}：存在性/可切换性/current_user 门禁，**在任何持久副作用之前**（R46-1）
- 连接串 = ${DATABASE_URL}（覆盖 ini 占位；断言脚本同源）
- G0 预检：PostgreSQL server_version_num >= 150000（online）
- offline 模式：明确关闭，稳定错误退出
- bootstrap（CREATE SCHEMA/GRANT/ALTER DEFAULT PRIVILEGES）与 revision 同一迁移事务，失败整体回滚
"""
import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool, text

from alembic import context

config = context.config

BUSINESS_SCHEMA = "app"
SEARCH_PATH = "app, pg_catalog"
MIGRATION_ROLE_ENV = "MIGRATION_ROLE"
DATABASE_URL_ENV = "DATABASE_URL"
MIN_PG_VERSION = 150000  # PG15+（UNIQUE NULLS NOT DISTINCT）


def _fail(msg: str) -> None:
    print(f"[T1 gate] {msg}", file=sys.stderr)
    sys.exit(1)


def _quote_ident(name: str) -> str:
    """安全标识符引用（防止注入）：双引号包裹，内部双引号转义。"""
    return '"' + name.replace('"', '""') + '"'


# ---- 必填门禁：migration_role ----
role = os.environ.get(MIGRATION_ROLE_ENV, "").strip()
if not role:
    _fail(
        f"缺少环境变量 {MIGRATION_ROLE_ENV}：migration_role 为启动必填门禁"
        "（ddl-order.md §一.2）。"
    )

# ---- 连接串：DATABASE_URL 覆盖 ini ----
db_url = os.environ.get(DATABASE_URL_ENV, "").strip()
if not db_url:
    _fail(f"缺少环境变量 {DATABASE_URL_ENV}：迁移必须显式指定数据库连接串。")
config.set_main_option("sqlalchemy.url", db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _verify_role_zero_side_effect(connection) -> None:
    """R46-1：角色门禁，零副作用——事务内 SET LOCAL ROLE + current_user 断言后 rollback。

    必须在任何 CREATE SCHEMA / GRANT / ALTER DEFAULT PRIVILEGES / commit 之前执行。
    - 不存在 → 失败
    - 不可切换（SET LOCAL ROLE 报错）→ 失败
    - current_user != 期望角色 → 失败
    说明：SET LOCAL ROLE 在事务结束时自动还原；本函数仅做只读查询与角色切换验证，
          最终 rollback 保证无任何持久副作用（SQLAlchemy 2.0 autobegin 下不显式 begin()）。
    """
    exists = connection.execute(
        text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}
    ).scalar()
    if not exists:
        _fail(f"migration_role 不存在于 pg_roles：{role}")

    try:
        connection.execute(text(f"SET LOCAL ROLE {_quote_ident(role)}"))
        cur = connection.execute(text("SELECT current_user")).scalar()
        if cur != role:
            _fail(f"SET LOCAL ROLE 未生效：current_user={cur} != 期望 {role}")
    except Exception as exc:  # noqa: BLE001
        _fail(f"migration_role 不可切换：{role}（{type(exc).__name__}: {exc}）")
    finally:
        # 回滚当前隐式事务：SET LOCAL ROLE 与只读查询一并还原，零持久副作用
        connection.rollback()


def run_migrations_offline() -> None:
    """offline 模式明确关闭，稳定错误退出（不产生不可执行 SQL）。"""
    _fail("offline 模式已关闭：本迁移仅支持 online 执行（app schema/search_path/PG15 需连接数据库）。")


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        # G0 预检：PG15+（只读，无副作用）
        ver = connection.execute(text("SHOW server_version_num")).scalar()
        if int(ver) < MIN_PG_VERSION:
            _fail(
                f"PostgreSQL 版本不足：server_version_num={ver} < {MIN_PG_VERSION}"
                "（需要 PG15+，UNIQUE NULLS NOT DISTINCT 语法前提）。"
            )

        # R46-1：角色门禁前置——任何持久副作用之前，零副作用验证
        _verify_role_zero_side_effect(connection)

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            version_table_schema=BUSINESS_SCHEMA,
        )
        # bootstrap（连接用户身份：schema/GRANT/默认权限）与 revision（迁移角色身份）同一事务，
        # 失败整体回滚，不留部分副作用（R46-1）
        with context.begin_transaction():
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{BUSINESS_SCHEMA}"'))
            connection.execute(
                text(f'GRANT USAGE, CREATE ON SCHEMA "{BUSINESS_SCHEMA}" TO {_quote_ident(role)}')
            )
            connection.execute(
                text(
                    f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{BUSINESS_SCHEMA}" '
                    f"GRANT ALL ON TABLES TO {_quote_ident(role)}"
                )
            )
            connection.execute(text(f"SET search_path TO {SEARCH_PATH}"))
            # 迁移角色：SET LOCAL ROLE 在事务内生效，事务结束自动还原
            connection.execute(text(f"SET LOCAL ROLE {_quote_ident(role)}"))
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
