"""Interactive configuration wizard for terma."""

import re
from typing import Any, Dict

import click
import typer

from terma.config import (
    get_config_path,
    load_config,
    save_config,
    summarize_config,
)
from terma.logging_setup import get_logger

logger = get_logger(__name__)

# Supported providers with their configuration requirements
PROVIDERS = {
    "openai": {
        "fields": ["api_key", "default_model"],
        "defaults": {"default_model": "gpt-5-mini"},
    },
    "anthropic": {
        "fields": ["api_key", "default_model"],
        "defaults": {"default_model": "claude-3-5-sonnet-20241022"},
    },
    "azure_openai": {
        "fields": ["api_key", "api_base", "api_version", "default_model"],
        "defaults": {"api_version": "2023-05-15", "default_model": "gpt-4"},
    },
    "ollama": {
        "fields": ["api_base", "default_model"],
        "defaults": {"api_base": "http://localhost:11434", "default_model": "mistral"},
    },
}


def _ensure_llm_section(config: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the config has an 'llm' section."""
    if "llm" not in config:
        config["llm"] = {}
    return config


def _get_provider_config(provider: str) -> Dict[str, str]:
    """
    Interactively get configuration for a provider.

    Args:
        provider: The provider name (e.g., 'openai', 'anthropic').

    Returns:
        Dictionary with provider configuration.
    """
    provider_info = PROVIDERS[provider]
    config_data = {}

    typer.echo(f"\n=== Configuring {provider} ===")

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
                    typer.echo("Note: Removed non-printable characters from input.")
                if not cleaned:
                    typer.echo("API key cannot be empty. Please paste/type your key.")
                    continue
                value = cleaned
                break
        else:
            value = typer.prompt(f"{field}", default=default if default else "")

        if value != "":  # Only add non-empty values
            config_data[field] = value

    return config_data


def _quick_setup(config: Dict[str, Any]) -> None:
    """
    Quick setup flow for first-time users.

    Args:
        config: Configuration dictionary to update.
    """
    typer.echo("\n=== Quick Setup ===")
    typer.echo("Let's get you started with a single provider.\n")

    # Ask for provider
    provider = typer.prompt(
        "Choose a provider",
        type=click.Choice(list(PROVIDERS.keys())),
        default="openai",
    )

    # Get provider config
    provider_config = _get_provider_config(provider)

    # Update config
    _ensure_llm_section(config)
    config["llm"][provider] = provider_config
    config["llm"]["default_provider"] = provider

    # Set default_model at top level if provider has one
    if "default_model" in provider_config:
        config["llm"]["default_model"] = provider_config["default_model"]

    typer.echo(f"\n✓ {provider} configured successfully!")


def _add_or_edit_provider(config: Dict[str, Any]) -> None:
    """
    Add or edit a provider configuration.

    Args:
        config: Configuration dictionary to update.
    """
    typer.echo("\n=== Add or Edit Provider ===")

    provider = typer.prompt(
        "Choose a provider to configure",
        type=click.Choice(list(PROVIDERS.keys())),
    )

    # Check if provider already exists
    _ensure_llm_section(config)
    existing = config["llm"].get(provider, {})

    if existing:
        typer.echo(f"\nProvider '{provider}' already configured.")
        if not typer.confirm("Do you want to edit it?", default=True):
            return

    # Get new configuration
    provider_config = _get_provider_config(provider)
    config["llm"][provider] = provider_config

    typer.echo(f"\n✓ {provider} configured successfully!")


def _remove_provider(config: Dict[str, Any]) -> None:
    """
    Remove a provider configuration.

    Args:
        config: Configuration dictionary to update.
    """
    typer.echo("\n=== Remove Provider ===")

    _ensure_llm_section(config)
    llm = config["llm"]

    # Find configured providers
    configured = [
        k
        for k, v in llm.items()
        if isinstance(v, dict) and "api_key" in v or k == "ollama"
    ]

    if not configured:
        typer.echo("No providers configured.")
        return

    provider = typer.prompt(
        "Choose a provider to remove",
        type=click.Choice(configured),
    )

    if provider in llm:
        del llm[provider]
        typer.echo(f"\n✓ {provider} removed.")

        # If this was the default provider, clear it
        if llm.get("default_provider") == provider:
            llm["default_provider"] = ""
            typer.echo("Note: This was your default provider. Set a new default.")

        # Warn if no providers remain
        remaining = [k for k, v in llm.items() if isinstance(v, dict)]
        if not remaining:
            typer.echo(
                "\nWarning: No providers configured. terma cannot run until you add one.\n"
                "Run 'terma --interactive-config' and choose quick-setup."
            )


def _set_default_provider(config: Dict[str, Any]) -> None:
    """
    Set the default provider.

    Args:
        config: Configuration dictionary to update.
    """
    typer.echo("\n=== Set Default Provider ===")

    _ensure_llm_section(config)
    llm = config["llm"]

    # Find configured providers
    configured = [k for k, v in llm.items() if isinstance(v, dict)]

    if not configured:
        typer.echo("No providers configured. Add a provider first.")
        return

    provider = typer.prompt(
        "Choose default provider",
        type=click.Choice(configured),
        default=configured[0],
    )

    llm["default_provider"] = provider

    # Also update the default model if the provider has one
    if provider in llm and "default_model" in llm[provider]:
        llm["default_model"] = llm[provider]["default_model"]

    typer.echo(f"\n✓ Default provider set to {provider}")


def run_wizard(existing_config: bool = False) -> None:
    """
    Run the interactive configuration wizard.

    Args:
        existing_config: If True, config already exists and we're editing it.
    """
    typer.echo("\n" + "=" * 50)
    typer.echo("       terma Configuration Wizard")
    typer.echo("=" * 50)

    # Try to load existing config or start with empty structure
    try:
        config = load_config(allow_ephemeral=True)
        if existing_config:
            typer.echo("\nCurrent configuration:")
            cfg_path = get_config_path()
            typer.echo(f"Config path: {cfg_path}")
            typer.echo(summarize_config(config))
    except Exception as e:
        logger.debug(f"Could not load config: {e}")
        # Start with empty config structure
        config = {"llm": {}}

    # Show menu
    configured_now = [
        k for k, v in config.get("llm", {}).items() if isinstance(v, dict)
    ]
    if existing_config and configured_now:
        actions = [
            "add-or-edit",
            "remove",
            "set-default",
            "view",
            "open-folder",
            "cancel",
        ]
        default_action = "view"
    else:
        # No providers yet - drive user to quick-setup
        actions = ["quick-setup", "add-or-edit", "open-folder", "cancel"]
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
        typer.echo(summarize_config(config))
        return

    # Execute the chosen action
    if action == "quick-setup":
        _quick_setup(config)
    elif action == "add-or-edit":
        _add_or_edit_provider(config)
    elif action == "remove":
        _remove_provider(config)
    elif action == "set-default":
        _set_default_provider(config)
    elif action == "open-folder":
        # Open config directory in system file explorer
        cfg_dir = get_config_path().parent
        try:
            import os
            import subprocess
            import sys

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
        typer.echo("\nYou can now use terma!")
        # Show current config for verification
        typer.echo("\nCurrent configuration:")
        typer.echo(f"Config path: {config_path}")
        typer.echo(summarize_config(config))
    except Exception as e:
        typer.echo(f"\n✗ Error saving configuration: {e}", err=True)
        raise typer.Exit(1)
