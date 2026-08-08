"""Tests for scripts/prepare_release.py."""

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from typer.testing import CliRunner

from scripts.prepare_release import (
    app,
    bump_version,
    get_current_version,
    get_release_notes_body,
    parse_version,
    update_version_file,
)

runner = CliRunner()

INIT_TEMPLATE = '__version__ = "{version}"\n'
NOTES_TEMPLATE = "# Release Notes\n\n## Latest Changes\n\n## 0.1.0 (2025-01-01)\n\nInitial release.\n"


@pytest.fixture()
def version_file(tmp_path: Path) -> Path:
    f = tmp_path / "__init__.py"
    f.write_text(INIT_TEMPLATE.format(version="0.1.0"))
    return f


@pytest.fixture()
def notes_file(tmp_path: Path) -> Path:
    f = tmp_path / "RELEASE_NOTES.md"
    f.write_text(NOTES_TEMPLATE)
    return f


# ---------------------------------------------------------------------------
# parse_version / get_current_version / bump_version (unit-level error paths)
# ---------------------------------------------------------------------------


def test_parse_version_rejects_malformed_string() -> None:
    with pytest.raises(ValueError, match="Invalid version: 'not-a-version'"):
        parse_version("not-a-version")


def test_get_current_version_raises_when_no_assignment_found(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    with pytest.raises(RuntimeError, match="found 0"):
        get_current_version("no version assignment here\n", f)


def test_get_current_version_raises_when_multiple_assignments_found(tmp_path: Path) -> None:
    f = tmp_path / "__init__.py"
    content = '__version__ = "0.1.0"\n__version__ = "0.2.0"\n'
    with pytest.raises(RuntimeError, match="found 2"):
        get_current_version(content, f)


def test_bump_version_rejects_invalid_bump_type() -> None:
    with pytest.raises(ValueError, match="Invalid bump type: 'sideways'"):
        bump_version("1.0.0", "sideways")  # type: ignore


# ---------------------------------------------------------------------------
# current-version
# ---------------------------------------------------------------------------


def test_current_version(version_file: Path) -> None:
    result = runner.invoke(app, ["current-version", "--version-file", str(version_file)])
    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


# ---------------------------------------------------------------------------
# prepare
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bump", "expected"),
    [
        ("patch", "0.1.1"),
        ("minor", "0.2.0"),
        ("major", "1.0.0"),
    ],
)
def test_prepare_bump(
    version_file: Path,
    notes_file: Path,
    bump: str,
    expected: str,
) -> None:
    result = runner.invoke(
        app,
        [
            "prepare",
            bump,
            "--version-file",
            str(version_file),
            "--release-notes-file",
            str(notes_file),
            "--date",
            "2026-01-01",
        ],
    )
    assert result.exit_code == 0, result.output
    assert f'__version__ = "{expected}"' in version_file.read_text()


def test_prepare_defaults_to_today_when_date_omitted(version_file: Path, notes_file: Path) -> None:
    result = runner.invoke(
        app,
        [
            "prepare",
            "minor",
            "--version-file",
            str(version_file),
            "--release-notes-file",
            str(notes_file),
        ],
    )
    assert result.exit_code == 0, result.output
    today = date.today().isoformat()
    assert f"## 0.2.0 ({today})" in notes_file.read_text()


def test_prepare_updates_release_notes(version_file: Path, notes_file: Path) -> None:
    runner.invoke(
        app,
        [
            "prepare",
            "minor",
            "--version-file",
            str(version_file),
            "--release-notes-file",
            str(notes_file),
            "--date",
            "2026-06-01",
        ],
    )
    notes = notes_file.read_text()
    assert "## Latest Changes" in notes
    assert "## 0.2.0 (2026-06-01)" in notes


def test_prepare_version_must_increase(version_file: Path, notes_file: Path) -> None:
    # bump to 0.2.0 first
    runner.invoke(
        app,
        [
            "prepare",
            "minor",
            "--version-file",
            str(version_file),
            "--release-notes-file",
            str(notes_file),
            "--date",
            "2026-01-01",
        ],
    )
    # write a fresh notes file — otherwise "already contains section" fires first
    notes_file.write_text(NOTES_TEMPLATE)
    # try to bump patch on already-bumped file: 0.2.0 patch → 0.2.1, which is valid.
    # To trigger the guard, manually set version higher than what bump produces.
    version_file.write_text(INIT_TEMPLATE.format(version="0.2.0"))
    # writing 0.2.0 again via a fake bump isn't easy via CLI, so test the helper directly
    content = version_file.read_text()
    with pytest.raises(RuntimeError, match="must be greater than"):
        update_version_file(content, "0.2.0", version_file)


def test_prepare_section_already_exists(version_file: Path, notes_file: Path) -> None:
    # bump once
    runner.invoke(
        app,
        [
            "prepare",
            "minor",
            "--version-file",
            str(version_file),
            "--release-notes-file",
            str(notes_file),
            "--date",
            "2026-01-01",
        ],
    )
    # restore version so bump produces the same version again
    version_file.write_text(INIT_TEMPLATE.format(version="0.1.0"))
    result = runner.invoke(
        app,
        [
            "prepare",
            "minor",
            "--version-file",
            str(version_file),
            "--release-notes-file",
            str(notes_file),
            "--date",
            "2026-01-01",
        ],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert "already contain a section" in str(result.exception)
    # The version file must stay untouched: writing it before the release notes
    # update had failed would leave a bumped version with no matching notes entry.
    assert version_file.read_text() == INIT_TEMPLATE.format(version="0.1.0")


def test_prepare_rolls_back_version_file_when_release_notes_write_fails(version_file: Path, notes_file: Path) -> None:
    original_version_content = version_file.read_text()
    original_write_text = Path.write_text
    calls = {"n": 0}

    def flaky_write_text(self: Path, *args: object, **kwargs: object) -> int:
        calls["n"] += 1
        if calls["n"] == 2:  # the release notes file is the second write
            raise OSError("disk full (simulated)")
        return original_write_text(self, *args, **kwargs)  # type: ignore[arg-type]

    with patch.object(Path, "write_text", flaky_write_text):
        result = runner.invoke(
            app,
            [
                "prepare",
                "minor",
                "--version-file",
                str(version_file),
                "--release-notes-file",
                str(notes_file),
                "--date",
                "2026-01-01",
            ],
        )

    assert result.exit_code != 0
    assert isinstance(result.exception, OSError)
    # The version file must be rolled back: it was already written before the
    # release notes write failed, and would otherwise stay bumped with no matching entry.
    assert version_file.read_text() == original_version_content
    assert notes_file.read_text() == NOTES_TEMPLATE


def test_prepare_notes_wrong_header(version_file: Path, tmp_path: Path) -> None:
    bad_notes = tmp_path / "RELEASE_NOTES.md"
    bad_notes.write_text("## Latest Changes\n\n## 0.1.0\n\nInitial release.\n")
    result = runner.invoke(
        app,
        ["prepare", "minor", "--version-file", str(version_file), "--release-notes-file", str(bad_notes)],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert "must start with" in str(result.exception)
    assert "# Release Notes" in str(result.exception)


def test_prepare_notes_missing_latest_changes(version_file: Path, tmp_path: Path) -> None:
    bad_notes = tmp_path / "RELEASE_NOTES.md"
    bad_notes.write_text("# Release Notes\n\n## 0.1.0\n\nInitial release.\n")
    result = runner.invoke(
        app,
        ["prepare", "minor", "--version-file", str(version_file), "--release-notes-file", str(bad_notes)],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert "must start with" in str(result.exception)
    assert "Latest Changes" in str(result.exception)


# ---------------------------------------------------------------------------
# release-notes
# ---------------------------------------------------------------------------


def test_release_notes_extracts_body(version_file: Path, tmp_path: Path) -> None:
    notes = tmp_path / "RELEASE_NOTES.md"
    notes.write_text("# Release Notes\n\n## Latest Changes\n\n## 0.1.0 (2025-01-01)\n\nInitial release.\n")
    result = runner.invoke(
        app,
        ["release-notes", "--version-file", str(version_file), "--release-notes-file", str(notes)],
    )
    assert result.exit_code == 0, result.output
    assert result.output.strip() == "Initial release."


def test_release_notes_missing_section(version_file: Path, tmp_path: Path) -> None:
    notes = tmp_path / "RELEASE_NOTES.md"
    notes.write_text("# Release Notes\n\n## Latest Changes\n\n## 0.2.0 (2025-01-01)\n\nSomething.\n")
    result = runner.invoke(
        app,
        ["release-notes", "--version-file", str(version_file), "--release-notes-file", str(notes)],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert "Could not find release notes section for 0.1.0" in str(result.exception)


def test_release_notes_empty_section(version_file: Path, tmp_path: Path) -> None:
    notes = tmp_path / "RELEASE_NOTES.md"
    notes.write_text("# Release Notes\n\n## Latest Changes\n\n## 0.1.0 (2025-01-01)\n")
    result = runner.invoke(
        app,
        ["release-notes", "--version-file", str(version_file), "--release-notes-file", str(notes)],
    )
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert "is empty" in str(result.exception)


def test_get_release_notes_body_stops_at_next_version_heading(tmp_path: Path) -> None:
    notes_file = tmp_path / "RELEASE_NOTES.md"
    content = (
        "# Release Notes\n\n"
        "## Latest Changes\n\n"
        "## 0.3.0 (2026-03-01)\n\n"
        "Third release notes.\n\n"
        "## 0.2.0 (2026-02-01)\n\n"
        "Second release notes.\n\n"
        "## 0.1.0 (2026-01-01)\n\n"
        "First release notes.\n"
    )

    assert get_release_notes_body(content, "0.2.0", notes_file) == "Second release notes.\n"
