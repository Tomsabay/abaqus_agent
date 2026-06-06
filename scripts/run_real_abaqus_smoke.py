#!/usr/bin/env python3
# ruff: noqa: E402,I001
"""
Minimal real Abaqus smoke/evidence harness.

The harness records a reproducible stage-by-stage evidence bundle. Dry-run and
mock-real modes are intentionally not real Abaqus verification.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import sys
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from capsule.metadata import evidence_metadata
from capsule.store import MANIFEST_NAME, create_capsule
from evidence.real_smoke_contract_diff import collect_real_smoke_contract_diff
from post.extract_kpis import extract_kpis
from runner.build_model import build_model
from runner.monitor_job import monitor_job
from runner.submit_job import _build_cmd, submit_job
from runner.syntaxcheck import syntaxcheck_inp
from scripts import validate_abaqus_env


STAGE_ENV_PREFLIGHT = "environment_preflight"
STAGE_INPUT = "input_job_preparation"
STAGE_SYNTAXCHECK = "syntaxcheck"
STAGE_SUBMIT = "submit_job"
STAGE_MONITOR = "monitor_status_collection"
STAGE_ODB = "odb_kpi_adapter_probe"
STAGE_CONTRACT_DIFF = "contract_diff"
STAGE_REPORT = "evidence_report_generation"

STAGE_ORDER = [
    STAGE_ENV_PREFLIGHT,
    STAGE_INPUT,
    STAGE_SYNTAXCHECK,
    STAGE_SUBMIT,
    STAGE_MONITOR,
    STAGE_ODB,
    STAGE_CONTRACT_DIFF,
    STAGE_REPORT,
]

STATUS_COMPLETED = "completed"
STATUS_DRY_RUN = "dry-run"
STATUS_MOCK_REAL = "mock-real"
STATUS_NOT_RUN = "not-run"
STATUS_ENV_LIMITED = "environment-limited"
STATUS_MISSING = "missing"
STATUS_FAILED = "failed"


@dataclass
class SmokeStage:
    name: str
    status: str
    command: list[str] | None = None
    evidence: list[str] = field(default_factory=list)
    real_env_required: bool = False
    real_env_verified: bool = False
    missing_reason: str | None = None
    artifact_path: str | None = None

    def to_json(self) -> dict:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_smoke_case(case_name: str) -> tuple[Path, Path | None, dict]:
    case_dir = ROOT / "cases" / case_name
    spec_path = case_dir / "spec.yaml"
    expected_path = case_dir / "expected.json"
    runner_path = case_dir / "runner.json"
    if not spec_path.exists():
        raise FileNotFoundError(f"case spec not found: {spec_path}")
    return spec_path, expected_path if expected_path.exists() else None, _read_json(runner_path)


def _copy_case_inputs(case_name: str, out_dir: Path) -> tuple[Path, Path | None, dict]:
    spec_path, expected_path, runner_cfg = _load_smoke_case(case_name)
    case_dir = out_dir / "case"
    case_dir.mkdir(parents=True, exist_ok=True)
    smoke_spec = case_dir / "spec.yaml"
    shutil.copy2(spec_path, smoke_spec)
    smoke_expected = None
    if expected_path:
        smoke_expected = case_dir / "expected.json"
        shutil.copy2(expected_path, smoke_expected)
    (case_dir / "runner.json").write_text(json.dumps(runner_cfg, indent=2), encoding="utf-8")
    return smoke_spec, smoke_expected, runner_cfg


def _model_name_from_spec(spec_path: Path) -> str:
    import yaml

    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    return spec.get("meta", {}).get("model_name", "SmokeJob")


def _kpi_spec_from_spec(spec_path: Path) -> list[dict]:
    import yaml

    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    return spec.get("outputs", {}).get("kpis", [])


def _write_cached_inp(workdir: Path, model_name: str) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    inp_path = workdir / f"{model_name}.inp"
    inp_path.write_text(
        "\n".join(
            [
                "*Heading",
                "** abaqus-agent smoke cached input",
                "*Node",
                "1, 0., 0., 0.",
                "2, 1., 0., 0.",
                "*Element, type=T3D2",
                "1, 1, 2",
                "*Material, name=SMOKE",
                "*Elastic",
                "210000., 0.3",
                "*Step, name=Step-1",
                "*Static",
                "1., 1.",
                "*End Step",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return inp_path


def _write_stage(out_dir: Path, stage: SmokeStage) -> SmokeStage:
    artifact = out_dir / f"stage_{stage.name}.json"
    stage.artifact_path = str(artifact)
    artifact.write_text(json.dumps(stage.to_json(), indent=2, sort_keys=True), encoding="utf-8")
    return stage


def _write_missing_report(out_dir: Path, missing: list[dict]) -> Path:
    path = out_dir / "missing_report.json"
    path.write_text(json.dumps({"missing": missing}, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _build_syntaxcheck_command(inp_path: Path) -> list[str]:
    return [
        "abaqus",
        f"job={inp_path.stem}_syntaxcheck",
        f"input={inp_path}",
        "syntaxcheck",
        "interactive",
    ]


def _fake_abaqus_script(path: Path) -> None:
    path.write_text(
        f"#!{sys.executable}\n"
        + """
from pathlib import Path
import json
import sys

args = sys.argv[1:]

def arg_value(prefix, default="SmokeJob"):
    for item in args:
        if item.startswith(prefix + "="):
            return item.split("=", 1)[1]
    return default

job = arg_value("job")

if "syntaxcheck" in args:
    Path(job + ".dat").write_text("Abaqus JOB %s\\nSYNTAX CHECK COMPLETE\\n" % job)
    print("SYNTAX CHECK COMPLETE")
    sys.exit(0)

if args[:1] == ["python"]:
    result_path = Path(args[-1])
    result_path.write_text(json.dumps({
        "kpis": {},
        "errors": ["mock-real: odbAccess not available; KPI not real-env verified"],
        "odb_path": args[-3] if len(args) >= 3 else None
    }, indent=2))
    print("KPI_RESULT_WRITTEN: " + str(result_path))
    sys.exit(0)

Path(job + ".log").write_text("BEGIN ANALYSIS\\nANALYSIS COMPLETE\\nJOB COMPLETED\\n")
Path(job + ".sta").write_text(" 1 1 1 0 0 100.0% 1.000E+00 1.000E+00 0.1\\nANALYSIS COMPLETE\\n")
Path(job + ".odb").write_text("mock odb placeholder\\n")
print("ANALYSIS COMPLETE")
sys.exit(0)
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _ensure_mock_abaqus(out_dir: Path, requested: str | None) -> Path:
    if requested:
        path = Path(requested).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"mock Abaqus executable not found: {path}")
        return path
    bin_dir = out_dir / "mock_bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "abaqus"
    _fake_abaqus_script(fake)
    return fake


@contextmanager
def _abaqus_path(executable: Path | None) -> Iterator[None]:
    if executable is None:
        yield
        return

    old_path = os.environ.get("PATH", "")
    old_executable = os.environ.get("ABAQUS_EXECUTABLE")
    os.environ["PATH"] = str(executable.parent) + os.pathsep + old_path
    os.environ["ABAQUS_EXECUTABLE"] = str(executable)
    try:
        yield
    finally:
        os.environ["PATH"] = old_path
        if old_executable is None:
            os.environ.pop("ABAQUS_EXECUTABLE", None)
        else:
            os.environ["ABAQUS_EXECUTABLE"] = old_executable


def _collect_preflight(mode: str, env: Mapping[str, str] | None = None) -> dict:
    return validate_abaqus_env.collect_report(mode=mode, env=env)


def _preflight_stage(preflight: dict, out_dir: Path, *, require_real: bool) -> SmokeStage:
    missing = preflight["require_real_missing"] if require_real else preflight["missing"]
    if require_real and missing:
        return _write_stage(
            out_dir,
            SmokeStage(
                name=STAGE_ENV_PREFLIGHT,
                status=STATUS_MISSING,
                evidence=[
                    f"overall_status={preflight['overall_status']}",
                    f"real_env_prerequisites_ready={preflight['real_env_prerequisites_ready']}",
                ],
                real_env_required=True,
                real_env_verified=False,
                missing_reason="; ".join(
                    f"{item['capability']}: {item['reason']}" for item in missing
                ),
            ),
        )

    status = STATUS_COMPLETED if preflight["real_env_prerequisites_ready"] else STATUS_ENV_LIMITED
    return _write_stage(
        out_dir,
        SmokeStage(
            name=STAGE_ENV_PREFLIGHT,
            status=status,
            evidence=[
                f"overall_status={preflight['overall_status']}",
                f"real_env_prerequisites_ready={preflight['real_env_prerequisites_ready']}",
                f"real_abaqus_e2e_verified={preflight['real_abaqus_e2e_verified']}",
            ],
            real_env_required=True,
            real_env_verified=preflight["real_env_prerequisites_ready"] and require_real,
            missing_reason=None if preflight["real_env_prerequisites_ready"] else "Real Abaqus prerequisites are incomplete.",
        ),
    )


def _prepare_input_stage(
    spec_path: Path,
    workdir: Path,
    out_dir: Path,
    *,
    dry_run: bool,
    mock_real: bool,
) -> tuple[SmokeStage, Path]:
    model_name = _model_name_from_spec(spec_path)
    cached_inp = None
    if dry_run or mock_real:
        cached_inp = _write_cached_inp(workdir, model_name)

    result = build_model(spec_path, workdir)
    inp_path = Path(result["inp_path"])
    evidence = [
        "function=runner.build_model.build_model",
        f"run_id={result.get('run_id')}",
        f"cached={result.get('cached')}",
        f"inp_path={inp_path}",
    ]
    if cached_inp:
        evidence.append(f"cached_inp_seeded={cached_inp}")

    status = STATUS_DRY_RUN if dry_run else STATUS_MOCK_REAL if mock_real else STATUS_COMPLETED
    return (
        _write_stage(
            out_dir,
            SmokeStage(
                name=STAGE_INPUT,
                status=status,
                command=["build_model", str(spec_path), str(workdir)],
                evidence=evidence,
                real_env_required=True,
                real_env_verified=not (dry_run or mock_real),
                missing_reason=None if not dry_run else "Dry-run uses cached .inp and does not call CAE noGUI.",
            ),
        ),
        inp_path,
    )


def _dry_run_stages(inp_path: Path, workdir: Path, out_dir: Path, runner_cfg: dict) -> list[SmokeStage]:
    submit_cmd = _build_cmd(
        job_name=inp_path.stem,
        inp_path=inp_path,
        cpus=runner_cfg.get("cpus", 1),
        mp_mode=runner_cfg.get("mp_mode", "threads"),
        memory=runner_cfg.get("memory", "90%"),
        background=False,
        interactive=True,
    )
    stages = [
        SmokeStage(
            name=STAGE_SYNTAXCHECK,
            status=STATUS_DRY_RUN,
            command=_build_syntaxcheck_command(inp_path),
            evidence=["function=runner.syntaxcheck.syntaxcheck_inp", "syntaxcheck_not_run=true"],
            real_env_required=True,
            missing_reason="Dry-run does not invoke Abaqus syntaxcheck.",
        ),
        SmokeStage(
            name=STAGE_SUBMIT,
            status=STATUS_DRY_RUN,
            command=submit_cmd,
            evidence=["function=runner.submit_job._build_cmd", "submit_job_not_run=true"],
            real_env_required=True,
            missing_reason="Dry-run does not submit an Abaqus job.",
        ),
        SmokeStage(
            name=STAGE_MONITOR,
            status=STATUS_DRY_RUN,
            evidence=["function=runner.monitor_job.monitor_job", f"workdir={workdir}", "monitor_not_run=true"],
            real_env_required=True,
            missing_reason="Dry-run does not collect live .sta/.log status.",
        ),
        SmokeStage(
            name=STAGE_ODB,
            status=STATUS_ENV_LIMITED,
            command=["abaqus", "python", "post/extract_kpis.py", "--", f"{inp_path.stem}.odb"],
            evidence=["function=post.extract_kpis.extract_kpis", "odb_kpi_not_run=true"],
            real_env_required=True,
            missing_reason="Requires Abaqus Python with odbAccess and a real .odb file.",
        ),
        SmokeStage(
            name=STAGE_CONTRACT_DIFF,
            status=STATUS_ENV_LIMITED,
            evidence=[
                "function=evidence.real_smoke_contract_diff.collect_real_smoke_contract_diff",
                "contract_diff_not_run=true",
            ],
            real_env_required=True,
            missing_reason="Requires verified real ODB KPIs before contract/diff evidence can run.",
        ),
    ]
    return [_write_stage(out_dir, stage) for stage in stages]


def _mock_or_real_stages(
    inp_path: Path,
    workdir: Path,
    out_dir: Path,
    runner_cfg: dict,
    *,
    mock_real: bool,
) -> list[SmokeStage]:
    stages: list[SmokeStage] = []

    syntax_result = syntaxcheck_inp(inp_path, workdir)
    stages.append(
        _write_stage(
            out_dir,
            SmokeStage(
                name=STAGE_SYNTAXCHECK,
                status=STATUS_MOCK_REAL if mock_real else STATUS_COMPLETED,
                command=_build_syntaxcheck_command(inp_path),
                evidence=[
                    "function=runner.syntaxcheck.syntaxcheck_inp",
                    f"ok={syntax_result.get('ok')}",
                    f"returncode={syntax_result.get('returncode')}",
                    f"log_path={syntax_result.get('log_path')}",
                ],
                real_env_required=True,
                real_env_verified=(not mock_real) and bool(syntax_result.get("ok")),
                missing_reason=None if syntax_result.get("ok") else "syntaxcheck did not pass.",
            ),
        )
    )

    submit_result = submit_job(
        inp_path=inp_path,
        workdir=workdir,
        cpus=runner_cfg.get("cpus", 1),
        mp_mode=runner_cfg.get("mp_mode", "threads"),
        memory=runner_cfg.get("memory", "90%"),
        background=False,
        interactive=True,
        allow_license_queue=runner_cfg.get("allow_license_queue", False),
        timeout_seconds=runner_cfg.get("timeout_seconds", 300),
    )
    stages.append(
        _write_stage(
            out_dir,
            SmokeStage(
                name=STAGE_SUBMIT,
                status=STATUS_MOCK_REAL if mock_real else STATUS_COMPLETED,
                command=str(submit_result.get("cmd", "")).split(),
                evidence=[
                    "function=runner.submit_job.submit_job",
                    f"status={submit_result.get('status')}",
                    f"job_name={submit_result.get('job_name')}",
                    f"log_path={submit_result.get('log_path')}",
                ],
                real_env_required=True,
                real_env_verified=(not mock_real) and submit_result.get("status") == "completed",
                missing_reason=None,
            ),
        )
    )

    monitor_result = monitor_job(submit_result["job_name"], workdir)
    stages.append(
        _write_stage(
            out_dir,
            SmokeStage(
                name=STAGE_MONITOR,
                status=STATUS_MOCK_REAL if mock_real else STATUS_COMPLETED,
                evidence=[
                    "function=runner.monitor_job.monitor_job",
                    f"status={monitor_result.get('status')}",
                    f"odb_exists={monitor_result.get('odb_exists')}",
                    f"sta_path={monitor_result.get('sta_path')}",
                ],
                real_env_required=True,
                real_env_verified=(not mock_real) and monitor_result.get("status") == "COMPLETED",
                missing_reason=None if monitor_result.get("status") == "COMPLETED" else "Job did not complete.",
            ),
        )
    )

    odb_path = workdir / f"{inp_path.stem}.odb"
    kpi_result = extract_kpis(odb_path, _kpi_spec_from_spec(out_dir / "case" / "spec.yaml"), workdir)
    kpi_errors = kpi_result.get("errors", [])
    kpi_verified = (not mock_real) and not kpi_errors and bool(kpi_result.get("kpis"))
    stages.append(
        _write_stage(
            out_dir,
            SmokeStage(
                name=STAGE_ODB,
                status=STATUS_ENV_LIMITED if mock_real or kpi_errors else STATUS_COMPLETED,
                command=["abaqus", "python", "post/extract_kpis.py", "--", str(odb_path)],
                evidence=[
                    "function=post.extract_kpis.extract_kpis",
                    f"odb_path={kpi_result.get('odb_path')}",
                    f"kpis={sorted(kpi_result.get('kpis', {}).keys())}",
                    f"errors={kpi_errors}",
                ],
                real_env_required=True,
                real_env_verified=kpi_verified,
                missing_reason=None
                if kpi_verified
                else "ODB KPI adapter did not produce real verified KPIs.",
            ),
        )
    )
    return stages


def _contract_diff_stage(
    *,
    mode: str,
    case_name: str,
    out_dir: Path,
    preflight: dict,
    stages: list[SmokeStage],
    dry_run: bool,
    mock_real: bool,
) -> tuple[SmokeStage, dict | None]:
    if dry_run:
        raise ValueError("dry-run contract diff stage is created by _dry_run_stages")

    odb_stage = next((stage for stage in stages if stage.name == STAGE_ODB), None)
    if mock_real or not odb_stage or not odb_stage.real_env_verified:
        return (
            _write_stage(
                out_dir,
                SmokeStage(
                    name=STAGE_CONTRACT_DIFF,
                    status=STATUS_ENV_LIMITED,
                    evidence=[
                        "function=evidence.real_smoke_contract_diff.collect_real_smoke_contract_diff",
                        "contract_diff_not_run=true",
                    ],
                    real_env_required=True,
                    real_env_verified=False,
                    missing_reason="Requires verified real ODB KPIs before contract/diff evidence can run.",
                ),
            ),
            None,
        )

    preliminary = _build_report(mode, case_name, out_dir, preflight, stages)
    preliminary["overall_status"] = _overall_status(stages, dry_run=False, mock_real=False)
    _write_report(out_dir, preliminary)
    contract_diff = collect_real_smoke_contract_diff(
        smoke_dir=out_dir,
        out_dir=out_dir / "contract_diff",
        run_id=f"{case_name}-{mode}-contract-diff",
    )
    return (
        _write_stage(
            out_dir,
            SmokeStage(
                name=STAGE_CONTRACT_DIFF,
                status=STATUS_COMPLETED,
                evidence=[
                    "function=evidence.real_smoke_contract_diff.collect_real_smoke_contract_diff",
                    f"overall_status={contract_diff['overall_status']}",
                    f"contracts={contract_diff['contracts']['status']}",
                    f"diff={contract_diff['diff']['status']}",
                    f"report_path={contract_diff['report_path']}",
                    f"html_path={contract_diff['html_path']}",
                    f"capsule={contract_diff['capsule']['manifest_path']}",
                ],
                real_env_required=True,
                real_env_verified=bool(contract_diff["real_env_verified"]),
            ),
        ),
        {
            "workflow": contract_diff["workflow"],
            "overall_status": contract_diff["overall_status"],
            "contracts_status": contract_diff["contracts"]["status"],
            "diff_status": contract_diff["diff"]["status"],
            "report_path": contract_diff["report_path"],
            "html_path": contract_diff["html_path"],
            "evidence_path": str(out_dir / "contract_diff" / "real_smoke_contract_diff.json"),
            "capsule": contract_diff["capsule"],
        },
    )


def _overall_status(stages: list[SmokeStage], *, dry_run: bool, mock_real: bool) -> str:
    if any(stage.status == STATUS_FAILED for stage in stages):
        return "failed"
    if dry_run:
        return "dry-run-ready"
    if mock_real:
        return "mock-real-completed-not-real-verified"
    if all(stage.real_env_verified for stage in stages if stage.real_env_required):
        return "real-env-verified"
    return "real-env-incomplete"


def collect_smoke_evidence(
    *,
    mode: str,
    out_dir: Path,
    case_name: str = "cantilever",
    abaqus_executable: str | None = None,
) -> tuple[dict, int]:
    dry_run = mode == "dry-run"
    mock_real = mode == "mock-real"
    require_real = mode == "require-real"
    out_dir.mkdir(parents=True, exist_ok=True)

    executable_path = _ensure_mock_abaqus(out_dir, abaqus_executable) if mock_real else None
    if require_real and abaqus_executable:
        executable_path = Path(abaqus_executable).expanduser().resolve()

    with _abaqus_path(executable_path):
        preflight = _collect_preflight(mode=mode)
        stages = [_preflight_stage(preflight, out_dir, require_real=require_real)]
        if require_real and preflight["require_real_missing"]:
            missing_path = _write_missing_report(out_dir, preflight["require_real_missing"])
            stages.append(
                _write_stage(
                    out_dir,
                    SmokeStage(
                        name=STAGE_REPORT,
                        status=STATUS_COMPLETED,
                        evidence=[f"missing_report={missing_path}"],
                        artifact_path=str(out_dir / "smoke_evidence.json"),
                    ),
                )
            )
            evidence = _build_report(mode, case_name, out_dir, preflight, stages)
            evidence["overall_status"] = "real-env-missing"
            _write_report(out_dir, evidence)
            evidence["capsule"] = _write_smoke_capsule(out_dir, mode, case_name, evidence, stages)
            _write_report(out_dir, evidence)
            return evidence, 2

        spec_path, _expected_path, runner_cfg = _copy_case_inputs(case_name, out_dir)
        workdir = out_dir / "run"

        try:
            input_stage, inp_path = _prepare_input_stage(
                spec_path,
                workdir,
                out_dir,
                dry_run=dry_run,
                mock_real=mock_real,
            )
            stages.append(input_stage)

            if dry_run:
                stages.extend(_dry_run_stages(inp_path, workdir, out_dir, runner_cfg))
            else:
                stages.extend(
                    _mock_or_real_stages(
                        inp_path,
                        workdir,
                        out_dir,
                        runner_cfg,
                        mock_real=mock_real,
                    )
                )
                contract_stage, contract_diff_summary = _contract_diff_stage(
                    mode=mode,
                    case_name=case_name,
                    out_dir=out_dir,
                    preflight=preflight,
                    stages=stages,
                    dry_run=dry_run,
                    mock_real=mock_real,
                )
                stages.append(contract_stage)
            exit_code = 0
        except Exception as exc:
            stages.append(
                _write_stage(
                    out_dir,
                    SmokeStage(
                        name="pipeline_exception",
                        status=STATUS_FAILED,
                        evidence=[f"exception={type(exc).__name__}: {exc}"],
                        real_env_required=not dry_run,
                        real_env_verified=False,
                        missing_reason=str(exc),
                    ),
                )
            )
            exit_code = 1

        report_stage = SmokeStage(
            name=STAGE_REPORT,
            status=STATUS_COMPLETED,
            evidence=["target=smoke_evidence.json", "stage_logs=stage_*.json"],
            artifact_path=str(out_dir / "smoke_evidence.json"),
        )
        stages.append(_write_stage(out_dir, report_stage))
        evidence = _build_report(mode, case_name, out_dir, preflight, stages)
        evidence["overall_status"] = _overall_status(stages, dry_run=dry_run, mock_real=mock_real)
        if "contract_diff_summary" in locals() and contract_diff_summary:
            evidence["contract_diff"] = contract_diff_summary
        _write_report(out_dir, evidence)
        evidence["capsule"] = _write_smoke_capsule(out_dir, mode, case_name, evidence, stages)
        _write_report(out_dir, evidence)
        return evidence, exit_code


def _build_report(
    mode: str,
    case_name: str,
    out_dir: Path,
    preflight: dict,
    stages: list[SmokeStage],
) -> dict:
    return {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "mode": mode,
        "case": case_name,
        "generated_at": _utc_now(),
        "out_dir": str(out_dir),
        "overall_status": "pending",
        "real_env_verified": all(
            stage.real_env_verified for stage in stages if stage.real_env_required
        ),
        "missing": preflight.get("missing", []),
        "require_real_missing": preflight.get("require_real_missing", []),
        "preflight": preflight,
        "stages": [stage.to_json() for stage in stages],
    }


def _write_report(out_dir: Path, evidence: dict) -> Path:
    path = out_dir / "smoke_evidence.json"
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_smoke_capsule(
    out_dir: Path,
    mode: str,
    case_name: str,
    evidence: dict,
    stages: list[SmokeStage],
) -> dict:
    inputs = [
        path
        for path in (
            out_dir / "case" / "spec.yaml",
            out_dir / "case" / "expected.json",
            out_dir / "case" / "runner.json",
        )
        if path.exists()
    ]
    artifacts = [
        Path(stage.artifact_path)
        for stage in stages
        if stage.artifact_path and Path(stage.artifact_path).exists()
    ]
    missing_report = out_dir / "missing_report.json"
    if missing_report.exists():
        artifacts.append(missing_report)
    contract_diff = evidence.get("contract_diff")
    if isinstance(contract_diff, dict):
        for key in ("evidence_path", "report_path", "html_path"):
            path = contract_diff.get(key)
            if path and Path(path).exists():
                artifacts.append(Path(path))

    run_id = f"{case_name}-{mode}"
    manifest = create_capsule(
        out_dir / "capsule",
        run_id,
        inputs=inputs,
        artifacts=artifacts,
        metadata=evidence_metadata(
            workflow="real-abaqus-smoke-harness",
            evidence_source=f"smoke-harness:{mode}",
            evidence_level=_smoke_evidence_level(mode, evidence["overall_status"]),
            overall_status=evidence["overall_status"],
            real_env_required=True,
            real_env_verified=evidence["real_env_verified"],
            extra={
                "case": case_name,
                "mode": mode,
            },
        ),
    )
    manifest_path = out_dir / "capsule" / run_id / MANIFEST_NAME
    return {
        "run_id": run_id,
        "manifest_path": str(manifest_path),
        "capsule_hash": manifest["capsule_hash"],
        "input_count": len(manifest["inputs"]),
        "artifact_count": len(manifest["artifacts"]),
    }


def _smoke_evidence_level(mode: str, overall_status: str) -> str:
    if overall_status == "real-env-verified":
        return "real-env-verified"
    if mode == "mock-real":
        return "mock-real"
    if mode == "dry-run":
        return "dry-run"
    return "environment-limited"


def _print_text(evidence: dict) -> None:
    print(f"abaqus-agent real smoke harness ({evidence['mode']})")
    print(f"overall_status: {evidence['overall_status']}")
    print(f"real_env_verified: {evidence['real_env_verified']}")
    print(f"out_dir: {evidence['out_dir']}")
    for stage in evidence["stages"]:
        print(f"- {stage['name']}: {stage['status']}")
        if stage.get("missing_reason"):
            print(f"  missing: {stage['missing_reason']}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real Abaqus smoke/evidence harness.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Construct smoke evidence without calling Abaqus.")
    mode.add_argument("--mock-real", action="store_true", help="Run through fake Abaqus executable/files.")
    mode.add_argument("--require-real", action="store_true", help="Require real Abaqus prerequisites, else exit 2.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--out-dir", required=True, help="Directory for smoke evidence bundle.")
    parser.add_argument("--case", default="cantilever", help="Case name under cases/ (default: cantilever).")
    parser.add_argument(
        "--abaqus-executable",
        help="Optional Abaqus executable path for mock-real or require-real PATH setup.",
    )
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        mode = "dry-run"
    elif args.mock_real:
        mode = "mock-real"
    else:
        mode = "require-real"

    evidence, exit_code = collect_smoke_evidence(
        mode=mode,
        out_dir=Path(args.out_dir),
        case_name=args.case,
        abaqus_executable=args.abaqus_executable,
    )
    evidence["exit_code"] = exit_code
    _write_report(Path(args.out_dir), evidence)

    if args.json:
        print(json.dumps(evidence, indent=2, sort_keys=True))
    else:
        _print_text(evidence)
    return exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
