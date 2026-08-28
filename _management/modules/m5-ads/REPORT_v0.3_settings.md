# M5 自动小店投放（商品托管）· v0.3 投放设置交付说明

> 撰写人：M5 子代理（投放设置）｜ 日期：2025 体系建立日
> 范围：v0.3 执行层第二部分「投放设置」——托管两步之②：目标三选一 / 目标 ROI 填值 /
> 素材绑定 / 提交与页面校验。**当前只做抽象接口 + fixtures 模拟（Mock 页面），
> 不依赖真实登录态/真实浏览器**；真实 Playwright 适配器后续接入，接口不变。

## 一、交付文件清单

| 文件 | 说明 |
|---|---|
| `backend/ads/settings.py` | **本任务核心**：`SubmitResult`（dataclass）、`pick_materials`（素材优选纯函数）、`validate_submit`（提交校验纯函数）、`SettingsForm`（投放设置表单）、`MockSettingsPage`（PageOps Protocol 假页面，独立实现，不 import executor） |
| `backend/ads/config.py` | **仅尾部追加** 2 字段：`target_roi_override: float | None = None`（ADS_TARGET_ROI_OVERRIDE）、`roi_recommended_source: str = "system"`（ADS_ROI_RECOMMENDED_SOURCE）；既有字段零改动 |
| `backend/tests/test_ads_settings.py` | 25 个 Mock 驱动用例（fixtures 全部测试文件内自建，未改 conftest） |
| `_management/modules/m5-ads/REPORT_v0.3_settings.md` | 本交付说明 |

未创建/未改动：`executor.py`（并行子代理文件，不存在时不得创建）、
`ui_config.py`/`interfaces.py`/`tables.py`/`models.py`（v0.2 定稿，禁止改动）。

## 二、接口说明

### 2.1 `SubmitResult`（dataclass）
```python
@dataclass
class SubmitResult:
    passed: bool
    blocked_reason: str = ""   # 中文原因（展示/人工接管用）
    error_code: str = ""       # 复用 09 码表（blocked 场景统一 PLATFORM_REJECT）
```

### 2.2 `pick_materials(materials: list[dict], limit: int = 3) -> list[dict]`
素材优选纯函数：
- 只选 `upload_status == "approved"`（审核通过）素材；rejected（审核不通过）/ corrupt
  （源文件损坏）/ reviewing（审核中）/ uploading（上传中）一律排除（10 文档第三节）；
- 按 evaluation 优先级 **efficient(高效) > potential(潜力) > exploring(探索期)** 升序取前 limit；
  未知标签按最低优先级兜底（不排除）；
- 同级别按可选字段 `(impressions, gmv)` 降序**稳定排序**（缺失/None 视为 0，排同级末尾）；
- 返回保持输入 dict 字段结构（同引用，不裁剪不复制）。

### 2.3 `validate_submit(balance_fen, min_balance_fen, materials_ok, budget_state=None) -> SubmitResult`
提交前校验（08 文档四③ + 止损规则表 S5/S7）：
- 余额 < 阈值 → `blocked_reason="余额不足"`、`error_code="PLATFORM_REJECT"`；
- 素材不可用 → `blocked_reason="素材未过审/不可投放"`、`error_code="PLATFORM_REJECT"`；
- `budget_state={"over_limit": True, ...}`（预算三重硬约束 S7 上游计算结果）→
  `blocked_reason="预算超限"`、`error_code="PLATFORM_REJECT"`；
- 检查优先级：余额 > 素材 > 预算（同时命中上报优先级最高项）；全过 → `passed=True`。

### 2.4 `SettingsForm(page: PageOps, ui_config: ShopAdsUiConfig, target_roi_override=None)`
| 方法 | 行为 |
|---|---|
| `choose_target(target_type)` | 目标三选一：`roi`/`net_roi`/`goods`（英文枚举；中文映射 成交ROI/净成交ROI/商品成交 注释+evidence label）；非法枚举抛 ValueError；按 ui_config 对应单选选择器点击 |
| `fill_roi(roi)` | 填 settings_roi_input（两位小数格式化，如 2.00）；`roi ≤ 0` 抛 ValueError（高于类目上限由调用方控制，本层只做 >0 校验） |
| `read_recommended_roi()` | 读 settings_roi_recommended 系统推荐值；未配置/无元素/解析失败 → None（**扩展方法**，见偏差 2） |
| `resolve_roi(recommended_roi)` | 目标 ROI 取值策略：**可配置覆盖优先，否则系统推荐**；两者皆无抛 ValueError（**扩展方法**） |
| `bind_materials(material_ids)` | 按 settings_material_checkbox 模板逐素材勾选（`{mid}` 占位 format）；空列表抛 ValueError；evidence 记录每次勾选 + bind 汇总 |
| `submit()` | 点 settings_submit → 读 settings_error_banner：错误文本关键词匹配（余额不足 / 素材未过审/未通过审核/审核不通过/不可投放）→ blocked(PLATFORM_REJECT)；无错误/无 banner 元素 → passed=True；banner 选择器未配置或读取失败 → 抛 RuntimeError（**TIMEOUT 语义**，上层映射 09 码表 TIMEOUT） |

每步操作记录 evidence：`{"op", "selector", "ms"(耗时), "ts"(UTC ISO8601), ...}`。

### 2.5 `MockSettingsPage`（PageOps Protocol 假页面）
独立实现（与 executor 子代理 MockPageOps 解耦，不 import）。场景化脚本：
- `scenario="happy"`：全部操作成功，banner 文本空 → submit 通过；
- `scenario="error_banner"`：banner 预设「余额不足」（可用 `banner_text=` 覆盖，或
  `set_text(selector, text)` 精确指定文案）→ submit 返回 blocked；
- `scenario="missing_element"`：所有选择器操作抛 RuntimeError（模拟页面未加载/page_changed）；
  也可 `missing=[selector,...]` 精确指定缺失元素（`exists`→False，`count`→0，符合真实 DOM 语义）。

记录 `operations` 操作历史（goto/wait_for/click/fill/select_option/screenshot/close，含
selector/value/ms）；提供 `click_count(selector)` / `fill_value(selector)` 断言辅助；
查询方法（exists/read_text/read_attr/count）不写操作历史。`isinstance(mock, PageOps)`
通过（runtime_checkable Protocol 合规）。

## 三、与 ui_config / interfaces 对接说明

- **ui_config.py**：只读使用 `ShopAdsUiConfig.selectors` 的 settings_* 系列 key：
  `settings_target_roi` / `settings_target_net_roi` / `settings_target_goods` /
  `settings_roi_input` / `settings_roi_recommended` / `settings_material_row` /
  `settings_material_checkbox`（`{mid}` 模板占位）/ `settings_submit` /
  `settings_error_banner`。fixtures 阶段选择器值为空串时各操作抛明确 RuntimeError
  （提示注入选择器）；实机校准后填真实 CSS，本模块代码零改动（P-003）。
- **interfaces.py**：只读使用 `PageOps` Protocol（goto/wait_for/click/fill/select_option/
  read_text/read_attr/exists/count/screenshot/close）与 `PageChangedError` 语义
  （mock 元素缺失抛 RuntimeError，由上层统一映射 page_changed/人工接管）。
- **config.py**：`target_roi_override` 由执行器编排时注入 `SettingsForm.__init__`
  （覆盖优先）；`roi_recommended_source="system"` 预留后续来源扩展。
- **repo.py（v0.2）**：本任务不直接依赖（pick_materials 入参为 dict 列表，由执行器
  从 `list_materials`/`upsert_material` 结果映射），解耦更干净。

## 四、测试结果（backend 目录执行）

### 4.1 定向测试（验收标准 1）
```
python -m pytest tests/test_ads_settings.py -q --basetemp=".pytest-tmp"
25 passed in 0.10s
```
覆盖：pick_materials 6 例（优先级/排除未过审/limit 截断/同级稳定排序/空输入/无过审素材）、
validate_submit 5 例（余额不足/素材不可用/预算超限/全过/优先级）、SettingsForm 11 例
（目标三选一与非法、ROI 填值正常与 ≤0 报错、素材绑定与空列表报错、submit happy path
全流程、余额不足 banner → blocked、素材未过审 banner（两种文案）→ blocked、banner 选择器
未配置 → TIMEOUT RuntimeError、通用错误文本 → blocked、系统推荐/覆盖策略、evidence 留痕）、
MockSettingsPage 2 例（冒烟+Protocol 合规、元素缺失）、config 追加字段 1 例。

### 4.2 全量测试（验收标准 2）
```
python -m pytest tests -q --basetemp=".pytest-tmp"
361 passed, 1 skipped in 27.67s     （连续两轮复跑一致，0 failed）
```
全量**无任何失败**（含既有 M0 foundation 用例，本轮未复现历史环境性失败——见偏差 4）。
期间曾出现一次 195 个 PermissionError ERROR：与并行子代理（托管执行器）同跑 pytest
争用同一 `.pytest-tmp` basetemp 的 Windows 文件锁冲突（P-001 同源，WinError 32），
错开运行后连续两轮全绿，判定为瞬时环境冲突，非代码问题。

### 4.3 ads 包协同（本模块三测试文件）
```
python -m pytest tests/test_ads_settings.py tests/test_ads_repo.py tests/test_ads_tables.py -q --basetemp=".pytest-tmp"
52 passed in 1.78s
```

### 4.4 import 验收（验收标准 3）
```
python -c "from ads.settings import SettingsForm, pick_materials, validate_submit, MockSettingsPage"   → 无错
```

## 五、验收标准对照

| # | 标准 | 结果 |
|---|---|---|
| 1 | 定向 pytest 全绿（带 `--basetemp=".pytest-tmp"`） | ✅ 25 passed |
| 2 | 全量无新增失败 | ✅ 361 passed / 1 skipped / 0 failed（连续两轮） |
| 3 | `from ads.settings import ...` 无错 | ✅ |
| 4 | 无真实浏览器依赖（无 playwright 连接调用） | ✅ 全 Mock 驱动，settings.py 零 playwright import |
| 5 | 纪律项全部满足 | ✅ 见第七节 |

## 六、偏差说明

1. **无功能偏差**：任务书要求的方法/常量/枚举/错误码全部按规格实现。
2. **扩展方法（属任务意图内实现）**：`read_recommended_roi()` 与 `resolve_roi()` 实现
   「目标 ROI 填值：系统推荐优先/可配置覆盖」（08 文档四②）的取值策略，供执行器编排
   时调用（`effective = form.resolve_roi(form.read_recommended_roi())` → `fill_roi`）；
   不改动任务书列出的 4 个必需方法语义。
3. **ROI 填值格式化**：`fill_roi` 统一两位小数（`2.5 → "2.50"`），对齐后台展示口径
   （如 2.00）；ROI 为浮点倍数，**不走「分」**（金额才走分，DA-001）。
4. **全量既有失败未复现**：v0.2 记录的环境性失败（foundation 5~7 例）本轮全量未复现
   （361 passed 0 failed），与本任务无关；本任务未改动任何 foundation/materials 文件。
5. **`MockSettingsPage` 独立实现**：按任务要求不 import executor 的 MockPageOps；
   交互契约（PageOps Protocol）与 ui_config key 完全对齐，v0.3 集成时可直接互换。
6. **config 环境变量命名**：任务书指定 ADS_ 前缀（`ADS_TARGET_ROI_OVERRIDE`），
   context README 中的 `M5_ADS_TARGET_ROI_OVERRIDE` 为模块级命名，字段注释已说明映射关系。

## 七、纪律核对

- ✅ 禁 git：全程未执行任何 git 命令。
- ✅ 一模块一库：未连接/写入任何数据库（本任务纯函数+Mock，无 DB 访问；
  测试零 DB fixture，仅 config 字段默认值断言）。
- ✅ 禁新增表：未触碰 tables.py，无任何建表/迁移。
- ✅ 禁明文密钥：无凭证字段/代码/文档。
- ✅ 金额分 int、时间 UTC 带时区（evidence `ts` 用 `datetime.now(timezone.utc).isoformat()`）、
  枚举英文（target_type=roi/net_roi/goods；evaluation 与 M2 共口径）、error_code 复用 09 码表。
- ✅ 中文文件全部 write 工具 UTF-8 无 BOM 写入（本说明/settings.py/test 文件）。
- ✅ 未改动 ui_config.py / interfaces.py / tables.py / models.py；config.py 仅尾部追加；
  未创建/import executor.py。
- ✅ 测试均带 `--basetemp=".pytest-tmp"`（P-001）。

## 八、环境备注

- Python 3.13，pytest 全量 361 用例 27s 级。
- 控制台中文乱码为 GBK 显示问题，不影响功能与文件编码。
- 与并行子代理（托管执行器）共享工作区：请总工在 executor 子代理完成后统一跑
  `tests/test_ads_executor.py + tests/test_ads_settings.py` 做 v0.3 集成验收，
  两者通过 PageOps/ShopAdsUiConfig 契约对接，无需改本模块接口。
