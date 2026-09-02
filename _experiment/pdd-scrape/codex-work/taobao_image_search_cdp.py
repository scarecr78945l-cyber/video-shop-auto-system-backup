#!/usr/bin/env python3
"""Run Taobao image search through an already running remote-debugging Chrome."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import BrowserContext, Page, TimeoutError, sync_playwright


CAMERA = '[data-spm="image_search_icon"]'
FILE_INPUT = '#image-search-custom-file-input'
SEARCH_BUTTON = '#image-search-upload-button'


def canonical_product_url(url: str) -> str | None:
    parsed = urlsplit(url)
    item_id = parse_qs(parsed.query).get("id", [None])[0]
    host = parsed.netloc.lower()
    if not item_id:
        return None
    if host == "item.taobao.com":
        return f"https://item.taobao.com/item.htm?id={item_id}"
    if host == "detail.tmall.com":
        return f"https://detail.tmall.com/item.htm?id={item_id}"
    if host == "detail.taobao.com":
        return f"https://detail.taobao.com/item.htm?id={item_id}"
    return None


def extract_product_urls(page: Page) -> list[str]:
    hrefs = page.locator("a[href]").evaluate_all(
        "els => [...new Set(els.map(a => a.href).filter(h => "
        "/item\\.taobao\\.com|detail\\.tmall\\.com|detail\\.taobao\\.com/.test(h)))]"
    )
    result: list[str] = []
    for href in hrefs:
        clean = canonical_product_url(href)
        if clean and clean not in result:
            result.append(clean)
    return result


def wait_for_stage(page: Page, timeout_ms: int) -> None:
    # FileReader + canvas compression are asynchronous; an active button proves stage 1.
    page.wait_for_function(
        """() => {
          const button = document.querySelector('#image-search-upload-button');
          return button && button.classList.contains('upload-button-active');
        }""",
        timeout=timeout_ms,
    )


def run_image_search(context: BrowserContext, image: Path, timeout_ms: int) -> dict[str, object]:
    page = context.new_page()
    popup: Page | None = None
    try:
        page.goto("https://www.taobao.com/", wait_until="domcontentloaded", timeout=timeout_ms)
        # Keep requests low-frequency and give the image-search widget time to mount.
        page.wait_for_timeout(3000)
        page.locator(CAMERA).click(timeout=timeout_ms)
        page.locator(FILE_INPUT).set_input_files(str(image), timeout=timeout_ms)
        wait_for_stage(page, timeout_ms)

        with page.expect_popup(timeout=timeout_ms) as popup_info:
            # This is the required second click: first click selects a file, second starts image search.
            page.locator(SEARCH_BUTTON).click(timeout=timeout_ms)
        popup = popup_info.value
        popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)

        popup.wait_for_function(
            """() => [...document.querySelectorAll('a[href]')].some(a =>
              /item\\.taobao\\.com|detail\\.tmall\\.com|detail\\.taobao\\.com/.test(a.href))""",
            timeout=timeout_ms,
        )
        urls = extract_product_urls(popup)
        if not urls:
            raise RuntimeError("The result page loaded but has no product links.")
        return {"result_url": popup.url, "product_urls": urls}
    finally:
        if popup and not popup.is_closed():
            popup.close()
        if not page.is_closed():
            page.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path, help="Local PNG or JPEG input image")
    parser.add_argument("--cdp", default="http://127.0.0.1:9223")
    parser.add_argument("--timeout-ms", type=int, default=30000)
    args = parser.parse_args()

    image = args.image.expanduser().resolve()
    if not image.is_file():
        parser.error(f"Image not found: {image}")
    if image.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        parser.error("Taobao's current widget accepts PNG/JPG/JPEG only.")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(args.cdp)
            if not browser.contexts:
                raise RuntimeError("The CDP browser has no browser context.")
            result = run_image_search(browser.contexts[0], image, args.timeout_ms)
            browser.close()
    except TimeoutError as exc:
        print(json.dumps({"ok": False, "error": f"Timeout: {exc}"}, ensure_ascii=True), file=sys.stderr)
        return 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 1

    print(json.dumps({"ok": True, **result}, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
