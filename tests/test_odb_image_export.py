"""Tests for ODB image export orchestration."""

from __future__ import annotations

import json
from types import SimpleNamespace

from post.export_odb_images import export_odb_images


def test_export_odb_images_returns_error_when_odb_missing(tmp_path):
    result = export_odb_images(
        tmp_path / "missing.odb",
        [{"name": "mises_contour", "field_variable": "S", "invariant": "MISES"}],
        workdir=tmp_path,
    )

    assert result["images"] == []
    assert "ODB not found" in result["errors"][0]


def test_export_odb_images_passes_paths_through_environment(tmp_path, monkeypatch):
    odb = tmp_path / "model.odb"
    odb.write_text("fake odb\n", encoding="utf-8")

    def fake_run(cmd, **kwargs):
        assert "--" not in cmd
        env = kwargs["env"]
        assert env["ABAQUS_AGENT_ODB_PATH"].endswith("model.odb")
        result_path = env["ABAQUS_AGENT_PLOT_RESULT"]
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({"images": [{"path": "mises_contour.png"}], "errors": []}, f)
        return SimpleNamespace(stdout="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = export_odb_images(
        odb,
        [{"name": "mises_contour", "field_variable": "S", "invariant": "MISES"}],
        workdir=tmp_path,
    )

    assert result["images"][0]["path"] == "mises_contour.png"
