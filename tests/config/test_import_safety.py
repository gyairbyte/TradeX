"""Import-safety tests.

ARCH-001 requires that no production module reads the process environment, a
``.env`` file, or snapshots paths like ``Path.home()`` at import time.  Only
``tradex.config`` may load environment state, and only inside the public
``settings_from_mapping`` / ``load_runtime_settings`` loaders.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import ClassVar

import pytest

import tradex


class _EnvReadVisitor(ast.NodeVisitor):
    """Detect env, dotenv, and path-snapshot reads at module/class scope.

    Function and lambda bodies are skipped; class bodies and comprehension
    expressions are treated as import-time code.
    """

    ENV_CALLS: ClassVar[set[str]] = {"getenv", "load_dotenv", "dotenv_values", "find_dotenv"}
    PATH_SNAPSHOT_ATTRS: ClassVar[set[str]] = {"home", "expanduser"}

    def __init__(self) -> None:
        self.offending: list[ast.AST] = []
        self._depth = 0

    def _visit_scoped(self, node: ast.AST) -> None:
        self._depth += 1
        self.generic_visit(node)
        self._depth -= 1

    visit_FunctionDef = _visit_scoped
    visit_AsyncFunctionDef = _visit_scoped
    visit_Lambda = _visit_scoped

    def visit_Call(self, node: ast.Call) -> None:
        if self._depth == 0:
            func = node.func
            offending = False
            if isinstance(func, ast.Attribute):
                if (
                    func.attr == "getenv"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                ):
                    offending = True
                if func.attr in self.ENV_CALLS:
                    offending = True
                if func.attr in self.PATH_SNAPSHOT_ATTRS:
                    offending = True
                if (
                    func.attr == "expanduser"
                    and isinstance(func.value, ast.Attribute)
                    and isinstance(func.value.value, ast.Name)
                    and func.value.value.id == "os"
                    and func.value.attr == "path"
                ):
                    offending = True
            elif isinstance(func, ast.Name) and func.id in self.ENV_CALLS:
                offending = True
            if offending:
                self.offending.append(node)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if (
            self._depth == 0
            and node.attr == "environ"
            and isinstance(node.value, ast.Name)
            and node.value.id == "os"
        ):
            self.offending.append(node)
        self.generic_visit(node)


def _offending_files(root: Path) -> list[tuple[Path, list[ast.AST]]]:
    """Return files in ``root`` with env/dotenv/path-snapshot reads at module/class scope."""
    offenders: list[tuple[Path, list[ast.AST]]] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError as e:
            pytest.fail(f"Syntax error in {path}: {e}")

        visitor = _EnvReadVisitor()
        visitor.visit(tree)
        if visitor.offending:
            offenders.append((path, visitor.offending))
    return offenders


def test_no_module_scope_dotenv_loading():
    """``load_dotenv`` / ``dotenv_values`` must not be called at import time."""
    root = Path(tradex.__file__).parent
    offenders = _offending_files(root)
    dotenv_offenders: list[Path] = []
    for path, nodes in offenders:
        lines = path.read_text(encoding="utf-8").splitlines()
        if any(
            "load_dotenv" in lines[node.lineno - 1] or "dotenv_values" in lines[node.lineno - 1]
            for node in nodes
        ):
            dotenv_offenders.append(path)
    assert not dotenv_offenders, f"module-scope dotenv loading in: {dotenv_offenders}"


def test_no_module_scope_env_or_path_snapshot_reads():
    """``os.getenv`` / ``os.environ`` / ``Path.home()`` / ``.expanduser()`` must not be read at import time."""
    root = Path(tradex.__file__).parent
    offenders = _offending_files(root)
    allowed = {root / "config.py"}
    offenders = [(p, n) for p, n in offenders if p not in allowed]
    assert not offenders, f"module-scope env/path reads in: {[p for p, _ in offenders]}"


def test_config_central_module_env_reads_are_inside_loaders():
    """In ``tradex.config``, env/dotenv/path-snapshot reads occur only inside the two public loaders."""
    config_path = Path(tradex.__file__).parent / "config.py"
    text = config_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(config_path))

    loaders = {"settings_from_mapping", "load_runtime_settings"}

    class _ConfigLoaderVisitor(ast.NodeVisitor):
        ENV_CALLS: ClassVar[set[str]] = {"getenv", "load_dotenv", "dotenv_values", "find_dotenv"}
        PATH_SNAPSHOT_ATTRS: ClassVar[set[str]] = {"home", "expanduser"}

        def __init__(self) -> None:
            self.stack: list[str] = []
            self.outside: list[tuple[str, ast.AST]] = []

        def _current(self) -> str:
            return ".".join(self.stack) or "<module>"

        def _in_loader(self) -> bool:
            return any(name in loaders for name in self.stack)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_Lambda(self, node: ast.Lambda) -> None:
            self.stack.append("<lambda>")
            self.generic_visit(node)
            self.stack.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.stack.append(f"<class {node.name}>")
            self.generic_visit(node)
            self.stack.pop()

        def _record_if_outside_loader(self, node: ast.AST) -> None:
            if not self._in_loader():
                self.outside.append((self._current(), node))

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            offending = False
            if isinstance(func, ast.Attribute):
                if (
                    func.attr == "getenv"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                ):
                    offending = True
                if func.attr in self.ENV_CALLS:
                    offending = True
                if func.attr in self.PATH_SNAPSHOT_ATTRS:
                    offending = True
                if (
                    func.attr == "expanduser"
                    and isinstance(func.value, ast.Attribute)
                    and isinstance(func.value.value, ast.Name)
                    and func.value.value.id == "os"
                    and func.value.attr == "path"
                ):
                    offending = True
            elif isinstance(func, ast.Name) and func.id in self.ENV_CALLS:
                offending = True
            if offending:
                self._record_if_outside_loader(node)
            self.generic_visit(node)

        def visit_Attribute(self, node: ast.Attribute) -> None:
            if (
                node.attr == "environ"
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
            ):
                self._record_if_outside_loader(node)
            self.generic_visit(node)

    visitor = _ConfigLoaderVisitor()
    visitor.visit(tree)
    assert not visitor.outside, (
        "env/dotenv/path-snapshot reads outside loaders in tradex/config.py:\n"
        + "\n".join(f"  {scope}: line {node.lineno}" for scope, node in visitor.outside)
    )


PYTHON_IMPORT_GUARD = r"""
import http.client
import os
import pathlib
import socket
import sys
import urllib.request

home = os.environ["TRADEX_GUARD_HOME"]

class GuardSocket:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("network guard: socket.socket")

socket.socket = GuardSocket

def guard_urlopen(url, *args, **kwargs):
    raise RuntimeError(f"network guard: urllib.request.urlopen({url!r})")

urllib.request.urlopen = guard_urlopen

_original_http_init = http.client.HTTPConnection.__init__
def guard_http_init(self, host, *args, **kwargs):
    raise RuntimeError(f"network guard: http.client.HTTPConnection({host!r})")
http.client.HTTPConnection.__init__ = guard_http_init

module_name = sys.argv[1]
__import__(module_name)

home_path = pathlib.Path(home)
items = sorted(str(p.relative_to(home)) for p in home_path.rglob("*"))
if items:
    print("HOME_NOT_EMPTY")
    for item in items:
        print(item)
else:
    print("OK")
"""


def _subprocess_import_ok(module_name: str) -> None:
    """Import ``module_name`` in a clean process with isolated HOME/CWD, no .env, and a network guard."""
    repo = Path(tradex.__file__).parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp) / "home"
        cwd = Path(tmp) / "cwd"
        home.mkdir()
        cwd.mkdir()

        env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "PYTHONPATH": str(repo),
            "PYTHONDONTWRITEBYTECODE": "1",
            "TRADEX_GUARD_HOME": str(home),
        }
        if "SYSTEMROOT" in os.environ:
            env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
        if "SystemRoot" in os.environ:
            env["SystemRoot"] = os.environ["SystemRoot"]
        # Block any .env in the repo from being found by accident.
        env["PWD"] = str(cwd)

        result = subprocess.run(
            [sys.executable, "-c", PYTHON_IMPORT_GUARD, module_name],
            env=env,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, (
            f"Failed to import {module_name} with clean env:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert result.stdout.strip().startswith("OK"), (
            f"Import of {module_name} created files under HOME or triggered network:\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )


@pytest.mark.parametrize(
    "module",
    [
        "tradex.config",
        "tradex.data.fetcher",
        "tradex.alerts.notifier",
        "tradex.options.flow",
        "tradex.tracker.watcher",
        "tradex.tracker.store",
        "tradex.watchlists.store",
        "tradex.patterns.fingerprint",
        "tradex.earnings.calendar",
        "tradex.signals.weights",
        "tradex.ui.dashboard",
    ],
)
def test_key_modules_import_cleanly_in_isolated_environment(module: str) -> None:
    """Persistence, provider, alert, options, watcher, and dashboard modules import without side effects."""
    _subprocess_import_ok(module)
