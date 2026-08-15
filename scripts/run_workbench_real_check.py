"""
scripts/run_workbench_real_check.py
-----------------------------------
Real-solve E2E for the Cursor-style workbench:

  chat (claude CLI or template) -> spec proposal + diff -> accept
  -> real Abaqus solve -> KPIs + contour PNGs served over HTTP.

Requires real Abaqus on PATH and (for the claude backend) a logged-in
claude CLI. Evidence JSON is written to artifacts/workbench/real_check/.

Usage:
  .venv/Scripts/python.exe scripts/run_workbench_real_check.py [--backend auto|template]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8031
BASE = f"http://127.0.0.1:{PORT}"
TERMINAL = ("COMPLETED", "FAILED", "ABORTED", "ERROR")

CHAT_TEXT = (
    "悬臂梁 100x10x10 mm，钢，左端固定，右端向下 1N 集中力，"
    "网格 2mm，求尖端位移和最大 Mises 应力"
)


def http_json(method: str, path: str, payload: dict | None = None, timeout: int = 300) -> dict:
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_status(path: str) -> int:
    try:
        with urllib.request.urlopen(BASE + path, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code


def wait_health(deadline_s: int = 60) -> dict:
    t0 = time.time()
    while time.time() - t0 < deadline_s:
        try:
            return http_json("GET", "/health", timeout=5)
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise RuntimeError("server did not become healthy")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="auto", choices=["auto", "claude_cli", "template"])
    args = parser.parse_args()

    evidence: dict = {"started_at": time.time(), "backend_requested": args.backend, "steps": {}}
    out_dir = ROOT / "artifacts" / "workbench" / "real_check"
    out_dir.mkdir(parents=True, exist_ok=True)
    # File, not PIPE: an undrained PIPE freezes uvicorn once the buffer fills.
    server_log = open(out_dir / "server.log", "w", encoding="utf-8")  # noqa: SIM115
    server = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--port", str(PORT)],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    try:
        health = wait_health()
        evidence["steps"]["health"] = health
        if not health.get("abaqus_available"):
            raise RuntimeError("real Abaqus not available on PATH — this check needs it")

        assert http_status("/workbench") == 200, "/workbench page not served"
        evidence["steps"]["workbench_page"] = "200 OK"

        session = http_json("POST", "/api/workbench/sessions", {"title": "real-check"})
        sid = session["session_id"]

        t0 = time.time()
        chat = http_json("POST", f"/api/workbench/sessions/{sid}/chat",
                         {"text": CHAT_TEXT, "backend": args.backend}, timeout=300)
        pending = chat.get("pending")
        assert pending, f"no proposal returned: {json.dumps(chat)[:400]}"
        assert "+" in pending["diff"], "diff has no additions"
        evidence["steps"]["chat"] = {
            "elapsed_s": round(time.time() - t0, 1),
            "backend_used": pending["backend"],
            "diff_lines": len(pending["diff"].splitlines()),
            "summary_head": pending["summary"][:160],
        }

        accepted = http_json("POST", f"/api/workbench/sessions/{sid}/accept", {})
        run_id = accepted["run_id"]
        evidence["steps"]["accept"] = {"run_id": run_id}

        t0 = time.time()
        run = None
        while time.time() - t0 < 900:
            run = http_json("GET", f"/api/run/{run_id}")
            if run["status"] in TERMINAL:
                break
            time.sleep(5)
        assert run and run["status"] == "COMPLETED", \
            f"run ended {run and run['status']}: {json.dumps(run.get('stages', {}), default=str)[:600]}"
        evidence["steps"]["solve"] = {
            "elapsed_s": round(time.time() - t0, 1),
            "status": run["status"],
            "kpis": run.get("kpis", {}),
        }

        kpis = run.get("kpis", {})
        assert kpis, "no KPIs extracted"
        visuals = [v for v in run.get("orchestrator_result", {}).get("visuals", []) if v]
        assert visuals, "no contour images exported"
        artifact_checks = {}
        for v in visuals:
            raw = (v.get("path") or v.get("file") or "") if isinstance(v, dict) else v
            name = Path(str(raw)).name
            artifact_checks[name] = http_status(f"/api/run/{run_id}/artifact/{name}")
        evidence["steps"]["visuals"] = artifact_checks
        assert all(code == 200 for code in artifact_checks.values()), "artifact PNG not served"

        final_session = http_json("GET", f"/api/workbench/sessions/{sid}")
        record = next(r for r in final_session["runs"] if r["run_id"] == run_id)
        assert record["status"] == "COMPLETED" and record.get("kpis"), "session record not synced"
        evidence["steps"]["session_sync"] = {
            "status": record["status"],
            "visuals": record.get("visuals", []),
        }

        evidence["overall"] = "PASS"
        return 0
    except Exception as e:  # noqa: BLE001 — evidence must record any failure kind
        evidence["overall"] = "FAIL"
        evidence["error"] = str(e)
        return 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        server_log.close()
        evidence["finished_at"] = time.time()
        out_path = out_dir / "workbench_real_check.json"
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        print(f"\nevidence -> {out_path}")


if __name__ == "__main__":
    sys.exit(main())
