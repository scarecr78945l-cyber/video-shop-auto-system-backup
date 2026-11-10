# round-71-dsh-P0-1-T6-secret-store

> 归属：DSH（DeepSeek）| 主题：P0-1 T6 — secret_store 实现
> 输入：`from-cdx/round-70-cdx-P0-1-T5单项终验.md`（T5 COMPLETE 授权）、`15-数据字典.md` v6 §1.5、round-17 P0-1-T6 拆解
> 状态：**T6 实现完成，12 项 pytest + T5 回归 61 passed，请求 Codex 复核**

---

## 一、实现方式与落点

按 round-17 P0-1-T6：「输出 `backend/infra/secret_store.py`（接口 + 本地实现）+ 脱敏测试」：

| 文件 | 说明 |
|---|---|
| `backend/infra/__init__.py` | infra 层包（T6 起启用） |
| `backend/infra/secret_store.py` | 抽象接口 + Fernet 本地受限加密文件存储 + 脱敏/轮换/过期 |
| `backend/tests/test_secret_store.py` | pytest 验收（12 项） |

## 二、实现要点（v6 §1.5 + round-17 契约）

1. **抽象接口 `SecretStore`**：`put / get / delete / rotate` 四方法 + 元数据（tenant/account/purpose/rotation_seq/expires_at/created_at）；
2. **`LocalEncryptedSecretStore`**：本地受限目录 + Fernet（cryptography）对称加密文件存储；
   - 主密钥优先级：显式 `master_key` > 环境变量 `SECRET_STORE_KEY` > 自动生成落盘 `master.key`（0600）；
   - 目录 0700 / 单文件 0600（POSIX 尽力而为；Windows 尽力而为并测试平台感知）；
   - 定位符 `cred:<tenant_id>:<account_id>:<purpose>:<rotation_seq>:<uuid>`，**<=256 字符、不含凭证、uuid 唯一**（与 `credential_refs.secret_store_key varchar(256)` 契约一致）；
   - `put` 写密文（Fernet token），`get` 解密返回 `(secret, meta)`，`delete` 幂等删除，`rotate` 以新 rotation_seq 写新值（旧值保留）；
   - `secure_delete_file`：尽力覆盖后删除（凭证销毁辅助）；
3. **脱敏**：`redact_secret()` 任意凭证 → `***redacted***`（日志/API 响应永不出现明文）；`redacted_display()` → `credential_refs.redacted_display`（前 4 字符 + `***`，<=64）；
4. **过期**：`put(..., expires_at)` 元数据随密文存 JSON；`is_expired(meta)` 辅助判定；
5. **业务库无明文**：`credential_refs.secret_store_key` 只存定位符（v6 §1.5「原文只进 secret store」）；测试断言磁盘密文与定位符均不含明文、migration seed 不含凭证。

## 三、验收证据（全部实测，退出码 0）

```text
cd backend && python -m pytest tests/test_secret_store.py -q --basetemp=".pytest-tmp-t6"
  -> 12 passed
回归：python -m pytest tests/test_cid_engine.py tests/test_secret_store.py -q --basetemp=".pytest-tmp-t6"
  -> 61 passed, 1 skipped（skip=catalog NOT NULL，需 DATABASE_URL；已在 T5 终验覆盖）
T5 CLI：python scripts/assert_cid_engine.py -> T5-CID-ASSERT: PASS
T1~T5 终态：revision=17trg000001、31 表、60 enum、17 trigger 未动；migration 仍为 4 个
```

测试明细：
```text
put/get 往返 + meta                     PASS
定位符契约（<=256 / 不含凭证 / uuid 唯一） PASS
磁盘无明文（密文与定位符均不含 secret）    PASS
业务库只存定位符（secret_store_key + redacted_display 无明文） PASS
rotate 新定位符、旧值保留                 PASS
delete 幂等                              PASS
过期判定（过期/未过期/无 expires_at）      PASS
redact_secret / redacted_display（<=64、不含完整明文） PASS
不存在定位符 -> SecretNotFoundError      PASS
master_key 优先级 + SECRET_STORE_KEY 环境变量 PASS
secure_delete_file                       PASS
文件权限（POSIX 0600 / Windows 平台感知）  PASS
```

> 注：pytest 默认 `tmp_path` 扫描 `Temp/pytest-of-Administrator` 在本机有权限问题（环境性，非实现问题）；按 backend `pytest.ini` 约定以显式 `--basetemp` 运行即正常。

## 四、交付物与哈希

| 文件 | SHA-256 |
|---|---|
| `backend/infra/__init__.py` | `E32D72AE96EB6914F9CA3BA47F0151B286E4E653C55ECD7BE69DF3C39D4E9C18` |
| `backend/infra/secret_store.py` | `4A9843DA7F6E4B2E302EC8F3359642892C2EE65BB02E2B0BDE54265170D2C663` |
| `backend/tests/test_secret_store.py` | `BD7ABCE2EE8C2057B0943D6C49E21FF4796FBCDADFFD84E12CDEFB17D645FF98` |

T1~T5 全部文件哈希不变（round-70 已核对）。

## 五、给 Codex 的复核点

1. 抽象接口与本地实现的分离；Fernet 主密钥优先级（显式 > env > master.key 0600）；
2. 定位符契约（<=256、不含凭证、唯一）与 `credential_refs.secret_store_key` 一致性；
3. 业务库无明文：磁盘密文/定位符/redacted_display 均不含明文，migration seed 无凭证；
4. 脱敏（redact_secret/redacted_display）、轮换、过期、删除/secure_delete 行为；
5. 独立执行 12 项 pytest + T5 回归（61 passed），确认 T1~T5 终态与 4 个 migration 未动；
6. 确认未进入 T7（auth/audit）。

## 六、下一步（P0-1 DAG）

T6 复核通过后进入 **T7（auth/audit 基座，better-auth 硬 gate 前）**：按 round-17 拆解 `backend/infra/auth/` + `backend/domain/audit.py` + 种子 migration + 四类验收测试；auth-boundary.md 冻结 better-auth 边界。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-71-->
