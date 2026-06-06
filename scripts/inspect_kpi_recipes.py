#!/usr/bin/env python3
"""Inspect and export built-in ODB Lens KPI recipes without starting a server."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from post.kpi_recipes import get_kpi_recipe, list_kpi_recipes  # noqa: E402


def _export_recipe(recipe_id: str, out_path: str) -> dict[str, Any]:
    recipe = get_kpi_recipe(recipe_id)
    target = Path(out_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(recipe["kpi_spec"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "recipe_id": recipe["id"],
        "case": recipe["case"],
        "title": recipe["title"],
        "kpi_spec_path": str(target),
        "kpi_spec": recipe["kpi_spec"],
        "extract_command_hint": (
            "abaqus python post/extract_kpis.py -- <model.odb> "
            f"{target} <kpi-result.json>"
        ),
        "real_env_verified": False,
        "verification_boundary": recipe["verification_boundary"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect built-in ODB Lens KPI recipes."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List KPI recipes")
    list_parser.add_argument("--case", default="", help="Filter by example case")
    list_parser.add_argument("--kpi-type", default="", help="Filter by KPI extractor type")

    detail_parser = subparsers.add_parser("detail", help="Return one KPI recipe")
    detail_parser.add_argument("recipe_id")

    export_parser = subparsers.add_parser("export", help="Export a recipe kpi_spec JSON file")
    export_parser.add_argument("recipe_id")
    export_parser.add_argument("--out", required=True, help="Output JSON path for the recipe kpi_spec list")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            data = list_kpi_recipes(case=args.case, kpi_type=args.kpi_type)
        elif args.command == "detail":
            data = get_kpi_recipe(args.recipe_id)
        elif args.command == "export":
            data = _export_recipe(args.recipe_id, args.out)
        else:
            parser.error(f"Unsupported command: {args.command}")
        print(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))
        return 0
    except KeyError as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 2
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
