"""Tests for scripts/prepare_release.py."""

from pathlib import Path

import pytest

from typer.testing import CliRunner

from scripts.prepare_release import app

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
    from scripts.prepare_release import update_version_file

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


def test_prepare_notes_wrong_header(version_file: Path, tmp_path: Path) -> None:
    bad_notes = tmp_path / "RELEASE_NOTES.md"
    bad_notes.write_text("## Latest Changes\n\n## 0.1.0\n\nInitial release.\n")
    result = runner.invoke(
        app,
        ["prepare", "minor", "--version-file", str(version_file), "--release-notes-file", str(bad_notes)],
    )
    assert result.exit_code != 0


def test_prepare_notes_missing_latest_changes(version_file: Path, tmp_path: Path) -> None:
    bad_notes = tmp_path / "RELEASE_NOTES.md"
    bad_notes.write_text("# Release Notes\n\n## 0.1.0\n\nInitial release.\n")
    result = runner.invoke(
        app,
        ["prepare", "minor", "--version-file", str(version_file), "--release-notes-file", str(bad_notes)],
    )
    assert result.exit_code != 0


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


def test_release_notes_empty_section(version_file: Path, tmp_path: Path) -> None:
    notes = tmp_path / "RELEASE_NOTES.md"
    notes.write_text("# Release Notes\n\n## Latest Changes\n\n## 0.1.0 (2025-01-01)\n")
    result = runner.invoke(
        app,
        ["release-notes", "--version-file", str(version_file), "--release-notes-file", str(notes)],
    )
    assert result.exit_code != 0
