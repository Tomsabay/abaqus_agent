"""PDF entry status/attempt helper — BUILD_SPEC W20 criterion 7, route 乙.

Route 乙 = declared degradation. The packaged bundle ships without Playwright /
Chromium (packaging/abaqus_agent.spec excludes it), so the PDF entry must be
disabled with a fixed message instead of blowing up mid-render. The UI-facing text
and the exception text are the same constant (``reporting.export.PDF_FROZEN_NOTICE``),
so they cannot drift.

    python -m reporting.pdf_route                     # print the capability contract
    python -m reporting.pdf_route --source <run> --out r.pdf   # try the export
    abaqus-agent-server.exe report-pdf --source <run> --out r.pdf   # frozen bundle

Exit codes: 0 available/ok · 3 disabled or failed (readable message, no traceback).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reporting.export import (  # noqa: E402
    PDF_ALTERNATIVE_HINT,
    PDF_FROZEN_NOTICE,
    export_offline_run_report,
    is_frozen_bundle,
    pdf_export_capability,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="report-pdf",
        description="Report the PDF export capability of this build, optionally trying it",
    )
    parser.add_argument("--source", help="Run directory / capsule.json / result.json")
    parser.add_argument("--out", help="Output .pdf path (only used with --source)")
    parser.add_argument("--template", default="standard")
    args = parser.parse_args(argv)

    capability = pdf_export_capability()
    print("frozen_bundle:", is_frozen_bundle())
    print("capability:", json.dumps(capability, ensure_ascii=False))
    if capability["disabled"]:
        print(f"UI 文案（置灰入口显示）：{PDF_FROZEN_NOTICE}")
        print(f"替代途径：{PDF_ALTERNATIVE_HINT}")

    if not args.source:
        return 0 if capability["available"] else 3

    if not args.out:
        print("错误：--source 需要配合 --out 使用", file=sys.stderr)
        return 3
    try:
        result = export_offline_run_report(args.source, args.out, export_format="pdf",
                                          template=args.template)
    except RuntimeError as e:
        message = str(e)
        print(f"PDF 导出不可用：{message}")
        print("verbatim_match_with_ui_notice:", message == PDF_FROZEN_NOTICE)
        return 3
    except (FileNotFoundError, OSError, ValueError) as e:
        print(f"PDF 导出失败：{e}", file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
