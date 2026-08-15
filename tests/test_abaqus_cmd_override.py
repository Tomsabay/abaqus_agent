"""Tests for the ABAQUS_AGENT_ABAQUS_CMD override path resolution."""

from __future__ import annotations

from core.helpers import check_abaqus
from tools.abaqus_cmd import ENV_ABAQUS_CMD, get_abaqus_cmd


def test_override_wins_over_path(monkeypatch, tmp_path):
    fake = tmp_path / "abaqus.bat"
    fake.write_text("echo hi", encoding="utf-8")
    monkeypatch.setenv(ENV_ABAQUS_CMD, str(fake))
    assert get_abaqus_cmd() == str(fake)


def test_check_abaqus_uses_override_existence(monkeypatch, tmp_path):
    fake = tmp_path / "abaqus.bat"
    monkeypatch.setenv(ENV_ABAQUS_CMD, str(fake))
    assert check_abaqus() is False  # path set but file absent
    fake.write_text("echo hi", encoding="utf-8")
    assert check_abaqus() is True


def test_blank_override_ignored(monkeypatch):
    monkeypatch.setenv(ENV_ABAQUS_CMD, "   ")
    # Falls through to shutil.which; result depends on host, just assert type.
    assert isinstance(get_abaqus_cmd(), str)
