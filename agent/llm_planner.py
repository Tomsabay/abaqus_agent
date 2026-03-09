"""
llm_planner.py
--------------
LLM-powered planner: natural language → Problem Spec YAML.

Supports OpenAI (GPT-4o) and Anthropic (Claude) backends.
Falls back to template-based generation if no API key is set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from tools.errors import AbaqusAgentError, ErrorCode
from tools.schema_validator import validate_spec

PROMPT_DIR = Path(__file__).parent.parent / "prompts"


class LLMPlanner:
    """
    Converts natural language FEA requests to Problem Spec YAML.

    Usage
    -----
    planner = LLMPlanner(backend="anthropic")  # or "openai", "template"
    spec_yaml = planner.generate("一个100mm悬臂梁，承受1MPa端部压力，输出梁端挠度")
    """

    def __init__(self, backend: str = "auto"):
        """
        Parameters
        ----------
        backend : "openai" | "anthropic" | "template" | "auto"
            "auto" picks the first backend with available API key.
        """
        self.backend = self._resolve_backend(backend)
        self.prompt_template = (PROMPT_DIR / "spec_generator.txt").read_text(encoding="utf-8")

    def generate(self, user_text: str) -> tuple[dict, list[str]]:
        """
        Generate a Problem Spec from natural language.

        Returns
        -------
        (spec: dict, missing_questions: list[str])
        """
        prompt = self.prompt_template.replace("{USER_TEXT}", user_text)

        if self.backend == "template":
            return self._template_fallback(user_text)

        raw_yaml = self._call_llm(prompt)

        try:
            spec = yaml.safe_load(raw_yaml)
        except yaml.YAMLError as e:
            raise AbaqusAgentError(
                ErrorCode.LLM_GENERATION_FAILED,
                f"LLM returned invalid YAML: {e}\n\nOutput:\n{raw_yaml[:500]}",
            )

        valid, errors = validate_spec(spec)
        if not valid:
            raise AbaqusAgentError(
                ErrorCode.SPEC_INVALID,
                f"Generated spec failed validation: {errors}",
            )

        missing = spec.get("meta", {}).get("missing_questions", [])
        return spec, missing

    def _call_llm(self, prompt: str) -> str:
        if self.backend == "openai":
            return self._call_openai(prompt)
        elif self.backend == "anthropic":
            return self._call_anthropic(prompt)
        raise AbaqusAgentError(ErrorCode.LLM_GENERATION_FAILED, f"Unknown backend: {self.backend}")

    def _call_openai(self, prompt: str) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise AbaqusAgentError(
                ErrorCode.LLM_GENERATION_FAILED,
                "openai package not installed. Run: pip install openai",
            )
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=2000,
        )
        return response.choices[0].message.content.strip()

    def _call_anthropic(self, prompt: str) -> str:
        try:
            import anthropic
        except ImportError:
            raise AbaqusAgentError(
                ErrorCode.LLM_GENERATION_FAILED,
                "anthropic package not installed. Run: pip install anthropic",
            )
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()

    def _template_fallback(self, user_text: str) -> tuple[dict, list[str]]:
        """Return a default cantilever spec with missing questions."""
        spec = {
            "meta": {
                "abaqus_release": "2024",
                "model_name": "DefaultModel",
                "units": "mm_MPa_t",
                "description": user_text[:100],
                "missing_questions": [
                    "What are the dimensions (L × W × H)?",
                    "What material should be used?",
                    "What type of analysis (static/modal/dynamic)?",
                    "What boundary conditions and loads apply?",
                    "What KPIs should be extracted?",
                ],
            },
            "geometry": {"type": "cantilever_block", "L": 100.0, "W": 10.0, "H": 10.0},
            "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
            "analysis": {"solver": "standard", "step_type": "Static", "cpus": 1},
            "bc_load": {"fixed_face": "x=0", "load_face": "x=L", "load_type": "pressure", "value": -1.0},
            "outputs": {"kpis": [{"name": "U_tip", "type": "nodal_displacement", "location": "tip_center"}]},
        }
        return spec, spec["meta"]["missing_questions"]

    @staticmethod
    def _resolve_backend(backend: str) -> str:
        if backend != "auto":
            return backend
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "anthropic"
        if os.environ.get("OPENAI_API_KEY"):
            return "openai"
        return "template"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "悬臂梁静力分析"
    planner = LLMPlanner()
    spec, questions = planner.generate(text)
    print("# Generated Spec")
    print(yaml.dump(spec, allow_unicode=True, default_flow_style=False))
    if questions:
        print("# Missing information:")
        for q in questions:
            print(f"  - {q}")
