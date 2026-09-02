# Codex 攻坚任务书：CDP 环境触发淘宝以图搜款（识图上传）

## 背景

视频号小店全自动系统项目。我们要用"以图搜款"在淘宝找商品同款，然后扒同款商品详情页的多张主图（用于上架素材，替代 AI 生成）。

**已验证可行**：
- 淘宝网页登录态正常（cookie2/_tb_token_ 等存在）；
- 关键词搜索（s.taobao.com/search?q=...）能精准搜同款；
- 1688 详情页主图（cbu01.alicdn.com）可下载。

**卡点**：淘宝网页端"以图搜款"（识图上传）在 **CDP 连接的 Chrome** 环境下无法触发。已穷尽尝试：
1. s.taobao.com/image 直连 → 跳 error.taobao.com 错误页；
2. 首页搜索框相机图标（`[class*='image-search-icon-wrapper']`）JS 点击/真实 hover+click → 上传后 URL 停在 www.taobao.com，无识图 API 请求（只有埋点 mmstat image_choose），页面展示的是"猜你喜欢"推荐流（`tb-pick-content-item` 卡片混入显卡/内存条等无关商品）；
3. Playwright `expect_file_chooser` + `set_files`、CDP `DOM.setFileInputFiles` → 均无识图 API、不跳转；
4. Ctrl+V 粘贴图片（系统剪贴板 + keyboard.press）→ 无识图 API；
5. 手机 UA（TmallH5）→ 首页重定向 main.m.taobao.com，无识图入口；
6. 真实 Windows 文件对话框 + pywinauto → CDP 环境下系统对话框不弹出；
7. 输入图格式（webp→png 转换）→ 无关。

**用户环境**：用户在共享 Chrome 手动操作能弹出标准识图结果页（综合/销量/价格布局 + 精准同款），说明网页识图功能本身存在且可用，问题在自动化触发。

## 环境

- 共享 Chrome：`--remote-debugging-port=9223 --user-data-dir=E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\backend\data\chrome-profiles\shared`
- Playwright + CDP 连接：`pw.chromium.connect_over_cdp("http://127.0.0.1:9223")`
- Python 3.13 + pywinauto 0.6.9 已装
- 淘宝已登录（cookie 在共享 profile）
- 测试图：`E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\_experiment\pdd-scrape\data\tmp_taobao_input\22_clean.png`（洗衣粉，800x800 PNG）和 `1_clean.png`（锅刷）

## 目标

**找到一种可靠方式，在 CDP 连接的 Chrome 里触发淘宝网页端的以图搜款（识图上传→跳转标准结果页→能读同款商品链接），并给出可复用的 Playwright/Python 代码。**

## 方向建议（不限于此）

1. 研究淘宝识图上传的真实 API（抓包：上传文件后应该调用 `h5api.m.taobao.com` 的某个 mtop 接口，如 `mtop.taobao.picture.search` 或 `mtop.taobao.wireless.aotupicture.getPicSearchResult` 之类）——先摸清前端 JS 里识图组件的调用链；
2. 观察"搜同款"按钮（每个商品卡片 hover 出现 `搜同款`）——它可能是用商品图直接识图，不经文件上传，可能绕开上传注入卡点；
3. 研究 `Page.setInterceptFileChooserDialog` 与真实文件选择的组合；
4. 研究是否可通过 `Page.fileChooserOpened` 事件 + DOM.setFileInputFiles 在正确时机触发；
5. 检查网页 JS 里是否有把文件转 base64 上传的路径（识图组件可能用 XHR 传 base64 而非 file input）。

## 交付物

1. 一份分析文档：淘宝网页识图功能的完整实现机制（前端组件、真实 API、触发条件、为什么 CDP 注入失败）；
2. 可复用的 Python 脚本：能成功触发识图并返回同款商品链接（或明确说明不可行的证据 + 替代方案）；
3. 每步尝试都要有实际运行验证（不是纯理论）。

## 约束

- 只读/低频访问淘宝（防风控），间隔 3s+；
- 不写明文密钥；脚本放 `_experiment\pdd-scrape\codex-work\`；
- 完成后写一份 `REPORT.md` 总结：做了什么、结果、可复用的代码、仍卡住的原因。
