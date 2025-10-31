"""Context capture from tmux or shell history."""

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from terma.logging_setup import get_logger
from terma.utils import detect_shell

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


def _get_tmux_context() -> Optional[str]:
    """
    Get context from tmux scrollback buffer.

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
            logger.debug(
                "Captured tmux scrollback (%d chars)",
                len(result.stdout),
                extra={"category": "perf"},
            )
            return result.stdout
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
    max_commands: int = 50, shell: Optional[str] = None
) -> Optional[str]:
    """
    Get context from shell history file.

    Args:
        max_commands: Maximum number of commands to include.

    Returns:
        Formatted history string if available, None otherwise.
    """
    shell = shell or _get_shell_from_env()
    home = Path.home()

    # Prefer explicit zsh/bash history if the shell is known, regardless of OS
    commands: list[str] = []
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

    # Format as a readable history
    formatted = "Recent command history:\n"
    for i, cmd in enumerate(commands, 1):
        formatted += f"{i}. {cmd}\n"

    logger.debug(
        "Captured history (%d commands) using shell=%s",
        len(commands),
        shell,
        extra={"category": "perf"},
    )
    return formatted


def get_context(max_commands: int = 50) -> Tuple[str, bool]:
    """
    Get terminal context for the LLM.

    Tries to get tmux scrollback first (deep context with command output).
    Falls back to shell history (shallow context with commands only).

    Args:
        max_commands: Maximum number of history commands to include in fallback.

    Returns:
        Tuple of (context_string, is_deep_context).
        - context_string: The captured context or empty string if none available.
        - is_deep_context: True if tmux context (includes output), False if history only.
    """
    # Try tmux context first
    tmux_context = _get_tmux_context()
    if tmux_context:
        return tmux_context, True

    # Fall back to history (determine shell once and pass through)
    detected_shell = _get_shell_from_env()
    history_context = _get_history_context(max_commands, shell=detected_shell)
    if history_context:
        return history_context, False

    # No context available
    return "", False
