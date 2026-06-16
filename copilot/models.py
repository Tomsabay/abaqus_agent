"""Typed action protocol for the Abaqus/CAE Copilot MVP."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AllowedAction = Literal[
    "create_cantilever_model",
    "apply_boundary_condition",
    "submit_job_or_prepare_run",
]


class CopilotAction(BaseModel):
    action: AllowedAction
    title: str
    rationale: str = ""
    params: dict[str, Any] = Field(default_factory=dict)
    abaqus_python: str = ""


class CopilotPlan(BaseModel):
    session_id: str
    backend: Literal["codex_app_server", "template"]
    intent: str
    user_summary: str
    model_type: str = "cantilever"
    needs_clarification: bool = False
    clarification_questions: list[str] = Field(default_factory=list)
    actions: list[CopilotAction]
    expected_outputs: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    assistant_message: str
    raw_assistant_text: str = ""


class CopilotExecutionResult(BaseModel):
    session_id: str
    status: Literal["prepared", "mock_executed", "real_bridge_pending"]
    bridge_mode: Literal["mock", "abaqus_plugin"]
    script_path: str
    timeline: list[dict[str, str]]
    user_visible_summary: str
    next_step: str
