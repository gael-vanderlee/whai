"""System prompt generation for whai."""

import os
import platform
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from whai.logging_setup import get_logger

logger = get_logger(__name__)


def get_base_system_prompt(is_deep_context: bool, timeout: int = None) -> str:
    """
    Get the base system prompt that is prepended to all conversations.

    Args:
        is_deep_context: Whether we have deep context (tmux) or shallow (history).
        timeout: Optional command timeout in seconds. If provided, adds timeout info to context.

    Returns:
        The base system prompt string.

    Raises:
        FileNotFoundError: If the system prompt template file doesn't exist.
    """
    # Build context note with system information
    context_parts = []

    # Terminal history context
    if is_deep_context:
        context_parts.append(
            "You will be given the recent terminal scrollback (commands and their output) along with the user message."
        )
    else:
        context_parts.append(
            "You will be given ONLY the recent command history of the user (commands only, no command outputs). CRITICAL: In this mode, you cannot see your own previous responses. Do NOT end with questions like 'Do you want me to run X?' or suggestions requiring you to remember this conversation. Provide complete, standalone answers."
        )

    # System information
    system_info = []

    # Operating system
    os_name = platform.system()
    os_release = platform.release()
    system_info.append(f"OS: {os_name} {os_release}")

    # Shell (from environment or detect)
    shell_path = os.environ.get("SHELL", "")
    if shell_path:
        shell_name = Path(shell_path).name
        system_info.append(f"Shell: {shell_name}")
    elif os.name == "nt":
        # Windows detection
        if "PSModulePath" in os.environ:
            system_info.append("Shell: PowerShell")
        else:
            system_info.append("Shell: cmd.exe")

    # Current working directory
    try:
        cwd = os.getcwd()
        system_info.append(f"CWD: {cwd}")
    except Exception:
        pass

    # Current date and time
    current_datetime = datetime.now()
    datetime_str = current_datetime.strftime('%Y-%m-%d %H:%M:%S')
    # Add timezone if available
    tz_str = current_datetime.strftime('%Z')
    if tz_str:
        datetime_str += f" {tz_str}"
    else:
        # Fallback: use timezone offset
        tz_offset = current_datetime.strftime('%z')
        if tz_offset:
            datetime_str += f" {tz_offset}"
    system_info.append(f"DateTime: {datetime_str}")

    # Timeout information
    if timeout is not None:
        context_parts.append(
            f"The user configured a {timeout} seconds timeout on your commands; "
            "If the command doesn't finish executing in that time it will be interrupted."
        )

    if system_info:
        context_parts.append("System: " + " | ".join(system_info))

    context_note = " ".join(context_parts)

    # Read from packaged defaults file
    system_prompt_file = files("whai").joinpath("defaults", "system_prompt.txt")

    if not system_prompt_file.exists():
        raise FileNotFoundError(
            f"System prompt template not found at {system_prompt_file}. "
            "This indicates a broken installation. Please reinstall whai."
        )

    template = system_prompt_file.read_text()
    logger.info(
        "Loaded system prompt template from %s",
        system_prompt_file,
    )
    return template.format(context_note=context_note)
