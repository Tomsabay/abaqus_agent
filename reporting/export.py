"""Offline run report assembly and export helpers."""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import sys
import zipfile
from pathlib import Path
from typing import Any

from .templates import render_run_report_html, render_run_report_markdown

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# BUILD_SPEC W20 criterion 7, route 乙 (declared degradation): the packaged bundle
# excludes Playwright/Chromium on purpose (packaging/abaqus_agent.spec), so the PDF
# entry is disabled there instead of failing halfway through a render. This single
# constant is both the UI's disabled-entry text and the exception message, so the
# two cannot drift apart.
PDF_FROZEN_NOTICE = "打包版不含 PDF 导出，请用 Word 另存为 PDF"
PDF_ALTERNATIVE_HINT = (
    "计算书请用 reporting/build_docx_report.py 生成 .docx 后在 Word 里「另存为 PDF」；"
    "开发环境（非打包版）安装 abaqus-agent[pdf] 后仍可直接导出 PDF。"
)


def is_frozen_bundle() -> bool:
    """True inside a PyInstaller bundle (dist\\AbaqusAgent-portable backend exe)."""
    return bool(getattr(sys, "frozen", False))


def pdf_export_capability() -> dict[str, Any]:
    """UI contract for the PDF entry: enabled, or disabled with the exact text.

    A UI must render ``notice`` verbatim on the greyed-out entry; the same string
    is what ``render_html_to_pdf`` raises in a frozen bundle.
    """
    frozen = is_frozen_bundle()
    return {
        "available": not frozen,
        "disabled": frozen,
        "notice": PDF_FROZEN_NOTICE if frozen else "",
        "hint": PDF_ALTERNATIVE_HINT if frozen else "",
        "reason": "frozen_bundle_excludes_chromium" if frozen else "",
        "formats_available": ["md", "html", "zip"] if frozen else ["md", "html", "pdf", "zip"],
    }


def build_offline_run_report(
    source: str | Path,
    *,
    template: str = "standard",
    embed_images: bool = False,
) -> dict[str, Any]:
    """Build a run report from a run directory, capsule.json, or result.json."""
    run = load_offline_run(source)
    capsule = run.get("capsule", {})
    artifacts = capsule.get("artifacts", {}) if isinstance(capsule, dict) else {}
    image_artifacts = [
        name for name in artifacts
        if Path(name).suffix.lower() in IMAGE_SUFFIXES
    ]
    report = {
        "summary": {
            "run_id": run.get("run_id"),
            "status": run.get("status"),
            "model_name": _model_name(run, capsule),
            "abaqus_release": _abaqus_release(run, capsule),
            **_solver_provenance(run, capsule),
            "capsule_path": run.get("capsule_path"),
            "result_path": run.get("result_path"),
            "workdir": run.get("workdir"),
        },
        "unsolved": bool(run.get("unsolved")),
        "kpi_notice": run.get("kpi_notice") or "",
        "kpis": run.get("kpis", {}),
        "kpis_missing": run.get("kpis_missing", []),
        "limitations": run.get("limitations", []),
        "regression": run.get("regression", {}),
        "contracts": run.get("contracts", {}),
        "diagnosis": run.get("diagnosis", {}),
        "artifacts": artifacts,
        "image_artifacts": image_artifacts,
        "capsule": capsule,
        "template": template,
    }
    if embed_images:
        report["image_artifact_sources"] = _load_image_artifact_sources(run, image_artifacts)
    report["markdown"] = render_run_report_markdown(report, template=template)
    report["html"] = render_run_report_html(report, template=template)
    return report


def build_offline_report_bundle(
    source: str | Path,
    *,
    template: str = "standard",
    max_artifact_bytes: int = 25_000_000,
) -> bytes:
    """Build a report zip bundle from an offline run source."""
    run = load_offline_run(source)
    report = build_offline_run_report(source, template=template, embed_images=True)
    workdir = Path(run["workdir"]).resolve() if run.get("workdir") else None
    manifest: dict[str, Any] = {
        "run_id": report["summary"].get("run_id"),
        "template": template,
        "included_artifacts": [],
        "skipped_artifacts": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("report.md", report.get("markdown", "") + "\n")
        bundle.writestr("report.html", report.get("html", ""))
        if report.get("capsule"):
            bundle.writestr("capsule.json", json.dumps(report["capsule"], indent=2, sort_keys=True))
        if run.get("result"):
            bundle.writestr("result.json", json.dumps(run["result"], indent=2, sort_keys=True))
        if workdir:
            for name in sorted(report.get("artifacts", {})):
                artifact_path = (workdir / name).resolve()
                if workdir not in artifact_path.parents and artifact_path != workdir:
                    manifest["skipped_artifacts"].append({"name": name, "reason": "invalid_path"})
                    continue
                if not artifact_path.is_file():
                    manifest["skipped_artifacts"].append({"name": name, "reason": "missing"})
                    continue
                size = artifact_path.stat().st_size
                if size > max_artifact_bytes:
                    manifest["skipped_artifacts"].append({"name": name, "reason": "too_large", "bytes": size})
                    continue
                bundle.write(artifact_path, _artifact_zip_name(name))
                manifest["included_artifacts"].append({"name": name, "bytes": size})
        bundle.writestr("artifact_manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    return buffer.getvalue()


def build_offline_report_pdf(
    source: str | Path,
    *,
    template: str = "standard",
) -> bytes:
    """Build a PDF report from an offline run source."""
    report = build_offline_run_report(source, template=template, embed_images=True)
    return render_html_to_pdf(report["html"])


def export_offline_run_report(
    source: str | Path,
    out: str | Path,
    *,
    export_format: str = "auto",
    template: str = "standard",
    max_artifact_bytes: int = 25_000_000,
) -> dict[str, Any]:
    """Write an offline run report to Markdown, HTML, PDF, or zip."""
    out_path = Path(out)
    fmt = _resolve_export_format(export_format, out_path)
    if fmt == "zip":
        content = build_offline_report_bundle(
            source,
            template=template,
            max_artifact_bytes=max_artifact_bytes,
        )
        out_path.write_bytes(content)
        size = len(content)
    elif fmt == "pdf":
        content = build_offline_report_pdf(source, template=template)
        out_path.write_bytes(content)
        size = len(content)
    else:
        report = build_offline_run_report(source, template=template, embed_images=(fmt == "html"))
        content = report["markdown"] + "\n" if fmt == "md" else report["html"]
        out_path.write_text(content, encoding="utf-8")
        size = out_path.stat().st_size
    return {"format": fmt, "output_path": str(out_path), "bytes": size}


def render_html_to_pdf(html: str) -> bytes:
    """Render standalone report HTML to PDF using optional Playwright."""
    if is_frozen_bundle():
        raise RuntimeError(PDF_FROZEN_NOTICE)
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "PDF export requires the optional Playwright dependency. "
            "Install with `pip install 'abaqus-agent[pdf]'` and run `playwright install chromium`."
        ) from e

    try:
        with sync_playwright() as playwright:
            browser = None
            browser = playwright.chromium.launch()
            try:
                page = browser.new_page()
                page.set_content(html, wait_until="networkidle")
                return page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "16mm", "right": "14mm", "bottom": "16mm", "left": "14mm"},
                )
            finally:
                if browser:
                    browser.close()
    except PlaywrightError as e:
        raise RuntimeError(
            "PDF export failed. Ensure Chromium is installed with `playwright install chromium`."
        ) from e


def load_offline_run(source: str | Path) -> dict[str, Any]:
    """Load flexible offline run evidence into a normalized run dict."""
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(source_path)

    workdir = source_path if source_path.is_dir() else source_path.parent
    capsule_path = _candidate_file(source_path, "capsule.json")
    result_path = _candidate_file(source_path, "result.json")
    capsule = _read_json(capsule_path) if capsule_path else {}
    result = _read_json(result_path) if result_path else {}
    if source_path.is_file() and source_path.name != "capsule.json" and not result:
        result = _read_json(source_path)
        result_path = source_path

    run_id = result.get("run_id") or capsule.get("run_id") or source_path.stem
    provenance = capsule.get("provenance", {}) if isinstance(capsule, dict) else {}
    return {
        "run_id": run_id,
        "status": result.get("status") or provenance.get("status") or "-",
        "unsolved": bool(result.get("unsolved")),
        "kpi_notice": result.get("kpi_notice") or "",
        "spec": result.get("spec", {}),
        "kpis": result.get("kpis", {}),
        "kpis_missing": result.get("kpis_missing", []),
        "limitations": result.get("limitations", []),
        "regression": result.get("regression", {}),
        "contracts": result.get("contracts") or capsule.get("contracts", {}),
        "diagnosis": result.get("diagnosis", {}),
        "capsule": capsule,
        "result": result,
        "capsule_path": str(capsule_path) if capsule_path else "",
        "result_path": str(result_path) if result_path else "",
        "workdir": str(workdir),
    }


def _candidate_file(source_path: Path, filename: str) -> Path | None:
    if source_path.is_dir():
        candidate = source_path / filename
        return candidate if candidate.is_file() else None
    if source_path.name == filename:
        return source_path
    candidate = source_path.parent / filename
    return candidate if candidate.is_file() else None


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must contain an object: {path}")
    return data


def _model_name(run: dict[str, Any], capsule: dict[str, Any]) -> str:
    spec = run.get("spec", {})
    inputs = capsule.get("inputs", {}) if isinstance(capsule, dict) else {}
    return (
        spec.get("meta", {}).get("model_name")
        or inputs.get("model_name")
        or capsule.get("model_name")
        or "-"
    )


def _solver_provenance(run: dict[str, Any], capsule: dict[str, Any]) -> dict[str, Any]:
    """Which solver actually produced this run, straight from the capsule.

    Only one answer is possible now, but it is still read rather than assumed:
    a run archived before the backend was recorded says nothing, and nothing is
    the honest value. An archived report that names the wrong solver is a false
    claim about how a number was obtained, which is the one thing these reports
    exist to get right.
    """
    provenance = capsule.get("provenance", {}) if isinstance(capsule, dict) else {}
    backend = provenance.get("solver_backend")
    if not backend:
        return {"solver_backend": None, "solver_label": None}
    return {"solver_backend": backend, "solver_label": provenance.get("solver_label")}


def _abaqus_release(run: dict[str, Any], capsule: dict[str, Any]) -> str:
    provenance = capsule.get("provenance", {}) if isinstance(capsule, dict) else {}
    spec = run.get("spec", {})
    return (
        spec.get("meta", {}).get("abaqus_release")
        or provenance.get("abaqus_release")
        or "-"
    )


def _load_image_artifact_sources(run: dict[str, Any], image_artifacts: list[str]) -> dict[str, str]:
    workdir = Path(run["workdir"]).resolve() if run.get("workdir") else None
    if not workdir:
        return {}
    sources = {}
    for name in image_artifacts:
        artifact_path = (workdir / name).resolve()
        if workdir not in artifact_path.parents and artifact_path != workdir:
            continue
        if not artifact_path.is_file() or artifact_path.stat().st_size > 5 * 1024 * 1024:
            continue
        media_type = mimetypes.guess_type(artifact_path.name)[0] or "application/octet-stream"
        data = base64.b64encode(artifact_path.read_bytes()).decode("ascii")
        sources[name] = f"data:{media_type};base64,{data}"
    return sources


def _artifact_zip_name(name: str) -> str:
    parts = [part for part in Path(name).parts if part not in {"", ".", ".."}]
    return "artifacts/" + "/".join(parts or ["artifact"])


def _resolve_export_format(export_format: str, out_path: Path) -> str:
    fmt = export_format.lower()
    if fmt != "auto":
        if fmt not in {"md", "html", "pdf", "zip"}:
            raise ValueError("export_format must be one of auto, md, html, pdf, zip")
        return fmt
    suffix = out_path.suffix.lower()
    if suffix == ".md":
        return "md"
    if suffix == ".html":
        return "html"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".zip":
        return "zip"
    raise ValueError("Cannot infer report format; use --format md|html|pdf|zip")
