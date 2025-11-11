"""Interactive configuration wizard for whai."""

import datetime
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

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
    print_configuration_summary,
    print_section,
    prompt_numbered_choice,
    success,
    warn,
)
from whai.utils import detect_shell

logger = get_logger(__name__)

# Use centralized provider defaults
PROVIDERS = PROVIDER_DEFAULTS



def _get_provider_config(
    provider: str, existing_config: Optional[ProviderConfig] = None
) -> ProviderConfig:
    """
    Interactively get configuration for a provider.

    Args:
        provider: The provider name (e.g., 'openai', 'anthropic').
        existing_config: Optional existing ProviderConfig to use as defaults when editing.

    Returns:
        ProviderConfig instance with user-provided configuration.
    """
    provider_info = PROVIDERS[provider]
    config_data: Dict[str, Any] = {}

    print_section(f"Configuring {provider}")

    for field in provider_info["fields"]:
        # Use existing config value if available, otherwise use provider default
        if existing_config and hasattr(existing_config, field):
            existing_value = getattr(existing_config, field)
            default = existing_value if existing_value is not None else ""
        else:
            default = provider_info["defaults"].get(field, "")

        # Special handling for API keys (hide input)
        if "api_key" in field.lower():
            # Mask the default value for display if it's an existing API key
            actual_default = default
            display_default = ""
            if existing_config and hasattr(existing_config, field):
                existing_value = getattr(existing_config, field)
                if existing_value and existing_value != "":
                    # Create masked version for display in prompt brackets
                    display_default = (
                        existing_value[:8] + "..." if len(existing_value) > 8 else "***"
                    )
                    # Store actual value to use when user presses Enter
                    actual_default = existing_value

            while True:
                value = typer.prompt(
                    f"{field}",
                    default=display_default if display_default else "",
                    hide_input=True,
                )
                # Sanitize pasted secrets on Windows/PowerShell (strip control chars like \x16)
                cleaned = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
                if cleaned != value:
                    info("Removed non-printable characters from input.")

                # If user pressed Enter (typer returns the masked default), use actual API key
                if (
                    display_default
                    and cleaned == display_default
                    and actual_default
                    and actual_default != display_default
                ):
                    value = actual_default
                    break

                # If user provided empty input
                if not cleaned:
                    if actual_default:
                        # Use the actual default if available
                        value = actual_default
                        break
                    warn("API key cannot be empty. Please paste/type your key.")
                    continue
                # User typed a new value
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
        info("\nValidating configuration:")

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

        def progress_callback(message: str, success_flag: Optional[bool]) -> None:
            """Progress callback that prints validation steps dynamically."""
            if success_flag is None:
                # Check in progress - show message without result yet
                formatted = _format_message(message)
                typer.echo(formatted, nl=False)
                in_progress[message] = True
            elif success_flag is True:
                # Success - complete line if in progress, or print full line
                if in_progress.get(message):
                    typer.echo(" ✓")
                    in_progress[message] = False
                else:
                    formatted = _format_message(message)
                    typer.echo(f"{formatted} ✓")
            elif success_flag is False:
                # Failure - complete line if in progress, or print full line
                if in_progress.get(message):
                    typer.echo(" ✗")
                    in_progress[message] = False
                else:
                    formatted = _format_message(message)
                    typer.echo(f"{formatted} ✗")

        validation_result = provider_config.validate(on_progress=progress_callback)

        if not validation_result.is_valid:
            warn("Validation issues found:")
            for issue in validation_result.issues:
                warn(f"  - {issue}")

            if not typer.confirm(
                "\nProceed with configuration despite validation issues?",
                default=False,
            ):
                raise typer.Abort()
        else:
            success("Configuration validated successfully!")

        return provider_config
    except (ValueError, InvalidProviderConfigError) as e:
        failure(f"Invalid configuration: {e}")
        raise typer.Exit(1)


def _quick_setup(config: WhaiConfig) -> None:
    """
    Quick setup flow for first-time users.

    Args:
        config: WhaiConfig instance to update.
    """
    print_section("Quick Setup", "Let's get you started with a single provider.")

    # Ask for provider
    provider = prompt_numbered_choice(
        "Choose a provider",
        list(PROVIDERS.keys()),
        default=DEFAULT_PROVIDER,
    )

    # Get provider config
    provider_config = _get_provider_config(provider)

    # Update config
    config.llm.providers[provider] = provider_config
    config.llm.default_provider = provider

    success(f"{provider} configured successfully!")


## (PowerShell offer function removed)


def _add_or_edit_provider(config: WhaiConfig) -> None:
    """
    Add or edit a provider configuration.

    Args:
        config: WhaiConfig instance to update.
    """
    print_section("Add or Edit Provider")

    provider = prompt_numbered_choice(
        "Choose a provider to configure",
        list(PROVIDERS.keys()),
    )

    # Check if provider already exists
    existing = config.llm.get_provider(provider)

    if existing:
        info(f"Provider '{provider}' already configured.")
        if not typer.confirm("Do you want to edit it?", default=True):
            return

    # Get new configuration (pass existing config to use as defaults when editing)
    provider_config = _get_provider_config(provider, existing_config=existing)
    config.llm.providers[provider] = provider_config

    success(f"{provider} configured successfully!")


def _remove_provider(config: WhaiConfig) -> None:
    """
    Remove a provider configuration.

    Args:
        config: WhaiConfig instance to update.
    """
    print_section("Remove Provider")

    # Find configured providers
    configured = list(config.llm.providers.keys())

    if not configured:
        warn("NO PROVIDERS CONFIGURED")
        return

    provider = prompt_numbered_choice(
        "Choose a provider to remove",
        configured,
    )

    if provider in config.llm.providers:
        del config.llm.providers[provider]
        success(f"{provider} removed.")

        # If this was the default provider, clear it
        if config.llm.default_provider == provider:
            config.llm.default_provider = ""
            warn("This was your default provider. Set a new default.")

        # Warn if no providers remain
        if not config.llm.providers:
            warn(
                "NO PROVIDERS CONFIGURED. whai cannot run until you add one.\n"
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
    print_section("Reset Configuration to Defaults")

    cfg_path = get_config_path()
    cfg_dir = cfg_path.parent
    info(f"Config path: {cfg_path}")

    if not typer.confirm(
        "This will overwrite your configuration file. A backup will be created. Continue?",
        default=False,
    ):
        warn("Reset cancelled.")
        raise typer.Abort()

    # Create backup if present
    if cfg_path.exists():
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = cfg_dir / f"{CONFIG_FILENAME}.bak-{timestamp}"
        try:
            backup_path.write_bytes(cfg_path.read_bytes())
            success(f"Backup created: {backup_path}")
        except Exception as e:
            failure(f"Failed to create backup: {e}")
            raise typer.Exit(1)

    # Minimal default configuration: no providers configured
    default_config = WhaiConfig(
        llm=LLMConfig(
            default_provider=None,
            providers={},
        ),
        roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
    )

    try:
        save_config(default_config)
        ensure_default_roles()
    except Exception as e:
        failure(f"Error writing default configuration: {e}")
        raise typer.Exit(1)

    success(f"Configuration reset. Wrote defaults to: {get_config_path()}\n")
    warn("NO PROVIDERS CONFIGURED. You'll be prompted to add one now.")

    return default_config


def _set_default_provider(config: WhaiConfig) -> None:
    """
    Set the default provider.

    Args:
        config: WhaiConfig instance to update.
    """
    print_section("Set Default Provider")

    # Find configured providers
    configured = list(config.llm.providers.keys())

    if not configured:
        warn("NO PROVIDERS CONFIGURED. Add a provider first.")
        return

    provider = prompt_numbered_choice(
        "Choose default provider",
        configured,
        default=configured[0],
    )

    config.llm.default_provider = provider

    success(f"Default provider set to {provider}")


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
                default_provider=None,
                providers={},
            ),
            roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
        )
    except Exception as e:
        logger.warning(f"Could not load config: {e}")
        return WhaiConfig(
            llm=LLMConfig(
                default_provider=None,
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
    print_section("Whai Configuration Wizard")

    # Try to load existing config or start with empty structure
    config = _load_or_create_config(existing_config)

    # Main loop - keep showing menu until user exits
    while True:
        # Display configuration summary on each loop iteration
        cfg_path = get_config_path()
        info(f"Config path: {cfg_path}")
        print_configuration_summary(config)
        typer.echo("")  # Add blank line before menu

        # Show warning if default_provider is invalid
        if (
            config.llm.default_provider is not None
            and config.llm.default_provider not in config.llm.providers
        ):
            warn(
                f"Default provider '{config.llm.default_provider}' is not configured. "
                f"Available providers: {list(config.llm.providers.keys()) if config.llm.providers else 'none'}"
            )

        # Show menu
        configured_now = list(config.llm.providers.keys())
        if configured_now:
            actions = [
                "add-or-edit",
                "remove",
                "default-provider",
                "reset-config",
                "open-folder",
                "exit",
            ]
            action_labels = {
                "add-or-edit": "Add or Edit Provider",
                "remove": "Remove Provider",
                "default-provider": "Set Default Provider",
                "reset-config": "Reset Configuration",
                "open-folder": "Open Config Folder",
                "exit": "Exit",
            }
            default_action = "add-or-edit"
        else:
            # No providers yet - drive user to quick-setup
            actions = [
                "quick-setup",
                "add-or-edit",
                "reset-config",
                "open-folder",
                "exit",
            ]
            action_labels = {
                "quick-setup": "Quick Setup",
                "add-or-edit": "Add or Edit Provider",
                "reset-config": "Reset Configuration",
                "open-folder": "Open Config Folder",
                "exit": "Exit",
            }
            default_action = "quick-setup"

        # Display choices with labels
        choices = [action_labels.get(action, action) for action in actions]
        default_choice = action_labels.get(default_action, default_action)

        selected_label = prompt_numbered_choice(
            "Choose an action",
            choices,
            default=default_choice,
        )

        # Find the action key from the selected label
        action = next(
            key for key, label in action_labels.items() if label == selected_label
        )

        if action == "exit":
            # Save before exiting
            try:
                save_config(config)
                config_path = get_config_path()
                success(f"Configuration saved to: {config_path}\n")
                celebration("You can now use whai!")
                typer.echo("")
            except Exception as e:
                failure(f"Error saving configuration: {e}")
                raise typer.Exit(1)
            break

        # Execute the chosen action
        config_changed = False
        try:
            if action == "quick-setup":
                _quick_setup(config)
                config_changed = True
            elif action == "add-or-edit":
                _add_or_edit_provider(config)
                config_changed = True
            elif action == "remove":
                _remove_provider(config)
                config_changed = True
            elif action == "default-provider":
                _set_default_provider(config)
                config_changed = True
            elif action == "reset-config":
                config = _reset_default()
                # After reset, start quick-setup to add a provider immediately
                _quick_setup(config)
                config_changed = True
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
                    success(f"Opened folder: {cfg_dir}")
                except Exception as e:
                    failure(f"Failed to open folder {cfg_dir}: {e}")
        # (PowerShell setup action removed)
        except typer.Abort:
            # User cancelled an action, return to menu
            typer.echo("")
            continue
        except typer.Exit:
            # Re-raise exit to terminate wizard
            raise

        # Save the configuration after actions that modify it
        if config_changed:
            try:
                save_config(config)
                config_path = get_config_path()
                success(f"Configuration saved to: {config_path}\n")
            except Exception as e:
                failure(f"Error saving configuration: {e}")
                raise typer.Exit(1)

            # Add a blank line before returning to menu
            typer.echo("")
