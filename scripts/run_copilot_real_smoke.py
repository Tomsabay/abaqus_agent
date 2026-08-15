#!/usr/bin/env python3
"""Run the Copilot MVP through a real Abaqus noGUI target.

This command is intentionally narrow: it proves the user-facing Copilot chain
for one cantilever request without requiring the web UI.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from copilot.planner import build_copilot_plan, execute_plan  # noqa: E402

DEFAULT_PROMPT = (
    "帮我建一个 200mm 长、20mm 高、20mm 宽的悬臂梁，材料钢，左端固定，"
    "右端向下 100N，运行并提取最大位移和最大 Mises 应力。"
)
DEFAULT_REMOTE_SCRIPT = "copilot_real_smoke.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--backend", default="codex_strict", choices=["codex", "codex_strict", "template"])
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--remote-host", default="")
    # No defaults: the account and checkout path belong to whoever runs this.
    # They used to default to the author's, which was both a privacy leak and
    # useless to anyone else.
    parser.add_argument("--remote-user", default="",
                        help="SSH user on the Windows host (required unless --skip-remote)")
    parser.add_argument("--remote-path", default="",
                        help="Checkout path on the remote host (required unless --skip-remote)")
    parser.add_argument("--remote-script", default=DEFAULT_REMOTE_SCRIPT)
    parser.add_argument("--identity-file", default=str(Path.home() / ".ssh" / "id_ed25519"))
    parser.add_argument("--proxy-command", default="")
    parser.add_argument("--skip-remote", action="store_true")
    args = parser.parse_args(argv)

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    plan = build_copilot_plan(args.prompt, backend=args.backend)
    execution = execute_plan(plan, bridge_mode="mock")
    script_path = Path(execution.script_path)
    out_dir = Path(args.out_dir) if args.out_dir else script_path.parent / "real_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)

    result: dict[str, Any] = {
        "started_at": started_at,
        "prompt": args.prompt,
        "plan": plan.model_dump(),
        "execution": execution.model_dump(),
        "script_path": str(script_path),
        "remote": None,
        "overall_status": "SCRIPT_GENERATED",
    }
    job_name = _job_name_from_script(script_path)

    if not args.skip_remote:
        missing = [
            name for name, value in (
                ("--remote-host", args.remote_host),
                ("--remote-user", args.remote_user),
                ("--remote-path", args.remote_path),
            ) if not value
        ]
        if missing:
            raise SystemExit(
                "%s required unless --skip-remote is set" % ", ".join(missing))
        result["remote"] = _run_remote_abaqus(
            script_path=script_path,
            out_dir=out_dir,
            remote_user=args.remote_user,
            remote_host=args.remote_host,
            remote_path=args.remote_path,
            remote_script=args.remote_script,
            job_name=job_name,
            identity_file=args.identity_file,
            proxy_command=args.proxy_command,
        )
        remote_result = result["remote"].get("copilot_result") or {}
        result["overall_status"] = (
            "PASS" if remote_result.get("status") == "COMPLETED" else "FAIL"
        )

    summary_path = out_dir / "copilot_real_smoke_summary.json"
    summary_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    return 0 if result["overall_status"] in {"PASS", "SCRIPT_GENERATED"} else 1


def _run_remote_abaqus(
    *,
    script_path: Path,
    out_dir: Path,
    remote_user: str,
    remote_host: str,
    remote_path: str,
    remote_script: str,
    job_name: str,
    identity_file: str,
    proxy_command: str,
) -> dict[str, Any]:
    remote = f"{remote_user}@{remote_host}"
    ssh_base = _ssh_base(identity_file=identity_file, proxy_command=proxy_command)
    scp_base = _scp_base(identity_file=identity_file, proxy_command=proxy_command)
    remote_script_path = f"{remote_path.rstrip('/')}/{remote_script}"
    remote_cmd_path = remote_path.replace("/", "\\")

    _run([*scp_base, str(script_path), f"{remote}:{remote_script_path}"])
    _run(
        [
            *ssh_base,
            remote,
            (
                f'cmd /c "cd /d {remote_cmd_path} && '
                f"del /q {job_name}.* 2>nul & "
                f'abaqus cae noGUI={remote_script}"'
            ),
        ],
        timeout=600,
    )

    local_files: dict[str, str] = {}
    for filename in [
        f"{job_name}_copilot_result.json",
        f"{job_name}.sta",
        f"{job_name}.log",
    ]:
        local_path = out_dir / filename
        _run([*scp_base, f"{remote}:{remote_path.rstrip('/')}/{filename}", str(local_path)])
        local_files[filename] = str(local_path)

    copilot_result = json.loads(
        Path(local_files[f"{job_name}_copilot_result.json"]).read_text(encoding="utf-8")
    )
    return {
        "host": remote_host,
        "user": remote_user,
        "remote_path": remote_path,
        "remote_script": remote_script,
        "job_name": job_name,
        "files": local_files,
        "copilot_result": copilot_result,
    }


def _job_name_from_script(script_path: Path) -> str:
    for line in script_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("COPILOT_JOB_NAME = "):
            return line.split("=", 1)[1].strip().strip("'\"")
    return "CantileverBeamJob"


def _ssh_base(*, identity_file: str, proxy_command: str) -> list[str]:
    cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ServerAliveInterval=30",
        "-i",
        identity_file,
    ]
    if proxy_command:
        cmd.extend(["-o", f"ProxyCommand={proxy_command}"])
    return cmd


def _scp_base(*, identity_file: str, proxy_command: str) -> list[str]:
    cmd = [
        "scp",
        "-i",
        identity_file,
    ]
    if proxy_command:
        cmd.extend(["-o", f"ProxyCommand={proxy_command}"])
    return cmd


def _run(cmd: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    if not shutil.which(cmd[0]):
        raise RuntimeError(f"Command not found: {cmd[0]}")
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    if proc.returncode != 0:
        output = "\n".join(part for part in [proc.stdout, proc.stderr] if part).strip()
        raise RuntimeError(f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{output}")
    return proc


if __name__ == "__main__":
    raise SystemExit(main())
