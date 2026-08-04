"""AST-based import safety tests.

The goal of ARCH-001 is to make the production code import-safe: no module
reads the process environment or a .env file at import time.  Only
``tradex.config`` is allowed to load environment state, and it does so only
inside the public ``load_runtime_settings`` / ``settings_from_mapping`` callables.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

import tradex


class _TopLevelEnvVisitor(ast.NodeVisitor):
    """Collect env/dotenv references that appear at module scope (not inside functions/classes)."""

    def __init__(self) -> None:
        self.offending: list[ast.AST] = []
        self._in_function_or_class = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._in_function_or_class += 1
        self.generic_visit(node)
        self._in_function_or_class -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._in_function_or_class += 1
        self.generic_visit(node)
        self._in_function_or_class -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._in_function_or_class += 1
        self.generic_visit(node)
        self._in_function_or_class -= 1

    def visit_Call(self, node: ast.Call) -> None:
        if self._in_function_or_class == 0:
            func = node.func
            if isinstance(func, ast.Attribute):
                # os.getenv(...)
                if (
                    func.attr == "getenv"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                ):
                    self.offending.append(node)
                # *.load_dotenv / *.dotenv_values
                if func.attr in {"load_dotenv", "dotenv_values"}:
                    self.offending.append(node)
            if isinstance(func, ast.Name) and func.id in {"load_dotenv", "dotenv_values", "getenv"}:
                self.offending.append(node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            self._in_function_or_class == 0
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            self.offending.append(node)
        self.generic_visit(node)


def _offending_files(root: Path, *, allowed: set[str]) -> list[Path]:
    """Return files in ``root`` that read env/dotenv at module scope."""
    offenders: list[Path] = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if str(rel) in allowed:
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {path}: {e}")

        visitor = _TopLevelEnvVisitor()
        visitor.visit(tree)
        if visitor.offending:
            offenders.append(path)
    return offenders


def test_no_module_scope_dotenv_loading():
    """``load_dotenv`` / ``dotenv_values`` must not be called at module scope in tradex/."""
    root = Path(tradex.__file__).parent
    offenders = _offending_files(root, allowed={"config.py"})
    # Filter to files that actually contain dotenv calls.
    dotenv_offenders = [
        p for p in offenders
        if "load_dotenv" in p.read_text() or "dotenv_values" in p.read_text()
    ]
    assert not dotenv_offenders, f"module-scope dotenv loading in: {dotenv_offenders}"


def test_no_module_scope_os_env_reads():
    """``os.getenv`` and ``os.environ`` must not be read at module scope in tradex/."""
    root = Path(tradex.__file__).parent
    offenders = _offending_files(root, allowed={"config.py"})
    assert not offenders, f"module-scope env reads in: {offenders}"


def _subprocess_import_ok(module_name: str) -> None:
    """Import ``module_name`` in a clean process with no .env and no credentials."""
    repo = Path(tradex.__file__).parent.parent
    clean_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(repo),
    }
    cmd = [
        sys.executable,
        "-c",
        f"import {module_name}; print('imported')",
    ]
    result = subprocess.run(cmd, env=clean_env, capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, (
        f"Failed to import {module_name} with clean env:\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "imported" in result.stdout


@pytest.mark.parametrize(
    "module",
    [
        "tradex.data.fetcher",
        "tradex.alerts.notifier",
        "tradex.options.flow",
        "tradex.tracker.watcher",
        "tradex.ui.dashboard",
    ],
)
def test_key_modules_import_with_clean_environment(module: str) -> None:
    """Previously env-reading modules now import safely without .env or credentials."""
    _subprocess_import_ok(module)


def test_dashboard_importable_without_credentials():
    """The Streamlit dashboard module can be imported with no .env file loaded."""
    _subprocess_import_ok("tradex.ui.dashboard")
