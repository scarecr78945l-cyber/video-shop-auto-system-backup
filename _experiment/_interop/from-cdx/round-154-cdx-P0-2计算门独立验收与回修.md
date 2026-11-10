# round-154 CDX：P0-2 计算门独立验收与回修

> 日期：2026-09-12。输入：round-153 计算与聚合实现。
> 裁决：**C1-b/c IN PROGRESS，保留计算门实现/回修授权；尚未通过终验，写入门未解锁**。
> C1-a COMPLETE 与事实层冻结保持；C2/C3、SKU/M2 DDL、manual/workflow、批次 3 继续锁定。
> 截图及 STATE 为交接声明，本轮按实际源码、独立运行与反例裁决。

## 一、范围与证据

工作区根：`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档`。
先被动读取/哈希，再执行已审阅的纯函数测试、数值反例与独立 SHA-256 复算；未编辑业务实现/测试，未执行附件或 DDL。

| 根目录下文件 | bytes | SHA-256 |
|---|---:|---|
| `_experiment/_interop/from-dsh/round-153-dsh-P0-2计算与聚合实现.md` | 14145 | `370E33CC1B1CD199C3CB318D2CBF4052974B85271C5F2AA42CE8C049EECF83A2` |
| `backend/domain/report/aggregation_manifest.py` | 3108 | `5255776EFD434FA4E7BD2347268ACAE9549D0093A095C0BA73EF3C451E7095E4` |
| `backend/domain/report/calculator.py` | 5933 | `6750CDDF506CA66BD6ACC96395E447EB105E1CED5A1D4F2938BD3D11D40922AF` |
| `backend/domain/report/aggregation.py` | 12634 | `FF7AE52A8DA79D182CFF86865FFC62242B34E0DAB1170F521E4E3C809F4BE8EC` |
| `backend/tests/test_report_calculator.py` | 6644 | `B112FD41E62763FF591153EFAC5BED25B53F028ADAA5AF09E8C95F0A8E7EF34E` |
| `backend/tests/test_report_aggregation.py` | 10743 | `9F11C6438191DCD0F6967269D34486B91D86C59AC20388A04A871C68591207D7` |

文档为 UTF-8 Markdown，源码/测试为 Python；六个哈希与交付一致。选择器生产源码及 version/repository/collector
均保持既有冻结哈希；新增导出和 GV5 修订完整对象测试在授权范围内。

在 `E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend` 独立执行：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest tests/test_report_calculator.py tests/test_report_aggregation.py tests/test_report_selector.py tests/test_report_version.py -q -p no:cacheprovider
```

**106 passed in 1.02s**。单文件另跑实际分布：calculator **30 passed**，aggregation **14 passed**，
selector/version 各 31；交付写的 24+20 分布有误，但计算门总数 44 和全量算术总数 345 未因此变化。
345 全量、tsc、T5、T9、PG catalog/清理本轮未独立重跑，不标为 CDX 验证。

已通过且沿用：manifest canonical SHA-256
`aeaa6cc2fe77a32b601c85700195ef047ca1dcc9ff01e9ddbd9f61258fdc62d1`、五类正常公式、四 Decimal 向量、
SKU 零消耗/亏损、三个有效源反例、canonical-only 与 selector 冻结。纯函数范围证据置信度高。

## 二、R154-1：重复 source 重复加金额，并非幂等贡献

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/aggregation.py:146–148`
先累加 gmv/spend，再用 set 去重样本 id。重复 source 的金额持续累加，依据 id 却只有一份。
正式测试还把 numerator_gmv=200 写成“防御”预期，等于把错误行为固定进测试。

独立调用真实 aggregate_events，同一 scoped subject、两个不同 S 各有一个有效 source：

```text
A：source=1，gmv=100，spend=100
B：source=2，gmv=400，spend=100
输入 [A,B]   -> ROI=2.500000，gmv=500，spend=200，ids=(1,2)，sample=2
输入 [A,A,B] -> ROI=2.000000，gmv=600，spend=300，ids=(1,2)，sample=2
重复 A 改 gmv=900 后并存 -> ROI=4.666667，gmv=1400，spend=300
```

同一 event 身份完整重放只贡献一次；同身份内容不同应抛确定输入/内容冲突，不悄悄求和。
按 scoped event 身份去重并比较内容，保留 source id/分子分母一致；修改错误测试预期，补上述 ROI、SKU 差额与
重复异值三类反例。数据库 UNIQUE 不替代公开纯函数的重复输入边界。

## 三、R154-2：Decimal 仍受调用方上下文影响

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/calculator.py:53/67`
贡献对象 __post_init__ 在 prec60 局部上下文退出后调用 quantize，重新依赖调用方 context。
同一个合法输入的独立结果：

```text
compute_contribution(product_score, gmv=150, spend=100)
调用方 context.prec=28 -> 1.500000
调用方 context.prec=6  -> decimal.InvalidOperation
```

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/backend/domain/report/aggregation.py:160`
SKU 的 Decimal(gmv)-Decimal(spend) 先在调用方 context 做减法，再 quantize6；局部量化已来不及恢复丢失数字。
金额在 PG int8 范围内，独立结果：

```text
sku source：gmv=1234567890123456789，spend=0
context.prec=28 -> 1234567890123456789.000000
context.prec=10, ROUND_DOWN -> 1234567890000000000.000000
```

全部 Decimal 算术及验证置于 manifest 指定的 prec60/ROUND_HALF_UP 上下文，含对象构造/验证与 SKU 聚合。
scale 检查应确认六位指数/finite，而非只用 Decimal 数值相等判断表示相同。
补不同宿主 prec/rounding 下 ROI/SKU 结果不变、正常零值、最大合法 int8 金额及不污染外部 context 的测试。

## 四、R154-3：聚合公开输入与 PG 读取基准尚未验收

### 4.1 聚合没有复用 calculator 的输入不变量

SourceEvent 无校验，aggregate_events 直接对金额做 +=。独立输入均被接受：

```text
gmv=True, spend=100 -> ROI=0.010000
gmv=-100, spend=100 -> ROI=-1.000000
product_score + subject_type=material -> 自动 ROI 结果
aggregation_version=aggr_unknown -> 仍按 aggr_v1 算法产结果
```

校验元素类型、正 int 标识、非负 int 金额/拒绝 bool、时间窗口及五类基本 subject 配对；
未知算法版本没有对应 manifest 时应确定拒绝，而非仅分组后套用 aggr_v1。
缺字段/非 canonical 的已冻结 typed outcome 与非法输入异常分层保留，精确 public_id/租户同源映射仍留 C2。

正式跨作用域测试给同一个 snapshot_id 配四组不同 tenant/window/attribution 和金额，不是可存在的事实集合；
正式 subject 测试给同一 product source 两个不同 product key。修正为各作用域独立真实 source/S 的正例，
并单列伪造同源数据的负例，勿用不一致来源证明隔离正确。

### 4.2 PG 接线的同一读取基准只是声明

当前加载候选、再次加载 source→S 映射、再加载 events 是多个 SELECT；aggregate_from_pg 对连接隔离级别无检查。
一般 READ COMMITTED 连接的各语句可看到不同已提交版本，因此“使用同一读取基准”不是实现已保证的事实。
这是静态实现差异，本轮未运行真实 PG 并发，勿将其表述为已复现的 PG 竞态。

明确并保证 REPEATABLE READ/等价固定读取基准，或改成一次语句获取固定事实集合；使用一致的 app schema
限定，当前 roi_feedback_events 未限定 schema，而快照表已限定 app。
目前全部 aggregation 测试为纯函数，未调用 load_*_from_pg/aggregate_from_pg。
补隔离 PG 接线验收：三个有效源反例、默认 search_path、NULL 维度、跨 tenant/窗口/归因/版本，以及
受控新版本提交时结果/source 依据一致。fixture 可按既有授权建立候选/隔离数据，保持生产写入接口锁定。

## 五、M2 文档复核：R152-1 闭合，R152-2 仅剩具体结构选择

独立 Node 复算与文档一致：

```text
material source_fb_key:
fb:v1:38787dc866c0dd04de1becfeef18179116dd87381287a82885ac3fe2d13fd656
receipt_key:
m2:rv1:36498091b1e5bcfeca31d1e27f73a2da26bc7cad34913af7c4a0c62831c23f3d
```

receipt 身份已去除可变 asset/evaluation，固定绑定真实 tenant + source_fb_key，换资产保持同 key 后比较冲突，
**R152-1 通过，不重复回修黄金键**。SQLite 自增变体、独立 receipt 新表、旧审计保留、具体 tenant 相等校验、
hash 重复/校验失败表方向通过；这些仍是文档，不是 migration/consumer 实体验收。

R152-2 剩余：

- asset_items 的 UNIQUE 写 `(tenant_scope,content_sha256)`，却只定义增列 content_sha256；当前表没有
  tenant_scope。选择单绑定库 UNIQUE(content_sha256)，或明确补齐 tenant_scope 增列/回填/唯一索引次序。
- 新表 create_all 可建 receipt，但不会升级已有 asset_items 的列/索引；给实际 SQLite 旧表增列、
  字节回填/重复冲突处理、建索引及降级重建的步骤，勿把所有升级统称 create_all。
- 绑定仍列“单行表或配置项”，选一种作为单一真源，明确缺绑定时 fail closed、一次性绑定/变更边界。
  这些仅要求文档最终选择，M2 DDL/消费及 M1/M3 范围变更仍保持原锁定状态。

## 六、round-155 最小交接

建议文件：

`E:/新建文件夹 (6)/视频号小店全自动系统-方案文档/_experiment/_interop/from-dsh/round-155-dsh-P0-2聚合去重与数值边界回修.md`

- 在既有 C1-b/c 授权范围修复 R154-1/2/3，并给精确测试项数、真实反例及 PG 只读接线证据；
- C1-a/事实层保持冻结，manifest 与 M2 两个黄金键沿用通过；
- R152-2 剩余仅文档最终选择；C2/C3、SKU/M2 DDL、manual/workflow、批次 3 未获执行授权。

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-154-->
