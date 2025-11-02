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
            shell_type = detect_shell()
            if shell_type == "pwsh":
                full_command = f'powershell.exe -Command "{command}"'
            else:
                full_command = f'cmd.exe /c "{command}"'
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=True,
            )
        else:
            # Unix-like systems: use detected shell or fallback
            shell = os.environ.get("SHELL", "/bin/sh")
            full_command = f"{shell} -c {shlex.quote(command)}"
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=True,
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
