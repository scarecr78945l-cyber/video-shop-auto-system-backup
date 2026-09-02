# -*- coding: utf-8 -*-
"""分析：淘宝以图搜结果精准度（detail_0 场景图 vs 白底图）（用后即删）"""
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "pdd-scrape"
items = json.loads((OUT / "taobao_same_items.json").read_text(encoding="utf-8"))

# 相关关键词（锅刷/厨房清洁类）
BRUSH_KW = ["锅刷", "刷锅", "洗锅", "钢丝", "清洁刷", "厨房", "洗碗", "炊帚", "刷子"]
rel = [it for it in items if any(k in it["title"] for k in BRUSH_KW)]
unrel = [it for it in items if not any(k in it["title"] for k in BRUSH_KW)]
print(f"总共 {len(items)} | 锅刷相关 {len(rel)} | 无关 {len(unrel)}")
print("\n=== 无关（推荐流误入）===")
for it in unrel[:10]:
    print("  ", it["title"][:40])
print("\n=== 锅刷相关（同款）===")
for it in rel[:10]:
    print("  ", it["title"][:45])
