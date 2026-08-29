# -*- coding: utf-8 -*-
"""P2-1：从旧系统备份库提取 AI 生成物样本，落盘为 M3 测试 fixtures。

- 文案样本：products.ai_title / ai_detail（真实生产 AI 生成物，UTF-8 保留）；
- 生图样本：image_assets.prompt / plan_json / file_path（真实 Wan 生图记录）；
- 图片样本：拷贝 2~3 张小体积真实生成图到 fixtures 目录。

零写入旧系统；零密钥（不读取任何 session/cookie 字段）；全部输出 UTF-8 无 BOM。
"""
import json
import os
import shutil
from pathlib import Path

DB = r"E:\视频号上架系统\视频号上架系统\backend_backup_20260816_214116.db"
OLD_RUNTIME = Path(r"E:\视频号上架系统\视频号上架系统\backend\runtime")
FIX_DIR = Path(r"E:\新建文件夹 (6)\视频号小店全自动系统-方案文档\backend\fixtures\optimization")
IMG_DIR = FIX_DIR / "old_ai_image_samples"
COPY_COUNT = 3          # 拷贝图片张数（小体积）
MAX_IMG_BYTES = 200_000

import sqlite3
con = sqlite3.connect(DB)
con.text_factory = lambda b: b.decode("utf-8", "replace")
cur = con.cursor()

# ---------------------------------------------------------------- 1) 文案样本
copy_rows = cur.execute(
    "SELECT id, opportunity_category, material_result, sku_result, ai_title, ai_detail "
    "FROM products WHERE ai_title IS NOT NULL AND ai_title != '' "
    "AND ai_detail IS NOT NULL AND ai_detail != '' "
    "ORDER BY updated_at DESC LIMIT 6"
).fetchall()
copy_samples = []
for i, (pid, cat, mat, sku, title, detail) in enumerate(copy_rows, start=1):
    def _trunc(s, n):
        s = str(s or "")
        return s[:n] + ("…" if len(s) > n else "")
    copy_samples.append({
        "sample_id": f"old_copy_{i:02d}",
        "source": "旧系统 products 表（backend_backup_20260816_214116.db）",
        "old_product_id": pid,
        "category": str(cat or ""),
        "material": _trunc(mat, 100),
        "sku_json": _trunc(sku, 300),
        "ai_title": _trunc(title, 200),
        "ai_detail": _trunc(detail, 800),
        "note": "旧系统 AI 生成物（标题+详情页文案），供 M3 文案管线回归",
    })

# ---------------------------------------------------------------- 2) 生图 prompt/plan 样本
img_rows = cur.execute(
    "SELECT id, batch_id, kind, position, prompt, plan_json, file_path, status "
    "FROM image_assets WHERE prompt IS NOT NULL AND prompt != '' "
    "ORDER BY updated_at DESC LIMIT 8"
).fetchall()
prompt_samples = []
for i, (aid, bid, kind, pos, prompt, plan, fp, st) in enumerate(img_rows, start=1):
    plan_obj = None
    try:
        plan_obj = json.loads(plan) if plan else None
    except Exception:
        plan_obj = None
    prompt_samples.append({
        "sample_id": f"old_img_prompt_{i:02d}",
        "source": "旧系统 image_assets 表（backend_backup_20260816_214116.db）",
        "old_asset_id": aid,
        "old_batch_id": bid,
        "kind": str(kind or ""),
        "position": pos,
        "status": str(st or ""),
        "prompt": str(prompt or ""),
        "plan_json": plan_obj,
        "old_file_path": str(fp or ""),
        "note": "旧系统 Wan 生图真实 prompt/plan（Kimi 规划），供 M3 生图管线回归",
    })

# ---------------------------------------------------------------- 3) 拷贝小体积真实生成图
IMG_DIR.mkdir(parents=True, exist_ok=True)
picked = []
for row in img_rows:
    fp = str(row[6] or "")
    if not fp or len(picked) >= COPY_COUNT:
        continue
    p = Path(fp)
    if not p.is_absolute():
        p = OLD_RUNTIME / p
    if not p.is_file():
        # 尝试在 generated_images 下按文件名找
        cand = OLD_RUNTIME / "generated_images" / p.name
        if cand.is_file():
            p = cand
        else:
            continue
    if p.stat().st_size > MAX_IMG_BYTES:
        continue
    try:
        from PIL import Image
        with Image.open(p) as im:
            w, h = im.size
    except Exception:
        continue
    target = IMG_DIR / f"old_ai_image_{len(picked) + 1:02d}{p.suffix.lower() or '.png'}"
    shutil.copyfile(str(p), str(target))
    picked.append({
        "file": target.name,
        "source_file": str(p),
        "width": w, "height": h, "bytes": p.stat().st_size,
        "kind": str(row[2] or ""), "prompt": str(row[4] or "")[:120],
    })

# ---------------------------------------------------------------- 落盘
def _dump(name, obj):
    path = FIX_DIR / name
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path

p1 = _dump("old_ai_copy_samples.json", {
    "meta": {
        "purpose": "P2-1 AI 生成物 fixtures：旧系统真实 AI 生成文案（标题+详情）回归样本",
        "source": "旧系统 backend_backup_20260816_214116.db (products 表)",
        "extracted_at": "2026-08-29",
        "count": len(copy_samples),
        "license_note": "本地离线测试 fixtures，仅供 M3 管线回归，不入生产",
    },
    "samples": copy_samples,
})
p2 = _dump("old_ai_image_prompt_samples.json", {
    "meta": {
        "purpose": "P2-1 AI 生成物 fixtures：旧系统真实 Wan 生图 prompt/plan 回归样本",
        "source": "旧系统 backend_backup_20260816_214116.db (image_assets 表)",
        "extracted_at": "2026-08-29",
        "count": len(prompt_samples),
    },
    "samples": prompt_samples,
})
p3 = _dump("old_ai_image_samples_manifest.json", {
    "meta": {
        "purpose": "旧系统真实 AI 生成图（小体积）回归样本清单",
        "source": "旧系统 backend/runtime/generated_images",
        "extracted_at": "2026-08-29",
        "count": len(picked),
    },
    "images": picked,
})

print("== 文案样本 ==")
for s in copy_samples:
    print(f"  {s['sample_id']} id={s['old_product_id']} cat={s['category']}")
    print(f"    title={s['ai_title'][:80]}")
print("== 生图 prompt 样本 ==")
for s in prompt_samples:
    print(f"  {s['sample_id']} kind={s['kind']} status={s['status']} prompt={s['prompt'][:70]}")
    print(f"    file={s['old_file_path'][:110]}")
print("== 拷贝图片 ==")
for it in picked:
    print(f"  {it['file']} {it['width']}x{it['height']} {it['bytes']}B kind={it['kind']}")
print()
print("WROTE:", p1)
print("WROTE:", p2)
print("WROTE:", p3)
con.close()
