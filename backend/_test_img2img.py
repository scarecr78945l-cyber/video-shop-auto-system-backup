# -*- coding: utf-8 -*-
"""测试 img2img（图生图）：参考商品图 → 变体主图（用后即删）"""
import base64
import json
import urllib.request
from pathlib import Path

KEY = "agt_codex_dE6nIFINxTkGSTIXR7YzpRPpt2OZqMKa"
BASE = "http://192.168.31.12:51000/v1"
REF = Path("data/images/listing/1/main_0.png")  # 真实商品图（锅刷）

# 方案A：/v1/images/edits（multipart：image + prompt）
import uuid
boundary = "----b" + uuid.uuid4().hex
parts = []
def add_field(name, value):
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
def add_file(name, path):
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{path.name}\"\r\nContent-Type: image/png\r\n\r\n".encode())
    parts.append(path.read_bytes())
    parts.append(b"\r\n")
add_field("model", "gpt-image-2")
add_field("prompt", "将图片中的商品放在干净的纯白背景上，商品居中，电商主图风格，保留商品本体完全一致")
add_field("size", "1024x1024")
add_file("image", REF)
parts.append(f"--{boundary}--\r\n".encode())
body = b"".join(parts)

req = urllib.request.Request(
    BASE + "/images/edits",
    data=body,
    headers={"Authorization": f"Bearer {KEY}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        resp = json.loads(r.read())
    data = resp.get("data", [{}])[0]
    b64 = data.get("b64_json", "")
    if b64:
        img = base64.b64decode(b64)
        out = Path("data/images/_tmp/img2img_test.png")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(img)
        print(f"img2img 成功！输出 {out} ({len(img)//1024} KB), size={resp.get('size')}")
        print("revised_prompt:", data.get("revised_prompt", "")[:150])
    else:
        print("img2img 响应无 b64_json:", json.dumps(resp, ensure_ascii=False)[:300])
except urllib.error.HTTPError as e:
    print(f"img2img HTTP {e.code}: {e.read().decode()[:500]}")
except Exception as e:
    print(f"img2img ERR: {type(e).__name__} {str(e)[:200]}")
