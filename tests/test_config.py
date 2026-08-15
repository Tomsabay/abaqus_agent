"""Tests for core/config.py — the centralized runtime configuration.

Env is monkeypatched per case; values are read at call time so this works
without re-importing the module.
"""

from __future__ import annotations

from core import config


def _clear(monkeypatch):
    for name in (
        config.ENV_DATA_DIR, config.ENV_PORT, config.ENV_HOST, config.ENV_DEV,
        config.ENV_ABAQUS_CMD, config.ENV_RUN_ROOT,
        config.ENV_WORKBENCH_SESSION_DIR, config.ENV_COPILOT_SESSION_DIR,
    ):
        monkeypatch.delenv(name, raising=False)


def test_dev_mode_defaults(monkeypatch):
    _clear(monkeypatch)
    assert config.is_dev() is True
    assert config.is_packaged() is False
    # Loopback even in dev: the server has no auth and can start solver jobs,
    # so a source checkout must not be reachable from the LAN by default.
    assert config.host() == "127.0.0.1"
    assert config.port() == 8000
    assert config.data_dir() is None
    assert config.run_root() is None
    assert config.abaqus_cmd_override() is None
    # dev session dirs stay repo-local
    assert config.workbench_session_dir() == config.REPO_ROOT / "artifacts" / "workbench_sessions"


def test_packaged_mode_redirects(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path))
    assert config.is_packaged() is True
    assert config.is_dev() is False
    assert config.host() == "127.0.0.1"
    assert config.data_dir() == tmp_path
    assert config.workbench_session_dir() == tmp_path / "workbench_sessions"
    assert config.copilot_session_dir() == tmp_path / "copilot_sessions"
    assert config.run_root() == tmp_path / "runs"


def test_dev_override_forces_off(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_DEV, "0")
    assert config.is_dev() is False
    assert config.host() == "127.0.0.1"


def test_dev_override_forces_on_even_when_packaged(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path))
    monkeypatch.setenv(config.ENV_DEV, "1")
    assert config.is_dev() is True
    assert config.host() == "127.0.0.1"


def test_host_override_is_the_only_way_to_leave_loopback(monkeypatch):
    """Exposing the API to the network stays possible, but has to be asked for."""
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_HOST, "0.0.0.0")
    assert config.host() == "0.0.0.0"


def test_port_override(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_PORT, "9123")
    assert config.port() == 9123


def test_port_invalid_falls_back(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_PORT, "not-a-port")
    assert config.port() == 8000


def test_explicit_session_dir_overrides_packaged(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path))
    custom = tmp_path / "custom_wb"
    monkeypatch.setenv(config.ENV_WORKBENCH_SESSION_DIR, str(custom))
    assert config.workbench_session_dir() == custom


def test_abaqus_cmd_override(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_ABAQUS_CMD, r"C:\SIMULIA\Commands\abaqus.bat")
    assert config.abaqus_cmd_override() == r"C:\SIMULIA\Commands\abaqus.bat"


def test_run_root_explicit_override(monkeypatch, tmp_path):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_RUN_ROOT, str(tmp_path / "myruns"))
    assert config.run_root() == tmp_path / "myruns"


def test_blank_env_treated_as_unset(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(config.ENV_DATA_DIR, "   ")
    assert config.data_dir() is None
    assert config.is_packaged() is False


def _fake_frozen(monkeypatch):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config.sys, "_MEIPASS", "/tmp/_MEI", raising=False)


def test_frozen_defaults_off_dev_and_user_data_dir(monkeypatch):
    _clear(monkeypatch)
    _fake_frozen(monkeypatch)
    assert config.is_frozen() is True
    # frozen with no explicit data dir must NOT be dev, and must resolve a real
    # user data dir (not the _MEIPASS temp extraction root).
    assert config.is_dev() is False
    dd = config.data_dir()
    assert dd is not None
    assert "AbaqusAgent" in str(dd)
    assert config.is_packaged() is True


def test_frozen_explicit_data_dir_wins(monkeypatch, tmp_path):
    _clear(monkeypatch)
    _fake_frozen(monkeypatch)
    monkeypatch.setenv(config.ENV_DATA_DIR, str(tmp_path))
    assert config.data_dir() == tmp_path


def test_frozen_dev_override_still_respected(monkeypatch):
    _clear(monkeypatch)
    _fake_frozen(monkeypatch)
    monkeypatch.setenv(config.ENV_DEV, "1")
    assert config.is_dev() is True
