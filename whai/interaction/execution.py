"""Command execution for whai."""

import os
import shutil
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
        timeout: Maximum time to wait for command completion (seconds). Use 0 for infinite timeout (no limit).

    Returns:
        Tuple of (stdout, stderr, return_code).

    Raises:
        subprocess.TimeoutExpired: If command execution exceeds timeout.
        RuntimeError: For other execution errors.
    """
    # Convert 0 to None for infinite timeout
    timeout_for_subprocess = None if timeout == 0 else timeout

    try:
        if is_windows():
            # Windows: use detected shell (PowerShell or cmd)
            # Don't use shell=True to ensure timeout works properly.
            # When shell=True, subprocess wraps command in cmd.exe, creating a process hierarchy.
            # On Windows, killing the parent (cmd.exe) doesn't properly terminate child processes
            # (PowerShell), causing timeouts to fail. Invoking the shell directly avoids this issue.
            shell_type = detect_shell()
            if shell_type == "pwsh" or shell_type == "powershell":
                # PowerShell: detect_shell() already determined which version is available
                # Resolve to actual executable path
                shell_exe = shutil.which(shell_type) or shutil.which("powershell") or "powershell.exe"
                result = subprocess.run(
                    [shell_exe, "-Command", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_for_subprocess,
                )
            elif shell_type == "cmd":
                # CMD: use /c with the command
                result = subprocess.run(
                    ["cmd.exe", "/c", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_for_subprocess,
                )
            else:
                # Unknown Windows shell, try cmd as fallback
                result = subprocess.run(
                    ["cmd.exe", "/c", command],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_for_subprocess,
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
                timeout=timeout_for_subprocess,
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
        timeout_msg = f"{timeout} seconds" if timeout > 0 else "infinite timeout"
        raise RuntimeError(
            f"Command timed out after {timeout_msg}. You can change timeout limits with the --timeout flag"
        )
    except Exception as e:
        raise RuntimeError(f"Error executing command: {e}")
