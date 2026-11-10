# -*- coding: utf-8 -*-
"""计算 idempotency.md 黄金向量（权威算法，round-41 冻结）。
算法：
  1. 字段转 str；None → 'nil'
  2. 转义顺序冻结：先 replace('\\','\\\\') 再 replace('|','\\|')
  3. '|'.join
  4. NFC normalize → UTF-8 bytes
  5. sha256 hex lowercase
  6. final = f'{domain}:v1:{digest}'
"""
import hashlib, unicodedata

def canonical_join(fields):
    parts = []
    for f in fields:
        s = 'nil' if f is None else str(f)
        s = s.replace("\\", "\\\\")   # 先反斜杠
        s = s.replace("|", "\\|")     # 再竖线
        parts.append(s)
    joined = "|".join(parts)
    nfc = unicodedata.normalize("NFC", joined)
    return nfc, nfc.encode("utf-8")

def key(domain, fields):
    text, data = canonical_join(fields)
    digest = hashlib.sha256(data).hexdigest()
    return text, digest, f"{domain}:v1:{digest}"

UUID1 = "00000000-0000-0000-0000-000000000001"
UUID2 = "00000000-0000-0000-0000-000000000002"
UUID3 = "00000000-0000-0000-0000-000000000003"

# 向量1：普通 step key（UUID 小写、无 NULL、无特殊字符）
f1 = [UUID1, UUID2, "listing_submit", "product_submit_audit", UUID3]
t1, d1, k1 = key("step", f1)
print("V1 text :", repr(t1))
print("V1 digest:", d1)
print("V1 key  :", k1)
print()

# 向量2：含 NULL
f2 = [UUID1, UUID2, "campaign_start", "campaign_start", None]
t2, d2, k2 = key("step", f2)
print("V2 text :", repr(t2))
print("V2 digest:", d2)
print("V2 key  :", k2)
print()

# 向量3：转义 + Unicode（字段值 = 'a|b\\c中'，即一个竖线、一个反斜杠、中文）
f3 = [UUID1, UUID2, "material_upload", "material_upload", "a|b\\c中"]
t3, d3, k3 = key("step", f3)
print("V3 text :", repr(t3))
print("V3 digest:", d3)
print("V3 key  :", k3)
