"""Formatting utilities for whai UI."""

from contextlib import contextmanager
from typing import TYPE_CHECKING, Iterator, List, Optional

from rich.box import DOUBLE
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from whai.constants import UI_BORDER_COLOR_OUTPUT
from whai.ui.output import PLAIN_MODE, console

if TYPE_CHECKING:  # Avoid circular import
    from whai.configuration.user_config import WhaiConfig


def rule(title: str = "") -> None:
    """Print a horizontal rule with optional title."""
    if PLAIN_MODE:
        console.print("=" * 60)
    else:
        console.rule(Text(title, style="bold") if title else "")


@contextmanager
def spinner(message: str) -> Iterator[None]:
    """Context manager for a spinner with a message."""
    if PLAIN_MODE:
        console.print(f"{message} ...")
        yield
        return
    with console.status(message, spinner="dots"):
        yield


def print_configuration_summary(config: "WhaiConfig") -> None:
    """Print a pretty configuration summary using Rich components.

    Args:
        config: WhaiConfig instance to display.
    """
    if PLAIN_MODE:
        # Plain mode - generate simple text
        default_provider_name = config.llm.default_provider
        if default_provider_name is None or not config.llm.get_provider(default_provider_name):
            default_provider = "MISSING"
            effective_model = "MISSING"
        else:
            default_provider = default_provider_name
            default_prov_config = config.llm.get_provider(default_provider)
            effective_model = (
                default_prov_config.default_model if default_prov_config else "MISSING"
            )
        default_role = config.roles.default_role

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
            console.print("⚠️  NO PROVIDERS CONFIGURED")
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
        default_provider_name = config.llm.default_provider
        if default_provider_name is None or not config.llm.get_provider(default_provider_name):
            default_provider = "[red]MISSING[/red]"
            effective_model = "[red]MISSING[/red]"
        else:
            default_provider = default_provider_name
            default_prov_config = config.llm.get_provider(default_provider_name)
            effective_model = (
                default_prov_config.default_model
                if default_prov_config
                else "[red]MISSING[/red]"
            )
        default_role = config.roles.default_role

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
            table.add_row("[bold yellow]⚠️  NO PROVIDERS CONFIGURED[/bold yellow]", "")

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
