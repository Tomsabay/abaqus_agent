"""Compare saved Case Memory KPI artifacts from the local evidence vault."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evidence.vault import get_vault_file_path
from simdiff.service import collect_kpi_diff


def collect_case_memory_diff(
    *,
    baseline_vault_id: str,
    candidate_vault_id: str,
    out_dir: str | Path,
    diff_id: str = "case-memory-diff",
    baseline_filename: str | None = None,
    candidate_filename: str | None = None,
) -> dict[str, Any]:
    """Compare candidate KPI dictionaries from two saved vault entries."""
    baseline = load_vault_kpi_source(baseline_vault_id, filename=baseline_filename)
    candidate = load_vault_kpi_source(candidate_vault_id, filename=candidate_filename)
    result = collect_kpi_diff(
        baseline_kpis=baseline["kpis"],
        candidate_kpis=candidate["kpis"],
        tolerances={
            name: {"rtol": 0.05, "atol": 0.0}
            for name in set(baseline["kpis"]) | set(candidate["kpis"])
        },
        out_dir=out_dir,
        diff_id=diff_id,
        input_metadata={
            "source": "case-memory-vault",
            "baseline": baseline["metadata"],
            "candidate": candidate["metadata"],
        },
    )
    result["case_memory_diff"] = {
        "baseline_vault_id": baseline_vault_id,
        "candidate_vault_id": candidate_vault_id,
        "baseline_source": baseline["metadata"],
        "candidate_source": candidate["metadata"],
    }
    _rewrite_outputs(result, Path(out_dir))
    return result


def load_vault_kpi_source(vault_id: str, filename: str | None = None) -> dict[str, Any]:
    """Load a comparable KPI dictionary from a vault entry."""
    filenames = (filename,) if filename else ("evidence.json", "diff.json")
    for candidate_filename in filenames:
        if candidate_filename is None:
            continue
        try:
            path = get_vault_file_path(vault_id, candidate_filename)
        except FileNotFoundError:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if candidate_filename.endswith("evidence.json"):
            kpis = data.get("candidate_kpis")
        elif candidate_filename.endswith("diff.json"):
            kpis = data.get("inputs", {}).get("candidate_kpis")
        else:
            raise ValueError(
                "Case Memory diff filename must end with evidence.json or diff.json"
            )
        if isinstance(kpis, dict):
            return {
                "kpis": kpis,
                "metadata": {
                    "vault_id": vault_id,
                    "filename": candidate_filename,
                    "workflow": data.get("workflow", ""),
                    "run_id": data.get("run_id") or data.get("diff_id") or "",
                    "overall_status": data.get("overall_status", ""),
                },
            }
    raise FileNotFoundError(
        f"Vault entry does not contain comparable KPI artifact: {vault_id}"
    )


def _rewrite_outputs(result: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "diff.json").write_text(
        json.dumps(result, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    report_path = out_dir / "diff.md"
    report_text = report_path.read_text(encoding="utf-8")
    report_path.write_text(
        report_text
        + "\n## Case Memory Sources\n\n"
        + f"- Baseline vault id: `{result['case_memory_diff']['baseline_vault_id']}`\n"
        + f"- Candidate vault id: `{result['case_memory_diff']['candidate_vault_id']}`\n",
        encoding="utf-8",
    )
