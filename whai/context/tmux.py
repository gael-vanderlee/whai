"""Tmux context capture for whai."""

import os
import re
import subprocess
from typing import Optional

from whai.constants import (
    CONTEXT_CAPTURE_TIMEOUT,
    TMUX_SCROLLBACK_LINES,
    WSL_CHECK_TIMEOUT,
)
from whai.logging_setup import get_logger

logger = get_logger(__name__)


def _is_wsl() -> bool:
    """
    Check if we're running on Windows with WSL available.

    Returns:
        True if WSL is available on Windows, False otherwise.
    """
    if os.name != "nt":
        return False

    try:
        result = subprocess.run(
            ["wsl", "--status"], capture_output=True, timeout=WSL_CHECK_TIMEOUT
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _matches_command_pattern(line: str, command: str) -> bool:
    """
    Check if a line matches the command pattern.

    Handles variations like prompts, quotes, and whitespace.
    Avoids false positives from substring matches (e.g., "whai" in "whaiting").
    Excludes log lines (lines starting with [INFO], [DEBUG], etc.).

    Args:
        line: Line from context to check.
        command: Command to match against.

    Returns:
        True if the line contains the command pattern and appears to be a command line.
    """
    if not command:
        return False

    # Exclude log lines - these typically start with log level markers
    if re.match(r"^\s*\[(INFO|DEBUG|ERROR|WARNING|CRITICAL)\]", line):
        return False

    # Exclude lines that are clearly whai's log output (contain log message patterns)
    # This catches log lines that might have formatting before the log level marker
    if re.search(
        r"(Will exclude command from context|Found matching command at line|Filtered.*from tmux context|Captured.*scrollback)",
        line,
    ):
        return False

    # Normalize whitespace
    line_normalized = " ".join(line.split())
    command_normalized = " ".join(command.split())

    # Normalize quotes: remove quotes around arguments to handle cases where
    # sys.argv has "whai -vv" but terminal shows "whai -vv"
    # We'll compare after removing surrounding quotes from each argument
    def normalize_quotes(text: str) -> str:
        """Remove quotes around words/arguments while preserving structure."""
        # Replace quoted strings (may contain spaces) with unquoted versions
        # This handles: "DEBUG" -> DEBUG, "some text" -> some text, 'test' -> test
        # But preserves quotes in the middle like: don't -> don't
        # Match double-quoted strings (with spaces allowed inside)
        text = re.sub(r'"([^"]+)"', r"\1", text)
        # Match single-quoted strings (with spaces allowed inside)
        text = re.sub(r"'([^']+)'", r"\1", text)
        return text

    line_quote_normalized = normalize_quotes(line_normalized)
    command_quote_normalized = normalize_quotes(command_normalized)

    # Escape special regex characters in the command
    escaped_command = re.escape(command_quote_normalized)

    # Match the command with word boundaries to avoid substring matches
    # The pattern ensures the command appears as a complete phrase or after whitespace/prompt
    # and before whitespace or end of line
    # First check if command starts the line (optionally after prompt characters)
    pattern_start = rf"^[\w@$:/\-\.~]*\s*{escaped_command}(\s|$)"
    # Then check if command appears as a complete word/phrase in the middle
    pattern_middle = rf"\s+{escaped_command}(\s|$)"
    # Finally check if command ends the line
    pattern_end = rf"\s+{escaped_command}$"

    # Try all patterns on quote-normalized line
    for pattern in [pattern_start, pattern_middle, pattern_end]:
        if re.search(pattern, line_quote_normalized):
            return True

    # Also check exact match after prompt removal and quote normalization
    # Remove common prompt patterns
    prompt_removed = re.sub(r"^[\w@$:/\-\.~]+\s+", "", line_quote_normalized)
    if prompt_removed.strip() == command_quote_normalized:
        return True

    return False


def _get_tmux_context(exclude_command: Optional[str] = None) -> Optional[str]:
    """
    Get context from tmux scrollback buffer.

    Captures scrollback history
    providing deep context including commands and their outputs.

    Args:
        exclude_command: Command pattern to filter out from the context.

    Returns:
        Tmux pane content if available, None otherwise.
    """
    # Check if we're in a tmux session
    if "TMUX" not in os.environ:
        return None

    try:
        # On Windows with WSL, run tmux command through WSL
        if os.name == "nt" and _is_wsl():
            result = subprocess.run(
                [
                    "wsl",
                    "tmux",
                    "capture-pane",
                    "-p",
                    "-S",
                    f"-{TMUX_SCROLLBACK_LINES}",
                ],
                capture_output=True,
                text=True,
                timeout=CONTEXT_CAPTURE_TIMEOUT,
            )
        else:
            # On Unix-like systems, run tmux directly
            result = subprocess.run(
                ["tmux", "capture-pane", "-p", "-S", f"-{TMUX_SCROLLBACK_LINES}"],
                capture_output=True,
                text=True,
                timeout=CONTEXT_CAPTURE_TIMEOUT,
            )

        if result.returncode == 0:
            output = result.stdout

            # Filter out the last occurrence of the command and everything after it
            if exclude_command:
                lines = output.split("\n")

                # Find the last occurrence of the command line (search from end)
                last_command_index = None
                for i in range(len(lines) - 1, -1, -1):
                    if _matches_command_pattern(lines[i], exclude_command):
                        last_command_index = i
                        logger.info(
                            "Found matching command at line %d: %s",
                            i,
                            lines[i][:100] if len(lines[i]) > 100 else lines[i],
                        )
                        break

                # If we found the command, remove it and everything after
                if last_command_index is not None:
                    filtered_lines = lines[:last_command_index]
                    output = "\n".join(filtered_lines)
                    removed_count = len(lines) - len(filtered_lines)
                    logger.info(
                        "Filtered %d line(s) from tmux context (removed command at index %d and everything after)",
                        removed_count,
                        last_command_index,
                    )
                else:
                    logger.debug("No matching command found in tmux context to exclude")

            logger.info(
                "Captured tmux scrollback (%d chars)",
                len(output),
            )
            return output
        else:
            return None

    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
