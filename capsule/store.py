"""Experiment capsule store.

Capsules make an Abaqus run auditable by recording inputs, artifacts, hashes,
environment metadata, and post-processing outputs in one small JSON manifest.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
from datetime import datetime
from pathlib import Path

from capsule.schema import CAPSULE_SCHEMA_VERSION, validate_capsule


def hash_file(path: str | Path) -> str:
    """Return a sha256 hash for a file without loading it all into memory."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def create_capsule(
    run_id: str,
    capsule_dir: str | Path,
    inputs: dict | None = None,
    artifacts: dict | None = None,
    metadata: dict | None = None,
) -> dict:
    """Create and persist a minimal capsule manifest."""
    capsule_dir = Path(capsule_dir)
    capsule_dir.mkdir(parents=True, exist_ok=True)

    capsule = {
        "schema_version": CAPSULE_SCHEMA_VERSION,
        "run_id": run_id,
        "created_at": datetime.now().isoformat(),
        "inputs": inputs or {},
        "artifacts": artifacts or {},
        "provenance": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            **(metadata or {}),
        },
    }
    write_capsule(capsule, capsule_dir)
    return capsule


def init_from_inp(
    inp_path: str | Path,
    capsule_dir: str | Path,
    run_id: str | None = None,
    model_name: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Initialize a capsule from a customer-provided .inp file."""
    src = Path(inp_path).resolve()
    if not src.exists():
        raise FileNotFoundError(src)
    if src.suffix.lower() != ".inp":
        raise ValueError(f"Expected a .inp file, got: {src}")

    capsule_dir = Path(capsule_dir)
    input_dir = capsule_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    copied = input_dir / src.name
    if src != copied.resolve():
        shutil.copyfile(src, copied)

    file_hash = hash_file(copied)
    run_id = run_id or file_hash[:16]
    return create_capsule(
        run_id=run_id,
        capsule_dir=capsule_dir,
        inputs={
            "model_name": model_name or src.stem,
            "source_inp": str(src),
            "inp": str(copied.relative_to(capsule_dir)),
            "inp_sha256": file_hash,
        },
        artifacts={},
        metadata=metadata,
    )


def write_capsule(capsule: dict, capsule_dir: str | Path) -> Path:
    """Write capsule.json after validating the minimal shape."""
    valid, errors = validate_capsule(capsule)
    if not valid:
        raise ValueError("; ".join(errors))
    path = Path(capsule_dir) / "capsule.json"
    path.write_text(json.dumps(capsule, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_capsule(path: str | Path) -> dict:
    """Load a capsule from capsule.json or from its containing directory."""
    path = Path(path)
    if path.is_dir():
        path = path / "capsule.json"
    capsule = json.loads(path.read_text(encoding="utf-8"))
    valid, errors = validate_capsule(capsule)
    if not valid:
        raise ValueError("; ".join(errors))
    return capsule
