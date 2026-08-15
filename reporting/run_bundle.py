"""Normalized view of one finished run directory, for docx/xlsx report builders.

Everything here is read-only and stdlib+PyYAML only, so it also works inside the
frozen bundle. The KPI numbers come from ``_kpi_result.json`` when present (the
file the ODB extraction step wrote) and fall back to ``result.json``; the report
records which file it read so a number in the document can always be traced.

W20 criterion 5: the Abaqus release printed on the cover comes from
``abaqus information=release`` (via tools.abaqus_cmd.detect_abaqus_release), never
from ``spec.meta.abaqus_release`` — that field is unvalidated user metadata and
has drifted from this machine before.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from tools.abaqus_cmd import detect_abaqus_release

RELEASE_UNKNOWN = "未检测到（本机无可用 Abaqus）"
DEMO_KPI_NOTICE_FALLBACK = "未检测到 Abaqus，无法求解；本报告不含任何数值 KPI。"

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg")
_COUNT_PATTERNS = {
    "elements": re.compile(r"NUMBER OF ELEMENTS IS\s+(\d+)", re.IGNORECASE),
    "nodes": re.compile(r"NUMBER OF NODES IS\s+(\d+)", re.IGNORECASE),
}


@dataclass
class RunBundle:
    """Everything a report needs from one run directory."""

    run_dir: Path
    run_id: str
    model_name: str
    status: str
    demo_mode: bool
    kpi_notice: str
    kpis: dict[str, Any]
    kpi_source: str
    result: dict[str, Any]
    capsule: dict[str, Any]
    spec: dict[str, Any]
    spec_path: str
    images: list[Path] = field(default_factory=list)
    mesh_counts: dict[str, int] = field(default_factory=dict)
    dat_path: str = ""
    odb_path: str = ""

    @property
    def spec_release(self) -> str:
        meta = self.spec.get("meta", {}) if isinstance(self.spec, dict) else {}
        return str(meta.get("abaqus_release", "") or "")

    @property
    def started_at(self) -> str:
        return str(self.result.get("started_at", "") or "")

    @property
    def finished_at(self) -> str:
        return str(self.result.get("finished_at", "") or "")

    @property
    def artifacts(self) -> dict[str, Any]:
        artifacts = self.capsule.get("artifacts", {})
        return artifacts if isinstance(artifacts, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _mesh_counts(run_dir: Path, model_name: str) -> tuple[dict[str, int], str]:
    """Element/node counts as printed by the solver in <job>.dat (if available)."""
    candidates = []
    if model_name:
        candidates.append(run_dir / f"{model_name}.dat")
    candidates.extend(sorted(p for p in run_dir.glob("*.dat") if "syntaxcheck" not in p.name))
    for dat in candidates:
        if not dat.is_file():
            continue
        try:
            text = dat.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        counts = {}
        for key, pattern in _COUNT_PATTERNS.items():
            match = pattern.search(text)
            if match:
                counts[key] = int(match.group(1))
        if counts:
            return counts, str(dat)
    return {}, ""


def _images(run_dir: Path, result: dict[str, Any]) -> list[Path]:
    """Report figures: the run's declared visuals first, then any other image."""
    ordered: list[Path] = []
    for visual in result.get("visuals", []) or []:
        if not isinstance(visual, dict):
            continue
        name = str(visual.get("path") or "")
        if not name:
            continue
        candidate = run_dir / name
        if candidate.is_file() and candidate not in ordered:
            ordered.append(candidate)
    for suffix in IMAGE_SUFFIXES:
        for candidate in sorted(run_dir.glob(f"*{suffix}")):
            if candidate not in ordered:
                ordered.append(candidate)
    return ordered


def load_run_bundle(run_dir: str | Path, spec_path: str | Path | None = None) -> RunBundle:
    """Load one run directory into a RunBundle.

    ``spec_path`` overrides the spec recorded in result.json (used by the W20
    criterion-5 check, which points the builder at a tampered %TEMP% copy to
    prove the cover release does not come from the spec).
    """
    directory = Path(run_dir)
    if not directory.exists():
        raise FileNotFoundError(f"run 目录不存在：{directory}")
    if directory.is_file():
        directory = directory.parent

    result = _read_json(directory / "result.json")
    capsule = _read_json(directory / "capsule.json")
    kpi_result = _read_json(directory / "_kpi_result.json")

    if kpi_result.get("kpis"):
        kpis = dict(kpi_result["kpis"])
        kpi_source = str(directory / "_kpi_result.json")
    else:
        kpis = dict(result.get("kpis", {}) or {})
        kpi_source = str(directory / "result.json") if result else ""

    resolved_spec_path = str(spec_path) if spec_path else str(result.get("spec_path", "") or "")
    spec = _read_yaml(Path(resolved_spec_path)) if resolved_spec_path else {}

    # cases/<case>/runs/<run_id> -> the case name; anything else -> the directory name.
    fallback_name = (
        directory.parents[1].name
        if directory.parent.name == "runs" and len(directory.parents) > 1
        else directory.name
    )
    model_name = (
        str(spec.get("meta", {}).get("model_name", "") or "")
        or str(capsule.get("inputs", {}).get("model_name", "") or "")
        or fallback_name
    )
    run_id = str(result.get("run_id") or capsule.get("run_id") or directory.name)
    status = str(result.get("status") or "-")
    demo_mode = bool(result.get("demo_mode")) or status.upper() == "DEMO"
    counts, dat_path = _mesh_counts(directory, model_name)
    odb_path = str(kpi_result.get("odb_path", "") or "")

    return RunBundle(
        run_dir=directory,
        run_id=run_id,
        model_name=model_name or directory.name,
        status=status,
        demo_mode=demo_mode,
        kpi_notice=str(result.get("kpi_notice", "") or ""),
        kpis={} if demo_mode else kpis,
        kpi_source=kpi_source,
        result=result,
        capsule=capsule,
        spec=spec,
        spec_path=resolved_spec_path,
        images=_images(directory, result),
        mesh_counts=counts,
        dat_path=dat_path,
        odb_path=odb_path,
    )


def actual_abaqus_release(timeout: float = 90.0) -> str:
    """The release the installed solver reports, or an explicit unknown marker."""
    release = detect_abaqus_release(timeout=timeout)
    return release or RELEASE_UNKNOWN


def generated_at() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def demo_notice(bundle: RunBundle) -> str:
    return bundle.kpi_notice or DEMO_KPI_NOTICE_FALLBACK
