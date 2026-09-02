# -*- coding: utf-8 -*-
"""检查淘宝登录态 cookie（识图可能需登录）（用后即删）"""
from playwright.sync_api import sync_playwright

pw = sync_playwright().start()
try:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    for c in browser.contexts:
        cookies = c.cookies()
        tb = [ck for ck in cookies if any(d in ck.get("domain","") for d in ["taobao.com","tmall.com","alicdn.com"])]
        names = [ck.get("name") for ck in tb]
        # 登录关键 cookie：cookie2 / _tb_token_ / unb / lgc
        login_keys = [n for n in names if n in ("cookie2","_tb_token_","unb","lgc","_nk_","tracknick","sgcookie")]
        print(f"淘宝 cookies: {len(tb)} 个")
        print(f"登录关键 cookie: {login_keys}")
        if "cookie2" in names:
            print("  cookie2 存在 = 已登录")
        else:
            print("  cookie2 缺失 = 未登录（识图可能被拦）")
    pw.stop()
except Exception as e:
    print("ERR", e)
