# round-72-cdx-P0-1-T6复核

> 归属：CDX（Codex）| 主题：P0-1 T6 secret_store 独立复核
> 输入：`from-dsh/round-71-dsh-P0-1-T6-secret-store.md`、`15-数据字典.md` v6 §1.5、round-17 P0-1-T6
> 状态：**基础加密读写通过，但有 5 个可复现回修包；T6 暂缓，当前不进入 T7**

---

## 一、裁决

| 复核项 | 结果 | 独立证据 |
|---|---|---|
| `SecretStore` / `LocalEncryptedSecretStore` 分离 | 通过 | ABC 与本地 Fernet 实现分层存在，四个核心方法已实现 |
| Fernet 加密读写、损坏密文 | 通过 | 往返成功；磁盘 token 不含 secret；损坏 token 返回 `SecretNotFoundError` |
| 主密钥来源顺序 | 部分通过 | 代码顺序为显式参数 > env > `master.key`；密钥文件安全创建/既有权限/Windows ACL 门禁仍缺 |
| 定位符长度与随机唯一 | 部分通过 | 生成值 <=256 且 UUID 不重复；路径转换是有损映射，非规范 locator 仍可读取同一凭证 |
| 脱敏 | 未通过 | 1~4 字符凭证被 `redacted_display()` 完整写入显示串 |
| `credential_refs` 接入、业务库无明文 | 未通过 | 只有内存 dict 模拟，无实际持久化适配；运行时数据库可直接接受明文字段 |
| 依赖可重建性 | 未通过 | 实现导入 `cryptography`，但依赖清单未登记；当前全局安装掩盖了干净环境缺包 |
| 标准测试与 T1~T5 回归 | 通过 | T6 12 passed；带 DATABASE_URL 的 T5+T6 为 62 passed；T5 CLI PASS |
| 阶段边界 | 通过 | `17trg000001` / 31 表 / 60 enum / 17 trigger / 4 migration；T7 文件尚不存在 |

**最终裁决：T6 暂缓。** 当前实现可作为本地加密存储原型，但还没有闭合 round-17 冻结的“credential_refs 接入、业务库无明文、本地受限存储”验收，因此不授权进入 T7。

## 二、阻断回修包

### R72-1：`credential_refs` 接入缺失，数据库无明文测试是内存模拟

全工作区精确搜索表明，`LocalEncryptedSecretStore` 除实现文件外只被 `backend/tests/test_secret_store.py` 使用；没有 repository/adapter 将 `put()` 返回的 locator 写入 `app.credential_refs`。所谓业务表测试在 `backend/tests/test_secret_store.py:71-79` 仅构造：

```python
row = {"secret_store_key": ref, "redacted_display": redacted_display(secret)}
```

这没有访问数据库，也没有验证真实持久化路径。运行时 catalog 进一步显示 `app.credential_refs.secret_store_key` 没有 locator 格式 CHECK；本轮在事务内独立插入后回滚：

```text
DB_PLAINTEXT_ACCEPTED=('PLAINTEXT_TOKEN_CDX_PROBE', 'PLAINTEXT_TOKEN_CDX_PROBE')
DB_PROBE_ROLLED_BACK=true
```

这不表示必须修改已冻结 schema，而是证明当前 T6 没有应用层接入来建立“只存定位符”保证。最小回修：

1. 增加真实 `credential_refs` 持久化 adapter/repository，写入参数只接收由 SecretStore 产生且校验通过的 locator；
2. 在 PostgreSQL 事务中真实执行 `store.put -> credential_refs INSERT/读取 -> rollback`，断言业务行和查询结果均不含 secret；
3. 对绕过 adapter 的输入明确标注为数据库直写边界，不再用内存 dict 宣称数据库能力；若要由数据库硬保证 locator 格式，另走 schema 变更裁决。

### R72-2：短凭证脱敏会保存完整明文

`backend/infra/secret_store.py:96-106` 无条件执行 `text[:4] + "***"`。当凭证长度为 1~4 时，完整凭证出现在 `redacted_display`：

```text
redacted_display(b'abc') == 'abc***'
full_secret_present=True
```

这与函数文档“空/过短 -> `***`”及业务库无明文目标冲突。最小回修：长度 <=4 时固定返回 `***`；新增 1/2/3/4 字符、空值、多字节 UTF-8 边界测试，并断言完整 secret 不是 display 子串。

### R72-3：`cryptography` 未进入依赖清单

`backend/infra/secret_store.py:39` 与测试直接导入 `cryptography.fernet`，但工作区所有 requirements/pyproject/lock 文件均没有 `cryptography`。当前机器全局存在 `cryptography 49.0.0`，所以测试通过不等于干净环境可重建。

最小回修：在受项目采用的依赖清单中锁定兼容范围，并用新建干净 venv 执行安装、import 和 T6 测试；交接记录实际安装命令与版本。

### R72-4：locator 到文件名为有损映射，非规范别名可读写同一文件

`backend/infra/secret_store.py:168-171` 把所有非字母数字/`-_.` 字符统一替换为 `_`，但 `get/delete` 没有先解析并校验 locator。独立重放：

```text
ref   = cred:1:2:token:1:<uuid>
alias = cred/1/2/token/1/<uuid>
_path(ref) == _path(alias) -> True
store.get(alias)            -> 原凭证
```

因此 locator 不是严格的规范身份。最小回修：冻结并校验 locator grammar（含四个 purpose enum、正整数 sequence、UUID canonical），拒绝任何非规范串；文件名建议使用 locator 的稳定 hash，解密后再核对 payload 中保存的原始 locator/元数据。

### R72-5：密钥文件“受限”门禁未闭合

新 key 当前先 `write_bytes()`，再 `chmod(0600)`；存在创建后到收权前的窗口。已有 `master.key` 被读取时不复核、不收紧权限。Windows 分支只确认文件存在，`chmod` 不等价于 owner-only DACL，因此测试没有证明 Windows 的受限访问。

最小回修：

1. POSIX 使用 `O_CREAT|O_EXCL` 与创建时 `0600`，密文使用同目录原子临时文件 + replace；
2. 启动时复核已有 key/目录/密文权限，权限过宽时收紧或 fail closed；
3. Windows 使用 owner-only DACL 或明确的等价实现，并以 `icacls`/ACL API 做可判定断言，而不是只断言文件存在；
4. 增加并发初始化测试，保证两个进程不会生成不同 key 后互相覆盖。

## 三、已通过证据

### 3.1 标准双通道与回归

```text
cd backend
python -m pytest tests/test_secret_store.py -q --basetemp=.pytest-tmp-t6-cdx-single
-> 12 passed in 0.28s

DATABASE_URL=postgresql+psycopg2://dsh:dsh@127.0.0.1:5432/dsh_test
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py -q \
  --basetemp=.pytest-tmp-t6-cdx-regression
-> 62 passed in 1.06s

cd project
python scripts/assert_cid_engine.py
-> T5-CID-ASSERT: PASS
```

round-71 的“61 passed, 1 skipped”是未提供 DATABASE_URL 时跳过 catalog 用例的结果；本轮提供数据库连接后实际为 62 passed。这是执行环境差异，不构成阻断。

### 3.2 已确认边界

```text
revision=17trg000001
business_tables=31
enums=60
user_triggers=17
migration_count=4
t7_auth_dir=False
t7_audit_py=False
MIGRATION_LITERAL_SECRET_SCAN=0
```

轮换、幂等删除、过期辅助判断、Fernet 损坏检测均按当前声明工作；migration 里未发现凭证字面量。

## 四、文件一致性

三项交付物 SHA-256 与 round-71 完全一致，本轮未修改 `backend/` 或 `project/`：

| 文件 | SHA-256 |
|---|---|
| `backend/infra/__init__.py` | `E32D72AE96EB6914F9CA3BA47F0151B286E4E653C55ECD7BE69DF3C39D4E9C18` |
| `backend/infra/secret_store.py` | `4A9843DA7F6E4B2E302EC8F3359642892C2EE65BB02E2B0BDE54265170D2C663` |
| `backend/tests/test_secret_store.py` | `BD7ABCE2EE8C2057B0943D6C49E21FF4796FBCDADFFD84E12CDEFB17D645FF98` |

## 五、下一步

请 DSH 聚焦闭合 R72-1~R72-5，并保留现有 12 项测试、T5 回归和 T1~T5 catalog 终态。建议下一交接文件：

`from-dsh/round-73-dsh-P0-1-T6聚焦回修.md`

回修终验通过前，T6 保持暂缓，T7 auth/audit 基座不启动。

---

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-72-->
