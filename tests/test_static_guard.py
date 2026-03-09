"""
test_static_guard.py
--------------------
Unit tests for the static security guard.
No Abaqus required.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.static_guard import GuardResult, check_script_string


class TestStaticGuard:
    def _check(self, code: str) -> GuardResult:
        return check_script_string(code)

    # ── Should PASS ──────────────────────────────────────────────────────────

    def test_clean_abaqus_script(self):
        code = """
from abaqus import *
from abaqusConstants import *
import part, material, section, assembly, step, load, mesh, job

mdb.models['Model-1'].Material(name='Steel')
mdb.models['Model-1'].materials['Steel'].Elastic(table=((210000.0, 0.3),))
"""
        r = self._check(code)
        assert r.passed, f"Should pass but got: {r.findings}"

    def test_open_readonly_passes(self):
        code = """
with open('data.csv', 'r') as f:
    data = f.read()
"""
        r = self._check(code)
        assert r.passed

    def test_basic_math_passes(self):
        code = """
import math
x = math.sqrt(100.0)
result = x * 2.0
"""
        r = self._check(code)
        assert r.passed

    # ── Should BLOCK ─────────────────────────────────────────────────────────

    def test_import_os_blocked(self):
        code = "import os\nos.system('rm -rf /')"
        r = self._check(code)
        assert not r.passed
        assert any("os" in f for f in r.findings)

    def test_import_subprocess_blocked(self):
        code = "import subprocess\nsubprocess.run(['ls'])"
        r = self._check(code)
        assert not r.passed

    def test_from_os_import_blocked(self):
        code = "from os import path, getcwd\nprint(getcwd())"
        r = self._check(code)
        assert not r.passed

    def test_eval_blocked(self):
        code = "result = eval('1 + 1')"
        r = self._check(code)
        assert not r.passed

    def test_exec_blocked(self):
        code = "exec('print(42)')"
        r = self._check(code)
        assert not r.passed

    def test_dunder_import_blocked(self):
        code = "mod = __import__('os')"
        r = self._check(code)
        assert not r.passed

    def test_socket_blocked(self):
        code = "import socket\ns = socket.socket()"
        r = self._check(code)
        assert not r.passed

    def test_requests_blocked(self):
        code = "import requests\nr = requests.get('http://evil.com')"
        r = self._check(code)
        assert not r.passed

    def test_nested_os_import_blocked(self):
        code = "from os.path import join\nprint(join('/etc', 'passwd'))"
        r = self._check(code)
        assert not r.passed


class TestStaticGuardFile:
    def test_check_real_file(self, tmp_path):
        script = tmp_path / "test_script.py"
        script.write_text("""
from abaqus import *
from abaqusConstants import *
mdb.models['Model-1'].Material(name='Steel')
""")
        from tools.static_guard import check_script
        r = check_script(script)
        assert r.passed

    def test_nonexistent_file_raises(self):
        from tools.errors import AbaqusAgentError, ErrorCode
        from tools.static_guard import check_script
        with pytest.raises(AbaqusAgentError) as exc_info:
            check_script("/nonexistent/path/script.py")
        assert exc_info.value.code == ErrorCode.FILE_NOT_FOUND
