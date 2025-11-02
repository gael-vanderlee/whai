"""Main context capture function for whai."""

from typing import Optional, Tuple

from whai.constants import HISTORY_MAX_COMMANDS
from whai.context.history import _get_history_context, _get_shell_from_env
from whai.context.tmux import _get_tmux_context


def get_context(
    max_commands: int = HISTORY_MAX_COMMANDS, exclude_command: Optional[str] = None
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
