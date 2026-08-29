"""
core/spec_generator.py
----------------------
Spec generation logic extracted from server.py.
"""
from __future__ import annotations

import copy
import os

# The quarter-symmetry plate the "hole" keyword swaps in: 100 x 50 with a 10 mm
# quarter hole at the origin, plane stress. Drawn entity by entity because the
# named ops draw rectangles and circles, and this outline is four lines and an
# arc. The same geometry reproduces the frozen plate_hole baseline exactly.
_QUARTER_PLATE_WITH_HOLE = {
    "name": "Plate",
    "dimensionality": "TWO_D_PLANAR",
    "features": [
        {"op": "sketch", "id": "profile", "entities": [
            {"call": "Line", "point1": [10.0, 0.0], "point2": [100.0, 0.0]},
            {"call": "Line", "point1": [100.0, 0.0], "point2": [100.0, 50.0]},
            {"call": "Line", "point1": [100.0, 50.0], "point2": [0.0, 50.0]},
            {"call": "Line", "point1": [0.0, 50.0], "point2": [0.0, 10.0]},
            {"call": "ArcByCenterEnds", "center": [0.0, 0.0],
             "point1": [0.0, 10.0], "point2": [10.0, 0.0],
             "direction": "CLOCKWISE"},
        ]},
        {"call": "BaseShell", "sketch": {"sketch": "profile"}},
    ],
    "section": {"type": "solid", "material": "Steel", "thickness": 1.0},
    "mesh": {"seed": 3.0, "element": "CPS4"},
    "expect": {"area": 4921.4602, "faces": 1},
}

# Quarter symmetry is the whole reason the model is a quarter: without both
# planes held, the plate translates instead of stretching.
_QUARTER_PLATE_CONDITIONS = (
    {"call": "XsymmBC", "name": {"literal": "SymX"},
     "createStepName": {"literal": "Initial"},
     "region": {"set": "PH-1:edge@x=min", "name": "SYM_X", "expect": "=1"}},
    {"call": "YsymmBC", "name": {"literal": "SymY"},
     "createStepName": {"literal": "Initial"},
     "region": {"set": "PH-1:edge@y=min", "name": "SYM_Y", "expect": "=1"}},
    # Negative pressure is tension: Abaqus pressure is positive INTO the face.
    {"call": "Pressure", "name": {"literal": "Load-1"},
     "createStepName": {"literal": "Step-1"},
     "region": {"surface": "PH-1:edge@x=max", "name": "LOAD_SURF",
                "expect": "=1"},
     "magnitude": -100.0, "distributionType": "UNIFORM"},
)


async def generate_spec_async(
    text: str, release: str, backend: str,
    anthropic_key: str = "", openai_key: str = "", deepseek_key: str = "",
) -> tuple[dict, list]:
    """Generate spec from NL text, using LLM or template."""
    if backend in ("anthropic", "openai", "deepseek"):
        from agent.llm_planner import LLMPlanner
        env_backup = {}
        if backend == "anthropic" and anthropic_key:
            env_backup["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "")
            os.environ["ANTHROPIC_API_KEY"] = anthropic_key
        elif backend == "openai" and openai_key:
            env_backup["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
            os.environ["OPENAI_API_KEY"] = openai_key
        elif backend == "deepseek" and deepseek_key:
            env_backup["DEEPSEEK_API_KEY"] = os.environ.get("DEEPSEEK_API_KEY", "")
            os.environ["DEEPSEEK_API_KEY"] = deepseek_key
        try:
            # Only the CALL is allowed to fall through. It fails when there is
            # no key, no package or no network -- the model never answered, and
            # a template is a fair answer to that.
            #
            # `parse` is deliberately outside: it fails when the model DID
            # answer and the answer was rejected. Swallowing that used to hand
            # back the default cantilever below, reported as valid, to someone
            # who asked for two plates tied together -- the request was dropped
            # and nothing said so. The refusal names the spec key that is wrong,
            # which is the only thing here that helps.
            raw = None
            try:
                planner = LLMPlanner(backend=backend)
                raw = planner.call(text)
            except Exception:
                raw = None
            if raw is not None:
                return planner.parse(raw)
        finally:
            for k, v in env_backup.items():
                if v:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)

    # Template-based generation
    from agent.llm_planner import LLMPlanner
    planner = LLMPlanner(backend="template")
    spec, missing = planner.generate(text)
    spec["meta"]["abaqus_release"] = release
    # Enrich spec from text keywords. In v2 an analysis TYPE is the step's own
    # method name, so what these swap is the step call, not a `step_type` field.
    t = text.lower()
    if "\u5b54" in t or "hole" in t:
        spec["meta"]["model_name"] = "PlateWithHole"
        # Deep copies: the explicit branch below rewrites part["mesh"], and the
        # templates are module constants shared by every call.
        spec["parts"] = [copy.deepcopy(_QUARTER_PLATE_WITH_HOLE)]
        spec["assembly"] = {"instances": [{"name": "PH-1", "part": "Plate",
                                           "translate": [0.0, 0.0, 0.0]}]}
        spec["conditions"] = copy.deepcopy(list(_QUARTER_PLATE_CONDITIONS))
        spec["outputs"]["kpis"] = [
            {"name": "MISES_MAX", "type": "field_max", "location": "whole_model",
             "invariant": "MISES"},
        ]
    if "\u6a21\u6001" in t or "\u9891\u7387" in t or "freq" in t:
        spec["steps"] = [{"call": "FrequencyStep", "name": {"literal": "Step-1"},
                          "previous": {"literal": "Initial"}, "numEigen": 6}]
        # A modal analysis with no density solves for the frequencies of a
        # massless body, which Abaqus will happily attempt.
        spec["material"]["density"] = 7.85e-9
        # Eigenvalue extraction takes no load, and a load left on one is not an
        # error Abaqus reports \u2014 it is simply ignored.
        spec["conditions"] = [c for c in spec.get("conditions", [])
                              if str(c.get("call", "")).endswith("BC")]
        spec["outputs"]["kpis"] = [
            {"name": "freq_1", "type": "eigenfrequency", "location": "mode_1"},
            {"name": "freq_2", "type": "eigenfrequency", "location": "mode_2"},
        ]
        spec["outputs"]["field_variables"] = ["U"]
    if "\u663e\u5f0f" in t or "\u51b2\u51fb" in t or "explicit" in t:
        spec["steps"] = [{"call": "ExplicitDynamicsStep",
                          "name": {"literal": "Step-1"},
                          "previous": {"literal": "Initial"},
                          "timePeriod": 1.0e-4}]
        spec["material"]["density"] = 7.85e-9
        for part in spec.get("parts", []):
            mesh = part.get("mesh")
            if not mesh:
                continue
            # C3D8I is a Standard-library element and has no Explicit
            # counterpart, so an explicit step cannot keep the default above.
            if str(mesh.get("element", "")).endswith("I"):
                mesh["element"] = "C3D8R"
                mesh["hourglass_control"] = "ENHANCED"
    return spec, missing
