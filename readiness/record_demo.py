#!/usr/bin/env python3
"""
record_demo.py — Record a browser agent session as a video demo.

Records the browser agent attempting a task (e.g., add-to-cart) on a live URL,
saving the video + action log for use in demos and presentations.

Usage:
  python readiness/record_demo.py --url https://skims.com/products/fits-everybody-bandeau-bra-umber \
      --flow atc --out readiness/.scans/demos/skims-atc

Output:
  <out>/recording.webm   — browser session video
  <out>/steps.json        — action log with timestamps
  <out>/screenshots/      — per-step screenshots
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from dotenv import load_dotenv
load_dotenv(pathlib.Path(__file__).resolve().parent.parent / ".env")


def record_atc(url: str, out_dir: pathlib.Path, timeout: int = 30):
    """Record an add-to-cart browser agent session with video."""
    from playwright.sync_api import sync_playwright
    from browser_agent import (
        _extract_elements, _screenshot_b64, _ask_agent,
        _dismiss_popups, _force_clear_modals, MAX_STEPS,
    )
    import base64

    out_dir.mkdir(parents=True, exist_ok=True)
    screenshots_dir = out_dir / "screenshots"
    screenshots_dir.mkdir(exist_ok=True)

    steps = []
    goal = "Add the main product on this page to the shopping cart."

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)  # visible for recording
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            record_video_dir=str(out_dir),
            record_video_size={"width": 1280, "height": 800},
        )
        page = ctx.new_page()
        t0 = time.time()

        print(f"  Opening {url}...")
        page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        _dismiss_popups(page)

        consecutive_fails = 0
        last_selector = None
        repeat_count = 0

        for step_num in range(1, MAX_STEPS + 1):
            if consecutive_fails >= 3:
                _force_clear_modals(page)
                consecutive_fails = 0

            elements = _extract_elements(page)
            screenshot_b64 = _screenshot_b64(page)

            # Save screenshot
            ss_path = screenshots_dir / f"step_{step_num:02d}.png"
            ss_bytes = base64.b64decode(screenshot_b64)
            ss_path.write_bytes(ss_bytes)

            action = _ask_agent(elements, screenshot_b64, goal, steps, step_num)
            elapsed = round(time.time() - t0, 1)

            act = action.get("action", "fail")
            selector = action.get("selector", "")
            reason = action.get("reason", "")

            # Detect stuck loop
            if act == "click" and selector and selector == last_selector:
                repeat_count += 1
                if repeat_count >= 2:
                    step_record = {
                        "step": step_num, "action": "fail",
                        "selector": selector, "reason": "Stuck loop detected",
                        "result": "fail", "elapsed_s": elapsed,
                    }
                    steps.append(step_record)
                    print(f"  Step {step_num}: STUCK LOOP on {selector[:50]}")
                    break
            else:
                repeat_count = 0
            last_selector = selector

            result_str = "pending"
            try:
                if act == "click" and selector:
                    page.click(selector, timeout=5000)
                    page.wait_for_timeout(1500)
                    result_str = "ok"
                    consecutive_fails = 0
                elif act == "select" and selector:
                    value = action.get("value", "")
                    page.select_option(selector, value, timeout=5000)
                    page.wait_for_timeout(1000)
                    result_str = "ok"
                    consecutive_fails = 0
                elif act == "type" and selector:
                    text = action.get("text", action.get("value", ""))
                    page.fill(selector, text, timeout=5000)
                    page.wait_for_timeout(500)
                    result_str = "ok"
                    consecutive_fails = 0
                elif act == "scroll":
                    page.evaluate("window.scrollBy(0, 400)")
                    page.wait_for_timeout(1000)
                    result_str = "ok"
                elif act == "done":
                    result_str = "done"
                elif act == "fail":
                    result_str = "fail"
                else:
                    result_str = f"unknown action: {act}"
                    consecutive_fails += 1
            except Exception as e:
                result_str = f"error: {str(e)[:80]}"
                consecutive_fails += 1

            step_record = {
                "step": step_num, "action": act, "selector": selector[:80],
                "reason": reason, "result": result_str, "elapsed_s": elapsed,
            }
            steps.append(step_record)
            print(f"  Step {step_num}: {act}({selector[:40]}) → {result_str}")

            if act in ("done", "fail"):
                break

        # Final screenshot
        final_ss = screenshots_dir / "final.png"
        page.screenshot(path=str(final_ss))

        # Close context to finalize video
        video_path = page.video.path()
        ctx.close()
        browser.close()

    # Rename video file
    import shutil
    final_video = out_dir / "recording.webm"
    if pathlib.Path(video_path).exists():
        shutil.move(video_path, final_video)
        print(f"\n  Video saved: {final_video}")

    # Save action log
    log = {
        "url": url,
        "flow": "add_to_cart",
        "total_steps": len(steps),
        "success": any(s["result"] == "done" for s in steps),
        "steps": steps,
    }
    log_path = out_dir / "steps.json"
    log_path.write_text(json.dumps(log, indent=2))
    print(f"  Action log: {log_path}")
    print(f"  Screenshots: {screenshots_dir}")

    return log


def main():
    ap = argparse.ArgumentParser(description="Record a browser agent demo session")
    ap.add_argument("--url", required=True, help="Product page URL")
    ap.add_argument("--flow", default="atc", choices=["atc"],
                    help="Flow to record (default: atc)")
    ap.add_argument("--out", required=True, type=pathlib.Path,
                    help="Output directory for video + logs")
    args = ap.parse_args()

    print(f"\n  RECORDING DEMO: {args.flow} on {args.url}\n")
    record_atc(args.url, args.out)


if __name__ == "__main__":
    main()
