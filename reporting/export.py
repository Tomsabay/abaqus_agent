"""Offline run report assembly and export helpers."""

from __future__ import annotations

import base64
import io
import json
import mimetypes
import zipfile
from pathlib import Path
from typing import Any

from .templates import render_run_report_html, render_run_report_markdown

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


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
            "capsule_path": run.get("capsule_path"),
            "result_path": run.get("result_path"),
            "workdir": run.get("workdir"),
        },
        "kpis": run.get("kpis", {}),
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
        "spec": result.get("spec", {}),
        "kpis": result.get("kpis", {}),
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


def _abaqus_release(run: dict[str, Any], capsule: dict[str, Any]) -> str:
    spec = run.get("spec", {})
    provenance = capsule.get("provenance", {}) if isinstance(capsule, dict) else {}
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
