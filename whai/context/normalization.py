"""Utilities for normalizing captured session logs."""

from __future__ import annotations

import re


def apply_backspaces(text: str) -> str:
    """Apply backspace characters to reconstruct intended text."""
    result: list[str] = []
    for ch in text:
        if ch in ("\b", "\x08"):
            if result:
                result.pop()
        else:
            result.append(ch)
    return "".join(result)


_CSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_OSC_PATTERN = re.compile(r"\x1b\][0-9]+;[^\x07\x1b\\]*[\x07\x1b\\]")
_SINGLE_ESC_PATTERN = re.compile(r"\x1b[=><OP]")
_CONTROL_ONLY_PATTERN = re.compile(r"^[\x1b\[\]\x08\r\x07\s]*$")
_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_LINE_PATTERN = re.compile(
    rf"^.*[{_SPINNER_CHARS}].*Thinking.*$|^.*Thinking.*\[2K.*$",
    re.IGNORECASE,
)


def normalize_unix_log(text: str) -> str:
    """Normalize Unix/Linux script output by removing terminal artefacts."""
    lines = text.splitlines()
    cleaned: list[str] = []

    for line in lines:
        if "\x08" in line or "\b" in line:
            line = apply_backspaces(line)

        line = _CSI_PATTERN.sub("", line)
        line = _OSC_PATTERN.sub("", line)
        line = _SINGLE_ESC_PATTERN.sub("", line)
        line = re.sub(r"\[\d+m", "", line)
        line = re.sub(r"[\x08\r\x07]", "", line)

        if _SPINNER_LINE_PATTERN.match(line):
            continue

        if _CONTROL_ONLY_PATTERN.match(line):
            continue

        if re.match(rf"^[{_SPINNER_CHARS}\s]*$", line):
            continue

        if re.match(rf"^[{_SPINNER_CHARS}]\s*Thinking\s*$", line, re.IGNORECASE):
            continue

        if re.match(r"^\[2K|\[1A|\[25h|\[25l|\[\?1h|\[\?1l|\[\?2004h|\[\?2004l$", line):
            continue

        if re.search(r"\[2K$|\[1A$|\[25h$|\[25l$", line):
            stripped = re.sub(r"\[2K|\[1A|\[25h|\[25l", "", line).strip()
            if stripped.lower() in ("thinking", ""):
                continue

        line = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", line)

        stripped_line = line.strip()
        if stripped_line in {"%", "\\"}:
            continue

        if not stripped_line:
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def normalize_powershell_transcript(text: str) -> str:
    """Normalize PowerShell transcript while preserving useful metadata."""
    lines = text.splitlines()
    cleaned: list[str] = []
    in_metadata_block = False
    metadata: dict[str, str] = {}

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("**********************"):
            if not in_metadata_block:
                in_metadata_block = True
            else:
                if metadata:
                    cleaned.append("--- PowerShell Session ---")
                    for key, value in metadata.items():
                        cleaned.append(f"{key}: {value}")
                    cleaned.append("---")
                    metadata = {}
                in_metadata_block = False
            i += 1
            continue

        if in_metadata_block:
            if line.startswith("PowerShell transcript start"):
                metadata["Session"] = "PowerShell transcript"
            elif line.startswith("Start time:"):
                metadata["Start time"] = line.replace("Start time:", "").strip()
            elif line.startswith("Username:"):
                metadata["Username"] = line.replace("Username:", "").strip()
            elif line.startswith("RunAs User:"):
                metadata["RunAs User"] = line.replace("RunAs User:", "").strip()
            elif line.startswith("Machine:"):
                metadata["Machine"] = line.replace("Machine:", "").strip()
            elif line.startswith("OS:"):
                metadata["OS"] = line.replace("OS:", "").strip()
            elif line.startswith("PSVersion:"):
                metadata["PSVersion"] = line.replace("PSVersion:", "").strip()
            i += 1
            continue

        if line.startswith("Command start time:"):
            timestamp = line.replace("Command start time:", "").strip()
            cleaned.append(f"[Command timestamp: {timestamp}]")
            i += 1
            continue

        if line.startswith(">> "):
            i += 1
            continue

        cleaned.append(line)
        i += 1

    if in_metadata_block and metadata:
        cleaned.append("--- PowerShell Session ---")
        for key, value in metadata.items():
            cleaned.append(f"{key}: {value}")
        cleaned.append("---")

    return "\n".join(cleaned).strip()

