# M5 自动小店投放（商品托管）· v0.3 托管执行器交付说明

> 撰写人：M5 子代理（托管执行器，A2 重派版）｜ 日期：2025 体系建立日
> 范围：v0.3 执行层第一部分「托管执行器」——会话管理 / 浏览器连接抽象 / 托管两步之①添加商品 /
> page_changed 检测。**当前只做抽象接口 + fixtures 模拟（Mock 页面），不依赖真实浏览器/登录态**；
> 真实 Playwright 适配器后续接入，接口不变。
> 前置说明：此前同任务子代理因上下文耗尽中断且零产出，已弃用；本版从零完整实现。

## 一、交付文件清单

| 文件 | 说明 |
|---|---|
| `backend/ads/executor.py` | **本任务核心**：`ShopAdsSession`（会话 dataclass）、`check_login`（登录态判定）、`BrowserConnector`（ABC）+ `MockBrowserConnector` + `PlaywrightBrowserConnector`（骨架占位）、`MockPageOps`（PageOps Protocol 内存假页面）、`verify_page_signature`（page_changed 检测）、`ShopAdsExecutor`（add_product + run_batch 编排）、`_load_settings_form`（延迟加载 settings 兜底） |
| `backend/tests/test_ads_executor.py` | **25 个 Mock 驱动用例**（fixtures 全部测试文件内自建，未改 conftest） |
| `_management/modules/m5-ads/REPORT_v0.3_executor.md` | 本交付说明 |

未创建/未改动：`settings.py`（并行子代理产物，只延迟 import 消费）、
`ui_config.py`/`interfaces.py`/`tables.py`/`models.py`/`repo.py`（v0.2 定稿，禁止改动，本轮零改动）；
`config.py` 本轮无需追加（executor 不读 config 新字段）。

## 二、接口说明

### 2.1 `ShopAdsSession`（dataclass）
```python
@dataclass
class ShopAdsSession:
    cdp_url: str = "ws://127.0.0.1:9222/devtools/browser"
    port: int = 9222                # 对齐 AdsConfig.cdp_port
    profile: str = "default"
    login_state: str = "unknown"    # 英文枚举 unknown/logged_in/expired（非法值抛 ValueError）
    created_at: datetime = <UTC now>  # 强制 UTC 带时区；naive 输入自动补 timezone.utc（DA-001）
```

### 2.2 `check_login(page: PageOps, ui_config: ShopAdsUiConfig) -> str`
按 `page_signature` 特征选择器判断登录态（返回三态字符串）：
- 优先取 `page_signature["home"]` 锚点；home 未配置时回退任意已配置锚点；
- 锚点全部 `exists` → `"logged_in"`；
- 锚点已配置但任一缺失（特征选择器缺失）→ `"expired"`（上层映射 `error_code=AUTH_REQUIRED` 人工接管）；
- 未配置任何锚点（fixtures 默认）→ `"unknown"`（无法探测，不阻断流程，见偏差 2）。

### 2.3 浏览器连接抽象（三件套）
| 类 | 行为 |
|---|---|
| `BrowserConnector`（ABC） | `connect() -> PageOps` 抽象方法 |
| `MockBrowserConnector` | `connect()` 返回 `MockPageOps`（可注入预设页面，原样返回）；fixtures 用 |
| `PlaywrightBrowserConnector` | 骨架占位：`connect()` 抛 `NotImplementedError`（注释「实机后使用 connect_over_cdp 实现」）；**零 playwright import/安装/调用** |

### 2.4 `MockPageOps`（PageOps Protocol 内存假页面）
- 脚本化行为字典 `script = {selector: {"action": click/fill/select/text/error, ...}}`，扩展键
  `count`/`exists` 可叠加；`"error"` 操作抛 RuntimeError（模拟超时），`"missing"` 则
  `exists()→False`、`count()→0` 且操作抛错（模拟元素缺失/页面未加载）；
- `goto` 记录 `current_url`；`screenshot(path)` **实际写临时文件**（父目录自动创建）并返回路径；
- 记录 `self.history: list[str]`（`"op:selector"`）与 `self.ops: list[dict]`（含 `ts=perf_counter`
  时间戳，供防风控间隔断言）；`click_count`/`fill_value`/`option_value` 供断言；
- 查询方法（exists/read_text/read_attr/count）不写操作历史；`isinstance(mock, PageOps)` 通过。

### 2.5 `verify_page_signature(page, ui_config, page_key) -> dict`
- `page_signature[page_key]` 期望选择器逐一 `exists`（支持多锚点：换行/逗号/竖线分隔或列表）；
- 任一缺失 → 截图到 `screenshot_dir`（**不存在自动创建目录**）后抛
  `PageChangedError(evidence={page_key, missing, current_url, screenshot_path})`；
- 未配置锚点（fixtures 默认）→ 返回 `{"ok": True, "note": "signature_not_configured"}` 不阻塞；
- 通过 → 返回 `{"ok", "page_key", "checked", "missing", "current_url", "screenshot_path"}`。

### 2.6 `ShopAdsExecutor(page, ui_config)`
**`add_product(product_ids) -> dict`**（托管两步之①）：
进入添加商品页（goto）→ page_changed 检测（verify_signature）→ 逐个勾选
（`add_product_checkbox` 模板 `{pid}` 占位；**> batch_size 截断并标记 `truncated`**）→
防风控间隔 `item_interval_s`（留痕 interval 条目）→ 点 `add_product_next`。
返回 `{ok, error_code, error, selected_count, truncated, evidence, page_changed?}`。

**`run_batch(product_ids, settings_kwargs=None) -> dict`**（编排全链）：
`add_product` → **延迟 import settings.SettingsForm（`_load_settings_form` 函数内 import +
getattr 兜底）** → `choose_target` → `fill_roi`（`roi` 缺失时走系统推荐
`read_recommended_roi`+`resolve_roi` 策略）→ `bind_materials` → `submit`；
**settings 模块缺失 / SettingsForm 不存在 / 必需方法缺失 → `{ok: False, error: "settings_unavailable"}`
（不得抛 import 错误崩掉）**。
返回 `{ok, batch_id, selected, truncated, submit_result, evidence, error, error_code}`；
`submit_result` 为 `{passed, blocked_reason, error_code}` dict（SubmitResult 序列化）；
evidence 合并 add_product 留痕 + settings 表单 evidence。

`settings_kwargs` 约定键：`target_type`（默认 "roi"）、`roi`、`use_recommended_roi`、
`material_ids`；其余键透传 `SettingsForm` 构造（如 `target_roi_override`）。

**错误分类映射（09 码表）**：
| 异常/场景 | error_code |
|---|---|
| `PageChangedError`（特征锚点缺失） | `page_changed`（evidence 截图留痕） |
| 登录态 expired（特征选择器缺失） | `AUTH_REQUIRED` |
| 页面操作/显式等待失败（RuntimeError/TimeoutError，含选择器未配置） | `TIMEOUT` |
| 空商品列表 | `NO_MATCH` |
| submit 被平台驳回（余额不足/素材未过审） | `PLATFORM_REJECT`（透传 settings） |
| settings 模块/方法不可用 | `UNEXPECTED` + `error="settings_unavailable"` |
| 其余未知异常 | `UNEXPECTED` |

## 三、与 ui_config / interfaces / settings 对接说明

- **ui_config.py（只读）**：消费 `pages.add_product`、`selectors.add_product_checkbox`（`{pid}`
  占位）/`add_product_next`、`batch_size`（截断上限）、`item_interval_s`（防风控间隔）、
  `screenshot_dir`（page_changed 证据目录）、`page_signature`（check_login + page_changed 锚点）。
  选择器未配置时抛明确 RuntimeError（fixtures 阶段测试注入选择器值，同 settings.py 口径）。
- **interfaces.py（只读）**：`PageOps` Protocol 与 `PageChangedError` 语义完全对齐；
  `MockPageOps` 通过 `isinstance(mock, PageOps)` runtime_checkable 合规校验。
- **settings.py（延迟 import 消费，零改动）**：`run_batch` 在调用时才经 `_load_settings_form()`
  加载（函数内 import + getattr 兜底）；settings 尚未就绪时 executor 照常可 import/可测，
  编排返回 `settings_unavailable`；就绪后走 `choose_target/fill_roi/bind_materials/submit`
  全链，并复用其扩展方法 `read_recommended_roi/resolve_roi` 实现「系统推荐优先/可配置覆盖」。
- **config.py**：`cdp_port` 默认值与 `ShopAdsSession.port` 对齐；`target_roi_override` 由
  调用方经 `settings_kwargs` 透传，executor 不直接读 config（解耦）。
- **repo.py（v0.2）**：本任务不依赖（纯编排层，商品 ID 列表由上层传入）。

## 四、测试结果（backend 目录执行）

### 4.1 定向测试（验收标准 1）
```
python -m pytest tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"
25 passed in 0.25s
```
覆盖：MockPageOps 3 例（冒烟+Protocol 合规+截图写文件、脚本化动作、error/missing）、
ShopAdsSession 2 例（默认值+UTC 时区归一、非法登录态）、BrowserConnector 2 例
（Mock 连接器、Playwright 骨架占位）、check_login 2 例（logged_in；expired/unknown）、
verify_page_signature 3 例（通过+多锚点、缺失抛 PageChangedError evidence 齐全+目录自动创建、
未配置不阻塞）、add_product 6 例（happy path、>50 截断、防风控间隔时间戳验证、page_changed、
AUTH_REQUIRED、NO_MATCH/TIMEOUT 映射）、run_batch 7 例（fake form 调用链、
settings_unavailable 四种场景、add_product 错误传播、settings 异常映射 TIMEOUT/page_changed、
submit blocked、真实 settings 集成协同）。

### 4.2 import 验收（验收标准 2）
```
python -c "from ads.executor import ShopAdsExecutor, MockPageOps, verify_page_signature, check_login"
→ 无错
```

### 4.3 settings 协同（验收标准 3 定向组合）
```
python -m pytest tests/test_ads_settings.py tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"
50 passed in 0.21s
```

### 4.4 ads 包整体（额外自查，供总工参考）
```
python -m pytest tests/test_ads_repo.py tests/test_ads_tables.py tests/test_ads_settings.py tests/test_ads_executor.py -q --basetemp=".pytest-tmp-m5"
77 passed in 1.74s
```
全量回归按验收标准 3 由总控统一执行（本子代理不跑全量）。

## 五、验收标准对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 定向 pytest 全绿（带 `--basetemp=".pytest-tmp-m5"`） | ✅ 25 passed |
| 2 | `from ads.executor import ...` 无错 | ✅ |
| 3 | settings 协同组合测试全绿 | ✅ 50 passed（含真实 settings 集成用例） |
| 4 | 无真实浏览器依赖（无 playwright 实际连接调用） | ✅ executor.py 中 playwright 仅出现在注释/文档串，零 import/安装 |
| 5 | 纪律项全部满足 | ✅ 见第七节 |

## 六、偏差说明

1. **无功能偏差**：任务书要求的类/函数/错误码全部按规格实现；`add_product`/`run_batch` 返回
   结构化结果字段为规格超集（增加 ok/error_code/error/truncated 等，便于上层统一消费）。
2. **`check_login` 三态扩展**：除任务书两态（logged_in/expired）外，未配置任何特征锚点
   （fixtures 默认）返回 `"unknown"`（与 `ShopAdsSession.login_state` 枚举同词表）。理由：
   「特征缺失→expired」语义指**已配置锚点但页面上缺失**（此时必为登录页/结构变更，映射
   AUTH_REQUIRED 人工接管）；无锚点配置时无从探测，若也判 expired 会导致 fixtures 默认配置
   下所有流程直接 AUTH_REQUIRED 失败，happy path 无法离线验证。实机阶段 page_signature 必配，
   三态退化为两态，行为与任务书一致。
3. **settings 加载提取为 `_load_settings_form()`**：仍是「函数内 import + getattr 兜底」
   （延迟加载），提取为模块级函数是为了可测试（monkeypatch 模拟模块缺失/类缺失）且不改变
   语义；模块缺失/类不存在/必需方法缺失统一返回 `settings_unavailable`（error_code=UNEXPECTED）。
4. **空商品列表 → NO_MATCH**：`add_product([])` 返回 `{ok: False, error_code: "NO_MATCH"}`
   （复用 09 码表，语义=无可添加商品），而非静默成功。
5. **选择器未配置 → TIMEOUT**：executor 未配置 `add_product_checkbox`/`add_product_next` 时
   抛 RuntimeError 并映射 `TIMEOUT`（与 settings.py「选择器未配置抛 RuntimeError」同口径）。
6. **`MockPageOps` 独立实现**：与 settings.py 的 `MockSettingsPage` 相互独立（并行解耦，
   不互相 import）；两者均实现同一 `PageOps` Protocol，v0.3 集成时可直接互换。
7. **防风控间隔验证方式**：executor 真实 `time.sleep(item_interval_s)`（测试用小间隔），
   Mock `ops` 记录 perf_counter 时间戳，测试断言相邻勾选间隔 ≥ 配置值（含 0.045 容差）；
   evidence 同时留痕 `interval` 条目（含 interval_s）。

## 七、纪律核对

- ✅ 禁 git：全程未执行任何 git 命令。
- ✅ 一模块一库：本任务为纯编排+Mock，零 DB 访问；测试零 DB fixture。
- ✅ 禁明文密钥：无凭证字段/代码/文档。
- ✅ 金额=分 int（本任务无金额字段）、时间 UTC 带时区（evidence `ts` 用
  `datetime.now(timezone.utc).isoformat()`；`ShopAdsSession.created_at` 强制 UTC，naive 自动补
  timezone.utc）、枚举英文（login_state=unknown/logged_in/expired；error_code 复用 09 码表
  VERIFICATION_REQUIRED/AUTH_REQUIRED/RATE_LIMIT/TIMEOUT/NO_MATCH/PLATFORM_REJECT/UNEXPECTED/page_changed）。
- ✅ 中文文件全部 write 工具 UTF-8 无 BOM 写入（executor.py/test 文件/本说明）。
- ✅ 未改动 ui_config.py / interfaces.py / tables.py / models.py / settings.py / repo.py；
  config.py 本轮未触碰（无需追加字段）。
- ✅ 测试统一带 `--basetemp=".pytest-tmp-m5"`（P-001 + P-011 并行互清冲突规避）。

## 八、环境备注

- Python 3.13.14，pytest 9.1.1；控制台中文乱码为 GBK 显示问题，不影响功能与文件编码。
- 与并行子代理（投放设置）已完成 v0.3 集成联调：`run_batch` 通过真实 settings.py 全链跑通
  （test_run_batch_integration_with_real_settings），两者经 PageOps/ShopAdsUiConfig 契约对接，
  无需改任何接口。
