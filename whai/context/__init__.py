"""Context capture from tmux or shell history for whai."""

from whai.context.capture import get_context
from whai.context.history import get_shell_executable

__all__ = ["get_context", "get_shell_executable"]

