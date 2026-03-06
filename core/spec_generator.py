"""
core/spec_generator.py
----------------------
Spec generation logic extracted from server.py.
"""
from __future__ import annotations

import os


async def generate_spec_async(
    text: str, release: str, backend: str,
    anthropic_key: str = "", openai_key: str = "",
) -> tuple[dict, list]:
    """Generate spec from NL text, using LLM or template."""
    if backend in ("anthropic", "openai"):
        try:
            from agent.llm_planner import LLMPlanner
            env_backup = {}
            if backend == "anthropic" and anthropic_key:
                env_backup["ANTHROPIC_API_KEY"] = os.environ.get("ANTHROPIC_API_KEY", "")
                os.environ["ANTHROPIC_API_KEY"] = anthropic_key
            elif backend == "openai" and openai_key:
                env_backup["OPENAI_API_KEY"] = os.environ.get("OPENAI_API_KEY", "")
                os.environ["OPENAI_API_KEY"] = openai_key
            try:
                planner = LLMPlanner(backend=backend)
                return planner.generate(text)
            finally:
                for k, v in env_backup.items():
                    if v:
                        os.environ[k] = v
                    else:
                        os.environ.pop(k, None)
        except Exception:
            pass  # fall through to template

    # Template-based generation
    from agent.llm_planner import LLMPlanner
    planner = LLMPlanner(backend="template")
    spec, missing = planner.generate(text)
    spec["meta"]["abaqus_release"] = release
    # Enrich spec from text keywords
    t = text.lower()
    if "\u5b54" in t or "hole" in t:
        spec["geometry"]["type"] = "plate_with_hole"
        spec["meta"]["model_name"] = "PlateWithHole"
    if "\u6a21\u6001" in t or "\u9891\u7387" in t or "freq" in t:
        spec["analysis"]["step_type"] = "Frequency"
        spec["analysis"]["solver"] = "standard"
        spec["material"]["density"] = 7.85e-9
        spec["outputs"]["kpis"] = [
            {"name": "freq_1", "type": "eigenfrequency", "location": "mode_1"},
            {"name": "freq_2", "type": "eigenfrequency", "location": "mode_2"},
        ]
    if "\u663e\u5f0f" in t or "\u51b2\u51fb" in t or "explicit" in t:
        spec["analysis"]["step_type"] = "Dynamic_Explicit"
        spec["analysis"]["solver"] = "explicit"
        spec["material"]["density"] = 7.85e-9
    return spec, missing
