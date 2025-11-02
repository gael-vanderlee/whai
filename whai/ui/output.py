"""Basic output functions for whai UI."""

import os
import sys

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from whai.constants import (
    ENV_WHAI_PLAIN,
    UI_BORDER_COLOR_COMMAND,
    UI_BORDER_COLOR_ERROR,
    UI_BORDER_COLOR_OUTPUT,
    UI_BORDER_COLOR_STATUS_ERROR,
    UI_BORDER_COLOR_STATUS_SUCCESS,
    UI_TEXT_STYLE_ERROR,
    UI_TEXT_STYLE_WARNING,
    UI_THEME,
)


def _is_tty() -> bool:
    """Check if stdout is a TTY."""
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


# Detect plain mode: enabled when WHAI_PLAIN=1 or not a TTY
PLAIN_MODE = os.getenv(ENV_WHAI_PLAIN, "").strip() == "1" or not _is_tty()

# Create console with appropriate settings
console = Console(
    highlight=False,
    force_terminal=not PLAIN_MODE,
    color_system=None if PLAIN_MODE else "auto",
    soft_wrap=False,
)


def error(msg: str) -> None:
    """Print an error message to stderr."""
    if PLAIN_MODE:
        print(f"Error: {msg}", file=sys.stderr)
    else:
        # Rich Console handles stderr via stderr parameter in constructor
        stderr_console = Console(
            stderr=True, highlight=False, force_terminal=not PLAIN_MODE
        )
        stderr_console.print(Text(f"Error: {msg}", style=UI_TEXT_STYLE_ERROR))


def warn(msg: str) -> None:
    """Print a warning message to stderr."""
    if PLAIN_MODE:
        print(f"Warning: {msg}", file=sys.stderr)
    else:
        stderr_console = Console(
            stderr=True, highlight=False, force_terminal=not PLAIN_MODE
        )
        stderr_console.print(Text(f"⚠️  Warning: {msg}", style=UI_TEXT_STYLE_WARNING))


def info(msg: str) -> None:
    """Print an info message to stderr."""
    if PLAIN_MODE:
        print(f"Info: {msg}", file=sys.stderr)
    else:
        stderr_console = Console(
            stderr=True, highlight=False, force_terminal=not PLAIN_MODE
        )
        stderr_console.print(Text(f"{msg}", style="blue"))


def print_command(cmd: str) -> None:
    """Print a proposed shell command in a highlighted panel."""
    if PLAIN_MODE:
        console.print("Proposed command:")
        console.print(f"  > {cmd}")
    else:
        # Enable word wrapping so long commands fold onto the next line inside the panel
        syn = Syntax(cmd, "bash", theme=UI_THEME, word_wrap=True)
        console.print(
            Panel(syn, title="Proposed command", border_style=UI_BORDER_COLOR_COMMAND)
        )


def print_output(stdout: str, stderr: str, returncode: int = 0) -> None:
    """Print command output (stdout and stderr) in panels."""
    has_output = bool(stdout or stderr)

    if PLAIN_MODE:
        if stdout:
            console.print("\nOutput:")
            console.print(stdout.rstrip("\n"))
        if stderr:
            console.print("\nErrors:")
            console.print(stderr.rstrip("\n"))
        if not has_output:
            console.print(
                f"\nCommand completed with no output (exit code: {returncode})"
            )
    else:
        if stdout:
            syn_out = Syntax(
                stdout.rstrip("\n"), "text", theme=UI_THEME, word_wrap=False
            )
            console.print(
                Panel(syn_out, title="Output", border_style=UI_BORDER_COLOR_OUTPUT)
            )
        if stderr:
            syn_err = Syntax(
                stderr.rstrip("\n"), "text", theme=UI_THEME, word_wrap=False
            )
            console.print(
                Panel(syn_err, title="Errors", border_style=UI_BORDER_COLOR_ERROR)
            )
        if not has_output:
            status_color = (
                UI_BORDER_COLOR_STATUS_SUCCESS
                if returncode == 0
                else UI_BORDER_COLOR_STATUS_ERROR
            )
            console.print(
                Panel(
                    f"Command completed with no output\nExit code: {returncode}",
                    title="Command completed",
                    border_style=status_color,
                )
            )


def success(msg: str) -> None:
    """Print a success message with emoji."""
    emoji_msg = f"✅ {msg}"
    if PLAIN_MODE:
        console.print(emoji_msg)
    else:
        console.print(Text(emoji_msg, style="bold green"))


def failure(msg: str) -> None:
    """Print a failure message with emoji."""
    emoji_msg = f"❌ {msg}"
    if PLAIN_MODE:
        console.print(emoji_msg)
    else:
        console.print(Text(emoji_msg, style="bold red"))


def celebration(msg: str) -> None:
    """Print a celebration message with stars/confetti emojis."""
    emoji_msg = f"🎉 ✨ {msg} ✨ 🎉"
    if PLAIN_MODE:
        console.print(emoji_msg)
    else:
        console.print(Text(emoji_msg, style="bold bright_yellow"))
