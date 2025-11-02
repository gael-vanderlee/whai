"""Command approval loop for whai."""

from typing import Optional

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
