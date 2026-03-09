"""
test_errors.py
--------------
Unit tests for error codes and AbaqusAgentError.
No Abaqus required.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.errors import ERROR_SUGGESTIONS, AbaqusAgentError, ErrorCode


class TestErrorCodes:
    def test_all_codes_have_suggestions(self):
        for code in ErrorCode:
            assert code in ERROR_SUGGESTIONS, f"Missing suggestion for {code}"

    def test_error_to_dict(self):
        err = AbaqusAgentError(
            ErrorCode.NONCONVERGENCE,
            "Solution did not converge",
            log_snippet="*** ERROR: Solution diverging",
            workdir="/tmp/runs/abc123",
        )
        d = err.to_dict()
        assert d["error_code"] == "NONCONVERGENCE"
        assert "converge" in d["message"].lower()
        assert d["suggestion"] != ""
        assert d["workdir"] == "/tmp/runs/abc123"

    def test_error_str_includes_suggestion(self):
        err = AbaqusAgentError(ErrorCode.LICENSE_UNAVAILABLE, "License checkout failed")
        s = str(err)
        assert "LICENSE_UNAVAILABLE" in s
        assert "Suggestion" in s

    def test_error_code_values_are_strings(self):
        for code in ErrorCode:
            assert isinstance(code.value, str)

    def test_abaqus_not_found_suggestion(self):
        err = AbaqusAgentError(ErrorCode.ABAQUS_NOT_FOUND, "not found")
        assert "PATH" in err.suggestion or "abaqus" in err.suggestion.lower()

    def test_syntax_error_suggestion(self):
        err = AbaqusAgentError(ErrorCode.SYNTAX_ERROR, "bad keyword")
        assert "syntaxcheck" in err.suggestion.lower() or "inp" in err.suggestion.lower()

    def test_path_too_long_suggestion(self):
        err = AbaqusAgentError(ErrorCode.PATH_TOO_LONG, "256 chars")
        assert "256" in err.suggestion or "path" in err.suggestion.lower()
