"""Template planner must support both beam scenarios and parse dimensions safely."""

from __future__ import annotations

from pathlib import Path

from copilot.planner import build_copilot_plan, execute_plan


def _action(plan, name):
    return next(a for a in plan.actions if a.action == name)


def test_default_prompt_builds_cantilever_plan() -> None:
    plan = build_copilot_plan(
        "帮我建一个 200mm 长、20mm 高、20mm 宽的悬臂梁，左端固定，右端向下 100N",
        backend="template",
    )

    assert plan.model_type == "cantilever"
    bc = _action(plan, "apply_boundary_condition")
    assert bc.params["support"] == "cantilever"
    assert "EncastreBC" in bc.abaqus_python
    assert "RIGHT_LOAD_NODE" in bc.abaqus_python
    job = _action(plan, "submit_job_or_prepare_run")
    assert job.params["job_name"] == "Copilot_Cantilever_Job"
    # an aborted solve must raise (and reach the error/diagnosis loop), never
    # report COMPLETED with silent 0.0 KPIs — caught for real on 2026-07-05
    assert "if job_status != 'COMPLETED':" in job.abaqus_python
    assert "aborted" in job.abaqus_python


def test_simply_supported_keywords_switch_scenario() -> None:
    plan = build_copilot_plan(
        "做一个 300mm 长、30mm 高、20mm 宽的简支梁，跨中往下压 500N，看跨中挠度",
        backend="template",
    )

    assert plan.model_type == "simply_supported_beam"
    assert "简支" in plan.user_summary
    bc = _action(plan, "apply_boundary_condition")
    assert bc.params["support"] == "simply_supported"
    assert bc.params["force_n"] == 500.0
    assert "PinnedBC" in bc.abaqus_python
    assert "BC_Roller_Right" in bc.abaqus_python
    assert "MID_LOAD_NODE" in bc.abaqus_python
    assert "MIDSPAN_BOTTOM_NODE" in bc.abaqus_python
    assert "cf2=-500.000000" in bc.abaqus_python
    job = _action(plan, "submit_job_or_prepare_run")
    assert job.params["job_name"] == "Copilot_SimpleBeam_Job"
    # the dial-gauge KPI rides along in the shared extract script
    assert "midspan_deflection" in job.abaqus_python
    create = _action(plan, "create_cantilever_model")
    assert create.params["length_mm"] == 300.0
    assert create.params["height_mm"] == 30.0
    assert create.params["width_mm"] == 20.0
    assert "COPILOT_MODEL_NAME = 'Copilot_SimpleBeam'" in create.abaqus_python


def test_three_point_bend_keyword_also_triggers() -> None:
    plan = build_copilot_plan("帮我做一个三点弯试验的梁模型", backend="template")

    assert plan.model_type == "simply_supported_beam"


def test_force_number_is_not_mistaken_for_width() -> None:
    plan = build_copilot_plan(
        "帮我建一个 150mm 长、15mm 高的悬臂梁，右端向下 50N",
        backend="template",
    )

    create = _action(plan, "create_cantilever_model")
    # only two mm-suffixed numbers: width falls back to default, NOT 50 (the force)
    assert create.params["length_mm"] == 150.0
    assert create.params["height_mm"] == 15.0
    assert create.params["width_mm"] == 20.0
    bc = _action(plan, "apply_boundary_condition")
    assert bc.params["force_n"] == 50.0
    assert "cf2=-50.000000" in bc.abaqus_python


def test_execute_plan_renders_simply_supported_script() -> None:
    plan = build_copilot_plan("300mm 长的简支梁，跨中 200N", backend="template")

    execution = execute_plan(plan, bridge_mode="mock")

    script = Path(execution.script_path).read_text(encoding="utf-8")
    assert "PinnedBC" in script
    assert "MID_LOAD_NODE" in script
    assert "Copilot_SimpleBeam_Job" in script


def test_plate_with_hole_keywords_switch_scenario() -> None:
    plan = build_copilot_plan(
        "做一个 100mm 长、50mm 宽、5mm 厚的开孔板，孔径 10mm，右端拉 100MPa，看应力集中",
        backend="template",
    )

    assert plan.model_type == "plate_with_hole"
    assert "应力集中" in plan.user_summary or "开孔" in plan.user_summary
    create = _action(plan, "create_cantilever_model")
    assert create.params["hole_diameter_mm"] == 10.0
    assert create.params["length_mm"] == 100.0
    assert create.params["height_mm"] == 50.0
    assert create.params["width_mm"] == 5.0
    assert "COPILOT_MODEL_NAME = 'Copilot_PlateHole'" in create.abaqus_python
    assert "CircleByCenterPerimeter" in create.abaqus_python
    # unmeshable hex sweep must fall back to quadratic tets, not 0 elements
    assert "C3D10" in create.abaqus_python
    bc = _action(plan, "apply_boundary_condition")
    assert bc.params["support"] == "plate_with_hole"
    assert bc.params["tension_mpa"] == 100.0
    assert "Pressure" in bc.abaqus_python
    assert "COPILOT_TENSION = 100.000000" in bc.abaqus_python
    assert "BC_Left_U1" in bc.abaqus_python
    job = _action(plan, "submit_job_or_prepare_run")
    assert job.params["job_name"] == "Copilot_PlateHole_Job"
    # Kt rides along in the shared extract script when tension is defined
    assert "stress_concentration_kt" in job.abaqus_python


def test_plate_hole_defaults_without_explicit_hole_size() -> None:
    plan = build_copilot_plan("帮我做个带孔的板受拉分析", backend="template")

    create = _action(plan, "create_cantilever_model")
    # default plate 100x50x5 with hole = height/5
    assert create.params["hole_diameter_mm"] == 10.0
    bc = _action(plan, "apply_boundary_condition")
    assert bc.params["tension_mpa"] == 100.0


def test_execute_plan_renders_plate_hole_script() -> None:
    plan = build_copilot_plan("开孔板应力集中 200MPa", backend="template")

    execution = execute_plan(plan, bridge_mode="mock")

    script = Path(execution.script_path).read_text(encoding="utf-8")
    assert "CircleByCenterPerimeter" in script
    assert "COPILOT_TENSION = 200.000000" in script
    assert "magnitude=-COPILOT_TENSION" in script
    assert "Copilot_PlateHole_Job" in script


def test_modal_keywords_switch_scenario() -> None:
    plan = build_copilot_plan(
        "帮我做一个 200mm 长、20mm 高、20mm 宽悬臂梁的模态分析，看前几阶固有频率",
        backend="template",
    )

    assert plan.model_type == "cantilever_modal"
    create = _action(plan, "create_cantilever_model")
    assert create.params["analysis"] == "modal"
    assert "material.Density(table=((7.85e-09,),))" in create.abaqus_python
    assert "FrequencyStep(name='ModalStep', previous='Initial', numEigen=5)" in create.abaqus_python
    assert "StaticStep" not in create.abaqus_python
    bc = _action(plan, "apply_boundary_condition")
    assert bc.params["support"] == "cantilever_modal"
    assert "EncastreBC" in bc.abaqus_python
    assert "ConcentratedForce" not in bc.abaqus_python
    job = _action(plan, "submit_job_or_prepare_run")
    assert job.params["job_name"] == "Copilot_Modal_Job"
    assert "natural_frequencies_hz" in job.abaqus_python
    assert "frame, 'frequency'" in job.abaqus_python
    # the aborted-solve guard must protect modal jobs too
    assert "if job_status != 'COMPLETED':" in job.abaqus_python


def test_static_scenarios_keep_density_but_static_step() -> None:
    plan = build_copilot_plan("帮我建一个悬臂梁，右端 100N", backend="template")

    create = _action(plan, "create_cantilever_model")
    # density is harmless for statics and required the moment users switch to modal
    assert "material.Density" in create.abaqus_python
    assert "StaticStep(name='LoadStep'" in create.abaqus_python
    assert "FrequencyStep" not in create.abaqus_python


def test_cantilever_gets_tip_deflection_dial_gauge() -> None:
    plan = build_copilot_plan("帮我建一个悬臂梁，右端 100N", backend="template")

    bc = _action(plan, "apply_boundary_condition")
    assert "TIP_DEFLECTION_NODE" in bc.abaqus_python
    job = _action(plan, "submit_job_or_prepare_run")
    assert "tip_deflection" in job.abaqus_python


# ── name interpolation is an exec() boundary ─────────────────────────
#
# Everything _python_for_action returns is exec()'d by the Abaqus/CAE kernel,
# and _plan_from_payload builds each action straight out of Codex's JSON reply
# (`CopilotAction(**item)`), so any string field of that reply lands inside a
# quoted literal in generated Python. `model_name` was whitelisted from the
# start; `job_name` reached both submit templates unfiltered, where a single
# quote closes the literal.

import ast  # noqa: E402

from copilot.models import CopilotAction  # noqa: E402
from copilot.planner import _python_for_action, _safe_name  # noqa: E402

HOSTILE = "Job'; import os; os.system('calc') #"


def test_a_hostile_job_name_cannot_close_the_literal():
    action = CopilotAction(
        action="submit_job_or_prepare_run",
        title="submit",
        rationale="",
        params={"job_name": HOSTILE, "run_policy": "submit_and_extract"},
        abaqus_python="",
    )
    code = _python_for_action(action)

    assert "os.system" not in code
    safe = _safe_name(HOSTILE, "x")
    assert "'" not in safe and safe.startswith("Job_")
    assert f"COPILOT_JOB_NAME = '{safe}'" in code
    # The generated script must still be Python. Parsing it is the check that
    # actually proves the literal was never broken open -- an unbalanced quote
    # is a SyntaxError, not a subtle difference in a string.
    ast.parse(code)


def test_the_modal_template_is_guarded_too():
    action = CopilotAction(
        action="submit_job_or_prepare_run",
        title="submit",
        rationale="",
        params={"job_name": HOSTILE,
                "run_policy": "submit_and_extract_frequencies"},
        abaqus_python="",
    )
    code = _python_for_action(action)
    assert "os.system" not in code
    ast.parse(code)


def test_a_hostile_model_name_stays_guarded():
    action = CopilotAction(
        action="create_cantilever_model",
        title="create",
        rationale="",
        params={"model_name": HOSTILE, "length_mm": 200},
        abaqus_python="",
    )
    code = _python_for_action(action)
    assert "os.system" not in code
    ast.parse(code)


def test_an_empty_name_falls_back_rather_than_emitting_an_empty_literal():
    assert _safe_name("", "Copilot_Job") == "Copilot_Job"
    assert _safe_name(None, "Copilot_Job") == "Copilot_Job"
    # Not empty, but nothing survives the filter -- an empty literal would
    # make every downstream `NAME + '.odb'` open '.odb'.
    assert _safe_name("///", "Copilot_Job") == "___"


def test_a_normal_name_is_unchanged():
    assert _safe_name("Copilot_PlateHole_Job", "x") == "Copilot_PlateHole_Job"
