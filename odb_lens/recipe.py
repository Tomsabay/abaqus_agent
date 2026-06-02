"""Declarative ODB KPI recipe loading and reporting.

ODB Lens gives the project a stable YAML-facing API for KPI extraction while
the Abaqus-specific extractor keeps using its current compact spec format.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

SUPPORTED_TYPES = {
    "derived_stress_concentration",
    "eigenfrequency",
    "field_max",
    "field_min",
    "history_output_max",
    "nodal_displacement",
    "reaction_force_max",
}
SUPPORTED_REDUCERS = {"abs_max", "last", "max", "min"}
SUPPORTED_PLOT_FIELDS = {"S", "U", "PEEQ", "RF"}


def load_recipe(path: str | Path) -> list[dict]:
    """Load KPI recipe YAML/JSON and return normalized extractor specs."""
    recipe_path = Path(path)
    if recipe_path.suffix.lower() == ".json":
        data = json.loads(recipe_path.read_text(encoding="utf-8"))
    else:
        data = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    return normalize_recipe(data)


def normalize_recipe(data: dict | list | None) -> list[dict]:
    """Normalize supported recipe shapes to the extractor KPI spec list."""
    raw_kpis = _extract_kpi_list(data)
    normalized = [_normalize_kpi(kpi) for kpi in raw_kpis]
    valid, errors = validate_recipe(normalized)
    if not valid:
        raise ValueError("; ".join(errors))
    return normalized


def normalize_plots(data: dict | list | None, kpis: list[dict] | None = None) -> list[dict]:
    """Normalize ODB plot specs, inferring useful default plots from KPI recipes."""
    raw_plots = _extract_plot_list(data)
    if raw_plots:
        plots = [_normalize_plot(plot) for plot in raw_plots]
    else:
        plots = _infer_plots_from_kpis(kpis or normalize_recipe(data))
    return _dedupe_plots(plots)


def validate_recipe(kpis: list[dict]) -> tuple[bool, list[str]]:
    """Validate normalized KPI specs without requiring Abaqus."""
    errors = []
    if not isinstance(kpis, list) or not kpis:
        errors.append("recipe must contain at least one KPI")
        return False, errors

    names = set()
    for idx, kpi in enumerate(kpis):
        prefix = f"kpis[{idx}]"
        name = kpi.get("name")
        if not name:
            errors.append(f"{prefix}.name is required")
        elif name in names:
            errors.append(f"duplicate KPI name: {name}")
        else:
            names.add(name)

        kind = kpi.get("type")
        if kind not in SUPPORTED_TYPES:
            errors.append(f"{prefix}.type is unsupported: {kind}")

        if kpi.get("reducer") and kpi["reducer"] not in SUPPORTED_REDUCERS:
            errors.append(f"{prefix}.reducer is unsupported: {kpi['reducer']}")

    return not errors, errors


def render_kpi_markdown(kpis: dict, recipe: list[dict] | None = None) -> str:
    """Render extracted KPIs as a small Markdown report."""
    recipe_by_name = {item.get("name"): item for item in recipe or []}
    lines = [
        "# ODB Lens KPI Report",
        "",
        "| KPI | Value | Unit | Source | Query |",
        "|-----|-------|------|--------|-------|",
    ]
    for name in sorted(kpis):
        value = _value_of(kpis[name])
        unit = _unit_of(kpis[name])
        spec = recipe_by_name.get(name, {})
        source = spec.get("source", "odb")
        query = _query_summary(spec)
        lines.append(f"| {name} | {value} | {unit} | {source} | {query} |")
    return "\n".join(lines)


def _extract_kpi_list(data: dict | list | None) -> list[dict]:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("kpis"), list):
            return data["kpis"]
        outputs = data.get("outputs")
        if isinstance(outputs, dict) and isinstance(outputs.get("kpis"), list):
            return outputs["kpis"]
        lens = data.get("odb_lens")
        if isinstance(lens, dict) and isinstance(lens.get("kpis"), list):
            return lens["kpis"]
    raise ValueError("recipe must be a KPI list or contain kpis/outputs.kpis/odb_lens.kpis")


def _extract_plot_list(data: dict | list | None) -> list[dict]:
    if isinstance(data, dict):
        if isinstance(data.get("plots"), list):
            return data["plots"]
        outputs = data.get("outputs")
        if isinstance(outputs, dict) and isinstance(outputs.get("plots"), list):
            return outputs["plots"]
        lens = data.get("odb_lens")
        if isinstance(lens, dict) and isinstance(lens.get("plots"), list):
            return lens["plots"]
    return []


def _normalize_kpi(kpi: dict) -> dict:
    if not isinstance(kpi, dict):
        raise ValueError("each KPI recipe entry must be an object")

    normalized = dict(kpi)
    if normalized.get("type"):
        normalized["type"] = str(normalized["type"])
    else:
        normalized["type"] = _infer_type(normalized)

    if normalized.get("region") and not normalized.get("location"):
        normalized["location"] = _normalize_region(str(normalized["region"]))

    field = normalized.get("field")
    if field and "field_variable" not in normalized:
        normalized["field_variable"] = str(field)

    invariant = normalized.get("invariant")
    if invariant:
        normalized["invariant"] = str(invariant).upper()

    return normalized


def _normalize_plot(plot: dict) -> dict:
    if not isinstance(plot, dict):
        raise ValueError("each plot recipe entry must be an object")

    normalized = dict(plot)
    field = str(normalized.get("field") or normalized.get("field_variable") or "S").upper()
    if field not in SUPPORTED_PLOT_FIELDS:
        raise ValueError(f"plot field is unsupported: {field}")
    normalized["field_variable"] = field

    invariant = normalized.get("invariant")
    component = normalized.get("component")
    if invariant:
        normalized["invariant"] = str(invariant).upper()
    elif field == "S":
        normalized["invariant"] = "MISES"
    elif field == "U" and not component:
        normalized["invariant"] = "MAGNITUDE"

    if component:
        normalized["component"] = str(component).upper()

    normalized["name"] = _safe_plot_name(normalized.get("name") or _default_plot_name(normalized))
    normalized["deformed"] = bool(normalized.get("deformed", field == "U"))
    normalized["frame"] = normalized.get("frame", "last")
    return normalized


def _infer_plots_from_kpis(kpis: list[dict]) -> list[dict]:
    plots = []
    for kpi in kpis:
        name = str(kpi.get("name", "")).upper()
        field = str(kpi.get("field_variable") or kpi.get("field") or "").upper()
        component = str(kpi.get("component", "")).upper()
        kind = str(kpi.get("type", ""))

        if "MISES" in name or field == "S" or kind in {"field_max", "field_min"} and component.startswith("S"):
            plots.append({"name": "mises_contour", "field_variable": "S", "invariant": "MISES"})
        if field == "U" or component.startswith("U") or kind == "nodal_displacement":
            plots.append({"name": "u_magnitude", "field_variable": "U", "invariant": "MAGNITUDE", "deformed": True})
        if field == "PEEQ" or "PEEQ" in name:
            plots.append({"name": "peeq_contour", "field_variable": "PEEQ"})
    return [_normalize_plot(plot) for plot in plots]


def _dedupe_plots(plots: list[dict]) -> list[dict]:
    deduped = []
    seen = set()
    for plot in plots:
        name = plot["name"]
        if name in seen:
            continue
        seen.add(name)
        deduped.append(plot)
    return deduped


def _default_plot_name(plot: dict) -> str:
    field = str(plot.get("field_variable") or plot.get("field") or "field").lower()
    invariant = str(plot.get("invariant") or plot.get("component") or "contour").lower()
    return f"{field}_{invariant}"


def _safe_plot_name(value: object) -> str:
    raw = str(value).strip() or "odb_plot"
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in raw)


def _infer_type(kpi: dict) -> str:
    source = str(kpi.get("source", "odb")).lower()
    reducer = str(kpi.get("reducer", "max")).lower()
    field = str(kpi.get("field", "")).upper()

    if source == "history":
        return "history_output_max"
    if field == "RF":
        return "reaction_force_max"
    if reducer == "min":
        return "field_min"
    return "field_max"


def _normalize_region(region: str) -> str:
    if ":" in region:
        return region.split(":", 1)[1]
    return region


def _value_of(raw: object) -> object:
    if isinstance(raw, dict):
        return raw.get("value", "")
    return raw


def _unit_of(raw: object) -> str:
    if isinstance(raw, dict):
        return str(raw.get("unit", ""))
    return ""


def _query_summary(spec: dict) -> str:
    if not spec:
        return "-"
    parts = []
    for key in ("type", "field_variable", "invariant", "component", "location", "variable", "frame"):
        if spec.get(key):
            parts.append(f"{key}={spec[key]}")
    return ", ".join(parts) or "-"
