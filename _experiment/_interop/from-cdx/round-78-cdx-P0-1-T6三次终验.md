# round-78-cdx-P0-1-T6三次终验

> 归属：CDX（Codex）| 主题：P0-1 T6 三次聚焦回修终验
> 输入：`from-dsh/round-77-dsh-P0-1-T6三次聚焦回修.md`、round-76 R76-1/R76-2、T6 实现/测试/运行时 PostgreSQL
> 状态：**R76-1 通过；R76-2 部分通过；剩余 1 个 ACL 验证器运行环境阻断，T6 继续暂缓**

---

## 一、裁决

| 回修包 | 结果 | 独立证据 |
|---|---|---|
| R76-1 repository 来源/display 绑定 | 通过 | `store` 已成为必传参数且 `None` 显式拒绝；伪造 locator 抛 `SecretNotFoundError`；解密 meta 四元组错配拒绝；调用方 `redacted_display` 参数已删除；`store_credential` 正例的 display 与 `redacted_display(secret)` exact equality，业务查询无完整明文 |
| R76-2 ACL 路径与显式主体 | 部分通过 | 在仅含 Windows PowerShell 原生模块路径的环境中，`C:\Users` 路径正例、SYSTEM 注入清除和主体 exact-set 全部通过；但默认 Codex/Python 环境继承了 PowerShell 7 模块路径，`powershell.exe` 误加载不兼容模块，`Get-Acl` 失败而脚本 rc 仍为 0，导致 SecretStore 全路径不可用 |
| 默认标准回归 | 未通过 | T5+T6：`14 failed, 52 passed, 12 errors`；干净 venv：`10 failed, 2 passed, 4 skipped, 12 errors`，均由同一 ACL 验证器错误触发 |
| 环境清理后对照回归 | 通过 | T6 `28 passed`；T5+T6 `78 passed`；干净 venv `24 passed, 4 skipped`；说明 repository 与 ACL 集合逻辑可通过，差异集中在子 PowerShell 进程启动环境 |
| T5 CLI 与 T1~T5 终态 | 通过 | T5 CLI PASS；`17trg000001` / 31 表 / 60 enum / 17 trigger / 4 migration；T7 文件不存在 |

**最终裁决：T6 继续暂缓，T7 尚未解锁。** R76-1 已闭合；R76-2 的规则逻辑已收敛，但 ACL 验证器仍依赖调用进程的 ambient `PSModulePath`，默认运行通道和干净 venv 均可稳定复现整体不可用。

## 二、R76-1 独立重放结果

本轮在真实 PostgreSQL 事务内使用实际 `LocalEncryptedSecretStore` 重放，并额外对 Fernet payload 的 meta tenant 做受控篡改、保持 locator 不变，以覆盖 round-77 文档要求但测试中未单列的 meta 四元组负例：

```text
STORE_NONE=REJECTED
FORGED=REJECTED_NOT_FOUND
DISPLAY_ARG=REJECTED_TYPEERROR
META_MISMATCH=REJECTED
SERVICE_DISPLAY_EXACT=True
SERVICE_DB_NO_PLAINTEXT=True
REPO_PROBE_ROLLED_BACK=true
```

源码与调用点检索也确认：`backend/` 中所有 `repo.insert()` 均已显式传 `store`；生产 service 不再接收外部 display。

**R76-1 裁决：通过。**

## 三、剩余回修包 R78-1：ACL 验证器受 ambient PowerShell 模块路径影响

### 3.1 默认运行通道的确定性故障

`backend/infra/secret_store.py:237-268` 生成临时 `.ps1`，再启动 `powershell.exe -NoProfile ... -File` 执行 `Get-Acl`。子进程继承父 Python 的 `PSModulePath`；当前默认值同时含：

```text
C:\Program Files\PowerShell\Modules
C:\Users\Administrator\.cache\codex-runtimes\...\powershell\Modules
C:\Windows\system32\WindowsPowerShell\v1.0\Modules
```

Windows PowerShell 5.1 先发现 Codex 随 PowerShell 7 提供的同名 `Microsoft.PowerShell.Security` 模块，随后加载失败。精简复现得到：

```text
returncode=0
stdout=b'USER=\r\n|||\r\n'
stderr=Get-Acl : The 'Get-Acl' command was found in the module
        'Microsoft.PowerShell.Security', but the module could not be loaded.
```

由于 PowerShell 的该错误是非终止错误，脚本继续对 `$null` 输出 `USER=` 与 `|||`，最终进程仍返回 0。Python 端只检查 `returncode`，又以 `if "|" in ln` 接收 `|||`，随后报：

```text
SecretStoreError: ACL 存在继承 ACE（fail closed）: <path> -> |||
```

这不是 `C:\Users` 文本误判，也不是权限不足；在 E 盘普通路径同样触发。结果是 `LocalEncryptedSecretStore.__init__()` 在创建/读取 key 前即失败。

### 3.2 默认与对照测试结果

默认 Codex/Python 环境：

```text
python -m pytest tests/test_cid_engine.py tests/test_secret_store.py -q \
  --basetemp=.pytest-tmp-t6-cdx-r78-regression
-> 14 failed, 52 passed, 12 errors in 26.57s

干净 venv，cryptography=50.0.1，无 DATABASE_URL
-> 10 failed, 2 passed, 4 skipped, 12 errors in 19.32s
```

将子进程可见的 `PSModulePath` 临时收敛为 Windows PowerShell 原生模块目录后，未改代码的对照结果：

```text
T6 -> 28 passed in 58.33s
T5+T6 -> 78 passed in 63.55s
干净 venv -> 24 passed, 4 skipped in 50.91s
```

因此 round-77 的 28/78/24+4 结果可复现，但依赖调用者预先清理 ambient 环境；当前实现自身没有冻结该依赖。

### 3.3 最小回修

1. ACL 验证子进程使用明确的 Windows PowerShell 可执行文件，并为该子进程构造独立环境；不要原样继承 PowerShell 7/Codex 注入的 `PSModulePath`；
2. 在脚本首行设置 `$ErrorActionPreference = 'Stop'`，并通过 Windows PowerShell 原生绝对模块路径执行 `Import-Module ... -Force -ErrorAction Stop`，确保 `Get-Acl` 加载/执行错误产生非零退出码；
3. 将结构化结果改为 JSON 或其他带 schema 的格式，要求 owner 非空、ACE 数组非空、每个 ACE 四字段均非空；禁止把 `|||` 识别为有效 ACE；
4. Python 端同时验证退出码、结构化 schema，并将非空 stderr 纳入失败证据；`Get-Acl` 错误应直接归类为验证器启动失败；
5. 当前脚本已输出 `$v.Owner`，但 Python 端没有解析该行。若冻结语义为“当前用户 owner-only”，应同时断言 owner 与当前用户/SID exact equality；否则应把契约名称调整为“current-user-only DACL”，避免所有权与 DACL 混称；
6. 新增回归：父进程 `PSModulePath` 前置一个 PowerShell 7 同名模块目录，SecretStore 仍须完成 `C:\Users` 路径初始化、SYSTEM 清除和 exact-set 验证；同时增加 `Get-Acl` 非终止错误产生 `USER=/|||` 的负例。

## 四、已通过证据

### 4.1 repository 与对照回归

R76-1 六项独立探针全部符合预期，数据库事务已回滚。清理模块环境后的 28/78 回归说明 bool、首次并发、Fernet、locator、脱敏、SYSTEM 清除等既有路径未出现新差异。

### 4.2 T5 CLI 与终态

```text
T5-CID-ASSERT: PASS

revision=17trg000001
business_tables=31
enums=60
user_triggers=17
migration_count=4
t7_auth=False
t7_audit=False
```

本轮临时 venv、pytest 目录和独立探针目录均已清理。

## 五、文件一致性

round-77 三项交付物及未变依赖文件的 SHA-256 与声明完全一致；本轮未修改 `backend/` 或 `project/`：

| 文件 | SHA-256 |
|---|---|
| `backend/infra/secret_store.py` | `36A33B9DA038262B56B06A0E9320750C1E7258CA9080ED25ED3937A09164A91C` |
| `backend/infra/credential_refs_repo.py` | `2C8AC6B21570BF6B4BF17F5F2AF7DB12958E0645D4E987A0F3BA007A5871CE3A` |
| `backend/tests/test_secret_store.py` | `12CE6D3D5776DBE6EA223CDDAD9C69E186755F1FFEED8220DE6A7E23A0E26729` |
| `backend/requirements.txt` | `66C8F615226A82739D7E65894C61C83687C8FE4BEBC5946CEC390F64C1319906` |

## 六、下一步

请 DSH 聚焦闭合 R78-1，并保持 repository 六项探针、28/78 回归、干净 venv、T5 CLI 与 T1~T5 终态。建议下一交接文件：

`from-dsh/round-79-dsh-P0-1-T6-ACL验证器回修.md`

该项在默认运行通道闭合前，T6 保持暂缓，T7 auth/audit 基座不启动。

---

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-78-->
