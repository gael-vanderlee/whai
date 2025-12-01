"""Command approval loop for whai."""

from typing import Any, Dict, Optional

from rich.text import Text

from whai import ui
from whai.constants import UI_TEXT_STYLE_PROMPT
from whai.logging_setup import get_logger

logger = get_logger(__name__)


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


def approve_tool(
    tool_name: str,
    tool_args: Dict[str, Any],
    display_name: Optional[str] = None,
    description: Optional[str] = None,
) -> bool:
    """
    Present an MCP tool call to the user for approval.

    Args:
        tool_name: Full tool name (e.g., "mcp_time-server_get_current_time").
        tool_args: Tool arguments dictionary.
        display_name: Optional pretty name (e.g., "time-server/get_current_time").
        description: Optional tool description from MCP server.

    Returns:
        True if approved, False if rejected.
    """
    ui.console.print()
    ui.print_tool(tool_name, tool_args, display_name=display_name, description=description)

    while True:
        try:
            ui.console.print(
                Text("[a]pprove / [r]eject: ", style=UI_TEXT_STYLE_PROMPT),
                end="",
            )
            response = input().strip().lower()

            if response == "a" or response == "approve":
                logger.debug("Tool call approved", extra={"category": "mcp"})
                return True
            elif response == "r" or response == "reject":
                ui.info("Tool call rejected.")
                logger.debug("Tool call rejected by user", extra={"category": "mcp"})
                return False
            else:
                ui.warn("Invalid response. Please enter 'a' or 'r'.")
        except (EOFError, KeyboardInterrupt):
            ui.info("\nRejected.")
            logger.debug(
                "Tool call rejected via interrupt/EOF", extra={"category": "mcp"}
            )
            return False
