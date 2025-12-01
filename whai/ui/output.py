"""Basic output functions for whai UI."""

import json
import os
import sys
from typing import Any, Dict, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from whai.constants import (
    ENV_WHAI_PLAIN,
    TERMINAL_OUTPUT_MAX_LINES,
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


def _truncate_by_lines(text: str, max_lines: int) -> tuple[str, bool]:
    """
    Truncate text by lines, keeping the end (most recent lines).

    Args:
        text: Text to truncate.
        max_lines: Maximum number of lines (0 = no limit).

    Returns:
        Tuple of (truncated_text, was_truncated).
    """
    if max_lines == 0 or not text:
        return text, False

    lines = text.split("\n")
    if len(lines) <= max_lines:
        return text, False

    # Keep the last max_lines
    truncated_lines = lines[-max_lines:]
    truncated_text = "\n".join(truncated_lines)

    # Add truncation notice
    lines_removed = len(lines) - max_lines
    notice = f"... {lines_removed} lines removed to limit terminal output ...\n"
    return notice + truncated_text, True


def error(msg: str) -> None:
    """Print an error message to stderr."""
    if PLAIN_MODE:
        print(f"Error: {msg}", file=sys.stderr)
    else:
        # Rich Console handles stderr via stderr parameter in constructor
        stderr_console = Console(
            highlight=False,
            force_terminal=not PLAIN_MODE,
            color_system=None if PLAIN_MODE else "auto",
            file=sys.stderr,
        )
        stderr_console.print(Text(msg, style=UI_TEXT_STYLE_ERROR))


def info(msg: str) -> None:
    """Print an info message."""
    console.print(msg)


def warn(msg: str) -> None:
    """Print a warning message."""
    if PLAIN_MODE:
        console.print(f"Warning: {msg}")
    else:
        console.print(Text(msg, style=UI_TEXT_STYLE_WARNING))


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


def print_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    display_name: Optional[str] = None,
    description: Optional[str] = None,
) -> None:
    """
    Print a proposed MCP tool call in a highlighted panel.

    Args:
        tool_name: Full tool name (e.g., "mcp_time-server_get_current_time").
        tool_args: Tool arguments dictionary.
        display_name: Optional pretty name (e.g., "time-server/get_current_time").
        description: Optional tool description.
    """
    # Parse display name if not provided
    if not display_name:
        if tool_name.startswith("mcp_") and "_" in tool_name[4:]:
            parts = tool_name.split("_", 2)
            if len(parts) >= 3:
                display_name = f"{parts[1]}/{parts[2]}"
            else:
                display_name = tool_name
        else:
            display_name = tool_name

    if PLAIN_MODE:
        console.print("Proposed MCP tool call:")
        console.print(f"  Tool: {display_name}")
        if description:
            console.print(f"  Description: {description}")
        if tool_args:
            console.print("  Arguments:")
            args_json = json.dumps(tool_args, indent=2, ensure_ascii=False)
            for line in args_json.split("\n"):
                console.print(f"    {line}")
        else:
            console.print("  Arguments: (none)")
    else:
        # Build content with Rich formatting
        content_parts = []

        # Tool name (bold, colored)
        content_parts.append(Text("Tool: ", style="dim"))
        content_parts.append(Text(display_name, style="bold cyan"))
        content_parts.append(Text("\n"))

        # Description (if available)
        if description:
            content_parts.append(Text(f"Description: {description}\n", style="dim"))

        # Arguments section
        if tool_args:
            # Format arguments as pretty JSON
            args_json = json.dumps(tool_args, indent=2, ensure_ascii=False)
            content_parts.append(Text("Arguments:\n", style="dim"))
            # Use Syntax highlighting for JSON
            syn = Syntax(args_json, "json", theme=UI_THEME, word_wrap=True)
            # Combine text and syntax
            content = Group(Text().join(content_parts), syn)
        else:
            content_parts.append(Text("Arguments: (none)", style="dim"))
            content = Text().join(content_parts)

        console.print(
            Panel(
                content,
                title="Proposed MCP tool call",
                border_style=UI_BORDER_COLOR_COMMAND,
            )
        )


def print_output(stdout: str, stderr: str, returncode: int = 0) -> None:
    """Print command output (stdout and stderr) in panels."""
    # Truncate terminal output if limit is set
    stdout_truncated, stdout_was_truncated = _truncate_by_lines(
        stdout, TERMINAL_OUTPUT_MAX_LINES
    )
    stderr_truncated, stderr_was_truncated = _truncate_by_lines(
        stderr, TERMINAL_OUTPUT_MAX_LINES
    )

    if stdout_was_truncated or stderr_was_truncated:
        warn("Command output was truncated to limit terminal display.")

    has_output = bool(stdout_truncated or stderr_truncated)

    if PLAIN_MODE:
        if stdout_truncated:
            console.print("\nOutput:")
            console.print(stdout_truncated.rstrip("\n"))
        if stderr_truncated:
            console.print("\nErrors:")
            console.print(stderr_truncated.rstrip("\n"))
        if not has_output:
            console.print(
                f"\nCommand completed with no output (exit code: {returncode})"
            )
    else:
        if stdout_truncated:
            syn_out = Syntax(
                stdout_truncated.rstrip("\n"), "text", theme=UI_THEME, word_wrap=False
            )
            console.print(
                Panel(syn_out, title="Output", border_style=UI_BORDER_COLOR_OUTPUT)
            )
        if stderr_truncated:
            syn_err = Syntax(
                stderr_truncated.rstrip("\n"), "text", theme=UI_THEME, word_wrap=False
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
    """Print a celebration message with emoji."""
    emoji_msg = f"🎉✨ {msg} ✨🎉"
    if PLAIN_MODE:
        console.print(emoji_msg)
    else:
        console.print(Text(emoji_msg, style="bold green"))


def spinner(msg: str):
    """Create a spinner context manager."""
    from rich.spinner import Spinner
    from rich.status import Status

    return Status(Spinner("dots", msg), console=console)
