# -*- coding: utf-8 -*-
"""只读检查旧系统各 DB：AI 生成物（文案/标题/图片路径）样本。零写入、零密钥。"""
import sqlite3, os, json

CANDIDATES = [
    r"E:\视频号上架系统\视频号上架系统\app.db",
    r"E:\视频号上架系统\视频号上架系统\backend_backup_20260816_214116.db",
    r"E:\视频号上架系统\视频号上架系统\output\migration\视频号自动上架系统_迁移包_20260811_155324\data\app.sanitized.db",
]

for db in CANDIDATES:
    if not os.path.exists(db):
        print("MISSING:", db)
        continue
    print("=" * 70)
    print("DB:", db)
    try:
        con = sqlite3.connect(db)
        con.text_factory = lambda b: b.decode("utf-8", "replace")
        cur = con.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        print("TABLES:", tables)
        for t in tables:
            if "product" in t.lower() or "ai" in t.lower() or "image" in t.lower() or "content" in t.lower():
                cols = [d[1] for d in cur.execute(f'PRAGMA table_info("{t}")')]
                cnt = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                print(f"-- {t}: {cnt} rows; cols={cols}")
                if cnt and cnt <= 3:
                    try:
                        rows = cur.execute(f'SELECT * FROM "{t}" LIMIT 2').fetchall()
                        for r in rows:
                            print("   ROW:", str(r)[:600])
                    except Exception as e:
                        print("   err:", e)
        con.close()
    except Exception as e:
        print("ERR:", e)
