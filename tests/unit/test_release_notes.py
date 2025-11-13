from pathlib import Path

import pytest

from whai.doc.release_notes import extract_release_entries, extract_release_notes, format_entries


@pytest.fixture
def sample_changelog(tmp_path: Path) -> Path:
    content = (
        "# Changelog\n"
        "\n"
        "## v0.8.0\n"
        "\n"
        "[2025-11-13] [feature] [ui]: add spinner indicator\n"
        "[2025-11-13] [fix] [cli]: warn on flags\n"
        "\n"
        "## v0.7.2\n"
        "[2025-11-12] [docs] [readme]: document providers\n"
    )
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(content, encoding="utf-8")
    return changelog


def test_extract_release_entries_skips_leading_blank_lines():
    lines = [
        "# Changelog",
        "",
        "## v0.8.0",
        "",
        "[2025-11-13] [feature] [ui]: add spinner indicator",
        "",
        "## v0.7.2",
        "[2025-11-12] [docs] [readme]: document providers",
    ]

    entries = extract_release_entries(lines, "0.8.0")

    assert entries == [
        "[2025-11-13] [feature] [ui]: add spinner indicator",
    ]


def test_extract_release_notes_reads_file(sample_changelog: Path):
    notes = extract_release_notes(sample_changelog, "0.8.0")

    assert "- [Feature] [Ui]: Add spinner indicator" in notes
    assert "- [Fix] [Cli]: Warn on flags" in notes


def test_format_entries_without_matches():
    assert (
        format_entries([])
        == "No changelog entries found for this version."
    )


def test_format_entries_transforms_tags_and_sentence():
    result = format_entries(["[2025-11-13] [change] [prompt]: add separators around examples"])

    assert result == "- [Change] [Prompt]: Add separators around examples"


def test_format_entries_sorts_by_category_weight():
    entries = [
        "[2025-11-12] [test] [context]: add coverage",
        "[2025-11-11] [feature] [ui]: add spinner",
        "[2025-11-10] [fix] [cli]: fix parsing",
    ]

    result = format_entries(entries).splitlines()

    assert result == [
        "- [Feature] [Ui]: Add spinner",
        "- [Fix] [Cli]: Fix parsing",
        "- [Test] [Context]: Add coverage",
    ]

