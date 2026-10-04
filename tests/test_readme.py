from pathlib import Path

from scripts.generate_readme import generate_readme

README = Path(__file__).parent.parent / "README.md"


def test_readme_matches_what_the_docs_generate() -> None:
    """Regenerate it with `uv run python scripts/generate_readme.py`."""
    assert README.read_text(encoding="utf-8") == generate_readme()
