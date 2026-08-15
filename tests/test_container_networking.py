"""A published container port must actually accept connections.

Measured defect: core/config.host() returns 127.0.0.1 unless
ABAQUS_AGENT_HOST says otherwise — correct for a dev checkout, which has no
authentication and can launch solver jobs. Neither the Dockerfile nor
docker-compose.yml set it, so inside a container the server bound to the
container's own loopback and `docker run -p 8000:8000` published a port that
answered nothing. The whole documented Docker path was dead.

The container is not built here (no daemon in the hermetic suite), so this
pins the two halves that can be checked from source: the env var really does
move the bind address, and the image/compose really do set it.
"""

from __future__ import annotations

import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_loopback_stays_the_default_off_container(monkeypatch):
    """The safe default must survive: a dev checkout is not LAN-exposed."""
    import core.config as config

    monkeypatch.delenv("ABAQUS_AGENT_HOST", raising=False)
    importlib.reload(config)
    try:
        assert config.host() == "127.0.0.1"
    finally:
        importlib.reload(config)


def test_env_var_is_what_moves_the_bind_address(monkeypatch):
    import core.config as config

    monkeypatch.setenv("ABAQUS_AGENT_HOST", "0.0.0.0")
    importlib.reload(config)
    try:
        assert config.host() == "0.0.0.0"
    finally:
        monkeypatch.delenv("ABAQUS_AGENT_HOST", raising=False)
        importlib.reload(config)


def test_dockerfile_sets_the_bind_address():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "ABAQUS_AGENT_HOST=0.0.0.0" in dockerfile, (
        "without this the published port accepts nothing")


def test_compose_publishes_to_loopback_only():
    """0.0.0.0 inside the container is safe only because the port is published
    to the host's loopback. If one changes, the other has to."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "ABAQUS_AGENT_HOST=0.0.0.0" in compose
    published = [ln.strip() for ln in compose.splitlines()
                 if ln.strip().startswith("- \"") and ":" in ln]
    assert published, "no published ports found — did the format change?"
    for entry in published:
        assert entry.startswith('- "127.0.0.1:'), (
            "an unauthenticated solver-launching server must not be published "
            "to every interface: %s" % entry)
