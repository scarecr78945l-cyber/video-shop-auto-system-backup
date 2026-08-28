#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""临时 fake TikTokDownloader（CLI 自测用，验证后删除）。"""
import json
import os
import sys

if "--version" in sys.argv:
    print("TikTokDownloader 4.1.0 (fake)")
    sys.exit(0)
out_dir = None
if "--output" in sys.argv:
    out_dir = sys.argv[sys.argv.index("--output") + 1]
for i in range(1, 3):
    fn = "douyin_%04d.mp4" % i
    if out_dir:
        with open(os.path.join(out_dir, fn), "wb") as fh:
            fh.write(b"fake-video")
    print("文件名: " + fn)
    print("作品标题: 自测作品%d" % i)
    print("作者: 自测达人%d" % i)
    print("作品链接: https://www.douyin.com/video/8%d?sec_uid=SELFTESTUID%d&a_bogus=SELFTESTSIGN%d&token=SELFTESTTOK%d" % (i, i, i, i))
sys.exit(0)
