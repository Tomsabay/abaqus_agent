"""/ is the workbench; the old Copilot MVP page lives at /copilot.

The desktop shell always opened /workbench directly, but a browser user
following the README landed on the pre-workbench Copilot page — internal
gate diagnostics ("ALPHA_READY_WITH_GUI_BLOCKER", "1 BLOCKED") on the
first screen they ever saw. The front door now points at the product.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402


def _client():
    import server
    return TestClient(server.app)


def test_root_redirects_to_workbench():
    res = _client().get("/", follow_redirects=False)
    assert res.status_code == 307
    assert res.headers["location"] == "/workbench"


def test_workbench_serves_the_product():
    res = _client().get("/workbench")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]


def test_copilot_still_serves_the_old_page():
    res = _client().get("/copilot")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
