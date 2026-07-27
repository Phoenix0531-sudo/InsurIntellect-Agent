#!/usr/bin/env python
"""Capture four distinct UI states for README screenshots.

Requires running demo at BASE (default http://127.0.0.1:8766).
Uses Playwright Chromium. Overwrites docs/screenshots/*.png.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHOTS = ROOT / "docs" / "screenshots"


def wait_ready(page, timeout_ms: int = 60000) -> None:
    page.wait_for_selector("#askForm", timeout=timeout_ms)
    # corpus select should load
    page.wait_for_function(
        """() => {
          const s = document.getElementById('pdfSelect');
          return s && s.options && s.options.length >= 1;
        }""",
        timeout=timeout_ms,
    )


def ask(page, question: str, timeout_ms: int = 180000) -> None:
    page.fill("#messageInput", question)
    page.click("#sendBtn")
    # wait until gen pill hides and an assistant message exists
    page.wait_for_function(
        """() => {
          const gen = document.getElementById('genPill');
          const msgs = document.querySelectorAll('#messages .msg.assistant, #messages .message.assistant, #messages .assistant');
          const anyMsg = document.querySelectorAll('#messages .msg, #messages .message');
          const hidden = !gen || gen.hasAttribute('hidden') || gen.offsetParent === null;
          return hidden && (msgs.length > 0 || anyMsg.length >= 2);
        }""",
        timeout=timeout_ms,
    )
    time.sleep(1.2)


def reset_chat(page) -> None:
    btn = page.locator("#resetBtn")
    if btn.count():
        btn.click()
        time.sleep(0.6)


def shot(page, name: str, full: bool = True) -> Path:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / name
    page.screenshot(path=str(path), full_page=full)
    print(f"wrote {path} size={path.stat().st_size}")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8766")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    args = ap.parse_args()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": args.width, "height": args.height},
            device_scale_factor=1.25,
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto(args.base + "/", wait_until="networkidle", timeout=60000)
        wait_ready(page)

        # 1) empty / cold welcome
        reset_chat(page)
        page.wait_for_selector("#emptyChat:not([hidden])", timeout=10000)
        shot(page, "preview_empty.png")

        # 2) main dual-pane with answer + citations (Q1)
        ask(page, "等待期是多久？")
        page.wait_for_selector(".citations, .citations-title", timeout=30000)
        shot(page, "preview.png")

        # 3) citations-focused: scroll assistant message citations into view,
        #    optionally expand first card / click first cite
        cite = page.locator(".citations").first
        if cite.count():
            cite.scroll_into_view_if_needed()
            time.sleep(0.4)
        first_card = page.locator(".citations .cite, .citations .citation, .citations button, .citations a, .citations .cite-card").first
        if first_card.count():
            try:
                first_card.click(timeout=3000)
                time.sleep(1.0)
            except Exception as e:
                print("cite click skip:", e)
        # crop-ish by scrolling right panel a bit more and taking viewport shot
        page.evaluate(
            """() => {
              const m = document.getElementById('messages') || document.getElementById('aiWindow');
              if (m) m.scrollTop = m.scrollHeight;
            }"""
        )
        time.sleep(0.5)
        # full page still, but content should differ (PDF open + evidence strip)
        shot(page, "citations.png")

        # 4) refuse / advice boundary
        reset_chat(page)
        ask(page, "这份保单保证我一定能获赔吗？")
        time.sleep(0.8)
        shot(page, "refuse_advice.png")

        # optional: also capture weather refusal if needed later
        browser.close()

    # hash check
    import hashlib

    def h(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()[:12]

    pairs = [
        ("preview.png", "citations.png"),
        ("preview.png", "refuse_advice.png"),
        ("preview.png", "preview_empty.png"),
        ("citations.png", "refuse_advice.png"),
    ]
    for a, b in pairs:
        pa, pb = SHOTS / a, SHOTS / b
        same = h(pa) == h(pb)
        print(f"hash {a}={h(pa)} {b}={h(pb)} same={same}")
        if a == "preview.png" and b == "citations.png" and same:
            print("WARN: preview still identical to citations")
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
