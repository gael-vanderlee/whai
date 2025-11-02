"""UI helpers for pretty terminal output using Rich."""

import os
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, List, Optional

if TYPE_CHECKING:  # Avoid circular import
    from whai.configuration.user_config import WhaiConfig

from rich.box import DOUBLE
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
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


def rule(title: str = "") -> None:
    """Print a horizontal rule with optional title."""
    if PLAIN_MODE:
        console.print("=" * 60)
    else:
        console.rule(Text(title, style="bold") if title else "")


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


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Context manager for a spinner with a message."""
    if PLAIN_MODE:
        console.print(f"{message} ...")
        yield
        return
    with console.status(message, spinner="dots"):
        yield


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


def print_configuration_summary(config: "WhaiConfig") -> None:
    """Print a pretty configuration summary using Rich components.

    Args:
        config: WhaiConfig instance to display.
    """
    if PLAIN_MODE:
        # Plain mode - generate simple text
        default_provider = config.llm.default_provider or "MISSING"
        default_role = config.roles.default_role

        default_prov_config = config.llm.get_provider(default_provider)
        effective_model = (
            default_prov_config.default_model if default_prov_config else "MISSING"
        )

        console.print(f"Default provider: {default_provider}")
        console.print(f"Default model: {effective_model}")
        console.print(f"Default role: {default_role}")

        if config.llm.providers:
            console.print("Configured providers:")
            for name, provider_config in config.llm.providers.items():
                summary_fields = provider_config.get_summary_fields()
                field_parts = [f"{k}: {v}" for k, v in summary_fields.items()]
                star = " *" if name == default_provider else ""
                provider_str = f"{name}{star} ({', '.join(field_parts)})"
                console.print(f"  - {provider_str}")
        else:
            console.print("⚠️ NO PROVIDERS CONFIGURED")
    else:
        # Rich mode - use tables and styled components
        table = Table(
            title="Configuration Summary",
            box=DOUBLE,
            border_style=UI_BORDER_COLOR_OUTPUT,
            title_style="bold bright_white",
            show_header=False,
            padding=(0, 1),
        )

        # Add default settings
        default_provider = config.llm.default_provider or "[red]MISSING[/red]"
        default_role = config.roles.default_role

        default_prov_config = config.llm.get_provider(config.llm.default_provider or "")
        effective_model = (
            default_prov_config.default_model
            if default_prov_config
            else "[red]MISSING[/red]"
        )

        table.add_row("[bold cyan]Default provider:[/bold cyan]", default_provider)
        table.add_row("[bold cyan]Default model:[/bold cyan]", effective_model)
        table.add_row("[bold cyan]Default role:[/bold cyan]", default_role)

        # Add providers section
        if config.llm.providers:
            table.add_row()  # Empty row for spacing
            table.add_row("[bold cyan]Configured providers:[/bold cyan]", "")

            for idx, (name, provider_config) in enumerate(config.llm.providers.items()):
                # Add blank line between providers (not before first or after last)
                if idx > 0:
                    table.add_row()

                summary_fields = provider_config.get_summary_fields()

                # Add star indicator for default provider
                default_provider_name = config.llm.default_provider or ""
                star_indicator = " ⭐" if name == default_provider_name else ""

                # Get fields as list to handle first one specially
                fields_list = list(summary_fields.items())

                if fields_list:
                    # First field goes on same line as provider name
                    first_k, first_v = fields_list[0]
                    if first_v == "MISSING":
                        first_v = f"[red]{first_v}[/red]"
                    first_field = f"    [dim]{first_k}:[/dim] {first_v}"
                    table.add_row(
                        f"  └─ [yellow]{name}{star_indicator}[/yellow]", first_field
                    )

                    # Remaining fields on separate lines
                    for k, v in fields_list[1:]:
                        # Style MISSING values in red
                        if v == "MISSING":
                            v = f"[red]{v}[/red]"
                        table.add_row("", f"    [dim]{k}:[/dim] {v}")
                else:
                    # No fields, just provider name
                    table.add_row(f"  └─ [yellow]{name}{star_indicator}[/yellow]", "")
        else:
            table.add_row()  # Empty row for spacing
            table.add_row("[bold yellow]⚠️ NO PROVIDERS CONFIGURED[/bold yellow]", "")

        console.print(table)


def print_section(title: str, subtitle: str = "") -> None:
    """Print a formatted section header with double lines and bold text."""
    if PLAIN_MODE:
        console.print(f"\n=== {title} ===")
        if subtitle:
            console.print(subtitle)
        console.print()
    else:
        # Use double-line box with bold, bright white text
        title_styled = f"[bold bright_white]{title}[/bold bright_white]"
        content = title_styled
        if subtitle:
            content += f"\n[dim]{subtitle}[/dim]"
        console.print()
        console.print(
            Panel(
                content,
                box=DOUBLE,
                border_style="bright_white",
                padding=(0, 2),
            )
        )


def prompt_numbered_choice(
    prompt: str, choices: List[str], default: Optional[str] = None
) -> str:
    """Display a numbered list of choices and prompt for selection.

    Args:
        prompt: The prompt text to display before choices.
        choices: List of choice strings.
        default: Default choice value (optional).

    Returns:
        The selected choice string.

    Raises:
        ValueError: If invalid selection is made.
    """
    if not choices:
        raise ValueError("Choices list cannot be empty")

    # Display prompt and choices
    if PLAIN_MODE:
        console.print(f"\n{prompt}")
        for i, choice in enumerate(choices, 1):
            marker = " (default)" if default and choice == default else ""
            console.print(f"  {i}. {choice}{marker}")
    else:
        console.print(f"[bold yellow]{prompt}[/bold yellow]")
        for i, choice in enumerate(choices, 1):
            if default and choice == default:
                console.print(f"  [cyan]{i}.[/cyan] {choice} [dim](default)[/dim]")
            else:
                console.print(f"  [cyan]{i}.[/cyan] {choice}")
        console.print()  # Add spacing before prompt

    # Get user input
    while True:
        try:
            if PLAIN_MODE:
                if default:
                    prompt_text = (
                        f"Enter choice (1-{len(choices)}) (default: {default}): "
                    )
                else:
                    prompt_text = f"Enter choice (1-{len(choices)}): "
                response = input(prompt_text)
            else:
                if default:
                    prompt_text = f"[bold]Enter choice (1-{len(choices)})[/bold] [dim](default: {default})[/dim]: "
                else:
                    prompt_text = f"[bold]Enter choice (1-{len(choices)})[/bold]: "
                response = console.input(prompt_text)

            if not response.strip() and default:
                return default

            choice_num = int(response.strip())
            if 1 <= choice_num <= len(choices):
                return choices[choice_num - 1]
            else:
                if PLAIN_MODE:
                    print(
                        f"Invalid choice. Please enter a number between 1 and {len(choices)}."
                    )
                else:
                    console.print(
                        f"[red]Invalid choice. Please enter a number between 1 and {len(choices)}.[/red]"
                    )
        except ValueError:
            if PLAIN_MODE:
                print(
                    f"Invalid input. Please enter a number between 1 and {len(choices)}."
                )
            else:
                console.print(
                    f"[red]Invalid input. Please enter a number between 1 and {len(choices)}.[/red]"
                )
        except (EOFError, KeyboardInterrupt):
            raise
