"""
Utilities for extracting release notes from the project changelog.

This module is used by the release workflow to build the GitHub release
notes. It also exposes a CLI for local verification and unit testing.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, List


DATE_PREFIX_PATTERN = re.compile(r"^\[\d{4}-\d{2}-\d{2}\]")
TAG_PATTERN = re.compile(r"\[([^\]]+)\]")

TAG_WEIGHTS = {
    "feature": 0,
    "security": 1,
    "fix": 2,
    "change": 3,
    "docs": 4,
    "chore": 5,
    "test": 6,
}
DEFAULT_TAG_WEIGHT = max(TAG_WEIGHTS.values()) + 1


def capitalize_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    return text[0].upper() + text[1:]


def capitalize_tag(tag: str) -> str:
    if not tag:
        return tag
    leading = tag[0].upper()
    return f"{leading}{tag[1:]}"


def normalize_entry(entry: str) -> str:
    """
    Remove the date prefix, capitalize tags, and ensure the description starts
    with a capital letter. If the format is unexpected, fall back to the
    original entry.
    """
    if ":" not in entry:
        return entry

    prefix, message = entry.split(":", 1)
    tags = TAG_PATTERN.findall(prefix)

    if len(tags) < 2:
        return entry

    normalized_tags = [f"[{capitalize_tag(tag)}]" for tag in tags[1:]]
    description = capitalize_sentence(message)

    return f"{' '.join(normalized_tags)}: {description}"


def extract_release_entries(lines: Iterable[str], version: str) -> List[str]:
    """
    Extract changelog entries for a specific version.

    The function accepts the raw lines of the changelog and the target
    version string (e.g. "0.8.0"). It tolerates blank lines directly under
    the version heading and stops once it reaches the next heading or an
    empty separator line after collecting at least one entry.
    """
    header_variants = (f"## {version}", f"## v{version}")
    entries: List[str] = []
    in_section = False
    collected_entry = False

    for raw_line in lines:
        stripped = raw_line.strip()

        if stripped.startswith("## "):
            if any(variant == stripped for variant in header_variants):
                in_section = True
                collected_entry = False
                continue
            if in_section:
                break

        if not in_section:
            continue

        if not stripped:
            if collected_entry:
                break
            continue

        if DATE_PREFIX_PATTERN.match(stripped):
            entries.append(stripped)
            collected_entry = True

    return entries


def format_entries(entries: Iterable[str]) -> str:
    """
    Format changelog entries for GitHub release notes.
    """
    original_entries = list(entries)
    if not original_entries:
        return "No changelog entries found for this version."

    sorted_entries = sorted(
        original_entries,
        key=lambda entry: (get_entry_weight(entry), entry.lower()),
    )
    items = [normalize_entry(entry) for entry in sorted_entries]
    return "\n".join(f"- {entry}" for entry in items)


def get_entry_weight(entry: str) -> int:
    """
    Determine sort weight based on the primary tag (category).
    """
    tags = TAG_PATTERN.findall(entry)
    if len(tags) < 2:
        return DEFAULT_TAG_WEIGHT
    primary_tag = tags[1].lower()
    return TAG_WEIGHTS.get(primary_tag, DEFAULT_TAG_WEIGHT)


def extract_release_notes(changelog_path: Path, version: str) -> str:
    """
    Read the changelog file and return formatted release notes.
    """
    lines = changelog_path.read_text(encoding="utf-8").splitlines()
    entries = extract_release_entries(lines, version)
    return format_entries(entries)


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Extract release notes from the changelog.")
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("whai/doc/CHANGELOG.md"),
        help="Path to CHANGELOG.md.",
    )
    parser.add_argument("--version", required=True, help="Version string, e.g. 0.8.0.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("release_notes.txt"),
        help="Path to write the formatted release notes.",
    )

    args = parser.parse_args(argv)
    notes = extract_release_notes(args.changelog, args.version)
    args.output.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()

