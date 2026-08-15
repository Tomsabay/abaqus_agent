"""
scripts/run_workbench_browser_check.py
--------------------------------------
Browser-level E2E for the workbench, driven by Playwright chromium:

  type a request in the chat -> proposal card renders -> diff view renders
  -> click 接受并求解 -> live console streams -> results banner COMPLETED
  -> KPI cards render -> contour <img> actually loads pixels.

Screenshots + assertion evidence go to artifacts/workbench/browser_check/.

Usage:
  .venv/Scripts/python.exe scripts/run_workbench_browser_check.py [--backend auto|template]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8032
BASE = f"http://127.0.0.1:{PORT}"
OUT_DIR = ROOT / "artifacts" / "workbench" / "browser_check"

CHAT_TEXT = (
    "悬臂梁 100x10x10 mm，钢，左端固定，右端向下 1N 集中力，"
    "网格 2mm，求尖端位移和最大 Mises 应力"
)


def wait_health(deadline_s: int = 60) -> None:
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=5):
                return
        except OSError:
            time.sleep(1)
    raise RuntimeError("server did not become healthy")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="auto", choices=["auto", "claude_cli", "template"])
    args = parser.parse_args()

    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    evidence: dict = {"started_at": time.time(), "backend": args.backend, "steps": {}}

    # File, not PIPE: an undrained PIPE freezes uvicorn once the buffer fills.
    server_log = open(OUT_DIR / "server.log", "w", encoding="utf-8")  # noqa: SIM115
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--port", str(PORT)],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    try:
        wait_health()
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1680, "height": 950})
            page.goto(BASE + "/workbench", wait_until="networkidle")

            page.click("#btn-new-session")
            page.wait_for_timeout(500)

            page.select_option("#backend-select", args.backend)
            page.fill("#chat-input", CHAT_TEXT)
            t0 = time.time()
            page.click("#btn-send")
            page.wait_for_selector(".proposal-card", timeout=300_000)
            evidence["steps"]["proposal"] = {
                "elapsed_s": round(time.time() - t0, 1),
                "diff_line_count": page.locator("#diff-body .dline").count(),
            }
            assert page.locator("#diff-body .dline.add").count() > 0, "no + lines in diff view"
            page.screenshot(path=str(OUT_DIR / "1_proposal_diff.png"))

            t0 = time.time()
            page.click("#btn-accept")
            page.wait_for_selector(".status-banner", timeout=120_000)
            page.wait_for_timeout(2_000)
            page.screenshot(path=str(OUT_DIR / "2_solving_console.png"))

            page.wait_for_selector(".status-banner.ok", timeout=900_000)
            evidence["steps"]["solve"] = {"elapsed_s": round(time.time() - t0, 1)}

            page.wait_for_selector(".kpi-card", timeout=30_000)
            kpi_cards = page.locator(".kpi-card").count()
            page.wait_for_selector(".visual-card img", timeout=60_000)
            page.wait_for_function(
                "() => [...document.querySelectorAll('.visual-card img')]"
                ".some(i => i.complete && i.naturalWidth > 50)",
                timeout=60_000,
            )
            visual_imgs = page.evaluate(
                "[...document.querySelectorAll('.visual-card img')]"
                ".map(i => ({src: i.src.split('/').pop(), w: i.naturalWidth, h: i.naturalHeight}))")
            kpi_values = page.evaluate(
                "[...document.querySelectorAll('.kpi-card')].map(c => ({"
                "name: c.querySelector('.kpi-name').textContent,"
                "value: c.querySelector('.kpi-value').textContent}))")
            evidence["steps"]["results"] = {
                "kpi_cards": kpi_cards,
                "kpi_values": kpi_values,
                "visual_imgs": visual_imgs,
            }
            assert kpi_cards >= 1, "no KPI cards rendered"
            assert any(v["w"] > 50 for v in visual_imgs), "no contour image loaded pixels"
            page.wait_for_timeout(400)
            page.screenshot(path=str(OUT_DIR / "3_results_kpi_contour.png"), full_page=False)

            run_items = page.locator(".run-item").count()
            evidence["steps"]["run_history_items"] = run_items
            assert run_items >= 1, "run history empty"

            browser.close()
        evidence["overall"] = "PASS"
        return 0
    except Exception as e:  # noqa: BLE001 — evidence must record any failure kind
        evidence["overall"] = "FAIL"
        evidence["error"] = str(e)[:800]
        return 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()
        evidence["finished_at"] = time.time()
        out = OUT_DIR / "browser_check.json"
        out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        print(f"\nevidence -> {out}")


if __name__ == "__main__":
    sys.exit(main())
