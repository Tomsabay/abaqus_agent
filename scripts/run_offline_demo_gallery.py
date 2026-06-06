#!/usr/bin/env python3
# ruff: noqa: E402
"""
Run the built-in offline evidence example gallery.

This command does not invoke Abaqus. It evaluates supplied KPI fixtures and
contracts, then writes per-case evidence bundles plus a top-level index.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evidence.demo_gallery import collect_demo_gallery, render_index_markdown


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the offline evidence demo gallery.")
    parser.add_argument("--out-dir", required=True, help="Directory for gallery output.")
    parser.add_argument("--json", action="store_true", help="Print index JSON.")
    return parser.parse_args(argv)


def run(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    index = collect_demo_gallery(args.out_dir)
    if args.json:
        print(json.dumps(index, indent=2, sort_keys=True))
    else:
        print(render_index_markdown(index))
    return 0 if index["overall_status"] == "PASS" else 1


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
