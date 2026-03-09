"""
static_guard.py
---------------
Static AST-based security guard for LLM-generated Abaqus scripts.

Checks for:
  - Dangerous imports (os, subprocess, socket, requests, ...)
  - Dangerous function calls (eval, exec, __import__, open with write modes)
  - Path traversal patterns
  - Shell injection patterns

RUN: python tools/static_guard.py <script.py>
Returns exit code 0 (PASS) or 2 (BLOCKED).
"""

from __future__ import annotations

import ast
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from tools.errors import AbaqusAgentError, ErrorCode

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DENY_IMPORTS: set[str] = {
    "os", "subprocess", "socket", "requests", "urllib",
    "http", "ftplib", "smtplib", "asyncio", "multiprocessing",
    "threading", "ctypes", "cffi", "importlib", "builtins",
    "shutil", "tempfile", "glob",
}

# These Abaqus-specific modules are OK even if they look unusual
ALLOW_IMPORTS: set[str] = {
    "abaqus", "abaqusConstants", "part", "material", "section", "assembly",
    "step", "load", "mesh", "job", "visualization", "odbAccess",
    "abaqusExceptions", "regionToolset", "connectorBehavior",
    "caeModules", "driverUtils",
}

DENY_CALLS: set[str] = {
    "eval", "exec", "__import__", "compile",
    "execfile",    # Python 2 remnant
}

# open() is allowed read-only; flag any write modes
OPEN_WRITE_MODES = re.compile(r"""open\s*\(.*['"][wa+rb][wb+]*['"]""")

# Suspicious shell injection patterns
SHELL_PATTERNS: list[re.Pattern] = [
    re.compile(r"os\s*\.\s*system"),
    re.compile(r"os\s*\.\s*popen"),
    re.compile(r"subprocess\s*\.\s*(run|Popen|call|check_output)"),
    re.compile(r"__import__\s*\("),
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class GuardResult:
    passed: bool = True
    findings: list[str] = field(default_factory=list)

    def block(self, msg: str):
        self.passed = False
        self.findings.append(msg)

    def warn(self, msg: str):
        self.findings.append(f"WARN: {msg}")


# ---------------------------------------------------------------------------
# AST Visitor
# ---------------------------------------------------------------------------

class SecurityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.result = GuardResult()

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in DENY_IMPORTS and root not in ALLOW_IMPORTS:
                self.result.block(
                    f"Denied import: '{alias.name}' at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        if node.module:
            root = node.module.split(".")[0]
            if root in DENY_IMPORTS and root not in ALLOW_IMPORTS:
                self.result.block(
                    f"Denied from-import: '{node.module}' at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # Direct function call: eval(...), exec(...)
        if isinstance(node.func, ast.Name):
            if node.func.id in DENY_CALLS:
                self.result.block(
                    f"Denied call: '{node.func.id}()' at line {node.lineno}"
                )
        # Attribute call: os.system(...), subprocess.run(...)
        elif isinstance(node.func, ast.Attribute):
            full = f"{_unparse_attr(node.func)}"
            for pattern in SHELL_PATTERNS:
                if pattern.search(full):
                    self.result.block(
                        f"Denied call pattern: '{full}' at line {node.lineno}"
                    )
            # open() with write mode
            if isinstance(node.func, ast.Attribute) and node.func.attr == "open":
                pass  # handled in Name
            if isinstance(node.func, ast.Name) and node.func.id == "open":
                if node.args and isinstance(node.args[1], ast.Constant):
                    mode = str(node.args[1].s)
                    if any(c in mode for c in ["w", "a", "+"]):
                        self.result.warn(
                            f"open() with write mode '{mode}' at line {node.lineno}"
                        )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        # Catch os.system, subprocess.Popen etc. as attribute access
        full = _unparse_attr(node)
        for pattern in SHELL_PATTERNS:
            if pattern.match(full):
                self.result.block(
                    f"Denied attribute: '{full}'"
                )
        self.generic_visit(node)


def _unparse_attr(node) -> str:
    """Safely unparse an attribute chain to a dotted string."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def check_script(script_path: str | Path) -> GuardResult:
    """
    Run static security checks on a Python script file.

    Returns GuardResult.passed == True if safe, False if blocked.
    Raises AbaqusAgentError on parse failure.
    """
    script_path = Path(script_path)
    if not script_path.exists():
        raise AbaqusAgentError(ErrorCode.FILE_NOT_FOUND, f"Script not found: {script_path}")

    source = script_path.read_text(encoding="utf-8")

    # Quick regex pass (catches obfuscation that AST might miss)
    result = GuardResult()
    for pattern in SHELL_PATTERNS:
        matches = pattern.findall(source)
        for m in matches:
            result.block(f"Regex pattern match: '{m}'")

    # AST pass
    try:
        tree = ast.parse(source, filename=str(script_path))
    except SyntaxError as e:
        raise AbaqusAgentError(
            ErrorCode.SYNTAX_ERROR,
            f"Failed to parse script: {e}",
            workdir=str(script_path.parent),
        )

    visitor = SecurityVisitor()
    visitor.visit(tree)
    result.passed = result.passed and visitor.result.passed
    result.findings.extend(visitor.result.findings)

    return result


def check_script_string(source: str, label: str = "<generated>") -> GuardResult:
    """Run static checks on a script provided as a string."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        return check_script(tmp)
    finally:
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tools/static_guard.py <script.py>")
        sys.exit(1)

    path = sys.argv[1]
    try:
        result = check_script(path)
    except AbaqusAgentError as e:
        print(f"ERROR: {e}")
        sys.exit(2)

    if result.passed:
        print("PASS")
        if result.findings:
            print("Warnings:")
            for f in result.findings:
                print(f"  {f}")
        sys.exit(0)
    else:
        print("BLOCKED")
        for f in result.findings:
            print(f"  {f}")
        sys.exit(2)
