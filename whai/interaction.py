"""Command execution and approval loop."""

import os
import shlex
import subprocess
from typing import Optional, Tuple

from rich.text import Text

from whai import ui
from whai.constants import DEFAULT_COMMAND_TIMEOUT, UI_TEXT_STYLE_PROMPT
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


def approval_loop(command: str) -> Optional[str]:
    """
    Present a command to the user for approval.

    Args:
        command: The command to approve.

    Returns:
        The approved command (possibly modified), or None if rejected.
    """
    ui.console.print()
    ui.print_command(command)

    while True:
        try:
            ui.console.print(
                Text("[a]pprove / [r]eject / [m]odify: ", style=UI_TEXT_STYLE_PROMPT),
                end="",
            )
            response = input().strip().lower()

            if response == "a" or response == "approve":
                logger.debug("Command approved as-is", extra={"category": "cmd"})
                return command
            elif response == "r" or response == "reject":
                ui.info("Command rejected.")
                logger.debug("Command rejected by user", extra={"category": "cmd"})
                return None
            elif response == "m" or response == "modify":
                modified = input("Enter modified command: ").strip()
                if modified:
                    logger.debug(
                        "Command modified by user: %s",
                        modified,
                        extra={"category": "cmd"},
                    )
                    return modified
                else:
                    ui.warn("No command entered. Please try again.")
            else:
                ui.warn("Invalid response. Please enter 'a', 'r', or 'm'.")
        except (EOFError, KeyboardInterrupt):
            ui.info("\nRejected.")
            logger.debug(
                "Command rejected via interrupt/EOF", extra={"category": "cmd"}
            )
            return None


def parse_tool_calls(response_chunks: list) -> list:
    """
    Parse tool calls from LLM response chunks.

    Args:
        response_chunks: List of response chunks from LLM.

    Returns:
        List of tool call dicts with 'name' and 'arguments' keys.
    """
    tool_calls = []

    for chunk in response_chunks:
        if chunk.get("type") == "tool_call":
            tool_calls.append(
                {
                    "id": chunk.get("id"),
                    "name": chunk.get("name"),
                    "arguments": chunk.get("arguments", {}),
                }
            )

    logger.debug(
        "parse_tool_calls extracted %d tool calls",
        len(tool_calls),
        extra={"category": "api"},
    )
    return tool_calls
