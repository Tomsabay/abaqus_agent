"""
llm_planner.py
--------------
LLM-powered planner: natural language → Problem Spec YAML.

Supports OpenAI (GPT-4o), Anthropic (Claude) and DeepSeek backends.
Falls back to template-based generation if no API key is set.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

from tools.abaqus_cmd import detect_abaqus_release
from tools.errors import AbaqusAgentError, ErrorCode
from tools.schema_validator import validate_spec

PROMPT_DIR = Path(__file__).parent.parent / "prompts"

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
# deepseek-v4-pro over -flash: this prompt asks for a whole modelling plan in
# one shot, which is the reasoning-heavy end of what the two are for.
DEEPSEEK_MODEL = "deepseek-v4-pro"
# max_tokens covers REASONING plus the answer on v4: measured on the round-4
# gear-shaft ask, the model spent all 8000 of the old budget thinking
# (reasoning_content 29113 chars, finish_reason "length") and returned zero
# chars of content -- and one retry of the same ask burned through 32000 the
# same way. Billing follows what is generated, not this cap, so the only cost
# of headroom is worst-case latency; the documented model ceiling is 384K.
DEEPSEEK_MAX_TOKENS = 65536


def _relative_file_args(node) -> bool:
    """True if any ``{file:}`` in the spec is a path nothing here can resolve.

    `{file:}` is resolved against the directory the spec FILE lives in, and this
    spec has never been written to one. An absolute path still resolves, so only
    the relative ones are undecidable.
    """
    if isinstance(node, dict):
        raw = node.get("file")
        if isinstance(raw, str) and raw.strip() and not Path(raw).is_absolute():
            return True
        return any(_relative_file_args(v) for v in node.values())
    if isinstance(node, list):
        return any(_relative_file_args(v) for v in node)
    return False


def _dry_build_notes(spec: dict) -> list[str]:
    """Compile the spec the model wrote, and refuse here if it will not build.

    Schema validation is the weaker of the two checks and it is the only one
    that used to run. Everything the builder learned to refuse across #45-#71 --
    a partition whose section assignment is overwritten, an import that states
    no count, a seam nothing checks, a step chain that runs backwards -- passes
    the schema. Caught here, the model's mistake is reported in the builder's
    own words, which name the spec key; caught later it is a traceback from a
    CAE kernel, after a licence has been taken.

    Returns notes for the caller's `missing_questions`, and raises when the spec
    is one the builder will not compile.
    """
    from runner.build_model import _is_v2

    if not _is_v2(spec):
        return []
    if _relative_file_args(spec):
        return ["这份 spec 用了相对路径的 {file:}，它是相对 spec 文件所在目录解析的，"
                "而这份 spec 还没落盘——所以这里没有替你试建模型脚本。"
                "存盘后再跑一次校验，或者把路径写成绝对路径。"]

    from runner.build_v2 import SpecError, generate_script
    try:
        generate_script(spec)
    except SpecError as e:
        raise AbaqusAgentError(
            ErrorCode.SPEC_INVALID,
            f"Generated spec passed the schema and the model builder refused "
            f"it: {e}")
    return []


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
        backend : "openai" | "anthropic" | "deepseek" | "template" | "auto"
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
        if self.backend == "template":
            return self._template_fallback(user_text)
        return self.parse(self.call(user_text))

    def call(self, user_text: str) -> str:
        """Render the prompt, ask the backend, return its raw text.

        Split out from `generate` so a caller can tell the two kinds of failure
        apart. Everything that can go wrong HERE went wrong before the model
        said anything -- no key, package not installed, the API refused -- and
        falling back to a template is a reasonable answer to that. Everything
        that goes wrong in `parse` went wrong AFTER it answered, and there
        substituting a template silently answers a different question than the
        one that was asked (core/spec_generator.py).
        """
        return self._call_llm(self.prompt_template.replace("{USER_TEXT}", user_text))

    def parse(self, raw_yaml: str) -> tuple[dict, list[str]]:
        """Load, validate and dry-build what the model returned."""
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

        missing = list(spec.get("meta", {}).get("missing_questions", []) or [])
        missing.extend(_dry_build_notes(spec))
        return spec, missing

    def _call_llm(self, prompt: str) -> str:
        if self.backend == "openai":
            return self._call_openai(prompt)
        elif self.backend == "anthropic":
            return self._call_anthropic(prompt)
        elif self.backend == "deepseek":
            return self._call_deepseek(prompt)
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

    def _call_deepseek(self, prompt: str) -> str:
        """DeepSeek through the OpenAI SDK, which is what DeepSeek documents.

        The model name is a constant here and NOT `deepseek-chat`, because
        `deepseek-chat` and `deepseek-reasoner` are aliases DeepSeek began
        retiring on 2026-07-24; during the transition they point at
        deepseek-v4-flash's non-thinking and thinking modes. Writing an alias
        into a released tool means the tool changes behaviour on someone else's
        schedule, so the real id is written and the override is an env var.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise AbaqusAgentError(
                ErrorCode.LLM_GENERATION_FAILED,
                "openai package not installed (DeepSeek speaks the OpenAI "
                'protocol). Run: pip install -e ".[llm]"',
            )
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise AbaqusAgentError(
                ErrorCode.LLM_GENERATION_FAILED,
                "DEEPSEEK_API_KEY is not set.",
            )
        client = OpenAI(api_key=key, base_url=DEEPSEEK_BASE_URL)
        response = client.chat.completions.create(
            model=os.environ.get("ABAQUS_AGENT_DEEPSEEK_MODEL", DEEPSEEK_MODEL),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=int(os.environ.get("ABAQUS_AGENT_DEEPSEEK_MAX_TOKENS",
                                          DEEPSEEK_MAX_TOKENS)),
        )
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        # A thinking model that runs out of budget returns EMPTY content with
        # finish_reason "length" -- the tokens all went to reasoning. Passing
        # "" along yaml-loads to None and surfaces as a schema error about the
        # whole spec being None, which points the user at their own request
        # instead of at this knob.
        if choice.finish_reason == "length" or not text:
            raise AbaqusAgentError(
                ErrorCode.LLM_GENERATION_FAILED,
                "DeepSeek ran out of output budget before writing the spec "
                "(finish_reason=%r, %d chars of answer): the v4 models spend "
                "max_tokens on reasoning first. Raise "
                "ABAQUS_AGENT_DEEPSEEK_MAX_TOKENS (current %s) or simplify "
                "the request." % (
                    choice.finish_reason, len(text),
                    os.environ.get("ABAQUS_AGENT_DEEPSEEK_MAX_TOKENS",
                                   DEEPSEEK_MAX_TOKENS)))
        return text

    def _template_fallback(self, user_text: str) -> tuple[dict, list[str]]:
        """Return a default cantilever spec with missing questions.

        v2, like everything else written from scratch. This is what a machine
        with no API key gets, so it is also the dialect a first-time reader
        sees first — and a placeholder that demonstrated the frozen dialect
        would teach the one thing the planner is now told never to write.
        """
        spec = {
            "meta": {
                "abaqus_release": detect_abaqus_release() or "unknown",
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
            "material": {"name": "Steel", "E": 210000.0, "nu": 0.3},
            "parts": [{
                "name": "Beam",
                "features": [
                    {"op": "sketch", "id": "profile", "plane": "XY",
                     "profile": {"rect": {"corner1": [0.0, 0.0],
                                          "corner2": [10.0, 10.0]}}},
                    {"op": "extrude", "sketch": "profile", "depth": 100.0},
                ],
                "section": {"type": "solid", "material": "Steel"},
                # Not the C3D8R default: one element through a 10 mm thickness
                # measures 92x the closed form on exactly this bar.
                "mesh": {"seed": 5.0, "element": "C3D8I"},
                "expect": {"volume": 10000.0, "cells": 1},
            }],
            "assembly": {"instances": [{"name": "Beam-1", "part": "Beam",
                                        "translate": [0.0, 0.0, 0.0]}]},
            "steps": [{"call": "StaticStep", "name": {"literal": "Step-1"},
                       "previous": {"literal": "Initial"}}],
            "conditions": [
                {"call": "EncastreBC", "name": {"literal": "Fixed"},
                 "createStepName": {"literal": "Initial"},
                 "region": {"set": "Beam-1:face@z=min", "name": "FIXED_END",
                            "expect": "=1"}},
                # SurfaceTraction, not Pressure: an Abaqus pressure acts along
                # the surface NORMAL, so a "downward" load on the tip face is
                # axial compression and the bar never bends.
                {"call": "SurfaceTraction", "name": {"literal": "Load-1"},
                 "createStepName": {"literal": "Step-1"},
                 "region": {"surface": "Beam-1:face@z=max", "name": "LOAD_SURF",
                            "expect": "=1"},
                 "magnitude": 0.01,
                 "directionVector": [[0.0, 0.0, 0.0], [0.0, -1.0, 0.0]],
                 "distributionType": "UNIFORM", "traction": "GENERAL"},
            ],
            "outputs": {
                # field_min, not field_max: every U2 is negative under a
                # downward load, so a max returns the node closest to zero.
                "kpis": [{"name": "U_tip", "type": "field_min",
                          "component": "U2", "location": "whole_model"}],
                "field_variables": ["S", "E", "U", "RF"],
            },
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
        if os.environ.get("DEEPSEEK_API_KEY"):
            return "deepseek"
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
