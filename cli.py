"""Command line interface for Abaqus Agent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from capsule.store import init_from_inp
from contracts import evaluate_contracts
from doctor import diagnose_logs
from odb_lens import load_recipe, render_kpi_markdown
from simdiff.kpi_diff import diff_kpis
from simdiff.kpi_diff import render_markdown as render_diff_markdown

LOG_SUFFIXES = {".sta", ".msg", ".log", ".dat"}


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint. No args keeps the original server behavior."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return _cmd_serve(argparse.Namespace())

    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="abaqus-agent",
        description="Local simulation QA and regression framework for Abaqus.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="Start the FastAPI server")
    serve.set_defaults(func=_cmd_serve)

    capsule = sub.add_parser("capsule", help="Manage experiment capsules")
    capsule_sub = capsule.add_subparsers(dest="capsule_command", required=True)
    cap_init = capsule_sub.add_parser("init", help="Initialize a capsule from an input deck")
    cap_init.add_argument("--from-inp", required=True, dest="from_inp", help="Path to a .inp file")
    cap_init.add_argument("--out", required=True, help="Output capsule directory")
    cap_init.add_argument("--model-name", default="", help="Optional model name override")
    cap_init.set_defaults(func=_cmd_capsule_init)

    doctor = sub.add_parser("doctor", help="Diagnose Abaqus solver logs")
    doctor.add_argument("paths", nargs="+", help="Log files or directories to inspect")
    doctor.add_argument("--json", action="store_true", dest="as_json", help="Print JSON")
    doctor.add_argument("--out", help="Write Markdown report to this path")
    doctor.set_defaults(func=_cmd_doctor)

    lens = sub.add_parser("lens", help="Work with ODB Lens KPI recipes")
    lens_sub = lens.add_subparsers(dest="lens_command", required=True)
    lens_norm = lens_sub.add_parser("normalize", help="Normalize an ODB Lens recipe")
    lens_norm.add_argument("recipe", help="YAML/JSON KPI recipe")
    lens_norm.add_argument("--out", help="Write normalized JSON to this path")
    lens_norm.set_defaults(func=_cmd_lens_normalize)

    lens_report = lens_sub.add_parser("report", help="Render KPI JSON as Markdown")
    lens_report.add_argument("kpis", help="KPI JSON file, or result JSON containing kpis")
    lens_report.add_argument("--recipe", help="Optional ODB Lens recipe for query context")
    lens_report.add_argument("--out", help="Write Markdown report to this path")
    lens_report.set_defaults(func=_cmd_lens_report)

    check = sub.add_parser("check", help="Evaluate physics contracts against KPI JSON")
    check.add_argument("kpis", help="KPI JSON file, or a result JSON containing a kpis object")
    check.add_argument("contracts", help="Contracts YAML file")
    check.add_argument("--json", action="store_true", dest="as_json", help="Print JSON")
    check.add_argument("--out", help="Write Markdown report to this path")
    check.set_defaults(func=_cmd_check)

    diff = sub.add_parser("diff", help="Compare two KPI JSON files")
    diff.add_argument("baseline", help="Baseline KPI JSON file")
    diff.add_argument("candidate", help="Candidate KPI JSON file")
    diff.add_argument("--rtol", type=float, default=0.05, help="Default relative tolerance")
    diff.add_argument("--json", action="store_true", dest="as_json", help="Print JSON")
    diff.add_argument("--out", help="Write Markdown report to this path")
    diff.set_defaults(func=_cmd_diff)

    return parser


def _cmd_serve(_args: argparse.Namespace) -> int:
    from server import main as server_main

    server_main()
    return 0


def _cmd_capsule_init(args: argparse.Namespace) -> int:
    capsule = init_from_inp(
        args.from_inp,
        args.out,
        model_name=args.model_name or None,
    )
    print(json.dumps(capsule, indent=2, ensure_ascii=False))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    try:
        log_paths = _collect_log_paths(args.paths)
    except FileNotFoundError as e:
        print(f"Path not found: {e}", file=sys.stderr)
        return 2

    diagnosis = diagnose_logs(paths=log_paths)
    if args.as_json:
        output = json.dumps(diagnosis, indent=2, ensure_ascii=False)
    else:
        output = _render_doctor_markdown(diagnosis)

    _write_or_print(output, args.out)
    return 0


def _cmd_lens_normalize(args: argparse.Namespace) -> int:
    recipe = load_recipe(args.recipe)
    output = json.dumps(recipe, indent=2, ensure_ascii=False)
    _write_or_print(output, args.out)
    return 0


def _cmd_lens_report(args: argparse.Namespace) -> int:
    kpis = _load_kpis(args.kpis)
    recipe = load_recipe(args.recipe) if args.recipe else None
    output = render_kpi_markdown(kpis, recipe)
    _write_or_print(output, args.out)
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    kpis = _load_kpis(args.kpis)
    contracts = yaml.safe_load(Path(args.contracts).read_text(encoding="utf-8"))
    if isinstance(contracts, dict):
        contracts = contracts.get("contracts", [])

    result = evaluate_contracts(contracts or [], kpis)
    if args.as_json:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        output = _render_contract_markdown(result)

    _write_or_print(output, args.out)
    return 0 if result["passed"] else 1


def _cmd_diff(args: argparse.Namespace) -> int:
    baseline = _load_kpis(args.baseline)
    candidate = _load_kpis(args.candidate)
    result = diff_kpis(baseline, candidate, default_rtol=args.rtol)
    if args.as_json:
        output = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        output = render_diff_markdown(result)

    _write_or_print(output, args.out)
    return 0 if result["passed"] else 1


def _collect_log_paths(paths: list[str]) -> list[Path]:
    collected = []
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(path)
        if path.is_dir():
            collected.extend(
                p for p in sorted(path.iterdir())
                if p.is_file() and p.suffix.lower() in LOG_SUFFIXES
            )
        else:
            collected.append(path)
    return collected


def _load_kpis(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict) and isinstance(data.get("kpis"), dict):
        return data["kpis"]
    if isinstance(data, dict):
        return data
    raise ValueError(f"KPI file must contain an object: {path}")


def _render_doctor_markdown(diagnosis: dict) -> str:
    lines = ["# Solver Doctor Report", ""]
    if not diagnosis.get("matched"):
        lines.append("No known Abaqus solver patterns matched.")
        return "\n".join(lines)

    lines += [
        "| ID | Category | Severity | Evidence | Suggestion |",
        "|----|----------|----------|----------|------------|",
    ]
    for match in diagnosis.get("matches", []):
        evidence = str(match.get("evidence", "")).replace("\n", " ")
        suggestion = str(match.get("suggestion", "")).replace("\n", " ")
        lines.append(
            f"| {match['id']} | {match['category']} | {match['severity']} | "
            f"{evidence} | {suggestion} |"
        )
    return "\n".join(lines)


def _render_contract_markdown(result: dict) -> str:
    lines = [
        "# Physics Contract Report",
        "",
        f"Overall: {'PASS' if result.get('passed') else 'FAIL'}",
        "",
        "| Name | Type | Severity | Status | Detail |",
        "|------|------|----------|--------|--------|",
    ]
    for item in result.get("results", []):
        detail = str(item.get("detail", "")).replace("\n", " ")
        lines.append(
            f"| {item['name']} | {item['type']} | {item['severity']} | "
            f"{'PASS' if item['passed'] else 'FAIL'} | {detail} |"
        )
    return "\n".join(lines)


def _write_or_print(output: str, out_path: str | None) -> None:
    if out_path:
        Path(out_path).write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    raise SystemExit(main())
