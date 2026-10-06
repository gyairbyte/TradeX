"""CLI provenance, dirty worktree rejection, and governance isolation tests for LONG-002E2."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from tradex.research.long_002e2.cli import (
    check_worktree_clean,
    get_runtime_git_head,
    main,
)
from tradex.research.long_002e2.spec import (
    BASE_GIT_SHA,
    REPO_ROOT,
)
from tradex.strategies.registry import APPROVED_PRODUCTION_STRATEGIES


def test_60_runtime_head_resolves() -> None:
    """Verify runtime git HEAD resolves non-empty SHA."""
    head = get_runtime_git_head()
    assert isinstance(head, str)
    assert len(head) == 40


def test_61_execution_sha_mismatch_fails_closed() -> None:
    """Verify CLI fails closed if provided execution SHA does not match runtime HEAD."""
    with (
        patch("tradex.research.long_002e2.cli.check_worktree_clean"),
        pytest.raises(ValueError, match="EXECUTION SHA MISMATCH"),
    ):
        main(["--execution-sha", "0000000000000000000000000000000000000000"])


def test_62_dirty_worktree_fails_closed() -> None:
    """Verify check_worktree_clean raises if git status reports uncommitted files."""
    mock_res = subprocess.CompletedProcess(
        args=["git", "status", "--porcelain"],
        returncode=0,
        stdout=" M tradex/some_file.py\n",
        stderr="",
    )
    with (
        patch("subprocess.run", returncode=0, return_value=mock_res),
        pytest.raises(RuntimeError, match="DIRTY WORKTREE BREACH"),
    ):
        check_worktree_clean()


def test_63_no_public_allow_dirty_flag() -> None:
    """Verify CLI parser has no public allow-dirty flag."""
    with pytest.raises(SystemExit):
        main(["--allow-dirty"])


def test_66_no_provider_network_imports() -> None:
    """Verify no live network or data providers are imported in E2 modules."""
    import tradex.research.long_002e2.artifacts
    import tradex.research.long_002e2.bootstrap
    import tradex.research.long_002e2.cli
    import tradex.research.long_002e2.concentration
    import tradex.research.long_002e2.diagnostics
    import tradex.research.long_002e2.feature_profiles
    import tradex.research.long_002e2.loader
    import tradex.research.long_002e2.localization
    import tradex.research.long_002e2.probabilities
    import tradex.research.long_002e2.quarters
    import tradex.research.long_002e2.regimes
    import tradex.research.long_002e2.reproduction
    import tradex.research.long_002e2.selection
    import tradex.research.long_002e2.selection_sets
    import tradex.research.long_002e2.spec

    for mod in [
        tradex.research.long_002e2.artifacts,
        tradex.research.long_002e2.bootstrap,
        tradex.research.long_002e2.cli,
        tradex.research.long_002e2.concentration,
        tradex.research.long_002e2.diagnostics,
        tradex.research.long_002e2.feature_profiles,
        tradex.research.long_002e2.loader,
        tradex.research.long_002e2.localization,
        tradex.research.long_002e2.probabilities,
        tradex.research.long_002e2.quarters,
        tradex.research.long_002e2.regimes,
        tradex.research.long_002e2.reproduction,
        tradex.research.long_002e2.selection,
        tradex.research.long_002e2.selection_sets,
        tradex.research.long_002e2.spec,
    ]:
        source = Path(mod.__file__).read_text(encoding="utf-8")
        assert "yfinance" not in source
        assert "alpaca" not in source
        assert "schwab" not in source
        assert "requests.get" not in source
        assert "urllib" not in source


def test_67_no_production_files_changed() -> None:
    """Verify no production trading files were modified from base SHA."""
    res = subprocess.run(
        ["git", "diff", "--name-only", BASE_GIT_SHA, "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_files = [f.strip() for f in res.stdout.strip().splitlines() if f.strip()]
    for f in changed_files:
        assert not f.startswith("tradex/screener/"), f"Production file modified: {f}"
        assert not f.startswith("tradex/tracker/"), f"Production file modified: {f}"
        assert not f.startswith("tradex/alerts/"), f"Production file modified: {f}"
        assert not f.startswith("tradex/ui/"), f"Production file modified: {f}"
        assert not f.startswith("tradex/backtest/"), f"Production file modified: {f}"


def test_68_no_daytrade_files_changed() -> None:
    """Verify zero DAYTRADE files were modified from base SHA."""
    res = subprocess.run(
        ["git", "diff", "--name-only", BASE_GIT_SHA, "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    changed_files = [f.strip() for f in res.stdout.strip().splitlines() if f.strip()]
    for f in changed_files:
        assert "daytrade" not in f.lower(), f"DAYTRADE file modified: {f}"


def test_69_approved_production_strategies_empty() -> None:
    """Verify APPROVED_PRODUCTION_STRATEGIES is strictly empty."""
    assert APPROVED_PRODUCTION_STRATEGIES == ()
