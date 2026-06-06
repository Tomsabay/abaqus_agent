#!/usr/bin/env python3
"""
Local Abaqus environment validator for abaqus-agent.

This script checks local, reproducible prerequisites without submitting an
Abaqus job. It deliberately separates dry-run/source-supported capabilities
from real Abaqus environment prerequisites.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

Env = Mapping[str, str]
Which = Callable[[str], str | None]

STATUS_VERIFIED = "verified"
STATUS_COVERED_BY_TESTS = "covered-by-tests"
STATUS_SUPPORTED_BY_SOURCE = "supported-by-source"
STATUS_DRY_RUN_SUPPORTED = "dry-run-supported"
STATUS_AVAILABLE = "available"
STATUS_CANDIDATE = "candidate"
STATUS_ENV_LIMITED = "environment-limited"
STATUS_MISSING = "missing"
STATUS_NOT_RUN = "not-run"

LICENSE_ENV_KEYS = (
    "LM_LICENSE_FILE",
    "ABAQUSLM_LICENSE_FILE",
    "ABAQUS_LICENSE_FILE",
    "DSLS_CONFIG",
    "ABAQUS_AGENT_LICENSE_CONFIRMED",
)

ABAQUS_ENV_KEYS = (
    "ABAQUS_EXECUTABLE",
    "ABAQUS_COMMAND",
    "ABAQUS_PATH",
)


@dataclass(frozen=True)
class Capability:
    name: str
    status: str
    evidence: list[str]
    real_env_required: bool = False
    real_env_verified: bool = False
    missing_reason: str | None = None
    blocks_require_real: bool = False

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "evidence": self.evidence,
            "real_env_required": self.real_env_required,
            "real_env_verified": self.real_env_verified,
            "missing_reason": self.missing_reason,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _path_exists(path_value: str) -> bool:
    return bool(path_value) and Path(path_value).expanduser().exists()


def _find_abaqus_executable(env: Env, which: Which) -> tuple[str | None, str | None]:
    for key in ABAQUS_ENV_KEYS:
        value = env.get(key)
        if value and _path_exists(value):
            return str(Path(value).expanduser()), key

    found = which("abaqus")
    if found:
        return found, "PATH"
    return None, None


def _entry_point_target() -> str | None:
    try:
        entry_points = importlib.metadata.entry_points()
        if hasattr(entry_points, "select"):
            scripts = entry_points.select(group="console_scripts")
        else:
            scripts = entry_points.get("console_scripts", [])
        for entry in scripts:
            if entry.name == "abaqus-agent":
                return entry.value
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:
        return None
    return None


def _pyproject_entry_point() -> str | None:
    pyproject = ROOT / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - project requires Python >=3.10
        return None
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    return data.get("project", {}).get("scripts", {}).get("abaqus-agent")


def _probe_python_runtime() -> Capability:
    version = sys.version_info
    ok = version >= (3, 10)
    return Capability(
        name="python_runtime",
        status=STATUS_VERIFIED if ok else STATUS_MISSING,
        evidence=[
            f"python={platform.python_version()}",
            f"executable={sys.executable}",
            "requires-python=>=3.10",
        ],
        missing_reason=None if ok else "Python >=3.10 is required.",
    )


def _probe_package_import() -> Capability:
    modules = ["core.helpers", "tools.schema_validator", "runner.syntaxcheck", "post.extract_kpis"]
    imported: list[str] = []
    failures: list[str] = []
    for module in modules:
        try:
            importlib.import_module(module)
            imported.append(module)
        except Exception as exc:
            failures.append(f"{module}: {exc}")

    if failures:
        return Capability(
            name="package_imports",
            status=STATUS_MISSING,
            evidence=[f"imported={imported}", f"failures={failures}"],
            missing_reason="One or more core project modules could not be imported.",
        )

    return Capability(
        name="package_imports",
        status=STATUS_VERIFIED,
        evidence=[f"imported={', '.join(imported)}"],
    )


def _probe_console_entry() -> Capability:
    installed_target = _entry_point_target()
    pyproject_target = _pyproject_entry_point()
    target = installed_target or pyproject_target
    if target not in {"cli:main", "server:main"}:
        return Capability(
            name="console_entry_point",
            status=STATUS_MISSING,
            evidence=[
                f"installed_entry={installed_target}",
                f"pyproject_entry={pyproject_target}",
            ],
            missing_reason="Expected console script 'abaqus-agent = cli:main' or 'server:main'.",
        )

    try:
        module_name, attr_name = target.split(":", 1)
        module = importlib.import_module(module_name)
        main = getattr(module, attr_name)
    except Exception as exc:
        return Capability(
            name="console_entry_point",
            status=STATUS_MISSING,
            evidence=[f"target={target}", f"import_error={exc}"],
            missing_reason=f"{target} could not be imported.",
        )

    return Capability(
        name="console_entry_point",
        status=STATUS_VERIFIED,
        evidence=[f"target={target}", f"callable={callable(main)}"],
    )


def _probe_dry_run_benchmark() -> Capability:
    benchmark = ROOT / "run_benchmark.py"
    if not benchmark.exists():
        return Capability(
            name="benchmark_dry_run_entry",
            status=STATUS_MISSING,
            evidence=[f"path={benchmark}"],
            missing_reason="run_benchmark.py was not found.",
        )

    try:
        run_benchmark = importlib.import_module("run_benchmark")
        cases = run_benchmark.discover_cases()
        from tools.schema_validator import validate_spec

        invalid: list[str] = []
        for case in cases:
            valid, errors = validate_spec(case["spec"])
            if not valid:
                invalid.append(f"{case['name']}: {errors}")
    except Exception as exc:
        return Capability(
            name="benchmark_dry_run_entry",
            status=STATUS_MISSING,
            evidence=[f"path={benchmark}", f"error={exc}"],
            missing_reason="Benchmark dry-run entry could not be imported or probed.",
        )

    if invalid:
        return Capability(
            name="benchmark_dry_run_entry",
            status=STATUS_MISSING,
            evidence=[f"path={benchmark}", f"cases={len(cases)}", f"invalid={invalid}"],
            missing_reason="One or more benchmark specs failed schema validation.",
        )

    return Capability(
        name="benchmark_dry_run_entry",
        status=STATUS_DRY_RUN_SUPPORTED,
        evidence=[
            f"path={benchmark.relative_to(ROOT)}",
            f"cases={','.join(case['name'] for case in cases)}",
            "validated_specs_without_abaqus=true",
        ],
    )


def _probe_tests_discoverable() -> Capability:
    tests_dir = ROOT / "tests"
    test_files = sorted(tests_dir.glob("test_*.py")) if tests_dir.exists() else []
    if not test_files:
        return Capability(
            name="tests_discoverable",
            status=STATUS_MISSING,
            evidence=[f"tests_dir={tests_dir}"],
            missing_reason="No tests/test_*.py files were found.",
        )
    return Capability(
        name="tests_discoverable",
        status=STATUS_COVERED_BY_TESTS,
        evidence=[f"test_files={len(test_files)}"],
    )


def _probe_abaqus_executable(env: Env, which: Which) -> tuple[Capability, str | None]:
    executable, source = _find_abaqus_executable(env, which)
    if not executable:
        return (
            Capability(
                name="abaqus_executable",
                status=STATUS_MISSING,
                evidence=[
                    "checked=PATH:abaqus",
                    f"checked_env={','.join(ABAQUS_ENV_KEYS)}",
                ],
                real_env_required=True,
                missing_reason=(
                    "Abaqus executable was not found. Put 'abaqus' on PATH or set "
                    "ABAQUS_EXECUTABLE/ABAQUS_COMMAND/ABAQUS_PATH."
                ),
                blocks_require_real=True,
            ),
            None,
        )

    return (
        Capability(
            name="abaqus_executable",
            status=STATUS_AVAILABLE,
            evidence=[f"source={source}", f"path={executable}"],
            real_env_required=True,
            real_env_verified=True,
        ),
        executable,
    )


def _probe_license_hint(env: Env, executable: str | None) -> Capability:
    present = [key for key in LICENSE_ENV_KEYS if env.get(key)]
    if present:
        return Capability(
            name="abaqus_license_hint",
            status=STATUS_CANDIDATE,
            evidence=[f"env={','.join(present)}", "license_checkout_not_run=true"],
            real_env_required=True,
            real_env_verified=False,
        )

    reason = (
        "No explicit Abaqus license hint was found. Set LM_LICENSE_FILE, "
        "ABAQUSLM_LICENSE_FILE, DSLS_CONFIG, or ABAQUS_AGENT_LICENSE_CONFIRMED=1 "
        "after manually confirming the local license setup."
    )
    if not executable:
        reason = "Abaqus executable is missing, so license checkout cannot be evaluated."

    return Capability(
        name="abaqus_license_hint",
        status=STATUS_MISSING,
        evidence=[f"checked_env={','.join(LICENSE_ENV_KEYS)}", "license_checkout_not_run=true"],
        real_env_required=True,
        missing_reason=reason,
        blocks_require_real=True,
    )


def _source_exists(relative_path: str) -> bool:
    return (ROOT / relative_path).exists()


def _probe_syntaxcheck_prerequisites(executable: str | None) -> Capability:
    source = "runner/syntaxcheck.py"
    if not _source_exists(source):
        return Capability(
            name="syntaxcheck_prerequisites",
            status=STATUS_MISSING,
            evidence=[f"source={source}:missing"],
            real_env_required=True,
            missing_reason="runner/syntaxcheck.py is missing.",
            blocks_require_real=True,
        )
    if not executable:
        return Capability(
            name="syntaxcheck_prerequisites",
            status=STATUS_ENV_LIMITED,
            evidence=[f"source={source}:exists", "command=abaqus job=<name> input=<inp> syntaxcheck"],
            real_env_required=True,
            missing_reason="Requires Abaqus executable; syntaxcheck was not run.",
            blocks_require_real=True,
        )
    return Capability(
        name="syntaxcheck_prerequisites",
        status=STATUS_CANDIDATE,
        evidence=[f"source={source}:exists", "abaqus_executable=available", "syntaxcheck_not_run=true"],
        real_env_required=True,
        real_env_verified=False,
    )


def _probe_submit_monitor_prerequisites(executable: str | None, license_hint: Capability) -> Capability:
    sources = ["runner/submit_job.py", "runner/monitor_job.py"]
    missing_sources = [source for source in sources if not _source_exists(source)]
    if missing_sources:
        return Capability(
            name="submit_monitor_prerequisites",
            status=STATUS_MISSING,
            evidence=[f"missing_sources={missing_sources}"],
            real_env_required=True,
            missing_reason="Submit/monitor source files are missing.",
            blocks_require_real=True,
        )
    if not executable:
        return Capability(
            name="submit_monitor_prerequisites",
            status=STATUS_ENV_LIMITED,
            evidence=[f"sources={','.join(sources)}", "submit_job_not_run=true"],
            real_env_required=True,
            missing_reason="Requires Abaqus executable and license; solver submit was not run.",
            blocks_require_real=True,
        )
    if license_hint.status == STATUS_MISSING:
        return Capability(
            name="submit_monitor_prerequisites",
            status=STATUS_ENV_LIMITED,
            evidence=[f"sources={','.join(sources)}", "abaqus_executable=available", "submit_job_not_run=true"],
            real_env_required=True,
            missing_reason="Requires an explicit license hint before treating submit/monitor as ready.",
            blocks_require_real=True,
        )
    return Capability(
        name="submit_monitor_prerequisites",
        status=STATUS_CANDIDATE,
        evidence=[
            f"sources={','.join(sources)}",
            "abaqus_executable=available",
            "license_hint=present",
            "submit_job_not_run=true",
        ],
        real_env_required=True,
        real_env_verified=False,
    )


def _probe_odb_kpi_prerequisites(executable: str | None, license_hint: Capability) -> Capability:
    source = "post/extract_kpis.py"
    if not _source_exists(source):
        return Capability(
            name="odb_kpi_prerequisites",
            status=STATUS_MISSING,
            evidence=[f"source={source}:missing"],
            real_env_required=True,
            missing_reason="post/extract_kpis.py is missing.",
            blocks_require_real=True,
        )
    if not executable:
        return Capability(
            name="odb_kpi_prerequisites",
            status=STATUS_ENV_LIMITED,
            evidence=[f"source={source}:exists", "command=abaqus python post/extract_kpis.py"],
            real_env_required=True,
            missing_reason="Requires Abaqus Python with odbAccess and a real .odb file.",
            blocks_require_real=True,
        )
    if license_hint.status == STATUS_MISSING:
        return Capability(
            name="odb_kpi_prerequisites",
            status=STATUS_ENV_LIMITED,
            evidence=[f"source={source}:exists", "abaqus_executable=available", "odb_extraction_not_run=true"],
            real_env_required=True,
            missing_reason="Requires a completed Abaqus job/license context before ODB KPI extraction can be ready.",
            blocks_require_real=True,
        )
    return Capability(
        name="odb_kpi_prerequisites",
        status=STATUS_CANDIDATE,
        evidence=[
            f"source={source}:exists",
            "abaqus_executable=available",
            "license_hint=present",
            "odb_extraction_not_run=true",
        ],
        real_env_required=True,
        real_env_verified=False,
    )


def _probe_real_e2e_not_run() -> Capability:
    return Capability(
        name="real_abaqus_e2e_pipeline",
        status=STATUS_ENV_LIMITED,
        evidence=[
            "7_stage_pipeline_not_run_by_validator=true",
            "syntaxcheck_not_run=true",
            "submit_monitor_not_run=true",
            "odb_kpi_not_run=true",
        ],
        real_env_required=True,
        real_env_verified=False,
        missing_reason=(
            "This validator checks prerequisites only; it does not run CAE noGUI, "
            "syntaxcheck, solver submit/monitor, ODB KPI extraction, or compare_expected."
        ),
        blocks_require_real=False,
    )


def collect_report(
    *,
    mode: str,
    env: Env | None = None,
    which: Which | None = None,
) -> dict:
    env = env if env is not None else os.environ
    which = which if which is not None else shutil.which

    capabilities: list[Capability] = [
        _probe_python_runtime(),
        _probe_package_import(),
        _probe_console_entry(),
        _probe_dry_run_benchmark(),
        _probe_tests_discoverable(),
    ]

    executable_cap, executable = _probe_abaqus_executable(env, which)
    license_cap = _probe_license_hint(env, executable)
    capabilities.extend(
        [
            executable_cap,
            license_cap,
            _probe_syntaxcheck_prerequisites(executable),
            _probe_submit_monitor_prerequisites(executable, license_cap),
            _probe_odb_kpi_prerequisites(executable, license_cap),
            _probe_real_e2e_not_run(),
        ]
    )

    missing = [
        {
            "capability": cap.name,
            "status": cap.status,
            "reason": cap.missing_reason,
        }
        for cap in capabilities
        if cap.missing_reason and (cap.status in {STATUS_MISSING, STATUS_ENV_LIMITED})
    ]
    require_real_missing = [
        item
        for item in missing
        if next(cap for cap in capabilities if cap.name == item["capability"]).blocks_require_real
    ]

    local_failures = [
        cap.name
        for cap in capabilities
        if not cap.real_env_required and cap.status == STATUS_MISSING
    ]
    real_ready = not require_real_missing

    if local_failures:
        overall_status = "local-validation-failed"
    elif real_ready:
        overall_status = "real-env-prerequisites-candidate"
    elif mode == "require-real":
        overall_status = "real-env-missing"
    elif mode == "dry-run":
        overall_status = "dry-run-ready-real-env-missing"
    else:
        overall_status = "default-ok-real-env-missing"

    return {
        "schema_version": "1.0",
        "project": "abaqus-agent",
        "mode": mode,
        "generated_at": _utc_now(),
        "overall_status": overall_status,
        "real_env_prerequisites_ready": real_ready,
        "real_abaqus_e2e_verified": False,
        "missing": missing,
        "require_real_missing": require_real_missing,
        "capabilities": [cap.to_json() for cap in capabilities],
    }


def exit_code_for_report(report: dict, *, require_real: bool, dry_run: bool) -> int:
    local_missing = [
        cap
        for cap in report["capabilities"]
        if not cap["real_env_required"] and cap["status"] == STATUS_MISSING
    ]
    if local_missing:
        return 1
    if require_real and report["require_real_missing"]:
        return 2
    if dry_run:
        dry_run_cap = _capability(report, "benchmark_dry_run_entry")
        if dry_run_cap["status"] != STATUS_DRY_RUN_SUPPORTED:
            return 1
    return 0


def _capability(report: dict, name: str) -> dict:
    for cap in report["capabilities"]:
        if cap["name"] == name:
            return cap
    raise KeyError(name)


def _print_text(report: dict) -> None:
    print(f"abaqus-agent environment validation ({report['mode']})")
    print(f"overall_status: {report['overall_status']}")
    print(f"real_env_prerequisites_ready: {report['real_env_prerequisites_ready']}")
    print(f"real_abaqus_e2e_verified: {report['real_abaqus_e2e_verified']}")
    print()
    for cap in report["capabilities"]:
        real = " real-env" if cap["real_env_required"] else ""
        print(f"- {cap['name']}: {cap['status']}{real}")
        for item in cap["evidence"]:
            print(f"  evidence: {item}")
        if cap["missing_reason"]:
            print(f"  missing: {cap['missing_reason']}")
    if report["require_real_missing"]:
        print()
        print("require-real missing:")
        for item in report["require_real_missing"]:
            print(f"- {item['capability']}: {item['reason']}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate local Abaqus environment prerequisites.")
    parser.add_argument("--dry-run", action="store_true", help="Validate no-Abaqus local dry-run readiness.")
    parser.add_argument("--require-real", action="store_true", help="Fail if real Abaqus prerequisites are missing.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args(argv)


def run(
    argv: Sequence[str] | None = None,
    *,
    env: Env | None = None,
    which: Which | None = None,
) -> int:
    args = parse_args(argv)
    if args.require_real:
        mode = "require-real"
    elif args.dry_run:
        mode = "dry-run"
    else:
        mode = "default"

    report = collect_report(mode=mode, env=env, which=which)
    exit_code = exit_code_for_report(report, require_real=args.require_real, dry_run=args.dry_run)
    report["exit_code"] = exit_code

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_text(report)

    return exit_code


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
