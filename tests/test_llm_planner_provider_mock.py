"""Mocked LLM provider path tests.

These tests verify provider adapter plumbing without installing provider SDKs,
using real API keys, or making network calls.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _cantilever_spec() -> dict:
    return yaml.safe_load((ROOT / "cases" / "cantilever" / "spec.yaml").read_text())


def test_openai_adapter_extracts_message_content(monkeypatch: pytest.MonkeyPatch) -> None:
    from agent.llm_planner import LLMPlanner

    calls = {}

    class FakeCompletions:
        def create(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="meta:\n  model_name: Mock\n")
                    )
                ]
            )

    class FakeOpenAI:
        def __init__(self, api_key: str):
            calls["api_key"] = api_key
            self.chat = SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))

    planner = LLMPlanner(backend="openai")
    assert planner._call_openai("prompt").startswith("meta:")
    assert calls["api_key"] == "test-openai-key"
    assert calls["request"]["model"] == "gpt-4o"
    assert calls["request"]["messages"] == [{"role": "user", "content": "prompt"}]


def test_anthropic_adapter_extracts_text_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agent.llm_planner import LLMPlanner

    calls = {}

    class FakeAnthropicClient:
        def __init__(self, api_key: str):
            calls["api_key"] = api_key
            self.messages = self

        def create(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(content=[SimpleNamespace(text="meta:\n  model_name: Mock\n")])

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setitem(
        sys.modules,
        "anthropic",
        SimpleNamespace(Anthropic=FakeAnthropicClient),
    )

    planner = LLMPlanner(backend="anthropic")
    assert planner._call_anthropic("prompt").startswith("meta:")
    assert calls["api_key"] == "test-anthropic-key"
    assert calls["request"]["model"] == "claude-sonnet-4-6"
    assert calls["request"]["messages"] == [{"role": "user", "content": "prompt"}]


async def _run_generate_spec_async_env_restore(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.llm_planner
    from core.spec_generator import generate_spec_async

    spec = _cantilever_spec()
    seen_keys = []

    class FakePlanner:
        def __init__(self, backend: str):
            assert backend == "openai"
            seen_keys.append(os.environ.get("OPENAI_API_KEY"))

        def generate(self, text: str):
            assert text == "mock prompt"
            return spec, []

    monkeypatch.setenv("OPENAI_API_KEY", "original-key")
    monkeypatch.setattr(agent.llm_planner, "LLMPlanner", FakePlanner)

    generated, missing = await generate_spec_async(
        "mock prompt",
        "2024",
        "openai",
        openai_key="temporary-key",
    )

    assert generated == spec
    assert missing == []
    assert seen_keys == ["temporary-key"]
    assert os.environ["OPENAI_API_KEY"] == "original-key"


def test_generate_spec_async_restores_openai_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_generate_spec_async_env_restore(monkeypatch))
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())
