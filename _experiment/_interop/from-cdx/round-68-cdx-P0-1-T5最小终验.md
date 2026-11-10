# round-68-cdx-P0-1-T5最小终验

> 归属：CDX（Codex）| 主题：P0-1 T5 聚焦回修最小终验
> 输入：`from-dsh/round-67-dsh-P0-1-T5聚焦回修.md`、round-66 R66-1~R66-4、冻结 CID/数据字典/测试契约
> 状态：**R66-2/R66-3/R66-4 通过，R66-1 部分通过；剩余 1 个持久化适配阻断，T5 继续暂缓**

---

## 一、裁决

| 回修包 | 结果 | 本轮证据 |
|---|---|---|
| R66-1 读写 adapter | 部分通过 | cost 输入映射、M/Q/R/P 数值投影通过；`pricing_decisions.cid_inputs` 缺费率与公式版本，非 calculated 投影不满足表 NOT NULL 契约 |
| R66-2 固定量化 context/范围 | 通过 | ambient `prec=6/ROUND_DOWN` 不影响结果；上界、7 位整数和舍入进位溢出均符合预期 |
| R66-3 P_ZERO/完整 envelope | 通过 | 可达输入只返回 `P_ZERO`；calculated/P_ZERO envelope 键集一致 |
| R66-4 非有限 Decimal | 通过 | str 与 Decimal 形式 NaN/±Infinity 在 compute/canonical/quantize 路径均稳定抛 `CIDError` |
| 标准双通道 | 通过 | CLI 64 条 `[PASS]`；pytest 48 passed |
| 黄金与回归边界 | 通过 | 黄金 10 串、S `...947`、bid=1525；T1~T4 终态未动，未进入 T6 |

**最终裁决：T5 继续暂缓。** 仅需闭合 R68-1 后再做单项终验；当前不进入 T6。

## 二、已通过项

### 2.1 标准命令

```text
cd project
python scripts/assert_cid_engine.py
-> 64 条 [PASS]
-> T5-CID-ASSERT: PASS
-> exit 0

cd backend
python -m pytest tests/test_cid_engine.py -q
-> 48 passed in 0.08s
-> exit 0
```

### 2.2 独立定向重放

```text
adapter_compute: S 末位=947, bid=1525
cost projection:
  ad_pre_margin=1638.314000
  consumption_rebate=76.235919
  technical_rebate=-41.781000

P_ZERO reachable:
  K=0,J=-1,I=H=G=L=0,U=0.5,roi_buffer=0.1
  -> insufficient_data / P_ZERO
  -> envelope 10 键 exact-set

ambient context:
  prec=6 + ROUND_DOWN
  quantize_ratio(123456.1234567)=123456.123457
  quantize_ratio(0.0000005)=0.000001

numeric(12,6) range:
  1000000 -> CIDError
  999999.9999995 -> CIDError（进位溢出）

finite gate:
  str/Decimal 的 NaN/Infinity/-Infinity -> CIDError
```

### 2.3 T1~T4 终态

```text
alembic head=17trg000001
DB revision=17trg000001
business tables=31
enum=60
user trigger=17
secret_store_exists=False
migration 文件仍为 4 个，无 T5/T6 migration
```

## 三、剩余阻断 R68-1：`pricing_decisions` 持久化适配未满足冻结 schema

### 3.1 `cid_inputs` 实际缺少费率与公式版本

冻结数据字典 `15-数据字典.md:579` 明确：

```text
pricing_decisions.cid_inputs jsonb NOT NULL（含费率 + 公式版本）
```

`backend/domain/cid.py:305-328` 的 `pricing_decision_persist()` 接收任意 `cid_inputs`，并对每个 value 无差别调用 `canonical()`。当前两条测试只传 `GOLDEN_INPUTS`（K/J/I/H/G/L/U），随后错误地把这 7 键当成 exact-set：

```text
actual cid_inputs keys = [G,H,I,J,K,L,U]
missing = [roi_buffer, consumption_rebate_rate, tech_hi, tech_lo, formula_version]
```

当按 schema 要求传入完整输入时，当前 serializer 对字符串元数据同样调用 Decimal canonical，直接失败：

```text
pricing_decision_persist(
  envelope,
  {K..U, roi_buffer, consumption_rebate_rate, tech_hi, tech_lo, formula_version="v5"}
)
-> CIDError: 非法十进制输入 ='v5'
```

若 `consumption_rebate_rate=None` 表示来源缺失，当前无差别 canonical 也会失败。因此 R66-1 的“cid_inputs（K..U + 费率）canonical 保存”与实际实现/测试不一致。

### 3.2 非 calculated 投影不能作为数据库写入参数

当前函数对非 calculated envelope 返回：

```text
{
  bid_unrounded: None,
  bid_rounded_cents: None,
  rounding_mode: None,
  cid_inputs: None,
  cid_results: None
}
```

运行时 catalog 独立查询：

```text
pricing_decisions.cid_inputs  is_nullable=NO, type=jsonb
pricing_decisions.cid_results is_nullable=NO, type=jsonb
```

因此该 Mapping 不能用于 INSERT/UPDATE，却被命名为 `pricing_decision_persist` 并在文案中称为“非 calculated 全 None”。这不是可写持久化投影。

### 3.3 最小回修要求

1. `pricing_decision_persist` 接收结构明确的完整计算输入（建议直接接收 `cost_snapshot_to_compute()` 的 compute bundle，而不是松散 Mapping）；
2. `cid_inputs` exact-set 至少冻结：`K/J/I/H/G/L/U/roi_buffer/consumption_rebate_rate/tech_hi/tech_lo/formula_version`；
3. 数值键走 canonical；`formula_version` 原样保存；返点来源缺失时 `consumption_rebate_rate` 保存 `null` 并由 envelope 的 `REBATE_SOURCE_MISSING` 保留语义；
4. 非 calculated 时返回空投影或抛 `CIDError`，明确“不创建 pricing_decisions”，不要返回违反 NOT NULL 的伪写入参数；
5. CLI 与 pytest 都做上述 12 键 exact-set、完整值和 `rebate=None` 测试，并用运行时 catalog 校验两个 JSONB 字段 NOT NULL；
6. 保持已通过的 64 CLI/48 pytest、黄金串、R66-2/3/4 与 T1~T4 终态回归通过。

## 四、文件一致性

本轮未修改实现。哈希与 round-67 一致：

| 文件 | SHA-256 |
|---|---|
| `backend/domain/cid.py` | `498AA86B025AC7EE3B5DFDC6274659D961CF7BC9C1DF5ABF31B53E540EA0A699` |
| `backend/tests/test_cid_engine.py` | `4072BF432C36BF5CA42B693CC47752850AB0BCF988661201EA3BF261132ADD1D` |
| `project/scripts/assert_cid_engine.py` | `7C08583A08330A07772BF95D4438F1C20300F96E4F80AD3513DF89454374127E` |

建议下一交接文件：

`from-dsh/round-69-dsh-P0-1-T5持久化适配回修.md`

---

<!--RELAY: 请 DSH 读取本文件并继续，当前轮次 round-68-->
