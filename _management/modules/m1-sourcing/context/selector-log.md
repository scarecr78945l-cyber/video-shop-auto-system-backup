# M1 自动选品 · 选择器校准记录（selector-log）

> 版本：v1.1 ｜ 初始撰写：S3a 子代理（fixtures 对照，不依赖登录态）｜ S3b 子代理（2026-08-29）实施 A1~A4 并更新状态
> 目的：对照 `backend/sourcing/config.py` 与采集器代码 `backend/sourcing/collectors/*.py`，
> 校准 5 个来源的 URL 模板 / 选择器配置 / fixtures 字段映射，登记「待实测项」——
> 登录态就绪后在真实页面用 `inspect-page` 验证的选择器清单。
> **本次未运行任何真实采集（collect --mode auto 需登录态），未读取 cookie/localStorage/凭据。**
> 关联风险：R-20~R-25、P-003。

---

## 0. 全局结论（5 来源一致项）

1. **`config.py` 中 5 个来源的 `selectors` 已全部迁入（S3b/A1）** —— 与采集器内置 `DEFAULT_SELECTORS` 逐键一致（youmi/doudian 除 columns 外）；采集器构造时 `{**DEFAULT_SELECTORS, **config.selectors}` 合并，config 与默认同值 → 行为零变化。**改配置即可改选择器（R-23 完全落地）**；youmi/doudian 的 columns 刻意不进 config → 动态表头定位生效（A4）。
2. 各采集器 `probe()` / 登录态 gate 均用 `selectors["login_gate"]` / `["verify_gate"]`（默认选择器），config 无覆盖。
3. fixtures 字段结构（`fixtures/*.json`）与 `SourceItem` 字段一一对应（`platform_item_id/title/price/sales/rank/category/image_urls`，见 `collectors/fixtures.py collect_board`），**fixtures 模式与真实采集器的字段口径一致**（价格=元、销量=件，R-31 满足）。
4. `detect_page_changed` 当前仅在 **youmi / alibaba / taobao** 三处被调用；**opportunities 用 row.count()==0、doudian 用 row.count()<2 替代**（各自语义见下）。

---

## 1. 视频号商机中心（opportunities）

- **URL 模板**（config.boards[0]）：`https://store.weixin.qq.com/shop/goods/opprotunity`（机会品，唯一 board）
- **config.selectors 键清单**：`（空）`
- **采集器实际使用键**（`collectors/opportunities.py` DEFAULT_SELECTORS）：`home_url`、`row`=`table tbody tr`、`columns`={title:0, source:1, status:2}、`login_gate`=`[class*='login']`、`verify_gate`=`[class*='captcha'], [class*='verify']`
- **实际取数逻辑**：`_collect_from_page` 用 `row` 选择器 → 每行 `td` 按 `columns` 取 title(source 列进 raw)；`rank`=行序+1；**price/sales 恒为 0**（页面表格列：商品(0)/商机来源(1)/状态(2)/操作(3)，无价格/销量列）；`category` 恒为 `""`；`image_urls` 取行内前 4 张 http 图。改版检测用 `row.count()==0 → PAGE_CHANGED`（**未调用 detect_page_changed**）。
- **fixtures 字段映射**（opportunities.json → SourceItem）：`platform_item_id/title/price/sales/rank/category/image_urls` 直接映射（fixtures 采集器）。
- **现状评估**：配置齐全性 **基本齐全（仅代码默认，config 未迁移）**；结构与代码注释一致。注意：真实采集器产出的 `price/sales` 恒 0、`category` 恒空 → 该源对 trend 维度只贡献 rank/board_count（设计如此），**与 fixtures 中带 price/sales/category 的样本存在口径差异（R-25 漂移点）**。
- **待实测项**（登录态就绪后，`inspect-page --source opportunities`）：
  1. `table tbody tr` 是否命中机会品表格行（非零 count）；
  2. 列索引 title=0 / source=1 / status=2 与真实表头是否一致；
  3. `login_gate`/`verify_gate` 在未登录/验证码页是否可见；
  4. 行内 `<img>` 是否可提取真实图片 URL（src 或 data-src 是否为 http）；
  5. 弹窗 `_dismiss_modals` 的 modal/dialog 类名是否仍覆盖真实升级公告。

### 实测结果（S3c · 真实采集，子代理 S3c）
> 前置：CDP 9223 曾因僵尸页面（商机中心 home / 罗盘核心数据页）导致 playwright connect_over_cdp 挂起（见 pitfall-log P-016），关闭多余页面后恢复；登录态有效。
> 采集：`collect_board(机会品, limit=50)`，**成功入库 1 条**（当前类目筛选下机会品仅 1 条），状态 active，无 AUTH_REQUIRED/验证码。
1. `table tbody tr` **命中**（count=1，非零）✓；
2. 列索引 title=0 / source=1 / status=2 **命中**（title 正确、商机来源列文本写入 raw）✓；
3. `login_gate`/`verify_gate` **未触发**（登录态有效）✓；
4. 行内 `<img>` 提取 **命中**（imgs=2，真实 http 图片 URL）✓；
5. `_dismiss_modals` **工作正常**（无弹窗遮挡导致空采）✓；
6. **R-25 漂移点确认**：真实样本 price=0.0 / sales=0 / category='' 恒空（表格列仍为 商品(0)/商机来源(1)/状态(2)/操作(3)，无价格/销量/类目列）——与 fixtures 中带 price/sales/category 的样本口径不一致。**A5 建议维持成立**（该源对 trend 只贡献 rank/board_count，设计如此；若商机来源列含价格区间信息可后续扩展 columns，本次未改代码）。
7. 观察：机会品条数取决于页面当前类目筛选（本次仅 1 条）；如需多量采集需人工切换筛选或扩展多筛选遍历（后续建议，本次未改）。

---

## 2. 有米云（youmi）

- **URL 模板**（config.boards[0]）：`https://console.youshu.youcloud.com/goods/sale?site_id=10502&startDate={start_date}&endDate={end_date}`（商品榜；**日期参数已占位符化，S3b/A2**：导航时按 lookback_days 动态生成，end=当天、start=当天-7，不再硬编码过期日期）
- **config.selectors 键清单**：`（空）`
- **采集器实际使用键**（`collectors/youmi.py` DEFAULT_SELECTORS）：`home_url`、`row`=`.el-table__body-wrapper tr`、`columns`={rank:0, title:1, price:5, sales:7}、`next_page`=`.el-pagination .btn-next, .el-pagination__next`、`login_gate`、`verify_gate`
- **实际取数逻辑**：`_collect_from_page` 先查 login/verify gate → `detect_page_changed(page, [row])` → 逐行 `td` 按 columns 取数（cell 用 textContent 兼容 el-popover 隐藏标题）→ `parse_num` 支持 万/亿 → 翻页 `next_page` 最多 30 页。**注意：`_locate_columns` 的动态表头定位（未配置 columns 时）因 DEFAULT_SELECTORS 恒提供 columns 而成为死代码**——columns 固定 0/1/5/7，改版需改代码或 config。
- **fixtures 字段映射**：全字段直接映射（youmi.json，含 `image_phash` 进 raw）。
- **现状评估**：配置齐全（代码默认）；列索引为实测值（代码注释记录实测页面列：#(0) 商品(1) 价格(5) 新增销量(7) 累计销量(10)）；**URL 日期参数已动态化（A2）**；动态列定位分支已启用（A4，config.selectors.columns 留空时按表头自动定位）。
- **待实测项**（`inspect-page --source youmi`）：
  1. `console.youshu.youcloud.com/goods/sale` 打开后 `.el-table__body-wrapper tr` 是否命中；
  2. 列索引 title=1 / price=5 / sales=7 与真实表头顺序是否一致（重点：新增销量 vs 累计销量口径）；
  3. `next_page` 翻页按钮选择器是否可点；
  4. 标题 el-popover textContent 提取是否仍成立；
  5. `login_gate`/`verify_gate` 触发行为。

### 实测结果（S3c · 真实采集，子代理 S3c）
> 前置：CDP 9555 独立浏览器连接正常；页面 URL 显示 `startDate=2026-08-23&endDate=2026-08-29`（**A2 动态日期已生效**，lookback_days=7：end=当天、start=当天-7）。
> 采集：`collect_board(商品榜, limit=50)`，**成功入库 50 条**，状态 active，throttle 0/连续失败 0，无 AUTH_REQUIRED/验证码。
1. `.el-table__body-wrapper tr` **命中**（50 条真实行）✓；
2. **动态列定位 `_locate_columns` 命中**（A4 生效：config.selectors 无 columns → 按表头动态定位，title/price/sales 取值正确）✓——price 范围 0.01~69.9（元）、sales 范围 10万~162万（件），口径与 fixtures 一致；
3. `next_page` 翻页 **可点且生效**（50 条跨越 rank 1~52 多页，到达 limit 后停止）✓；
4. 标题 textContent 提取 **成立**（el-popover 隐藏标题正常取到完整真实标题）✓；
5. `login_gate`/`verify_gate` **未触发** ✓；
6. **新观察（需收敛）**：`_extract_images` **imgs=0**——行内 `<img>` 未提取到 http 开头的图片 URL（真实页面商品图可能 lazy 加载、data-src 非 http 或使用 blob/相对路径），与 fixtures 中带 image_urls 的样本不同。建议后续用 `inspect-page --source youmi` 检查商品图 DOM 结构（图片选择器收敛，本次未改代码）；
7. 观察：youmi rank 列取值跳号（本次 rank=21/46 缺失，共 50 条 max rank=52）——因页面存在重复标题行被 `seen` 去重跳过，属正常去重行为，非缺陷。

---

## 3. 抖店电商罗盘（doudian）

- **URL 模板**（config.boards）：商品榜=`https://compass.jinritemai.com/shop/chance/rank-product`；**飙升榜=`""`（空，未配置）** → 采集飙升榜时回退 `current_page("compass.jinritemai.com")` 读当前页
- **config.selectors 键清单**：`（空）`
- **采集器实际使用键**（`collectors/doudian.py` DEFAULT_SELECTORS）：`home_url`、`row`=`.aurora-table-tbody tr`、`columns`={title:1, sales:5}、`next_page`=`.aurora-pagination-next, [class*='pagination'] [class*='next']`、`login_gate`、`verify_gate`
- **实际取数逻辑**：查 login/verify gate → 改版检测用 **`row.count() < 2`（Aurora 首行是隐藏表头，不能用 is_visible，故未用 detect_page_changed）** → `_locate_columns`（同 youmi，默认 columns 短路动态定位，另 `setdefault("pay", 3)`）→ 逐行：跳过表头行（head0=="排名"）、title 取 col1、`price` 优先 `price_from_title`（标题「价格带 ¥XX」）否则 `parse_num(pay 列)`、sales=col5（成交件数，区间取最小）。
- **fixtures 字段映射**：全字段直接映射（doudian.json；含「商品榜」+「飙升榜」——**飙升榜 3 条样本已由 S3b/A3 补齐**，fixtures 采集器可回放）。
- **现状评估**：商品榜配置齐全（代码默认）；**飙升榜 fixtures 数据已补全（S3b/A3），真实 URL 模板仍待登录态回填**（board 存在时 url_template 为空 → 回退 current_page 读当前页）；Aurora 表格选择器 `.aurora-table-tbody tr` 为代码注释实测值，需真实验证；动态列定位已启用（A4）。
- **待实测项**（`inspect-page --source doudian`）：
  1. 商品榜页 `.aurora-table-tbody tr` count ≥ 2（含隐藏表头行）；
  2. 列索引 title=1 / sales=5 与真实表头顺序（排名/商品/店铺/支付金额/点击/成交件数/转化率）；
  3. 「价格带 ¥XX」是否仍在标题文本中（price_from_title 依赖）；
  4. `next_page` 选择器可点性；
  5. **飙升榜 URL 模板补全**（登录态就绪后从页面地址栏取真实 URL 回填 config.boards[1].url_template）；
  6. `login_gate`/`verify_gate` 触发行为。

### 实测结果（S3c · 真实采集，子代理 S3c）
> 前置：与商机中心同享 CDP 9223（僵尸页面清理后 playwright 连接恢复）；登录态有效。
> 采集：`collect_board(商品榜, limit=50)`，**成功入库 50 条**，状态 active，throttle 0/连续失败 0，无 AUTH_REQUIRED/验证码。
1. `.aurora-table-tbody tr` **命中**（50 条真实行，含隐藏表头行处理正常）✓；
2. **动态列定位 `_locate_columns` 命中**（config 无 columns → 表头动态定位；title=商品列、sales=成交件数列正确，shop=店铺列写入 raw）✓；
3. 「价格带 ¥XX」解析 **50/50 命中、0 失败**（price_from_title 完全生效：price 范围 15.0~1580.0 元，均来自标题价格带）✓；
4. `next_page` 翻页 **可点且生效**（50 条跨多页，到达 limit 后停止）✓；
5. **飙升榜 URL 模板未验证**（本次仅采商品榜；config.boards[1].url_template 仍为空，**A3 待总工安排**：登录态就绪后从页面地址栏取真实 URL 回填）；
6. `login_gate`/`verify_gate` **未触发** ✓；
7. 观察：真实样本 category 恒空（罗盘页面无类目列）；imgs=2（行内图片提取命中）；rank 1~50 连续（无跳号）。

---

## 4. 1688 询价（alibaba）

- **URL 模板**：config.boards 空；代码兜底 `selectors.get("home_url", "https://www.1688.com")`（DEFAULT_SELECTORS **无 home_url 键**，靠兜底常量）
- **config.selectors 键清单**：`（空）`
- **采集器实际使用键**（`collectors/alibaba.py` DEFAULT_SELECTORS）：`search_input`、`search_btn`、`image_upload`=`input[type='file'], .upload-btn`、`result_row`=`.card-item, [class*='offer'] li`、`result_title`、`order_price`=`.order-price, .price-box, [class*='price']`、`supplier_name`、`confirm_btn`、`login_gate`、`verify_gate`
- **实际取数逻辑**：`quote()` 新开页 → goto 1688 → login gate 检查 → **有图则以图搜款（`upload.set_input_files_from_url(item.image_urls[0])`，Playwright 较新 API）**，无图则标题搜索 → `detect_page_changed(page, [result_row])` → 结果行遍历：取 link/title/supplier → 进商品页 → 点 `confirm_btn`（订单确认页）→ 读 `order_price` → `_parse_price` 取首个数字 → Quote（raw_url=page.url）。**只读不下单（R-53）**。
- **fixtures 字段映射**：alibaba_quotes.json 按 `platform_item_id` → `Quote(supplier_name/sku_name/unit_cost/min_order/freight/raw_url)` 列表（fixtures.py FixtureQuoteCollector）。
- **现状评估**：配置齐全（代码默认）；选择器多为**宽泛模糊类名**（`[class*='price']`/`[class*='title']`）易误匹配，且未经真实页面验证；`set_input_files_from_url` 依赖以图搜款上传控件存在。**本源是最需要真实页面校准的补全源**。
- **待实测项**（`inspect-page --source alibaba` / 登录态就绪后手工链路验证）：
  1. 1688 首页 `image_upload` 上传控件选择器是否命中「以图搜款」入口；
  2. `set_input_files_from_url` 在该控件上是否可用（Playwright 版本兼容性）；
  3. 搜索结果 `result_row`（`.card-item, [class*='offer'] li`）是否命中真实 offer 卡片；
  4. 商品页 `confirm_btn` 是否命中「立即订购/确认」按钮（进入订单确认页的入口）；
  5. 订单确认页 `order_price` 是否命中单价元素（不下单，仅读价）；
  6. `login_gate` 未登录页触发行为。

---

## 5. 淘宝参考素材（taobao）

- **URL 模板**：config.boards 空；代码兜底 `selectors.get("home_url", "https://www.taobao.com")`（DEFAULT_SELECTORS 无 home_url 键）
- **config.selectors 键清单**：`（空）`
- **采集器实际使用键**（`collectors/taobao.py` DEFAULT_SELECTORS）：`search_input`、`search_btn`、`result_row`=`.items .item, [class*='item']`、`result_title`、`image`=`img`、`next_page`=`.next, [class*='next']`、`login_gate`、`verify_gate`
- **实际取数逻辑**：`quote()` 新开页 → goto taobao → login gate → 标题搜索 → `detect_page_changed(page, [result_row])` → 全页 `img` 收集 src/data-src（http 且去重，最多 max_images=12）→ 翻页最多 5 页 → 返回 `[{"kind": "reference_images", "urls": [...]}]`。
- **fixtures 字段映射**：taobao_references.json 按 `platform_item_id` → `{"images": [...]}`（fixtures.py 返回同结构）。
- **现状评估**：配置齐全（代码默认）；**选择器过于宽泛**（`[class*='item']`、`image="img"` 全页抓图可能收集导航/广告图），需真实页面收敛；淘宝反爬（滑块 `verify_gate`）风险高（R-05）。
- **待实测项**（`inspect-page --source taobao`）：
  1. 搜索结果页 `result_row`（`.items .item`）是否命中真实结果条目；
  2. `image="img"` 抓到的图片是否以商品主图为主（需排除 logo/广告图策略）；
  3. `next_page`（`.next`）翻页按钮可用性；
  4. 未登录/滑块触发时 `login_gate`/`verify_gate` 是否可见（决定 AUTH_REQUIRED/VERIFICATION_REQUIRED 分类是否正确）；
  5. 搜索页 URL 变化是否需要 `home_url` 显式配置。

---

## 6. 校准动作建议（S3b 已实施 A1~A4；S3c 已实测验证 A2/A4/A5 结论，A6 待后续）

> S3b（2026-08-29）已完成不依赖登录态的 4 项代码级动作：A1/A2/A3/A4，详见下方状态列。
> 对应代码：`backend/sourcing/config.py`、`collectors/{youmi,doudian}.py`、`backend/fixtures/doudian.json`、
> 新增测试 `backend/tests/test_collector_config.py`（17 用例，sourcing 域 108 全绿）。
> **S3c（2026-08-29，真实采集联调）**：三源真实采集验证 A2（动态日期生效）/A4（动态列定位命中）/A5（恒空确认），新增 youmi 图片提取收敛建议（见 A6 行下方注）。

| # | 动作 | 来源 | 状态 | 说明 |
|---|---|---|---|---|
| A1 | config.selectors 迁移 | 全部 | ✅ 已完成（S3b） | 5 来源 DEFAULT_SELECTORS 逐键迁入 `config.py` 各来源 `selectors`（键值一致，R-23 落地）；youmi/doudian 刻意**不含 columns**（见 A4）；`CollectorConfig.selectors` 类型改为 `dict[str, Any]`（承载 columns int 值）；代码内 DEFAULT_SELECTORS 保留兜底，合并 `{**DEFAULT_SELECTORS, **config.selectors}` 不变 → 行为零变化（测试验证合并结果与纯默认一致） |
| A2 | 有米云 URL 日期动态化 | youmi | ✅ 已完成（S3b）+ ✅ 实测生效（S3c） | config.boards[0].url_template 改为 `startDate={start_date}&endDate={end_date}` 占位符；采集器导航时 `render_board_url` 替换（end=当天、start=当天-lookback_days，`CollectorConfig.lookback_days` 默认 7 可配）；无占位符模板原样使用。**S3c 实测**：真实页面 URL 显示 `startDate=2026-08-23&endDate=2026-08-29`（lookback_days=7 生效） |
| A3 | 飙升榜 URL 补全 | doudian | ✅ fixtures 样本已完成（S3b）/ 🔲 真实 URL 待登录态回填 | `fixtures/doudian.json` 已补「飙升榜」3 条样本（dd-101~103，字段与商品榜同构，fixtures 采集器可直接回放）；config.boards[1].url_template **保持空**——登录态就绪后从页面地址栏取真实地址回填（S3c 仅采商品榜，未回填，仍待总工安排） |
| A4 | 动态列定位死代码 | youmi/doudian | ✅ 已完成（S3b）+ ✅ 实测命中（S3c） | `_locate_columns` 改为只认 `config.selectors.columns`（config 为空/缺键 → 走动态表头定位，DEFAULT_SELECTORS.columns 不再短路）；config 配置了 columns 时用配置值（保持现状）；mock 表头单测覆盖动态定位与配置覆盖。**S3c 实测**：youmi 与 doudian 均以动态定位成功取数（title/price/sales 列正确） |
| A5 | 商机中心 price/sales/category 恒空 | opportunities | ✅ 实测确认（S3c，维持现状） | **S3c 实测**：真实样本 price=0/sales=0/category='' 恒空（表格列仍为 商品/商机来源/状态/操作，无价格/销量/类目列）→ 维持「该源只贡献 rank/board_count」设计；若后续想利用商机来源列信息可扩展 columns（本次未改） |
| A6 | alibaba/taobao 宽泛选择器收敛 | alibaba/taobao | 🔲 待登录态实测 | 登录态就绪后按 inspect-page 结果收窄（优先级最高）。**S3c 新增观察（youmi 图片，非三源代码改动）**：有米云 `_extract_images` 在真实页面 **imgs=0**（行内 img 未取到 http URL，疑似 lazy/blob），建议后续 inspect-page 检查商品图 DOM 后收窄图片选择器；商机中心 imgs=2、抖店罗盘 imgs=2 均命中 |
