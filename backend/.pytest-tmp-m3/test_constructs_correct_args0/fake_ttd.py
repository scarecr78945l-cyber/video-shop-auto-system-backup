#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""fake TikTokDownloader CLI（fixtures 模式）：按环境变量输出模拟输出/退出码/超时。"""
import json
import os
import sys
import time


def _text_lines():
    return os.environ.get("FAKE_TTD_TEXT", "").splitlines()


def main():
    argv = sys.argv[1:]
    if "--version" in argv:
        print(os.environ.get("FAKE_TTD_VERSION", "TikTokDownloader 4.1.0 (fake)"))
        return 0
    mode = os.environ.get("FAKE_TTD_MODE", "text")
    exit_code = int(os.environ.get("FAKE_TTD_EXIT_CODE", "0") or "0")
    sleep_seconds = float(os.environ.get("FAKE_TTD_SLEEP_SECONDS", "0") or "0")
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)
    out_dir = None
    if "--output" in argv:
        idx = argv.index("--output")
        if idx + 1 < len(argv):
            out_dir = argv[idx + 1]
    if mode == "json":
        payload = os.environ.get("FAKE_TTD_JSON_PAYLOAD", "[]")
        print(json.dumps(json.loads(payload), ensure_ascii=False, indent=2))
    elif mode == "files":
        n = int(os.environ.get("FAKE_TTD_COUNT", "3"))
        for i in range(1, n + 1):
            fn = "douyin_%04d.mp4" % i
            if out_dir:
                with open(os.path.join(out_dir, fn), "wb") as fh:
                    fh.write(b"fake-video-" + str(i).encode())
            print("文件名: " + fn)
            print("作品标题: 测试作品%d" % i)
            print("作者: 达人%d" % i)
            print("作品链接: https://www.douyin.com/video/71%d?sec_uid=FAKESECRETUID%d&a_bogus=FAKESIGN%d&token=FAKETOKEN%d" % (i, i, i, i))
    else:
        for line in _text_lines():
            print(line)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
