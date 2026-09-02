# 淘宝 CDP 以图搜款验证报告

## 结论

已在 `http://127.0.0.1:9223` 的共享 Chrome 上复现成功。关键不是文件选择器或 `DOM.setFileInputFiles` 的兼容性，而是首页组件有**两阶段状态机**：

1. 相机图标打开面板，向隐藏的 `#image-search-custom-file-input` 注入 PNG/JPEG；
2. 组件用 `FileReader` 和 canvas 压缩图片，按钮变为 `#image-search-upload-button.upload-button-active`，文字从“上传图片”变为“搜索”；
3. 必须再次点击该“搜索”按钮。该点击会打开 `s.taobao.com/search?...&imgSearchOrigin=https://www.taobao.com`；
4. 首页和结果页经 `window.opener`/`postMessage` 传递压缩后的图片数据；结果页调用图片搜索请求并渲染商品卡片。

此前的 `set_files`、`DOM.setFileInputFiles`、剪贴板和系统文件对话框尝试都只覆盖了第 1 阶段，因此只看到 `image_choose` 埋点或首页推荐流，没有发生结果页跳转。

## 可复用脚本

脚本：`taobao_image_search_cdp.py`

```powershell
& 'C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe' `
  .\taobao_image_search_cdp.py `
  '..\data\tmp_taobao_input\22_clean.png'
```

脚本会连接既有的 CDP Chrome，创建并关闭自己的首页/结果页标签，不输出 cookie、token 或请求签名。标准输出为 JSON：`result_url` 和去除跟踪参数后的 `product_urls`。

约束已固化：只接受 PNG/JPG/JPEG；首页加载后等待 3 秒；等待按钮获得 `upload-button-active` 后才点击第二次；默认超时 30 秒。

最终交付脚本在 `22_clean.png` 上再次运行成功，退出码为 `0`，结果 URL 含
`localImgKey=localImgSearchKey...`，并返回 57 个去跟踪参数后的详情页 URL。

## 输入文件被动分诊

执行前仅做了目录清单、SHA-256 与固定长度头部读取，未执行任何输入文件。

| 相对路径 | 大小 | SHA-256 | 格式/决定性证据 | 置信度 | 后续动作 |
|---|---:|---|---|---|---|
| `../data/tmp_taobao_input/22_clean.png` | 420,658 | `59D3D9A2DF78F41C97054CA033CCE63D5BBA9F4FBDCF1B47A43CB2C57663B44C` | PNG；头部 `89 50 4E 47 0D 0A 1A 0A`；IHDR 为 800x800 | 高 | 作为首页隐藏 file input 的输入。 |
| `../data/tmp_taobao_input/1_clean.png` | 830,383 | `654B541BD6CEDB01D6F1C6820BBA71686B4B107A554CA55C236C93BA135FA256` | PNG；同一输入目录 | 高 | 作为第二张独立验证图。 |

## 实际运行验证

环境：Chrome `152.0.7977.64`，Playwright Python，CDP `127.0.0.1:9223`。

| 输入 | 观察到的阶段 1 | 阶段 2 / 结果 |
|---|---|---|
| `22_clean.png`（420,658 bytes，SHA-256 `59D3D9A2DF78F41C97054CA033CCE63D5BBA9F4FBDCF1B47A43CB2C57663B44C`） | 按钮文字为“搜索”，class 为 `upload-button upload-button-active` | 弹出标准 `s.taobao.com/search` 结果页，读取到 20 个商品详情链接；首个为 `https://item.taobao.com/item.htm?id=876153751740`。 |
| `1_clean.png`（830,383 bytes，SHA-256 `654B541BD6CEDB01D6F1C6820BBA71686B4B107A554CA55C236C93BA135FA256`） | 同一隐藏 file input 与激活按钮状态 | 弹出标准结果页，读取到商品详情链接；首个为 `https://item.taobao.com/item.htm?id=1000360925578`。 |

连续以图搜索之间均等待至少 3 秒。第二次验证的结果 URL 包含 `localImgKey=localImgSearchKey...` 和 `spm=...search_image.image_search_button`，并非首页“猜你喜欢”卡片。

## 前端实现机制

### 首页组件

证据文件：`evidence-main-search.bundle.js`，来自
`https://g.alicdn.com/main-search/new-search-suggest/2.14.6/bundle.js`，292,728 bytes，SHA-256 `C72DBF975639B404C97D745F61874731B689933B732E323F847ACB7991DD0CEE`。

- DOM 契约：`[data-spm="image_search_icon"]`、`#image-search-custom-file-input`、`#image-search-upload-button`。
- `change` 事件进入 `_onUpLoadStart -> _readFile`；只接受 `image/png`、`image/jpg`、`image/jpeg`。
- 图片先被 `FileReader.readAsDataURL` 和 canvas 压缩，成功后组件状态置为 `success`，并显示第二阶段“搜索”按钮。
- 默认 `imgSearchJumpDataMode` 是 `postMessage`；首页第二次点击调用 `_jumpModePostMessage`，先注册 message listener，再 `window.open` 结果页。
- 存在 CDN 备用路径：`ImageSpaceUploader({appkey: "tblife2_ugc"})` 上传 base64 后带 `imgSearchUrl` 跳转；本次 Windows Chrome 的实际分支是 `postMessage`，没有走该备用上传器。

### 结果页与真实图片搜索请求

证据文件：`evidence-pc-search.main.js`，来自
`https://g.alicdn.com/main-search/pc-search-2024/1.8.54/js/main.js`，5,114,899 bytes，SHA-256 `AFFD45C9FF2C9F31F92E8DF06C142CA31E398F61977799D12077FC6D80A453B4`。

1. 结果页识别 `imgSearchOrigin`，向 opener 发出 `onSearchSuggestPageInit`；首页随即 postMessage `{img: compressedImageData}`。
2. 结果页把压缩图片写到 sessionStorage，并把 URL 更新为 `localImgKey`；随后触发 `START_IMG_SEARCH_OUTSIDE`。
3. `getImgList` 将压缩后的 data URL 编码为 `strimg`，并调用 MTOP：
   `mtop.relationrecommend.wirelessrecommend.recommend`，版本 `2.0`，POST，`appId: "46006"`，请求参数含 `m: "pc_picture_search"`、`page`、`pageSize`、`strimg`、`ttid`、`imgFrom`、`pageFrom`。
4. 当前脚本不自行构造 MTOP 签名或重放 API；页面自身的 `window.lib.mtop.request` 使用已登录共享 profile 的运行时上下文完成请求。这正是 CDP 下最稳定、最少耦合的路径。

## 为什么 CDP 注入此前看似失败

`set_input_files` 本身是有效的：运行中已经观察到按钮变为 `upload-button-active`。隐藏 input 的 value 随 UI 成功态被清空，因此读取 value 为空不是失败证据。真正的完成条件是按钮 class/文字和随后第二次点击产生 popup。

CDP 不会阻断 `window.open` 或 postMessage；本次成功证明连接模式不是根因。若第二阶段没有等待 canvas 压缩完成就点击，组件仍处于非 `success` 状态，点击逻辑只会再次执行 `input.click()`，表现为“没有识图 API、没有跳转”。

## 后续接入建议

调用脚本返回的 `product_urls` 后，再用现有详情页主图下载流程逐个处理。每张新图搜索之间保留至少 3 秒，并复用同一个共享 profile。若页面版本更新，优先检查上述三个 DOM selector 和 `upload-button-active` 状态，而非改用原始 MTOP 重放。
