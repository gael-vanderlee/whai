"""User interface helpers for pretty terminal output using Rich."""

from whai.ui.formatting import (
    print_configuration_summary,
    print_section,
    prompt_numbered_choice,
    rule,
    spinner,
)
from whai.ui.output import (
    PLAIN_MODE,
    celebration,
    console,
    error,
    failure,
    info,
    print_command,
    print_output,
    success,
    warn,
)

__all__ = [
    # Output functions
    "console",
    "PLAIN_MODE",
    "error",
    "warn",
    "info",
    "print_command",
    "print_output",
    "success",
    "failure",
    "celebration",
    # Formatting functions
    "rule",
    "spinner",
    "print_configuration_summary",
    "print_section",
    "prompt_numbered_choice",
]

