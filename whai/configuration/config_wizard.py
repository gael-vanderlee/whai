"""Interactive configuration wizard for whai."""

import datetime
import os
import re
import subprocess
import sys
from typing import Any, Dict, Optional

import click
import typer

from whai.configuration.roles import ensure_default_roles
from whai.configuration.user_config import (
    InvalidProviderConfigError,
    LLMConfig,
    MissingConfigError,
    ProviderConfig,
    RolesConfig,
    WhaiConfig,
    get_config_path,
    get_provider_class,
    load_config,
    save_config,
)
from whai.constants import (
    CONFIG_FILENAME,
    DEFAULT_PROVIDER,
    DEFAULT_ROLE_NAME,
    PROVIDER_DEFAULTS,
)
from whai.logging_setup import get_logger
from whai.ui import (
    celebration,
    failure,
    info,
    print_section,
    prompt_numbered_choice,
    success,
    warn,
)

logger = get_logger(__name__)

# Use centralized provider defaults
PROVIDERS = PROVIDER_DEFAULTS


def _get_provider_config(provider: str) -> ProviderConfig:
    """
    Interactively get configuration for a provider.

    Args:
        provider: The provider name (e.g., 'openai', 'anthropic').

    Returns:
        ProviderConfig instance with user-provided configuration.
    """
    provider_info = PROVIDERS[provider]
    config_data: Dict[str, Any] = {}

    print_section(f"Configuring {provider}")

    for field in provider_info["fields"]:
        default = provider_info["defaults"].get(field, "")

        # Special handling for API keys (hide input)
        if "api_key" in field.lower():
            while True:
                value = typer.prompt(
                    f"{field}",
                    default=default if default else "",
                    hide_input=True,
                )
                # Sanitize pasted secrets on Windows/PowerShell (strip control chars like \x16)
                cleaned = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
                if cleaned != value:
                    info("Removed non-printable characters from input.")
                if not cleaned:
                    warn("API key cannot be empty. Please paste/type your key.")
                    continue
                value = cleaned
                break
        else:
            value = typer.prompt(f"{field}", default=default if default else "")

        if value != "":  # Only add non-empty values
            config_data[field] = value

    # Create the appropriate ProviderConfig subclass instance
    try:
        provider_class = get_provider_class(provider)
        provider_config = provider_class.from_dict(config_data)

        # Validate the configuration with external checks
        typer.echo("\nValidating configuration...")

        # Track if a message is in progress (waiting for result)
        in_progress: Dict[str, bool] = {}

        # Target width for alignment (characters including dots)
        TARGET_WIDTH = 38

        def _format_message(message: str, dots: int = 3) -> str:
            """Format message with dots to align checkmarks."""
            # Calculate dots needed to reach target width
            msg_len = len(f"  {message}")
            dots_needed = max(1, TARGET_WIDTH - msg_len - 1)  # -1 for the result char
            return f"  {message}{'.' * dots_needed}"

        def progress_callback(message: str, success: Optional[bool]) -> None:
            """Progress callback that prints validation steps dynamically."""
            if success is None:
                # Check in progress - show message without result yet
                formatted = _format_message(message)
                typer.echo(formatted, nl=False)
                in_progress[message] = True
            elif success is True:
                # Success - complete line if in progress, or print full line
                if in_progress.get(message):
                    typer.echo(" ✓")
                    in_progress[message] = False
                else:
                    formatted = _format_message(message)
                    typer.echo(f"{formatted} ✓")
            elif success is False:
                # Failure - complete line if in progress, or print full line
                if in_progress.get(message):
                    typer.echo(" ✗")
                    in_progress[message] = False
                else:
                    formatted = _format_message(message)
                    typer.echo(f"{formatted} ✗")

        validation_result = provider_config.validate(on_progress=progress_callback)

        if not validation_result.is_valid:
            typer.echo("\n⚠ Validation issues found:")
            for issue in validation_result.issues:
                typer.echo(f"  - {issue}")

            if not typer.confirm(
                "\nProceed with configuration despite validation issues?",
                default=False,
            ):
                raise typer.Abort()
        else:
            typer.echo("\n✓ Configuration validated successfully!")

        return provider_config
    except (ValueError, InvalidProviderConfigError) as e:
        typer.echo(f"\n✗ Invalid configuration: {e}", err=True)
        raise typer.Exit(1)


def _quick_setup(config: WhaiConfig) -> None:
    """
    Quick setup flow for first-time users.

    Args:
        config: WhaiConfig instance to update.
    """
    typer.echo("\n=== Quick Setup ===")
    typer.echo("Let's get you started with a single provider.\n")

    # Ask for provider
    provider = typer.prompt(
        "Choose a provider",
        type=click.Choice(list(PROVIDERS.keys())),
        default=DEFAULT_PROVIDER,
    )

    # Get provider config
    provider_config = _get_provider_config(provider)

    # Update config
    config.llm.providers[provider] = provider_config
    config.llm.default_provider = provider

    typer.echo(f"\n✓ {provider} configured successfully!")


def _add_or_edit_provider(config: WhaiConfig) -> None:
    """
    Add or edit a provider configuration.

    Args:
        config: WhaiConfig instance to update.
    """
    typer.echo("\n=== Add or Edit Provider ===")

    provider = typer.prompt(
        "Choose a provider to configure",
        type=click.Choice(list(PROVIDERS.keys())),
    )

    # Check if provider already exists
    existing = config.llm.get_provider(provider)

    if existing:
        typer.echo(f"\nProvider '{provider}' already configured.")
        if not typer.confirm("Do you want to edit it?", default=True):
            return

    # Get new configuration
    provider_config = _get_provider_config(provider)
    config.llm.providers[provider] = provider_config

    typer.echo(f"\n✓ {provider} configured successfully!")


def _remove_provider(config: WhaiConfig) -> None:
    """
    Remove a provider configuration.

    Args:
        config: WhaiConfig instance to update.
    """
    typer.echo("\n=== Remove Provider ===")

    # Find configured providers
    configured = list(config.llm.providers.keys())

    if not configured:
        typer.echo("⚠ NO PROVIDERS CONFIGURED")
        return

    provider = typer.prompt(
        "Choose a provider to remove",
        type=click.Choice(configured),
    )

    if provider in config.llm.providers:
        del config.llm.providers[provider]
        typer.echo(f"\n✓ {provider} removed.")

        # If this was the default provider, clear it
        if config.llm.default_provider == provider:
            config.llm.default_provider = ""
            typer.echo("Note: This was your default provider. Set a new default.")

        # Warn if no providers remain
        if not config.llm.providers:
            typer.echo(
                "\n⚠ Warning: NO PROVIDERS CONFIGURED. whai cannot run until you add one.\n"
                "Run 'whai --interactive-config' and choose quick-setup."
            )


def _reset_default() -> WhaiConfig:
    """
    Reset configuration to a clean default state with a clear warning and backup.

    Overwrites the current config file with a minimal default configuration and
    ensures default roles exist.

    Returns:
        New empty WhaiConfig instance.
    """
    typer.echo("\n=== Reset Configuration to Defaults ===")

    cfg_path = get_config_path()
    cfg_dir = cfg_path.parent
    typer.echo(f"Config path: {cfg_path}")

    if not typer.confirm(
        "This will overwrite your configuration file. A backup will be created. Continue?",
        default=False,
    ):
        typer.echo("\nReset cancelled.")
        raise typer.Abort()

    # Create backup if present
    if cfg_path.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = cfg_dir / f"{CONFIG_FILENAME}.bak-{timestamp}"
        try:
            backup_path.write_bytes(cfg_path.read_bytes())
            typer.echo(f"\nBackup created: {backup_path}")
        except Exception as e:
            typer.echo(f"\n✗ Failed to create backup: {e}", err=True)
            raise typer.Exit(1)

    # Minimal default configuration: no providers configured
    default_config = WhaiConfig(
        llm=LLMConfig(
            default_provider=DEFAULT_PROVIDER,
            providers={},
        ),
        roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
    )

    try:
        save_config(default_config)
        ensure_default_roles()
    except Exception as e:
        typer.echo(f"\n✗ Error writing default configuration: {e}", err=True)
        raise typer.Exit(1)

    typer.echo(f"\n✓ Configuration reset. Wrote defaults to: {get_config_path()}\n")
    typer.echo("⚠ NO PROVIDERS CONFIGURED. You'll be prompted to add one now.")

    return default_config


def _set_default_provider(config: WhaiConfig) -> None:
    """
    Set the default provider.

    Args:
        config: WhaiConfig instance to update.
    """
    typer.echo("\n=== Set Default Provider ===")

    # Find configured providers
    configured = list(config.llm.providers.keys())

    if not configured:
        typer.echo("⚠ NO PROVIDERS CONFIGURED. Add a provider first.")
        return

    provider = typer.prompt(
        "Choose default provider",
        type=click.Choice(configured),
        default=configured[0],
    )

    config.llm.default_provider = provider

    typer.echo(f"\n✓ Default provider set to {provider}")


def _load_or_create_config(existing_config: bool) -> WhaiConfig:
    """
    Load existing config or create a new empty one.

    Args:
        existing_config: Whether config is expected to exist.

    Returns:
        WhaiConfig instance.
    """
    try:
        return load_config()
    except MissingConfigError:
        logger.debug("Config not found, creating new empty config")
        return WhaiConfig(
            llm=LLMConfig(
                default_provider=DEFAULT_PROVIDER,
                providers={},
            ),
            roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
        )
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        return WhaiConfig(
            llm=LLMConfig(
                default_provider=DEFAULT_PROVIDER,
                providers={},
            ),
            roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
        )


def run_wizard(existing_config: bool = False) -> None:
    """
    Run the interactive configuration wizard.

    Args:
        existing_config: If True, config already exists and we're editing it.
    """
    typer.echo("\n" + "=" * 50)
    typer.echo("       whai Configuration Wizard")
    typer.echo("=" * 50)

    # Try to load existing config or start with empty structure
    config = _load_or_create_config(existing_config)

    if existing_config:
        typer.echo("\nCurrent configuration:")
        cfg_path = get_config_path()
        typer.echo(f"Config path: {cfg_path}")
        typer.echo(config.summarize())

    # Show menu
    configured_now = list(config.llm.providers.keys())
    if existing_config and configured_now:
        actions = [
            "add-or-edit",
            "remove",
            "default-provider",
            "reset-config",
            "view",
            "open-folder",
            "cancel",
        ]
        default_action = "view"
    else:
        # No providers yet - drive user to quick-setup
        actions = [
            "quick-setup",
            "add-or-edit",
            "reset-config",
            "open-folder",
            "cancel",
        ]
        default_action = "quick-setup"

    action = typer.prompt(
        "\nChoose an action",
        type=click.Choice(actions),
        default=default_action,
    )

    if action == "cancel":
        typer.echo("\nConfiguration cancelled.")
        raise typer.Abort()

    if action == "view":
        typer.echo("\nCurrent configuration:")
        cfg_path = get_config_path()
        typer.echo(f"Config path: {cfg_path}")
        typer.echo(config.summarize())
        return

    # Execute the chosen action
    if action == "quick-setup":
        _quick_setup(config)
    elif action == "add-or-edit":
        _add_or_edit_provider(config)
    elif action == "remove":
        _remove_provider(config)
    elif action == "default-provider":
        _set_default_provider(config)
    elif action == "reset-config":
        config = _reset_default()
        # After reset, start quick-setup to add a provider immediately
        _quick_setup(config)
    elif action == "open-folder":
        # Open config directory in system file explorer
        cfg_dir = get_config_path().parent
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(cfg_dir))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(cfg_dir)])
            else:
                subprocess.Popen(["xdg-open", str(cfg_dir)])
            typer.echo(f"\n✓ Opened folder: {cfg_dir}")
        except Exception as e:
            typer.echo(f"\n✗ Failed to open folder {cfg_dir}: {e}", err=True)

    # Save the configuration
    try:
        save_config(config)
        config_path = get_config_path()
        typer.echo(f"\n✓ Configuration saved to: {config_path}")
        typer.echo("\nYou can now use whai!")
    except Exception as e:
        typer.echo(f"\n✗ Error saving configuration: {e}", err=True)
        raise typer.Exit(1)
