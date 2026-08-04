"""Integrity checks for Architecture Decision Records in docs/decisions/."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
README = DECISIONS_DIR / "README.md"

ALLOWED_STATUSES = {"Proposed", "Accepted", "Deprecated", "Superseded"}
REQUIRED_SECTIONS = [
    "## Status",
    "## Date",
    "## Context",
    "## Decision",
    "## Consequences",
    "## Rejected alternatives",
    "## References",
]

# Placeholders that must not appear in accepted ADRs.
PLACEHOLDERS = {"TBD", "TODO", "<date>", "<owner>"}

# Glob for four-digit ADR files (excludes the template and README by design).
ADR_FILE_GLOB = "[0-9][0-9][0-9][0-9]-*.md"


@pytest.fixture
def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def _parse_index_rows(readme_text: str) -> list[dict]:
    """Parse the ADR index table from README.md."""
    rows = []
    for line in readme_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        # Drop empty leading/trailing cells from the table border.
        cells = [c for c in cells if c]
        if len(cells) < 4:
            continue
        # Match a row that links to an ADR markdown file.
        link_match = re.search(r"\[ADR-(\d{4})\]\(([^)]+\.md)\)", cells[0])
        if not link_match:
            continue
        rows.append(
            {
                "id": link_match.group(1),
                "link": link_match.group(2),
                "title": cells[1],
                "status": cells[2],
                "date": cells[3] if len(cells) > 3 else "",
            }
        )
    return rows


def _accepted_adr_paths(readme_text: str) -> list[Path]:
    """Return paths for accepted ADRs, excluding the template."""
    rows = _parse_index_rows(readme_text)
    paths = [DECISIONS_DIR / r["link"] for r in rows if r["id"] != "0000"]
    assert paths, "No accepted ADR files found in README index"
    return paths


def test_decisions_directory_has_required_files() -> None:
    assert README.exists(), f"{README} must exist"
    assert (DECISIONS_DIR / "0000-template.md").exists(), "ADR template must exist"


def test_readme_has_lifecycle_and_index(readme_text: str) -> None:
    assert "## ADR lifecycle" in readme_text
    assert "## Index" in readme_text


def test_index_entries_are_unique_and_consistent(readme_text: str) -> None:
    rows = _parse_index_rows(readme_text)
    ids = [r["id"] for r in rows]
    links = [r["link"] for r in rows]

    assert ids, "Index must contain at least one ADR row"
    assert len(ids) == len(set(ids)), f"Duplicate ADR ids in index: {Counter(ids)}"
    assert len(links) == len(set(links)), f"Duplicate ADR links in index: {Counter(links)}"

    for row in rows:
        assert row["link"].startswith(f"{row['id']}-"), (
            f"ADR-{row['id']} link {row['link']} must start with '{row['id']}-'"
        )


def test_indexed_adr_files_exist_and_match_metadata(readme_text: str) -> None:
    rows = _parse_index_rows(readme_text)
    for row in rows:
        path = DECISIONS_DIR / row["link"]
        assert path.exists(), f"Indexed ADR file missing: {path}"

        text = path.read_text(encoding="utf-8")
        title_line = text.splitlines()[0]
        expected_header = f"# ADR-{row['id']}: {row['title']}"
        assert title_line == expected_header, (
            f"{path}: expected header {expected_header!r}, got {title_line!r}"
        )

        if row["id"] == "0000":
            # Template is not a real ADR.
            continue

        status_match = re.search(r"## Status\s*\n+([A-Za-z]+)", text)
        assert status_match, f"{path}: missing or malformed ## Status"
        status = status_match.group(1)
        assert status in ALLOWED_STATUSES, (
            f"{path}: status {status!r} not in {ALLOWED_STATUSES}"
        )
        assert status == row["status"], (
            f"{path}: README status {row['status']!r} does not match file status {status!r}"
        )

        date_match = re.search(r"## Date\s*\n+(\d{4}-\d{2}-\d{2})", text)
        assert date_match, f"{path}: missing or malformed ## Date (expected YYYY-MM-DD)"
        assert date_match.group(1) == row["date"], (
            f"{path}: README date {row['date']!r} does not match file date {date_match.group(1)!r}"
        )

        for section in REQUIRED_SECTIONS:
            assert section in text, f"{path}: missing required section {section}"


def test_accepted_adrs_contain_no_placeholders(readme_text: str) -> None:
    """Accepted ADRs must not contain template placeholders (TBD, TODO, <date>, <owner>)."""
    for path in _accepted_adr_paths(readme_text):
        text = path.read_text(encoding="utf-8")
        found = {p for p in PLACEHOLDERS if p in text}
        assert not found, f"{path}: found placeholders {found}"


def test_every_adr_file_is_indexed_exactly_once(readme_text: str) -> None:
    rows = _parse_index_rows(readme_text)
    indexed_links = {r["link"] for r in rows}
    adr_files = {p.name for p in DECISIONS_DIR.glob("*.md") if p.name != "README.md"}
    assert adr_files == indexed_links, (
        f"ADR files missing from index or extra links: "
        f"files={adr_files} links={indexed_links}"
    )


def test_four_digit_adr_files_are_non_empty_and_match_convention() -> None:
    paths = list(DECISIONS_DIR.glob(ADR_FILE_GLOB))
    assert paths, f"No four-digit ADR files found with glob {ADR_FILE_GLOB!r}"
    for path in paths:
        assert path.stat().st_size > 0, f"{path} is empty"
        assert re.fullmatch(r"\d{4}-.*\.md", path.name), (
            f"{path.name} does not match the four-digit ADR naming convention"
        )


def test_supersession_links_are_valid(readme_text: str) -> None:
    paths = [p for p in DECISIONS_DIR.glob(ADR_FILE_GLOB) if p.name != "0000-template.md"]
    assert paths, "No four-digit ADR files to check for supersession links"

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"Superseded by:\s*\[ADR-(\d{4})\]\(([^)]+\.md)\)", text):
            target = DECISIONS_DIR / match.group(2)
            assert target.exists(), f"{path}: superseded-by link {target} missing"
            assert match.group(1) in target.name
        for match in re.finditer(r"Supersedes:\s*\[ADR-(\d{4})\]\(([^)]+\.md)\)", text):
            target = DECISIONS_DIR / match.group(2)
            assert target.exists(), f"{path}: supersedes link {target} missing"
            assert match.group(1) in target.name


def test_adr_internal_links_resolve(readme_text: str) -> None:
    """Check that relative .md links inside accepted ADR files point to existing files."""
    rows = _parse_index_rows(readme_text)
    indexed_files = {DECISIONS_DIR / r["link"] for r in rows if r["id"] != "0000"}
    indexed_files.add(README)

    paths = [p for p in DECISIONS_DIR.glob(ADR_FILE_GLOB) if p.name != "0000-template.md"]
    assert paths, "No four-digit ADR files to check for internal links"

    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\]\(([^)]+\.md)\)", text):
            link = match.group(1)
            target = (DECISIONS_DIR / link).resolve()
            assert target in {p.resolve() for p in indexed_files}, (
                f"{path}: broken relative link {link}"
            )
