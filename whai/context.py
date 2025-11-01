"""Context capture from tmux or shell history."""

import os
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from whai.logging_setup import get_logger
from whai.utils import detect_shell

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
        result = subprocess.run(["wsl", "--status"], capture_output=True, timeout=2)
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
    # sys.argv has "whai -v DEBUG" but terminal shows "whai -v \"DEBUG\""
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
                ["wsl", "tmux", "capture-pane", "-p"],
                capture_output=True,
                text=True,
                timeout=5,
            )
        else:
            # On Unix-like systems, run tmux directly
            result = subprocess.run(
                ["tmux", "capture-pane", "-p"],
                capture_output=True,
                text=True,
                timeout=5,
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


def _get_shell_from_env() -> str:
    """
    Detect the current shell from environment variables.

    Returns:
        Shell name ('bash', 'zsh', 'pwsh', 'fish').
    """
    # Use centralized shell detection from utils
    return detect_shell()


def get_shell_executable(shell_name: Optional[str] = None) -> str:
    """
    Get the executable path for a shell.

    Args:
        shell_name: Shell name ('bash', 'zsh', 'pwsh', 'fish').
                   If None, auto-detects from environment.

    Returns:
        Path to shell executable.
    """
    if shell_name is None:
        shell_name = _get_shell_from_env()

    # Handle known shells
    if shell_name == "bash":
        return "/bin/bash"
    elif shell_name == "zsh":
        return "/bin/zsh"
    elif shell_name == "pwsh":
        # PowerShell
        if os.name == "nt":
            import shutil

            # Try PowerShell 7 (pwsh) first
            pwsh_path = shutil.which("pwsh")
            if pwsh_path:
                return pwsh_path
            # Fall back to Windows PowerShell 5.1
            return "powershell.exe"
        return "pwsh"
    elif shell_name == "fish":
        return "fish"
    else:
        # Unknown shell, default to bash on Unix, PowerShell on Windows
        if os.name == "nt":
            return "powershell.exe"
        return "/bin/bash"


def _parse_zsh_history(history_file: Path, max_commands: int = 50) -> list:
    """
    Parse zsh history file.

    Zsh history format can include timestamps and multiline commands.
    Format: : <timestamp>:<duration>;<command>

    Args:
        history_file: Path to the history file.
        max_commands: Maximum number of commands to return.

    Returns:
        List of command strings.
    """
    if not history_file.exists():
        return []

    commands = []

    try:
        with open(history_file, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.rstrip("\n")

                # Check if line starts with timestamp
                if line.startswith(":"):
                    # Format: : <timestamp>:<duration>;<command>
                    parts = line.split(";", 1)
                    if len(parts) == 2:
                        commands.append(parts[1])
                else:
                    # Simple command without timestamp
                    if line.strip():
                        commands.append(line)
    except Exception:
        return []

    # Return the last N commands
    return commands[-max_commands:] if commands else []


def _parse_bash_history(history_file: Path, max_commands: int = 50) -> list:
    """
    Parse bash history file.

    Bash history is simpler - one command per line.

    Args:
        history_file: Path to the history file.
        max_commands: Maximum number of commands to return.

    Returns:
        List of command strings.
    """
    if not history_file.exists():
        return []

    try:
        with open(history_file, "r", encoding="utf-8", errors="ignore") as f:
            commands = [line.rstrip("\n") for line in f if line.strip()]
    except Exception:
        return []

    # Return the last N commands
    return commands[-max_commands:] if commands else []


def _get_history_context(
    max_commands: int = 50,
    shell: Optional[str] = None,
    exclude_command: Optional[str] = None,
) -> Optional[str]:
    """
    Get context from shell history file.

    Args:
        max_commands: Maximum number of commands to include.
        shell: Shell name to use for history detection.
        exclude_command: Command pattern to filter out from history.

    Returns:
        Formatted history string if available, None otherwise.
    """
    shell = shell or _get_shell_from_env()
    home = Path.home()

    # Prefer explicit zsh/bash history if the shell is known, regardless of OS
    commands: List[str] = []
    if shell == "zsh":
        history_file = home / ".zsh_history"
        commands = _parse_zsh_history(history_file, max_commands)
    elif shell == "bash":
        history_file = home / ".bash_history"
        commands = _parse_bash_history(history_file, max_commands)

    # If shell-specific history is not available, try platform-specific fallbacks
    if not commands:
        # Windows PowerShell / PowerShell (Core) via PSReadLine history
        # Use when shell is PowerShell or unknown on Windows.
        if os.name == "nt" and shell in {"powershell", "pwsh", "unknown"}:
            appdata = os.environ.get("APPDATA")
            psreadline_candidates = []

            if appdata:
                appdata_path = Path(appdata)
                psreadline_candidates.extend(
                    [
                        appdata_path
                        / "Microsoft"
                        / "Windows"
                        / "PowerShell"
                        / "PSReadLine"
                        / "ConsoleHost_history.txt",
                        appdata_path
                        / "Microsoft"
                        / "PowerShell"
                        / "PSReadLine"
                        / "ConsoleHost_history.txt",
                    ]
                )

            for candidate in psreadline_candidates:
                if candidate.exists():
                    try:
                        with open(
                            candidate, "r", encoding="utf-8", errors="ignore"
                        ) as f:
                            # Normalize path backslashes (e.g., 'C:\\Temp' -> 'C:\\Temp')
                            raw_lines = [
                                line.rstrip("\n") for line in f if line.strip()
                            ]
                            normalized = []
                            for cmd in raw_lines:
                                # Collapse repeated backslashes to a single backslash
                                # Do it twice to handle longer runs without a loop
                                cmd_norm = cmd.replace("\\\\", "\\")
                                cmd_norm = cmd_norm.replace("\\\\", "\\")
                                normalized.append(cmd_norm)
                            file_commands = normalized
                        commands = (
                            file_commands[-max_commands:] if file_commands else []
                        )
                    except Exception:
                        commands = []
                    break

        # On non-Windows or if PSReadLine not found, try typical *nix history files
        if not commands:
            zsh_history = home / ".zsh_history"
            bash_history = home / ".bash_history"
            if zsh_history.exists():
                commands = _parse_zsh_history(zsh_history, max_commands)
            elif bash_history.exists():
                commands = _parse_bash_history(bash_history, max_commands)

    if not commands:
        logger.warning("No history commands found")
        return None

    # Filter out the last command if it matches the exclude pattern
    if exclude_command and commands:
        logger.debug(
            "Checking history context (%d commands) for command to exclude: %s",
            len(commands),
            exclude_command,
        )
        # Check if the last command matches the pattern
        if _matches_command_pattern(commands[-1], exclude_command):
            logger.info(
                "Found matching last command in history: %s",
                commands[-1][:100] if len(commands[-1]) > 100 else commands[-1],
            )
            commands = commands[:-1]
            logger.info(
                "Filtered last command from history context (%d commands remaining)",
                len(commands),
            )
        else:
            logger.debug(
                "Last command in history does not match exclude pattern: %s",
                commands[-1][:100] if len(commands[-1]) > 100 else commands[-1],
            )

    if not commands:
        logger.warning("No history commands remaining after filtering")
        return None

    # Format as a readable history
    formatted = "Recent command history:\n"
    for i, cmd in enumerate(commands, 1):
        formatted += f"{i}. {cmd}\n"

    logger.info(
        "Captured history (%d commands) using shell=%s",
        len(commands),
        shell,
    )
    return formatted


def get_context(
    max_commands: int = 50, exclude_command: Optional[str] = None
) -> Tuple[str, bool]:
    """
    Get terminal context for the LLM.

    Tries to get tmux scrollback first (deep context with command output).
    Falls back to shell history (shallow context with commands only).

    Args:
        max_commands: Maximum number of history commands to include in fallback.
        exclude_command: Command pattern to filter out from context.

    Returns:
        Tuple of (context_string, is_deep_context).
        - context_string: The captured context or empty string if none available.
        - is_deep_context: True if tmux context (includes output), False if history only.
    """
    # Try tmux context first
    tmux_context = _get_tmux_context(exclude_command=exclude_command)
    if tmux_context:
        return tmux_context, True

    # Fall back to history (determine shell once and pass through)
    detected_shell = _get_shell_from_env()
    history_context = _get_history_context(
        max_commands, shell=detected_shell, exclude_command=exclude_command
    )
    if history_context:
        return history_context, False

    # No context available
    return "", False
