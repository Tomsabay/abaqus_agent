"""Tests for the ODB animation export wrapper (hermetic, no Abaqus/ffmpeg)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from post import export_odb_animation_runner as runner
from post.export_odb_animation_runner import export_odb_animation


def test_export_returns_error_when_odb_missing(tmp_path):
    result = export_odb_animation(tmp_path / "missing.odb", workdir=tmp_path)

    assert result["frames"] == 0
    assert result["video"] is None
    assert "ODB not found" in result["errors"][0]


def test_export_passes_env_and_stitches_video(tmp_path, monkeypatch):
    odb = tmp_path / "model.odb"
    odb.write_text("fake odb\n", encoding="utf-8")
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["stdin"] is not None  # DEVNULL, never inherited pipe
        env = kwargs.get("env")
        if env is not None and "ABQ_ANIM_ODB" in env:
            # abaqus cae noGUI leg: emit frames into the requested out dir
            assert env["ABQ_ANIM_ODB"].endswith("model.odb")
            out_dir = Path(env["ABQ_ANIM_OUT"])
            out_dir.mkdir(parents=True, exist_ok=True)
            for i in range(3):
                (out_dir / ("frame_%04d.png" % i)).write_bytes(b"\x89PNG\r\n\x1a\n")
            return SimpleNamespace(stdout="ANIM_EXPORT_DONE: 3 frames", stderr="",
                                   returncode=0)
        # ffmpeg leg: produce the video at the workdir root
        Path(cmd[-1]).write_bytes(b"mp4")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(runner, "_ffmpeg_exe", lambda: "ffmpeg-fake.exe")
    monkeypatch.setattr("subprocess.run", fake_run)

    result = export_odb_animation(odb, workdir=tmp_path)

    assert len(calls) == 2
    assert result["frames"] == 3
    assert result["video"] == "anim.mp4"
    # resolve(): Windows returns real on-disk casing, tmp_path may differ
    assert result["out_dir"] == str(tmp_path.resolve() / "anim")
    assert (tmp_path / "anim.mp4").is_file()
    assert result["errors"] == []


def test_export_failure_lands_in_errors_without_raising(tmp_path, monkeypatch):
    odb = tmp_path / "model.odb"
    odb.write_text("fake odb\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(stdout="", stderr="license checkout failed",
                               returncode=1)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = export_odb_animation(odb, workdir=tmp_path)

    assert result["frames"] == 0
    assert result["video"] is None
    assert "license checkout failed" in result["errors"][0]


def test_export_without_ffmpeg_keeps_frames(tmp_path, monkeypatch):
    odb = tmp_path / "model.odb"
    odb.write_text("fake odb\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        out_dir = Path(kwargs["env"]["ABQ_ANIM_OUT"])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "frame_0000.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        return SimpleNamespace(stdout="ANIM_EXPORT_DONE: 1 frames", stderr="",
                               returncode=0)

    def broken_ffmpeg():
        raise RuntimeError("imageio_ffmpeg not installed")

    monkeypatch.setattr(runner, "_ffmpeg_exe", broken_ffmpeg)
    monkeypatch.setattr("subprocess.run", fake_run)

    result = export_odb_animation(odb, workdir=tmp_path)

    assert result["frames"] == 1
    assert result["video"] is None
    assert "ffmpeg unavailable" in result["errors"][0]
