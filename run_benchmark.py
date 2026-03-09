#!/usr/bin/env python3
"""
run_benchmark.py
----------------
Benchmark runner for the Abaqus Agent.

Runs all cases in the cases/ directory and generates a benchmark report.
Each case needs: spec.yaml, expected.json, runner.json

Usage:
  python run_benchmark.py                        # run all cases
  python run_benchmark.py cantilever plate_hole  # run specific cases
  python run_benchmark.py --dry-run              # validate specs only (no Abaqus)
  python run_benchmark.py --report-only          # generate report from existing results
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from tools.schema_validator import validate_spec

CASES_DIR    = Path(__file__).parent / "cases"
REPORTS_DIR  = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Case discovery
# ---------------------------------------------------------------------------

def discover_cases(filter_names: list[str] | None = None) -> list[dict]:
    cases = []
    for case_dir in sorted(CASES_DIR.iterdir()):
        if not case_dir.is_dir():
            continue
        if filter_names and case_dir.name not in filter_names:
            continue
        spec_path   = case_dir / "spec.yaml"
        expect_path = case_dir / "expected.json"
        runner_path = case_dir / "runner.json"
        if spec_path.exists():
            cases.append({
                "name": case_dir.name,
                "dir": case_dir,
                "spec": spec_path,
                "expected": expect_path if expect_path.exists() else None,
                "runner_cfg": runner_path if runner_path.exists() else None,
            })
    return cases


# ---------------------------------------------------------------------------
# Individual case runner
# ---------------------------------------------------------------------------

def run_case(case: dict, dry_run: bool = False) -> dict:
    result = {
        "case": case["name"],
        "started_at": datetime.now().isoformat(),
        "stages": {},
        "kpis": {},
        "regression": {},
        "status": "PENDING",
        "elapsed_seconds": 0.0,
    }
    t0 = time.time()

    # Stage 1: Validate spec
    valid, errors = validate_spec(case["spec"])
    result["stages"]["validate_spec"] = {"valid": valid, "errors": errors}
    if not valid:
        result["status"] = "SPEC_INVALID"
        result["elapsed_seconds"] = time.time() - t0
        return result

    print("  [validate_spec] OK")

    if dry_run:
        result["status"] = "DRY_RUN_PASS"
        result["elapsed_seconds"] = time.time() - t0
        return result

    # Stage 2: Full pipeline (requires Abaqus)
    try:
        from agent.orchestrator import AbaqusOrchestrator

        def on_progress(stage, data):
            if stage in ("validate_spec", "build_model", "syntaxcheck",
                         "submit_job", "extract_kpis", "compare_kpis"):
                print(f"  [{stage}] {data}")

        orch = AbaqusOrchestrator(
            spec_path=case["spec"],
            expected_path=case["expected"],
            runner_cfg_path=case["runner_cfg"],
            on_progress=on_progress,
        )
        orch_result = orch.run()
        result["status"]     = orch_result["status"]
        result["stages"]     = orch_result["stages"]
        result["kpis"]       = orch_result.get("kpis", {})
        result["regression"] = orch_result.get("regression", {})
        if "error" in orch_result:
            result["error"] = orch_result["error"]

    except Exception as e:
        result["status"] = "ERROR"
        result["error"]  = {"message": str(e)}

    result["elapsed_seconds"] = round(time.time() - t0, 2)
    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(results: list[dict]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Abaqus Agent Benchmark Report",
        f"Generated: {now}",
        "",
        "## Summary",
        "",
    ]

    total   = len(results)
    passed  = sum(1 for r in results if r["status"] in ("COMPLETED", "DRY_RUN_PASS"))
    failed  = sum(1 for r in results if r["status"] in ("FAILED", "ERROR", "SPEC_INVALID"))
    reg_pass = sum(1 for r in results if r.get("regression", {}).get("passed") is True)

    lines += [
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total cases | {total} |",
        f"| Pipeline passed | {passed} / {total} |",
        f"| Regression passed | {reg_pass} / {total} |",
        f"| Failed / Error | {failed} |",
        "",
        "## Case Details",
        "",
        "| Case | Status | Elapsed | KPIs | Regression |",
        "|------|--------|---------|------|------------|",
    ]

    for r in results:
        case = r["case"]
        status = r["status"]
        elapsed = f"{r.get('elapsed_seconds', 0):.1f}s"
        kpis_str = ", ".join(f"{k}={v:.4g}" for k, v in r.get("kpis", {}).items()) or "-"
        reg = r.get("regression", {})
        reg_str = "PASS" if reg.get("passed") else ("FAIL" if reg.get("passed") is False else "-")
        lines.append(f"| {case} | {status} | {elapsed} | {kpis_str} | {reg_str} |")

    lines += ["", "## KPI Comparisons", ""]
    for r in results:
        comparisons = r.get("regression", {}).get("comparisons", {})
        if comparisons:
            lines.append(f"### {r['case']}")
            lines += [
                "| KPI | Expected | Actual | Rel Err | Status |",
                "|-----|----------|--------|---------|--------|",
            ]
            for kpi, comp in comparisons.items():
                exp = comp.get("expected", "-")
                act = comp.get("actual", "-")
                rel = f"{comp.get('rel_err', 0)*100:.1f}%" if comp.get("rel_err") is not None else "-"
                st  = comp.get("status", "-")
                lines.append(f"| {kpi} | {exp} | {act} | {rel} | {st} |")
            lines.append("")

    lines += ["## Error Details", ""]
    for r in results:
        if "error" in r:
            lines.append(f"**{r['case']}**: {r['error'].get('message', '')} "
                         f"(code: {r['error'].get('error_code', 'UNKNOWN')})")
            if r["error"].get("suggestion"):
                lines.append(f"  - Suggestion: {r['error']['suggestion']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Abaqus Agent Benchmark Runner")
    parser.add_argument("cases", nargs="*", help="Case names to run (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate specs only, skip Abaqus execution")
    parser.add_argument("--report-only", action="store_true",
                        help="Generate report from existing result.json files")
    args = parser.parse_args()

    cases = discover_cases(args.cases or None)
    if not cases:
        print("No cases found.")
        sys.exit(1)

    print(f"Found {len(cases)} case(s): {[c['name'] for c in cases]}")
    print()

    all_results = []

    if args.report_only:
        for case in cases:
            result_path = case["dir"] / "runs"
            # Find most recent result.json
            result_files = list(result_path.glob("*/result.json")) if result_path.exists() else []
            if result_files:
                latest = max(result_files, key=lambda p: p.stat().st_mtime)
                r = json.loads(latest.read_text(encoding="utf-8"))
                r["case"] = case["name"]
                all_results.append(r)
            else:
                all_results.append({"case": case["name"], "status": "NO_RESULT"})
    else:
        for case in cases:
            print(f"Running case: {case['name']}")
            result = run_case(case, dry_run=args.dry_run)
            all_results.append(result)
            status_icon = "✓" if result["status"] in ("COMPLETED", "DRY_RUN_PASS") else "✗"
            print(f"  {status_icon} {result['status']} ({result.get('elapsed_seconds', 0):.1f}s)")
            print()

    # Save raw results
    results_json = REPORTS_DIR / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_json.write_text(json.dumps(all_results, indent=2, default=str), encoding="utf-8")

    # Generate Markdown report
    report = generate_report(all_results)
    report_md = REPORTS_DIR / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_md.write_text(report, encoding="utf-8")

    # Print report to stdout
    print("=" * 60)
    print(report)
    print("=" * 60)
    print(f"\nReport saved: {report_md}")
    print(f"Raw results:  {results_json}")

    # Exit code
    failed = sum(1 for r in all_results if r["status"] in ("FAILED", "ERROR", "SPEC_INVALID"))
    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
