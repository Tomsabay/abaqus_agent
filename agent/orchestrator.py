"""
orchestrator.py
---------------
AbaqusOrchestrator: end-to-end pipeline controller.

Pipeline stages:
  1. validate_spec    - schema + structural checks
  2. build_model      - CAE noGUI → .inp
  3. syntaxcheck      - syntaxcheck (no license consumed)
  4. submit_job       - analysis execution
  5. monitor_job      - poll until completion
  6. extract_kpis     - ODB → KPI dict
  7. compare_expected - compare against expected.json (if provided)

All stages return structured dicts. Failures raise AbaqusAgentError
with an ErrorCode and a suggested fix.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from runner.build_model import build_model
from runner.syntaxcheck import syntaxcheck_inp
from runner.submit_job import submit_job
from runner.monitor_job import monitor_job, JobStatus
from post.extract_kpis import extract_kpis
from tools.errors import AbaqusAgentError, ErrorCode
from tools.schema_validator import validate_spec


class AbaqusOrchestrator:
    """
    Orchestrates the full Abaqus agent pipeline.

    Parameters
    ----------
    spec_path       : Path to spec.yaml
    workdir         : Override working directory
    expected_path   : Path to expected.json for regression comparison
    runner_cfg_path : Path to runner.json (cpus, timeout, etc.)
    on_progress     : Optional callback(stage: str, data: dict)
    """

    def __init__(
        self,
        spec_path: str | Path,
        workdir: str | Path | None = None,
        expected_path: str | Path | None = None,
        runner_cfg_path: str | Path | None = None,
        on_progress: Callable[[str, dict], None] | None = None,
    ):
        self.spec_path    = Path(spec_path).resolve()
        self.workdir      = Path(workdir) if workdir else None
        self.on_progress  = on_progress or (lambda s, d: None)

        # Load spec
        with open(self.spec_path, encoding="utf-8") as f:
            self.spec = yaml.safe_load(f)

        # Load runner config (with defaults)
        self.runner_cfg = {
            "cpus": 1,
            "mp_mode": "threads",
            "memory": "90%",
            "timeout_seconds": 1800,
            "allow_license_queue": False,
            "syntaxcheck_first": True,
        }
        if runner_cfg_path:
            with open(runner_cfg_path, encoding="utf-8") as f:
                self.runner_cfg.update(json.load(f))

        # Load expected KPIs
        self.expected: dict | None = None
        if expected_path and Path(expected_path).exists():
            with open(expected_path, encoding="utf-8") as f:
                self.expected = json.load(f)

        # Pipeline result accumulator
        self.result: dict = {
            "spec_path": str(self.spec_path),
            "started_at": datetime.now().isoformat(),
            "stages": {},
            "kpis": {},
            "regression": {},
            "status": "PENDING",
        }

    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------

    def run(self) -> dict:
        """Execute the full pipeline. Returns final result dict."""
        try:
            self._stage_validate()
            build_result = self._stage_build()
            inp_path = build_result["inp_path"]

            if self.runner_cfg.get("syntaxcheck_first", True):
                self._stage_syntaxcheck(inp_path, build_result["workdir"])

            submit_result = self._stage_submit(inp_path, build_result["workdir"])
            self._stage_monitor(submit_result)

            odb_path = build_result["workdir"] / f"{self.spec['meta']['model_name']}.odb"
            kpi_result = self._stage_extract(odb_path)

            if self.expected:
                self._stage_compare(kpi_result.get("kpis", {}))

            self.result["status"] = "COMPLETED"
        except AbaqusAgentError as e:
            self.result["status"] = "FAILED"
            self.result["error"] = e.to_dict()
        except Exception as e:
            self.result["status"] = "ERROR"
            self.result["error"] = {"error_code": "UNKNOWN", "message": str(e)}

        self.result["finished_at"] = datetime.now().isoformat()
        self._save_result()
        return self.result

    # -------------------------------------------------------------------------
    # Pipeline stages
    # -------------------------------------------------------------------------

    def _stage_validate(self):
        self.on_progress("validate_spec", {})
        valid, errors = validate_spec(self.spec)
        stage = {"valid": valid, "errors": errors}
        self.result["stages"]["validate_spec"] = stage
        if not valid:
            raise AbaqusAgentError(
                ErrorCode.SPEC_INVALID,
                f"Spec validation failed: {'; '.join(errors)}",
            )
        self.on_progress("validate_spec", {"ok": True})

    def _stage_build(self) -> dict:
        self.on_progress("build_model", {})
        result = build_model(self.spec_path, self.workdir)
        self.result["stages"]["build_model"] = {k: str(v) for k, v in result.items()}
        self.workdir = result["workdir"]
        self.on_progress("build_model", {"inp": str(result["inp_path"])})
        return result

    def _stage_syntaxcheck(self, inp_path: Path, workdir: Path):
        self.on_progress("syntaxcheck", {})
        result = syntaxcheck_inp(inp_path, workdir)
        self.result["stages"]["syntaxcheck"] = result
        if not result["ok"]:
            raise AbaqusAgentError(
                ErrorCode.SYNTAX_ERROR,
                f"syntaxcheck failed: {result['errors'][:3]}",
                workdir=str(workdir),
            )
        self.on_progress("syntaxcheck", {"ok": True, "warnings": len(result["warnings"])})

    def _stage_submit(self, inp_path: Path, workdir: Path) -> dict:
        self.on_progress("submit_job", {})
        result = submit_job(
            inp_path=inp_path,
            workdir=workdir,
            cpus=self.runner_cfg["cpus"],
            mp_mode=self.runner_cfg["mp_mode"],
            memory=self.runner_cfg["memory"],
            background=False,
            interactive=True,
            allow_license_queue=self.runner_cfg["allow_license_queue"],
            timeout_seconds=self.runner_cfg["timeout_seconds"],
        )
        self.result["stages"]["submit_job"] = {k: str(v) for k, v in result.items()}
        self.on_progress("submit_job", {"status": result.get("status")})
        return result

    def _stage_monitor(self, submit_result: dict):
        """For interactive mode this is already done; for background mode we poll."""
        job_name = submit_result.get("job_name", "")
        workdir  = Path(submit_result.get("workdir", self.workdir))

        if submit_result.get("status") == "completed":
            self.result["stages"]["monitor_job"] = {"status": JobStatus.COMPLETED}
            return

        # Background polling loop
        deadline = time.time() + self.runner_cfg["timeout_seconds"]
        poll_interval = 10
        while time.time() < deadline:
            status = monitor_job(job_name, workdir)
            self.result["stages"]["monitor_job"] = status
            self.on_progress("monitor_job", status)
            if status["status"] in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.ABORTED):
                break
            time.sleep(poll_interval)
            poll_interval = min(poll_interval * 1.5, 60)

        final = self.result["stages"].get("monitor_job", {})
        if final.get("status") not in (JobStatus.COMPLETED,):
            raise AbaqusAgentError(
                ErrorCode.JOB_FAILED,
                f"Job ended with status: {final.get('status')}",
                log_snippet=str(final.get("errors", "")),
                workdir=str(workdir),
            )

    def _stage_extract(self, odb_path: Path) -> dict:
        self.on_progress("extract_kpis", {})
        kpi_spec = self.spec.get("outputs", {}).get("kpis", [])
        result = extract_kpis(odb_path, kpi_spec, self.workdir)
        self.result["stages"]["extract_kpis"] = result
        self.result["kpis"] = result.get("kpis", {})
        if result.get("errors"):
            self.on_progress("extract_kpis", {"warnings": result["errors"]})
        else:
            self.on_progress("extract_kpis", {"kpis": self.result["kpis"]})
        return result

    def _stage_compare(self, actual_kpis: dict):
        """Compare extracted KPIs against expected.json."""
        expected_kpis = self.expected.get("kpis", {})
        comparison = {}

        for name, expected_def in expected_kpis.items():
            exp_val  = expected_def.get("value")
            rtol     = expected_def.get("rtol", 0.10)
            atol     = expected_def.get("atol", 0.0)
            act_val  = actual_kpis.get(name)

            if act_val is None:
                comparison[name] = {"status": "MISSING", "expected": exp_val, "actual": None}
                continue

            # Check within tolerance
            if exp_val is not None and exp_val != 0:
                rel_err = abs(act_val - exp_val) / abs(exp_val)
                abs_err = abs(act_val - exp_val)
                passed  = rel_err <= rtol or abs_err <= atol
                comparison[name] = {
                    "status": "PASS" if passed else "FAIL",
                    "expected": exp_val,
                    "actual": act_val,
                    "rel_err": round(rel_err, 4),
                    "abs_err": round(abs_err, 6),
                    "rtol": rtol,
                    "atol": atol,
                }
            else:
                comparison[name] = {"status": "INFO", "expected": exp_val, "actual": act_val}

        all_pass = all(v.get("status") in ("PASS", "INFO") for v in comparison.values())
        self.result["regression"] = {
            "passed": all_pass,
            "comparisons": comparison,
        }
        self.on_progress("compare_kpis", {"passed": all_pass, "details": comparison})

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save_result(self):
        if self.workdir:
            result_path = Path(self.workdir) / "result.json"
            try:
                result_path.write_text(
                    json.dumps(self.result, indent=2, default=str),
                    encoding="utf-8",
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python agent/orchestrator.py <spec.yaml> [expected.json] [runner.json]")
        sys.exit(1)

    def _progress(stage, data):
        print(f"  [{stage}] {data}")

    orch = AbaqusOrchestrator(
        spec_path=sys.argv[1],
        expected_path=sys.argv[2] if len(sys.argv) > 2 else None,
        runner_cfg_path=sys.argv[3] if len(sys.argv) > 3 else None,
        on_progress=_progress,
    )
    result = orch.run()
    print(json.dumps(result, indent=2, default=str))
    sys.exit(0 if result["status"] == "COMPLETED" else 1)
