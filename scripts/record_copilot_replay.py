#!/usr/bin/env python3
"""Record a real Abaqus/CAE Copilot session as a replayable frame stream.

The recording drives the same FastAPI server + CAE plugin bridge that the live
workspace uses, samples every observable UI state change (plan, action queue,
model tree, viewport PNG, errors), and writes them to a single JSON file that
the frontend can replay without Abaqus installed.

Story arc recorded by default:
  1. user prompt -> plan A -> plugin executes; action #3 hits a real failure
     (a stale .lck file is planted in the workdir beforehand, the classic
     "crashed session left a lock" situation)
  2. user asks Copilot to fix -> plan B -> clean rerun -> KPIs extracted

Usage:
  .venv/Scripts/python.exe scripts/record_copilot_replay.py
  .venv/Scripts/python.exe scripts/record_copilot_replay.py --skip-failure
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.abaqus_cmd import get_abaqus_cmd  # noqa: E402

DEFAULT_PROMPT = (
    "帮我建一个 200mm 长、20mm 高、20mm 宽的悬臂梁，材料钢，左端固定，"
    "右端向下 100N，运行并提取最大位移和最大 Mises 应力。"
)
DEFAULT_OUT = ROOT / "evidence" / "copilot_replay" / "replay.json"
PLUGIN_DIR = ROOT / "plugins" / "abaqus_agent"
JOB_NAME = "Copilot_Cantilever_Job"
SAMPLE_INTERVAL = 0.15

# A recording is a demo asset, so it ships in the public tree; but it captures
# a real traceback and a real workdir, which means it captures the recording
# machine's absolute paths. That is what kept these files out of the allowlist,
# which in turn made the README's headline demo a 404 for every public visitor.
# Redact at write time rather than at publish time: a publish step that quietly
# rewrites content is a content scanner that has stopped scanning.
REDACTED_ROOT = "<recording-workdir>"


def redact_machine_paths(payload: Any, repo_root: Path | None = None) -> Any:
    """Replace this machine's repo path with a visible placeholder, everywhere.

    Serialise-replace-reparse rather than walking the structure: the paths turn
    up inside traceback strings nested several levels down, and missing one is
    the whole failure mode. The placeholder is deliberately not path-shaped —
    a plausible-looking substitute like `C:/sim/...` would read as fact.
    """
    root = str(repo_root or ROOT)
    text = json.dumps(payload, ensure_ascii=False)
    for variant in (json.dumps(root)[1:-1],        # escaped, as it sits in JSON
                    root.replace("\\", "/"),
                    root):
        text = text.replace(variant, REDACTED_ROOT)
    out = json.loads(text)
    if isinstance(out, dict):
        out["paths_redacted"] = REDACTED_ROOT
    return out


# ── HTTP helpers (stdlib only, talking to our own local server) ──────────


def _get_json(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=15) as resp:
        return resp.read()


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ── Frame recorder ────────────────────────────────────────────────────────


class ReplayRecorder:
    """Collect timestamped frames; a sampler thread watches one session at a time."""

    def __init__(self, api: str) -> None:
        self.api = api
        self.t0 = time.time()
        self.frames: list[dict[str, Any]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def add(self, kind: str, **data: Any) -> None:
        with self._lock:
            self.frames.append({"dt": round(time.time() - self.t0, 3), "kind": kind, **data})

    def add_chat(self, role: str, text: str) -> None:
        self.add("chat", role=role, text=text)

    def start_sampling(self, session_id: str) -> None:
        self.stop_sampling()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._sample_loop, args=(session_id, self._stop), daemon=True
        )
        self._thread.start()

    def stop_sampling(self) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=10)
            self._thread = None

    def _sample_loop(self, session_id: str, stop: threading.Event) -> None:
        last_fingerprint = None
        last_model_state_at = None
        last_viewport_at = None
        base = f"{self.api}/api/copilot/sessions/{session_id}"
        while not stop.is_set():
            try:
                summary = _get_json(base)
            except (urllib.error.URLError, OSError):
                stop.wait(SAMPLE_INTERVAL)
                continue
            fingerprint = hashlib.md5(
                json.dumps(summary, sort_keys=True, default=str).encode()
            ).hexdigest()
            if fingerprint != last_fingerprint:
                last_fingerprint = fingerprint
                self.add("session", session=summary)
                if summary.get("model_state_at") and summary["model_state_at"] != last_model_state_at:
                    last_model_state_at = summary["model_state_at"]
                    try:
                        self.add("model_state", model_state=_get_json(base + "/model-state"))
                    except (urllib.error.URLError, OSError):
                        pass
                if summary.get("viewport_at") and summary["viewport_at"] != last_viewport_at:
                    last_viewport_at = summary["viewport_at"]
                    try:
                        png = _get_bytes(base + "/viewport.png")
                        self.add(
                            "viewport",
                            png_base64=base64.b64encode(png).decode("ascii"),
                            captured_at=summary["viewport_at"],
                        )
                    except (urllib.error.URLError, OSError):
                        pass
            stop.wait(SAMPLE_INTERVAL)

    def sorted_frames(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(self.frames, key=lambda f: f["dt"])


# ── Local server hosting ─────────────────────────────────────────────────


def start_local_server(port: int):
    import uvicorn

    from server import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    api = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            _get_json(f"{api}/api/copilot/status")
            return server, api
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    raise RuntimeError("Local FastAPI server did not come up on port %d" % port)


# ── Abaqus driver ─────────────────────────────────────────────────────────


def run_plugin_driver(session_id: str, api: str, workdir: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """Run the real CAE plugin bridge in `abaqus cae noGUI` against one session."""
    driver = workdir / ("copilot_replay_driver_%s.py" % session_id.replace("copilot-", ""))
    driver.write_text(
        "\n".join(
            [
                "import sys",
                "sys.path.insert(0, r'%s')" % str(PLUGIN_DIR),
                "import abaqusAgent_plugin",
                "abaqusAgent_plugin.execute_all_copilot_actions(r'%s')" % session_id,
            ]
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["ABAQUS_AGENT_SERVER_URL"] = api
    return subprocess.run(
        [get_abaqus_cmd(), "cae", "noGUI=%s" % driver.name],
        cwd=str(workdir),
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def plant_stale_lock(workdir: Path, job_name: str = JOB_NAME) -> None:
    """Recreate the classic 'crashed CAE session left a lock file' situation."""
    (workdir / (job_name + ".cae")).write_bytes(b"stale model database from a crashed session")
    (workdir / (job_name + ".lck")).write_text("stale lock", encoding="utf-8")
    os.chmod(workdir / (job_name + ".cae"), stat.S_IREAD)


def clear_stale_lock(workdir: Path, job_name: str = JOB_NAME) -> None:
    for suffix in (".cae", ".lck", ".jnl"):
        path = workdir / (job_name + suffix)
        if path.exists():
            os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
            path.unlink()


# ── Chapters ─────────────────────────────────────────────────────────────


def make_plan(recorder: ReplayRecorder, api: str, prompt: str, backend: str) -> dict[str, Any]:
    plan = _post_json(f"{api}/api/copilot/plan", {"text": prompt, "backend": backend})
    recorder.add("plan", plan=plan)
    recorder.add_chat("assistant", "%s（后端：%s）" % (plan["assistant_message"], plan["backend"]))
    _post_json(f"{api}/api/copilot/sessions/{plan['session_id']}/activate", {})
    return plan


def wait_session_settled(api: str, session_id: str) -> dict[str, Any]:
    return _get_json(f"{api}/api/copilot/sessions/{session_id}")


def record(args: argparse.Namespace) -> dict[str, Any]:
    workdir = ROOT / "artifacts" / "replay_recordings" / time.strftime("%Y%m%d_%H%M%S")
    workdir.mkdir(parents=True, exist_ok=True)
    _server, api = start_local_server(args.port)
    recorder = ReplayRecorder(api)
    log = lambda msg: print("[record] %s" % msg, flush=True)  # noqa: E731

    # Chapter 1: prompt -> plan A -> execution (optionally hitting a real failure)
    recorder.add_chat("user", args.prompt)
    plan_a = make_plan(recorder, api, args.prompt, args.backend)
    sid_a = plan_a["session_id"]
    log("plan A ready: %s (%d actions)" % (sid_a, len(plan_a["actions"])))

    if not args.skip_failure:
        plant_stale_lock(workdir, args.job_name)
        log("planted stale %s.lck + read-only .cae in %s" % (args.job_name, workdir))

    recorder.start_sampling(sid_a)
    proc = run_plugin_driver(sid_a, api, workdir)
    time.sleep(1.0)  # let the sampler catch the final state
    recorder.stop_sampling()
    summary_a = wait_session_settled(api, sid_a)
    log(
        "chapter 1 done: completed %s/%s, errors %d, abaqus rc %s"
        % (
            summary_a["completed_count"],
            summary_a["action_count"],
            len(summary_a["errors"]),
            proc.returncode,
        )
    )

    result: dict[str, Any] = {
        "version": 1,
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "prompt": args.prompt,
        "backend": args.backend,
        "abaqus_real": True,
        "workdir": str(workdir),
        "chapters": {"plan_a": sid_a},
    }

    if not args.skip_failure:
        errors = summary_a["errors"]
        if not errors:
            raise SystemExit(
                "Expected a real failure in chapter 1 but the session completed clean; "
                "adjust the failure trigger before recording."
            )
        traceback_text = str((errors[0].get("payload") or {}).get("traceback") or errors[0].get("message"))
        log("real failure captured: %s" % traceback_text.strip().splitlines()[-1])

        # Chapter 2: the user clicks "让 Copilot 修复" -> plan B -> clean rerun.
        # Mirror the exact prompt the frontend's one-click fix builds.
        diagnosis = errors[0].get("diagnosis") or {}
        diagnosis_line = (
            "\n\n诊断：%s——%s\n建议：%s"
            % (diagnosis.get("title"), diagnosis.get("explanation"), diagnosis.get("suggestion"))
            if diagnosis
            else ""
        )
        fix_text = (
            "我在 Abaqus/CAE 里执行动作 #%d 时报错了，请按诊断修复并给出新的操作计划：%s\n\n%s"
            % (int(errors[0]["action_index"]) + 1, diagnosis_line, traceback_text[-1200:])
        )
        recorder.add_chat("user", fix_text)
        clear_stale_lock(workdir, args.job_name)
        plan_b = make_plan(recorder, api, args.prompt, args.backend)
        sid_b = plan_b["session_id"]
        result["chapters"]["plan_b"] = sid_b
        log("plan B ready: %s" % sid_b)

        recorder.start_sampling(sid_b)
        proc_b = run_plugin_driver(sid_b, api, workdir)
        time.sleep(1.0)
        recorder.stop_sampling()
        summary_b = wait_session_settled(api, sid_b)
        log(
            "chapter 2 done: completed %s/%s, errors %d, abaqus rc %s"
            % (
                summary_b["completed_count"],
                summary_b["action_count"],
                len(summary_b["errors"]),
                proc_b.returncode,
            )
        )
        if summary_b["errors"] or summary_b["completed_count"] != summary_b["action_count"]:
            raise SystemExit("Chapter 2 rerun was expected to complete clean but did not.")

    # Closing chat: real KPIs from the run
    kpi_file = workdir / (args.job_name + "_copilot_result.json")
    if kpi_file.exists():
        kpis = json.loads(kpi_file.read_text(encoding="utf-8"))
        freqs = kpis.get("natural_frequencies_hz")
        if freqs:
            recorder.add_chat(
                "assistant",
                "作业 %s 模态求解完成：一阶固有频率 %.1f Hz（前 %d 阶：%s；一阶可对照悬臂梁解析解校核）。"
                % (
                    kpis.get("job_name"),
                    float(freqs[0]),
                    len(freqs),
                    "、".join("%.1f" % f for f in freqs),
                ),
            )
            result["kpis"] = kpis
            result["frames"] = recorder.sorted_frames()
            return result
        kt = kpis.get("stress_concentration_kt")
        kt_line = "，孔边应力集中系数 Kt=%.2f（Howland 理论约 3.1）" % float(kt) if kt else ""
        mid = kpis.get("midspan_deflection")
        mid_line = "，跨中挠度 %.4f mm（可对照 PL^3/48EI 手算校核）" % float(mid) if mid else ""
        recorder.add_chat(
            "assistant",
            "作业 %s 求解完成：最大位移 %.4f mm，最大 Mises 应力 %.2f MPa%s%s。"
            % (
                kpis.get("job_name"),
                float(kpis.get("max_displacement") or 0.0),
                float(kpis.get("max_mises") or 0.0),
                mid_line,
                kt_line,
            ),
        )
        result["kpis"] = kpis

    result["frames"] = recorder.sorted_frames()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--backend", default="template", choices=["template", "codex", "codex_strict"])
    parser.add_argument("--port", type=int, default=8123)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--job-name", default=JOB_NAME, help="job whose result JSON closes the story")
    parser.add_argument("--skip-failure", action="store_true", help="record a clean run only")
    args = parser.parse_args(argv)

    result = redact_machine_paths(record(args))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    print(
        "[record] wrote %s (%d frames, %.0f KB)"
        % (out, len(result["frames"]), size_kb)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
