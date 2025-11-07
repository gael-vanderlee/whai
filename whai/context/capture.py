"""Main context capture function for whai."""

import os
from typing import Optional, Tuple

from whai.constants import HISTORY_MAX_COMMANDS
from whai.context.history import (
    _get_history_context,
    _get_shell_from_env,
    get_additional_context,
)
from whai.context.tmux import _get_tmux_context
from whai.logging_setup import get_logger

from .session_reader import read_session_context

logger = get_logger(__name__)


def get_context(
    max_commands: int = HISTORY_MAX_COMMANDS, exclude_command: Optional[str] = None
) -> Tuple[str, bool]:
    """Get terminal context for the LLM.

    Priority order:
    1. Tmux scrollback (deep context with command output)
    2. Recorded whai shell session (deep context with command output)
    3. Shell history (shallow context with commands only)

    For PowerShell on Windows, also includes $Error context when available.

    Args:
        max_commands: Maximum number of history commands to include in fallback.
        exclude_command: Command pattern to filter out from context.

    Returns:
        Tuple of (context_string, is_deep_context).
        - context_string: The captured context or empty string if none available.
        - is_deep_context: True if tmux/session context (includes output), False if history only.
    """
    tmux_context = _get_tmux_context(exclude_command=exclude_command)
    # Check if tmux is active (even if capture is empty)
    is_tmux_active = "TMUX" in os.environ
    if tmux_context is not None:
        # tmux_context can be empty string if tmux is active but pane is empty
        return tmux_context, True
    elif is_tmux_active:
        # Tmux is active but capture failed or returned None
        # Still return empty string with is_deep_context=True to indicate tmux is active
        return "", True

    session_context = read_session_context(
        max_bytes=200_000, exclude_command=exclude_command
    )
    if session_context:
        return session_context, True

    detected_shell = _get_shell_from_env()
    history_context = _get_history_context(
        max_commands, shell=detected_shell, exclude_command=exclude_command
    )
    additional_context = get_additional_context(
        shell=detected_shell, exclude_command=exclude_command
    )

    context_parts = []
    if history_context:
        context_parts.append(history_context)
    if additional_context:
        context_parts.append(additional_context)

    if context_parts:
        combined = "\n\n".join(context_parts)
        if additional_context:
            logger.info(
                "Combined history and additional context for shell=%s",
                detected_shell,
            )
        return combined, False

    return "", False
