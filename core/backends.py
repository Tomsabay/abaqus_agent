"""
core/backends.py
----------------
Which solver runs this spec, and what that solver honestly cannot do.

Policy (the owner's words): if the user has Abaqus we use Abaqus — we do not
care which version or where it came from. If they do not, we fall back to
CalculiX, but only for a verified subset, and the interface must say plainly
what is and is not supported. If neither is present we keep the existing demo
(flow-walkthrough) mode, which produces no numbers at all.

Two rules shape everything below.

  1. A feature is supported only if it was actually measured. "CalculiX
     probably handles *FREQUENCY" is not evidence, so Frequency is refused here
     even though ccx has the keyword — it moves to supported when
     scripts/run_calculix_backend_check.py has a passing item for it.
  2. Refusing is a correct outcome. Silently approximating is a defect.

Leaf-ish module: imports only tools/*, so pytest can exercise the decision
logic without pulling in the runner or the server.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

from core import messages
from tools.abaqus_cmd import ENV_ABAQUS_CMD, detect_abaqus_release
from tools.ccx_cmd import ENV_CCX_EXE, detect_ccx_version, get_ccx_cmd

# auto | abaqus | calculix | demo
ENV_BACKEND = "ABAQUS_AGENT_SOLVER_BACKEND"

BACKEND_ABAQUS = "abaqus"
BACKEND_CALCULIX = "calculix"
BACKEND_DEMO = "demo"

Backend = Literal["abaqus", "calculix", "demo"]


@dataclass(frozen=True)
class Limitation:
    """One thing the chosen backend cannot do, in words a user can act on."""

    feature: str          # dotted spec path, e.g. "analysis.step_type"
    value: str            # the offending value
    reason: str           # rendered Chinese: what is wrong and what to do
    kind: str = "blocker"  # "blocker" = refuse the run; "caveat" = run, tag the number
    # The same sentence as a catalogue key, so a run recorded today can be read
    # back in English tomorrow. `reason` above stays Chinese and stays the
    # thing every existing caller reads; this is additive.
    reason_key: str = ""
    suffix_key: str = ""   # appended verbatim; the entry carries its own separator
    reason_params: Mapping[str, str] = field(default_factory=dict, compare=False)

    def localized(self, lang: str | None = None) -> str:
        if not self.reason_key:
            return self.reason
        text = messages.render(self.reason_key, lang, fallback=self.reason,
                               **self.reason_params)
        if self.suffix_key:
            text += messages.render(self.suffix_key, lang, **self.reason_params)
        return text

    def as_dict(self) -> dict:
        return {"feature": self.feature, "value": self.value,
                "reason": self.reason, "kind": self.kind,
                "reason_key": self.reason_key, "suffix_key": self.suffix_key,
                "reason_params": dict(self.reason_params)}


@dataclass(frozen=True)
class BackendDecision:
    backend: Backend
    label: str                                   # e.g. "CalculiX 2.23"
    reason: str                                  # why this backend was chosen
    source: str                                  # "auto" | "env" | "runner_cfg"
    version: str | None = None
    blockers: tuple[Limitation, ...] = field(default_factory=tuple)
    caveats: tuple[Limitation, ...] = field(default_factory=tuple)
    # As with Limitation: `reason` stays Chinese for every existing reader,
    # and the key lets a browser render the same sentence in English.
    reason_key: str = ""
    reason_params: Mapping[str, str] = field(default_factory=dict, compare=False)

    @property
    def supported(self) -> bool:
        return not self.blockers

    def as_dict(self) -> dict:
        return {
            "backend": self.backend,
            "label": self.label,
            "reason": self.reason,
            "reason_key": self.reason_key,
            "reason_params": dict(self.reason_params),
            "source": self.source,
            "version": self.version,
            "supported": self.supported,
            "blockers": [b.as_dict() for b in self.blockers],
            "caveats": [c.as_dict() for c in self.caveats],
        }


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def check_abaqus_available() -> bool:
    """Same rule core.helpers.check_abaqus uses; re-exported to avoid a cycle."""
    from core.helpers import check_abaqus
    return check_abaqus()


def check_calculix() -> bool:
    return get_ccx_cmd() is not None


def backend_label(backend: Backend, version: str | None, lang: str | None = None) -> str:
    if backend == BACKEND_ABAQUS:
        return ("Abaqus %s" % version if version
                else messages.render("backend.label.abaqus_unknown_version", lang))
    if backend == BACKEND_CALCULIX:
        return ("CalculiX %s" % version if version
                else messages.render("backend.label.calculix_unknown_version", lang))
    return messages.render("backend.label.demo", lang)


# ---------------------------------------------------------------------------
# CalculiX capability matrix
# ---------------------------------------------------------------------------

_HOWTO_KEY = "ccx.howto"
_HOWTO_PARAMS = {"env": ENV_ABAQUS_CMD}


def _limit(feature: str, value: str, key: str, *, kind: str = "blocker",
           howto: bool = True, **params) -> Limitation:
    """Build a refusal that can be read back in either language.

    ``reason`` stays the rendered Chinese, because that is what every existing
    reader — tests, CLI output, archived result.json files — already expects.
    The key rides along so the browser can render the same refusal in English
    without the backend having to know which language this particular reader
    speaks; a refusal outlives the request that produced it.
    """
    params = {**params, **(_HOWTO_PARAMS if howto else {})}
    reason = messages.render(key, "zh", **params)
    suffix = _HOWTO_KEY if howto else ""
    if suffix:
        reason += messages.render(suffix, "zh", **params)
    return Limitation(feature, value, reason, kind,
                      reason_key=key, suffix_key=suffix, reason_params=params)

_SUPPORTED_GEOMETRY = {"cantilever_block", "custom_inp"}
_SUPPORTED_STEP_TYPES = {"Static"}
_SUPPORTED_LOAD_TYPES = {"concentrated_force"}
_SUPPORTED_KPI_TYPES = {
    "nodal_displacement", "field_min", "field_max",
    "reaction_force_max", "derived_stress_concentration",
}
# KPI types that run but whose number is NOT Abaqus-equivalent.
_CAVEAT_KPI_TYPES = {"field_max", "derived_stress_concentration"}

_GEOMETRY_KEYS = {
    "plate_with_hole": "ccx.geometry.plate_with_hole",
    "square_plate": "ccx.geometry.square_plate",
    "axisymmetric_disk": "ccx.geometry.axisymmetric_disk",
    "beam_frame": "ccx.geometry.beam_frame",
    "composite_plate": "ccx.geometry.composite_plate",
    "cohesive_layer": "ccx.geometry.cohesive_layer",
}

_STEP_KEYS = {
    "Frequency": "ccx.step.frequency",
    "Dynamic_Implicit": "ccx.step.dynamic_implicit",
    "Dynamic_Explicit": "ccx.step.dynamic_explicit",
    "Coupled_Temperature_Displacement": "ccx.step.coupled_temp_disp",
    "Coupled_Thermal_Electrical": "ccx.step.coupled_thermal_electrical",
}

_LOAD_KEYS = {
    "blast_conwep": "ccx.load.blast_conwep",
    "pressure": "ccx.load.pressure",
    "displacement": "ccx.load.displacement",
    "temperature": "ccx.load.temperature",
    "heat_flux": "ccx.load.heat_flux",
    "body_heat_flux": "ccx.load.body_heat_flux",
}

_KPI_KEYS = {
    "eigenfrequency": "ccx.kpi.eigenfrequency",
    "history_output_max": "ccx.kpi.history_output_max",
}

_MATERIAL_KEYS = (
    ("electrical_conductivity", "ccx.material.conductivity"),
    ("fracture_energy", "ccx.material.fracture_energy"),
    ("max_traction", "ccx.material.max_traction"),
    ("yield", "ccx.material.plasticity"),
    ("yield_stress", "ccx.material.plasticity"),
)


def calculix_capability(spec: dict) -> tuple[list[Limitation], list[Limitation]]:
    """Evaluate a spec against the verified CalculiX subset.

    Returns ``(blockers, caveats)``. Pure function, no I/O — this is the part
    that has to be hermetically testable.
    """
    blockers: list[Limitation] = []
    caveats: list[Limitation] = []

    geo = spec.get("geometry", {}) or {}
    ana = spec.get("analysis", {}) or {}
    mat = spec.get("material", {}) or {}
    bc = spec.get("bc_load", {}) or {}
    outputs = spec.get("outputs", {}) or {}

    if spec.get("parts"):
        # Refused by name. Without this the v2 dialect still failed — it has no
        # `geometry` block, so the check below reported "geometry.type = None",
        # which reads as a malformed spec rather than as the whole modelling
        # dialect being Abaqus-only. A refusal that names the wrong field sends
        # the reader to fix something that was never wrong.
        blockers.append(_limit(
            "parts", "%d part(s)" % len(spec["parts"]),
            "ccx.spec.assembly_dialect"))
        return blockers, caveats

    geo_type = geo.get("type")
    if geo_type not in _SUPPORTED_GEOMETRY:
        blockers.append(_limit(
            "geometry.type", str(geo_type),
            _GEOMETRY_KEYS.get(str(geo_type), "ccx.geometry.unsupported")))

    step_type = ana.get("step_type", "Static")
    if step_type not in _SUPPORTED_STEP_TYPES:
        blockers.append(_limit(
            "analysis.step_type", str(step_type),
            _STEP_KEYS.get(str(step_type), "ccx.step.unsupported")))

    if ana.get("nlgeom"):
        blockers.append(_limit("analysis.nlgeom", "true", "ccx.step.nlgeom"))

    if (ana.get("adaptive_mesh") or {}).get("enabled"):
        blockers.append(_limit(
            "analysis.adaptive_mesh.enabled", "true", "ccx.step.adaptive_mesh"))

    if str(ana.get("mp_mode", "threads")).lower() == "mpi":
        # No howto suffix: this one is fixable without installing anything.
        blockers.append(_limit(
            "analysis.mp_mode", "mpi", "ccx.runner.no_mpi", howto=False))

    if spec.get("parametric", {}).get("parameters"):
        blockers.append(_limit(
            "parametric.parameters", "present", "ccx.step.parametric_sweep"))

    load_type = bc.get("load_type")
    if load_type and load_type not in _SUPPORTED_LOAD_TYPES:
        blockers.append(_limit(
            "bc_load.load_type", str(load_type),
            _LOAD_KEYS.get(str(load_type), "ccx.load.unsupported")))
    if bc.get("thermal_bc"):
        blockers.append(_limit(
            "bc_load.thermal_bc", "present", "ccx.load.thermal_bc"))

    for mat_field, key in _MATERIAL_KEYS:
        if mat.get(mat_field) is not None:
            blockers.append(_limit(
                "material.%s" % mat_field, str(mat.get(mat_field)), key))
    if spec.get("materials"):
        blockers.append(_limit(
            "materials", "multi-material", "ccx.material.multi_material"))

    for idx, kpi in enumerate(outputs.get("kpis", []) or []):
        kind = kpi.get("type")
        name = kpi.get("name", "kpi[%d]" % idx)
        location = str(kpi.get("location") or "").split(":", 1)[-1].strip().lower()
        if kind not in _SUPPORTED_KPI_TYPES:
            blockers.append(_limit(
                "outputs.kpis[%s].type" % name, str(kind),
                _KPI_KEYS.get(str(kind), "ccx.kpi.unsupported")))
        elif (kind in ("field_max", "derived_stress_concentration")
              and location and location not in ("whole_model", "all")):
            # Refuse BEFORE the solve, not at extraction: these KPIs read the
            # .frd field blocks, which are whole-model only. Letting the run
            # proceed would burn a real solve and then fail at the last stage
            # (post/extract_kpis_ccx.py has the same guard as belt-and-braces).
            blockers.append(_limit(
                "outputs.kpis[%s].location" % name, str(kpi.get("location")),
                "ccx.kpi.location_whole_model_only"))
        elif kind in _CAVEAT_KPI_TYPES:
            caveats.append(_limit(
                "outputs.kpis[%s].type" % name, str(kind),
                "ccx.kpi.stress_not_comparable", kind="caveat", howto=False))

    if geo_type == "custom_inp":
        caveats.append(_limit(
            "geometry.type", "custom_inp", "ccx.custom_inp.flattened",
            kind="caveat", howto=False))

    return blockers, caveats


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

def select_backend(
    spec: dict | None = None,
    *,
    abaqus_available: bool | None = None,
    calculix_available: bool | None = None,
    override: str | None = None,
) -> BackendDecision:
    """Pick the backend for this spec.

    Precedence: explicit ``override`` > ``ABAQUS_AGENT_SOLVER_BACKEND`` env >
    auto (Abaqus, then CalculiX, then demo). Abaqus always wins in auto mode;
    there is no user-facing switch that demotes a working Abaqus by accident.

    An explicit override naming an absent solver comes back as that backend
    WITH a blocker — it fails loudly instead of quietly dropping to demo mode.
    """
    spec = spec or {}
    if abaqus_available is None:
        abaqus_available = check_abaqus_available()
    if calculix_available is None:
        calculix_available = check_calculix()

    requested = (override or "").strip().lower() or None
    source = "runner_cfg" if requested else "auto"
    if not requested:
        env_value = os.environ.get(ENV_BACKEND, "").strip().lower()
        if env_value and env_value != "auto":
            requested = env_value
            source = "env"

    if requested and requested not in (BACKEND_ABAQUS, BACKEND_CALCULIX, BACKEND_DEMO):
        return BackendDecision(
            backend=BACKEND_DEMO,
            label=backend_label(BACKEND_DEMO, None),
            reason=messages.render("backend.select.bad_env_value", "zh",
                                   env=ENV_BACKEND, value=requested),
            reason_key="backend.select.bad_env_value",
            reason_params={"env": ENV_BACKEND, "value": str(requested)},
            source=source,
            blockers=(_limit(ENV_BACKEND, str(requested),
                             "backend.select.bad_env_hint", howto=False),),
        )

    if requested == BACKEND_DEMO:
        return BackendDecision(
            backend=BACKEND_DEMO, label=backend_label(BACKEND_DEMO, None),
            reason=messages.render("backend.select.demo_requested", "zh"),
            reason_key="backend.select.demo_requested", source=source,
        )

    if requested == BACKEND_ABAQUS or (not requested and abaqus_available):
        if not abaqus_available:
            return BackendDecision(
                backend=BACKEND_ABAQUS, label=backend_label(BACKEND_ABAQUS, None),
                reason=messages.render("backend.select.abaqus_requested_missing", "zh"),
                reason_key="backend.select.abaqus_requested_missing", source=source,
                blockers=(_limit(ENV_BACKEND, BACKEND_ABAQUS,
                                 "backend.select.abaqus_not_found",
                                 howto=False, env=ENV_ABAQUS_CMD),),
            )
        release = detect_abaqus_release()
        reason_key = ("backend.select.abaqus_auto" if source == "auto"
                      else "backend.select.abaqus_explicit")
        return BackendDecision(
            backend=BACKEND_ABAQUS,
            label=backend_label(BACKEND_ABAQUS, release),
            reason=messages.render(reason_key, "zh"),
            reason_key=reason_key,
            source=source, version=release,
        )

    if requested == BACKEND_CALCULIX or (not requested and calculix_available):
        if not calculix_available:
            return BackendDecision(
                backend=BACKEND_CALCULIX, label=backend_label(BACKEND_CALCULIX, None),
                reason=messages.render("backend.select.calculix_requested_missing", "zh"),
                reason_key="backend.select.calculix_requested_missing", source=source,
                blockers=(_limit(ENV_BACKEND, BACKEND_CALCULIX,
                                 "backend.select.calculix_not_found",
                                 howto=False, env=ENV_CCX_EXE),),
            )
        version = detect_ccx_version()
        blockers, caveats = calculix_capability(spec)
        if version is None:
            blockers = [_limit("calculix.version", "unknown",
                               "backend.select.calculix_no_version",
                               howto=False)] + blockers
        reason_key = ("backend.select.calculix_fallback" if source == "auto"
                      else "backend.select.calculix_explicit")
        return BackendDecision(
            backend=BACKEND_CALCULIX,
            label=backend_label(BACKEND_CALCULIX, version),
            reason=messages.render(reason_key, "zh"), reason_key=reason_key,
            source=source, version=version,
            blockers=tuple(blockers), caveats=tuple(caveats),
        )

    return BackendDecision(
        backend=BACKEND_DEMO, label=backend_label(BACKEND_DEMO, None),
        reason=messages.render("backend.select.no_solver", "zh"),
        reason_key="backend.select.no_solver", source=source,
    )


def refusal_messages(decision: BackendDecision,
                     lang: str | None = None) -> list[str]:
    """Plain-language refusal lines for the console / UI / API error payload."""
    lang = messages.resolve_lang(lang)
    # The separator is part of the sentence, so it has to follow the language:
    # a full-width colon in an English refusal reads as a typo.
    sep = "：" if lang == "zh" else ": "
    return ["%s = %s%s%s" % (b.feature, b.value, sep, b.localized(lang))
            for b in decision.blockers]
