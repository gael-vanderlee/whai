"""Command execution for whai."""

import os
import shlex
import subprocess
from typing import Tuple

from whai.constants import DEFAULT_COMMAND_TIMEOUT
from whai.logging_setup import get_logger
from whai.utils import detect_shell, is_windows

logger = get_logger(__name__)


def execute_command(
    command: str, timeout: int = DEFAULT_COMMAND_TIMEOUT
) -> Tuple[str, str, int]:
    """
    Execute a shell command and return its output.

    Each command runs independently in a fresh subprocess.
    State like cd or export does NOT persist between commands.

    Args:
        command: The command to execute.
        timeout: Maximum time to wait for command completion (seconds).

    Returns:
        Tuple of (stdout, stderr, return_code).

    Raises:
        subprocess.TimeoutExpired: If command execution exceeds timeout.
        RuntimeError: For other execution errors.
    """

    try:
        if is_windows():
            # Windows: use detected shell (PowerShell or cmd)
            # Don't use shell=True to ensure timeout works properly.
            # When shell=True, subprocess wraps command in cmd.exe, creating a process hierarchy.
            # On Windows, killing the parent (cmd.exe) doesn't properly terminate child processes
            # (PowerShell), causing timeouts to fail. Invoking the shell directly avoids this issue.
            shell_type = detect_shell()
            if shell_type == "pwsh":
                # PowerShell: pass command directly, PowerShell handles quoting
                result = subprocess.run(
                    ["powershell.exe", "-Command", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
            else:
                # cmd.exe: use /c with the command
                result = subprocess.run(
                    ["cmd.exe", "/c", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
        else:
            # Unix-like systems: use detected shell or fallback
            # Don't use shell=True to ensure timeout works properly
            shell = os.environ.get("SHELL", "/bin/sh")
            result = subprocess.run(
                [shell, "-c", command],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )

        logger.debug(
            "Command completed; stdout_len=%d stderr_len=%d rc=%d",
            len(result.stdout),
            len(result.stderr),
            result.returncode,
            extra={"category": "cmd"},
        )
        return result.stdout, result.stderr, result.returncode

    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Command timed out after {timeout} seconds. You can change timeout limits with the --timeout flag"
        )
    except Exception as e:
        raise RuntimeError(f"Error executing command: {e}")
