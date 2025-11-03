"""Shell history parsing for whai."""

import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from whai.constants import (
    CONTEXT_CAPTURE_TIMEOUT,
    HISTORY_MAX_COMMANDS,
)
from whai.context.tmux import _matches_command_pattern
from whai.logging_setup import get_logger
from whai.utils import detect_shell

logger = get_logger(__name__)


@dataclass
class ShellContextHandler:
    """Base handler for shell-specific context capture."""

    shell_name: str
    executable_path: str = ""

    def get_history_context(
        self,
        max_commands: int = HISTORY_MAX_COMMANDS,
        exclude_command: Optional[str] = None,
    ) -> Optional[str]:
        """Get command history context. Override in subclasses."""
        return None

    def get_additional_context(
        self,
        exclude_command: Optional[str] = None,
    ) -> Optional[str]:
        """Get additional context (errors, session info). Override in subclasses."""
        return None

    def _format_history(
        self, commands: List[str], exclude_command: Optional[str] = None
    ) -> Optional[str]:
        """Format commands into history string."""
        if not commands:
            return None

        if exclude_command:
            if _matches_command_pattern(commands[-1], exclude_command):
                commands = commands[:-1]

        if not commands:
            return None

        formatted = "Recent command history:\n"
        for i, cmd in enumerate(commands, 1):
            formatted += f"{i}. {cmd}\n"

        logger.info(
            "Captured %s history (%d commands)",
            self.shell_name,
            len(commands),
        )
        return formatted


@dataclass
class BashHandler(ShellContextHandler):
    """Handler for bash shell context."""

    def __post_init__(self):
        """Initialize bash handler."""
        if not self.executable_path:
            self.executable_path = "/bin/bash"

    def get_history_context(
        self,
        max_commands: int = HISTORY_MAX_COMMANDS,
        exclude_command: Optional[str] = None,
    ) -> Optional[str]:
        """Get bash history from ~/.bash_history."""
        history_file = Path.home() / ".bash_history"
        if not history_file.exists():
            return None

        try:
            with open(history_file, "r", encoding="utf-8", errors="ignore") as f:
                commands = [line.rstrip("\n") for line in f if line.strip()]
        except Exception:
            return None

        commands = commands[-max_commands:] if commands else []
        return self._format_history(commands, exclude_command)


@dataclass
class ZshHandler(ShellContextHandler):
    """Handler for zsh shell context."""

    def __post_init__(self):
        """Initialize zsh handler."""
        if not self.executable_path:
            self.executable_path = "/bin/zsh"

    def get_history_context(
        self,
        max_commands: int = HISTORY_MAX_COMMANDS,
        exclude_command: Optional[str] = None,
    ) -> Optional[str]:
        """Get zsh history from ~/.zsh_history."""
        history_file = Path.home() / ".zsh_history"
        if not history_file.exists():
            return None

        commands = []
        try:
            with open(history_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.rstrip("\n")
                    if line.startswith(":"):
                        # Format: : <timestamp>:<duration>;<command>
                        parts = line.split(";", 1)
                        if len(parts) == 2:
                            commands.append(parts[1])
                    elif line.strip():
                        commands.append(line)
        except Exception:
            return None

        commands = commands[-max_commands:] if commands else []
        return self._format_history(commands, exclude_command)


@dataclass
class PowerShellHandler(ShellContextHandler):
    """Handler for PowerShell context."""

    powershell_exe: str = field(default="")

    def __post_init__(self):
        """Initialize PowerShell handler."""
        if not self.powershell_exe:
            if os.name == "nt":
                pwsh_path = shutil.which("pwsh")
                self.powershell_exe = pwsh_path or "powershell.exe"
            else:
                self.powershell_exe = "pwsh"
        if not self.executable_path:
            self.executable_path = self.powershell_exe

    def get_history_context(
        self,
        max_commands: int = HISTORY_MAX_COMMANDS,
        exclude_command: Optional[str] = None,
    ) -> Optional[str]:
        """Get PowerShell history from PSReadLine."""
        if os.name != "nt":
            return None

        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None

        appdata_path = Path(appdata)
        candidates = [
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

        for candidate in candidates:
            if candidate.exists():
                try:
                    with open(candidate, "r", encoding="utf-8", errors="ignore") as f:
                        raw_lines = [line.rstrip("\n") for line in f if line.strip()]
                        commands = []
                        for cmd in raw_lines:
                            # Collapse repeated backslashes to a single backslash
                            cmd_norm = cmd.replace("\\\\", "\\")
                            cmd_norm = cmd_norm.replace("\\\\", "\\")
                            commands.append(cmd_norm)
                        commands = commands[-max_commands:] if commands else []
                        return self._format_history(commands, exclude_command)
                except Exception:
                    continue

        return None

    # No additional context for PowerShell beyond history


@dataclass
class CMDHandler(ShellContextHandler):
    """Handler for Windows CMD context."""

    def __post_init__(self):
        """Initialize CMD handler."""
        if not self.executable_path:
            self.executable_path = "cmd.exe"

    def get_history_context(
        self,
        max_commands: int = HISTORY_MAX_COMMANDS,
        exclude_command: Optional[str] = None,
    ) -> Optional[str]:
        """Get CMD history from DOSKEY (session-only)."""
        if os.name != "nt":
            return None

        try:
            result = subprocess.run(
                ["doskey", "/history"],
                capture_output=True,
                text=True,
                timeout=CONTEXT_CAPTURE_TIMEOUT,
            )

            if result.returncode == 0 and result.stdout.strip():
                commands = [
                    line.strip()
                    for line in result.stdout.strip().split("\n")
                    if line.strip()
                ]
                commands = commands[-max_commands:] if commands else []
                return self._format_history(commands, exclude_command)
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug("Failed to capture CMD history: %s", e)

        return None


# Registry of shell handlers
_SHELL_HANDLERS: Dict[str, ShellContextHandler] = {
    "bash": BashHandler(shell_name="bash"),
    "zsh": ZshHandler(shell_name="zsh"),
    "pwsh": PowerShellHandler(shell_name="pwsh"),
    "cmd": CMDHandler(shell_name="cmd"),
}


def _get_shell_from_env() -> str:
    """Detect the current shell from environment variables."""
    return detect_shell()


def get_shell_executable(shell_name: Optional[str] = None) -> str:
    """Get the executable path for a shell."""
    if shell_name is None:
        shell_name = _get_shell_from_env()

    handler = _get_handler_for_shell(shell_name)
    if handler:
        return handler.executable_path

    # Fallback
    if os.name == "nt":
        return "powershell.exe"
    return "/bin/bash"


def _get_handler_for_shell(shell: Optional[str] = None) -> Optional[ShellContextHandler]:
    """Get the context handler for a specific shell."""
    if shell is None:
        shell = _get_shell_from_env()

    # Try exact match first
    handler = _SHELL_HANDLERS.get(shell)
    if handler:
        return handler

    # Windows fallback: if not PowerShell, assume CMD
    if os.name == "nt" and shell != "pwsh":
        handler = _SHELL_HANDLERS.get("cmd")
        if handler:
            return handler

    # Fallback: try partial matches
    shell_lower = shell.lower()
    for handler_shell, handler_instance in _SHELL_HANDLERS.items():
        if handler_shell in shell_lower or shell_lower in handler_shell:
            return handler_instance

    return None


def _get_history_context(
    max_commands: int = HISTORY_MAX_COMMANDS,
    shell: Optional[str] = None,
    exclude_command: Optional[str] = None,
) -> Optional[str]:
    """Get context from shell history file."""
    handler = _get_handler_for_shell(shell)

    if handler:
        return handler.get_history_context(max_commands, exclude_command)

    # Fallback: try common history files (Unix shells)
    if os.name != "nt":
        home = Path.home()
        zsh_history = home / ".zsh_history"
        bash_history = home / ".bash_history"

        if zsh_history.exists():
            handler = _SHELL_HANDLERS.get("zsh")
            if handler:
                return handler.get_history_context(max_commands, exclude_command)
        elif bash_history.exists():
            handler = _SHELL_HANDLERS.get("bash")
            if handler:
                return handler.get_history_context(max_commands, exclude_command)

    logger.warning("No history commands found for shell=%s", shell)
    return None


def get_additional_context(
    shell: Optional[str] = None,
    exclude_command: Optional[str] = None,
) -> Optional[str]:
    """Get additional context (errors, session info) for the shell."""
    handler = _get_handler_for_shell(shell)

    if handler:
        return handler.get_additional_context(exclude_command)

    return None
