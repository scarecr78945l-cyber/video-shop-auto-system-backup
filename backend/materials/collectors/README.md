# M2 采集器侧封装（collectors）· TikTokDownloader 二次封装

> 交付：`tiktok_wrapper.py`（`TikTokDownloaderCLI` / `TikTokDownloaderError`）。
> 定位（context/README.md 2.1 + risks R-M2-04）：抖音/快手/小红书批量下载的
> **外部 CLI 进程封装**（子进程 + 超时 + 输出解析 + 错误分类），与下载中台解耦——
> 本封装只产出下载文件清单，任务账本（`asset_download_jobs`）由下载中台/上层管理。

## 〇、范围声明（重要）

**本封装只覆盖抖音/快手/小红书，视频号不在本封装范围（R-M2-05）。**
TikTokDownloader 对视频号支持弱（主流版本主打抖音/快手/小红书），视频号素材由
**自研视频号采集器**（批次 3，页面层 + `signer.py` 直链解析层）承担，与本封装无关。

## 一、外部契约与调用方式

- 调用方式：`subprocess.run` 外部 CLI + 超时（`timeout_seconds` 默认 300，可配）+ 输出解析；
- 输出：文本模式（含「文件名/作品标题/作者/作品链接」等关键字）与 JSON 模式双兼容；
- 结果条目：`[{file_path, title, author, platform, source_url}]`，字段口径对齐
  context/README.md 数据字典（`source_platform` 取值：`douyin`/`kuaishou`/`xiaohongshu`）；
- 失败分类（对齐 `backend/materials/downloader.py` 码表，详见第五节）；
- 二进制探测：`check_available()` 返回 `{available, version, error}`，缺失**不抛异常**，
  供上层降级（如跳过该来源、不阻塞全链路，R-M2-05 失败隔离）。

## 二、版本锁定与安装（★本机未安装 → fixtures 模式）

- **环境事实（已探测）**：本机未安装 TikTokDownloader（pip 无）。按总控指示，本封装采用
  「**锁定版本设计封装 + fixtures 测试**」：封装接口完整实现（含安装校验与版本锁定逻辑），
  真实二进制**不安装、不下载**；测试全部走临时 fake CLI fixtures（模拟 TikTokDownloader
  输出格式），零真实依赖、零外网（R-M2-17）。对接真实二进制由集成环境执行。
- **推荐版本线**：`TikTokDownloader 4.1.x`（Evil0ctal/TikTokDownloader，PyPI 包名
  `TikTokDownloader`；4.x 为当前稳定主线）。精确小版本以集成时 PyPI 实际可用为准，
  用 `pip index versions TikTokDownloader` 核对后固定。
- **安装命令（示例）**：
  ```bash
  pip install "TikTokDownloader==4.1.x"          # 锁定精确版本（x 以核对结果为准）
  ```
- **requirements 锁定**：`backend/requirements.txt` 追加固定行
  `TikTokDownloader==4.1.x`（精确版本，禁止 `>=`/`~=` 浮动）。
- **配置联动**：`MATERIALS_TIKTOK_BINARY`（可执行路径，None=走 PATH 探测）、
  `MATERIALS_TIKTOK_TIMEOUT_SECONDS`、`MATERIALS_TIKTOK_OUTPUT_DIR`、
  `MATERIALS_TIKTOK_VERSION_PIN`、`MATERIALS_TIKTOK_ENABLED`（JSON 平台开关）——
  见 `backend/materials/config.py` 的 `TikTokConfig`。

### 升级回归纪律（锁定版本的铁律）

1. 升级前备份当前锁定版本号与 requirements 行；
2. 升级后**必跑** `backend/tests/test_materials_tiktok_wrapper.py` 全量回归
   （fake fixtures 模拟输出格式，任何输出格式/参数契约变化都会暴露）；
3. 核对**锁定 CLI 契约**（见第三节）：真实版本的命令行语法若与本封装 `build_command`
   不同，需同步修改 `build_command` 与本文档「CLI 契约」；
4. 更新 `config.tiktok.version_pin` 与本文档推荐版本，并记入
   `_management/modules/m2-materials/decisions.md`；
5. 真实环境用少量关键词（count ≤ 3）冒烟后再放量（R-M2-04 频控保护）。

## 三、CLI 契约（锁定）

`build_command` 生成的参数格式（fixtures 与真实对接的统一契约）：

```
<binary> --mode search|author --target <关键词|达人URL> --count N --output DIR [extra_args...]
```

- `--mode search`：关键词搜索下载（`search_download`）；`--mode author`：达人主页下载
  （`author_download`）；
- `--output`：输出目录（相对文件名会拼接为绝对路径）；
- `extra_args`：构造参数时追加（如代理/无头等附加开关），全部透传给子进程；
- **真实版本对接**：若所安装版本的 CLI 语法不同（如旧版 `-M/-K/-C/-D` 风格），修改
  `build_command` 一处即可，其余封装逻辑（超时/解析/分类/脱敏）不变。

## 四、输出解析

- **JSON 模式**：输出以 `{`/`[` 开头时按 JSON 解析；兼容列表、`{"data": [...]}` 包裹、
  单条目 dict；字段键兼容 `file_path/path/local_path`、`title/desc/caption`、
  `author/nickname`、`source_url/url/share_url` 等常见变体；
- **文本模式**：按行识别「文件名/保存至/文件路径」「作品标题/标题」「作者/达人」
  「作品链接（http(s) URL）」关键字，字段顺序无关；同文件重复出现只保留首个；
- 解析失败（JSON 外观但语法错误）→ `UNEXPECTED`（带脱敏原文摘要）；无条目 → `NO_MATCH`。

## 五、错误分类映射（对齐 downloader.py 码表 + R-M2-06 退避）

| 输出特征 | 错误码 | 处置建议 |
|---|---|---|
| 子进程超时 | `TIMEOUT` | 60s 退避重试（R-M2-06）；调大 `timeout_seconds` |
| 输出含「频控/风控/验证码/限流」 | `RATE_LIMIT` | 180s 退避；连续失败≥2 熔断该平台（R-M2-21） |
| 输出含「登录失效/需要登录/Cookie 失效」 | `AUTH_REQUIRED` | **不自动重试 → 人工登录 → 断点续跑**（P-002） |
| 输出含「签名/参数错误/请求被拒绝」 | `PLATFORM_REJECT` | 记录证据；更新签名/参数（对齐所锁版本）后重试 |
| 无输出 / 无命中条目 | `NO_MATCH` | 120s 退避；核对关键词/达人 URL |
| 其他（非 0 退出且无已知特征） | `UNEXPECTED` | 查看脱敏证据，人工判断 |

> 注意：`AUTH_REQUIRED` 由上层转人工处理（本封装只分类、不自动重试），对齐
> `asset_download_jobs` 的 `blocked` 状态语义（database/README.md）。

## 六、脱敏纪律（P-004 / 宪法第 5 节）

- 日志/证据只留**脱敏后**文本：URL 敏感查询参数值（`token/sec_uid/a_bogus/x-bogus/
  mstoken/sign/sig/signature/cookie/session/verify/captcha/auth/key/...`）一律替换为 `***`；
- 自由文本中的疑似密钥键值（`token=...`/`cookie=...` 等）同样掩码；超长文本截断；
- 证据/日志中的文件路径经 `redact_path`（`@作者` 段掩码 + 截断）；
- **绝不落 Cookie/Token**（含 fake 输出中的假 Cookie/Token——测试断言其不出现在
  返回结果与日志中）；
- 返回结果的 `file_path` 保留真实路径（上层入库需要），`source_url/title/author` 已脱敏。

## 七、测试

```bash
cd backend
python -m pytest tests/test_materials_tiktok_wrapper.py -q --basetemp=".pytest-tmp-m2"   # 本封装（P-011：M2 独立 basetemp）
python -m pytest tests -q --basetemp=".pytest-tmp-m2" -k "materials"                    # 本模块范围（全量回归由总控统一执行）
```

- 测试纪律（宪法第 12 节 / P-011）：pytest **必须带独立 basetemp**，M2 模块统一
  `--basetemp=".pytest-tmp-m2"`（**禁止共用 `.pytest-tmp`**，并行代理会互相清理）；
  全量回归由总控统一执行，子代理只跑本模块范围测试。
- fake CLI fixtures：`tests/test_materials_tiktok_wrapper.py` 生成临时 python 脚本模拟
  TikTokDownloader 的文本/JSON 输出与退出码/超时，注入 `binary_path` 全场景覆盖
  （正常解析/参数构造/错误映射/超时/binary 缺失/脱敏）；
- 零真实 TikTokDownloader 依赖、零外网（R-M2-17）。

## 八、CLI 用法

```bash
python -m materials tiktok-download --keyword "美妆" --count 5            # 关键词搜索下载
python -m materials tiktok-download --author-url "https://www.kuaishou.com/profile/xxx" --count 5
python -m materials tiktok-download --keyword xx --count 1 --json          # JSON 输出
```

- binary 缺失时打印清晰错误（含安装指引，见第二节）并以非 0 退出；
- 平台开关：`MATERIALS_TIKTOK_ENABLED='{"kuaishou": false}'` 可禁用指定平台采集
  （R-M2-21 风控开关；`author_download` 按达人 URL 平台校验）。
