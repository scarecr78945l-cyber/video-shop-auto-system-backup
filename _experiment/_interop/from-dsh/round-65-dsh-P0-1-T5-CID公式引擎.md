# round-65-dsh-P0-1-T5-CID公式引擎

> 归属：DSH（DeepSeek）| 主题：P0-1 T5 — CID 公式引擎实现
> 输入：`from-cdx/round-64-cdx-P0-1-T4二次最小终验.md`（T4 COMPLETE 授权）、`docs/contracts/cid-engine-spec.md`（唯一公式契约）、`test-strategy.md` §五、`15-数据字典.md` v6 §7
> 状态：**T5 实现完成，黄金样例 10 项完整串逐字符等值 + canonical 不变量 + envelope 用例全 PASS，请求 Codex 复核**

---

## 一、实现方式与落点

按 round-17 任务拆解 P0-1-T5：「输出 `backend/domain/cid.py` + 测试」：

| 文件 | 说明 |
|---|---|
| `backend/domain/cid.py` | CID 公式引擎（纯 Python decimal，无 DB/平台依赖） |
| `backend/domain/__init__.py` | domain 包（T5 起启用） |
| `backend/tests/test_cid_engine.py` | pytest 验收（26 项） |
| `project/scripts/assert_cid_engine.py` | 独立 CLI 断言（42 项 PASS，退出码 0） |

## 二、引擎实现要点（cid-engine-spec.md 契约）

1. **decimal context 唯一冻结**：`Context(prec=60, rounding=ROUND_HALF_UP)`；输入必须为 `Decimal`/十进制字符串（**float 拒绝**，不经 binary float——已加反例）；中间值同一 context 一次算完；
2. **公式**：`M=K−J−I−H−G−L` → `N=K/M` → `O=N+roi_buffer` → `P=K/O` → `Q=P×rebate` → `R=K×tech_hi−K×tech_lo` → `S=K−P−J−I−H−G+R+Q`（**不减 L**）→ `T=S/P` → `V=P/U` → `X=O×U` → `bid=ROUND_HALF_UP(P)`；
3. **canonical serialization**（round-27 数值级）：`canonical(value)`——plain fixed-point、裁剪非显著尾随零、负零→`"0"`、exponent 展开（`1E+3`→`"1000"`）、整数无小数点；
4. **envelope**（round-23 A6）：`status / blocking_error / quality_flags / business_flags / field_details / values / bid_rounded_cents / formula_version / decimal_precision / rounding_mode`；
5. **除零/负毛利/空值**：`M≤0→M_NON_POSITIVE`、`O=0→O_ZERO`、`U≤0→U_NON_POSITIVE`、`P=0→P_ZERO`（防御分支）；必需 K/J/I/H/G/U 缺失→`REQUIRED_FIELD_MISSING`；`L` 缺失→默认 0+`FIELD_DEFAULTED`；rebate=0→`REBATE_NOT_APPLICABLE`（Q=0 继续）；rebate=None→`REBATE_SOURCE_MISSING`；`S≤0`→计算完成+`S_NON_POSITIVE`（业务闸门，非引擎失败）；
6. **N/O/T/X 量化 numeric(12,6)**：`quantize_ratio()` 仅供存储投影，**不回流**参与后续计算（引擎 values 始终返回未量化完整串）；
7. 另提供 `cid_results_payload()`：`pricing_decisions.cid_results` 持久化 JSON 形状（values+公式版本+精度+rounding）。

## 三、验收证据（全部实测，退出码 0）

### 3.1 黄金样例（cid-engine-spec §五，Excel 第 2 行）

输入 `K=2199, J=13.194, I=153.930, H=180, G=130, L=83.562, U=0.5, roi_buffer=0.1, rebate=0.05, tech_hi=0.036, tech_lo=0.055`：

```text
M = 1638.314                                          [PASS]
N = 1.34223354009060534183312844790436998035785569799196002719869   [PASS]
O = 1.44223354009060534183312844790436998035785569799196002719869   [PASS]
P = 1524.71838913263129988876904209077295993273155249248846108953   [PASS]
Q = 76.2359194566315649944384521045386479966365776246244230544765   [PASS]
R = -41.781                                            [PASS]
S = 231.612530324000265105669410013765688063905025132135961964947   [PASS]（末位 ...947）
T = 0.151905120299465930780868549195949287016521859444202856705946  [PASS]
V = 3049.43677826526259977753808418154591986546310498497692217906  [PASS]
X = 0.721116770045302670916564223952184990178927848995980013599345  [PASS]
bid_rounded_cents = 1525                                [PASS]
```

10 项均为**完整字符串等值**（非前缀匹配）；S 末位 `...947` 为 ROUND_HALF_UP 机械结果；状态=calculated、blocking=null、无 quality/business 标记。

### 3.2 canonical 不变量与边界

```text
canonical(1)==canonical(1.0)==canonical(1.00)=="1"      PASS
canonical(-0.000)=="0"                                  PASS
canonical(1E+3)=="1000"                                 PASS
canonical(1525.0)=="1525" / canonical(1638.314000)=="1638.314"  PASS
compact 输入 与 numeric(18,6)/numeric(8,4) 尺度输入 全串相等        PASS
ROUND_HALF_UP 分边界：1.5→2 / 2.5→3 / 3.5→4 / 1524.5→1525 / 1525.5→1526 / -1.5→-2  PASS
float 输入拒绝（不经 binary float）                     PASS
```

### 3.3 envelope 用例（test-strategy §五 全项）

```text
M=0 -> M_NON_POSITIVE（K=560.686 精确零毛利）           PASS
M<0 -> M_NON_POSITIVE                                  PASS
O=0 -> O_ZERO（K=-1000,J=-11000 构造 N=-0.1）           PASS
U=0 / U<0 -> U_NON_POSITIVE                            PASS
K=0 -> blocking（M_NON_POSITIVE 先行，P_ZERO 防御分支）  PASS
L 缺失 -> calculated + FIELD_DEFAULTED + M=1721.876     PASS
必需缺失 -> REQUIRED_FIELD_MISSING（details=4）         PASS
rebate=0 -> calculated + REBATE_NOT_APPLICABLE + Q=0    PASS
rebate=None -> calculated + REBATE_SOURCE_MISSING + Q=0 PASS
S<=0 -> calculated + S_NON_POSITIVE（非失败）            PASS
N/O/T/X 量化 numeric(12,6) 存在（不回流）                PASS
```

### 3.4 双通道验证

```text
python scripts/assert_cid_engine.py   -> 42 项 [PASS]，T5-CID-ASSERT: PASS，exit 0
cd backend && python -m pytest tests/test_cid_engine.py -q  -> 26 passed，exit 0
```

### 3.5 回归边界

```text
alembic heads = 17trg000001 (head)；DB revision = 17trg000001（T1~T4 终态未动）
T5 纯计算引擎，未新增 migration、未改表结构、未触碰平台能力
```

## 四、交付物与哈希

| 文件 | SHA-256 |
|---|---|
| `backend/domain/cid.py` | `DAA7BD6C0280455F18FA1672105CBB5BD357F6F54A38C51E5D7B5E71A00F33B9` |
| `backend/domain/__init__.py` | `E0AB7999072F148B8BDC6FA807E22E926CE3943DBB58A7243BA865DB2FEFE77E` |
| `backend/tests/test_cid_engine.py` | `A724E4F7D52F34392F069992F96786B8E44118357639D96F4D23F595CAAFD9D4` |
| `project/scripts/assert_cid_engine.py` | `B72663176DC4A7E9AACF961AA36B5993A32CB8661EB69A7A9A6E468FC662B2ED` |

T1~T4 全部文件哈希不变（round-64 已核对）。

## 五、给 Codex 的复核点

1. **黄金样例独立复算**：用 `Context(prec=60, ROUND_HALF_UP)` 独立实现复算，10 项完整串 + S 末位 `...947` + bid=1525 逐字符一致（cid-engine-spec §五）；
2. canonical serialization 六条规则（尾随零裁剪/负零/exponent/整数）机械不变量；
3. envelope 门禁：status/blocking_error/quality_flags/business_flags/field_details 分类语义（尤其 L 缺失 vs 必需缺失 vs rebate 三种状态区分、S≤0 非失败）；
4. 除零/负毛利覆盖：M=0/M<0/O=0/U≤0/P=0；
5. N/O/T/X 量化 numeric(12,6) 不回流；float 输入拒绝（不经 binary float）；
6. 双通道（pytest + CLI 断言）与回归边界（T1~T4 终态未动、无新 migration）。

## 六、下一步（P0-1 DAG）

T5 复核通过后进入 **T6（secret_store）**：`backend/infra/secret_store.py`（接口 + 本地实现）+ 脱敏测试（round-17 拆解）。

---

<!--RELAY: 请 CDX 读取本文件并继续，当前轮次 round-65-->
