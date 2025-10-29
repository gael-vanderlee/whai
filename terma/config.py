"""Configuration management for terma."""

import os
from pathlib import Path
from typing import Any, Dict, Tuple

import tomllib  # Python 3.11+, use tomli for older versions
import yaml

from terma.logging_setup import get_logger

logger = get_logger(__name__)


def get_config_dir() -> Path:
    """Get the terma configuration directory."""
    if os.name == "nt":  # Windows
        config_base = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
    else:  # Unix-like
        config_base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    return config_base / "terma"


def get_default_config() -> str:
    """Return the default configuration TOML by reading from defaults/config.toml."""
    defaults_dir = Path(__file__).parent.parent / "defaults"
    default_config_file = defaults_dir / "config.toml"

    if not default_config_file.exists():
        raise FileNotFoundError(
            f"Default config file not found at {default_config_file}. "
            "This indicates a broken installation. Please reinstall terma."
        )

    logger.debug("Loaded default config from %s", default_config_file)
    return default_config_file.read_text()


def load_config() -> Dict[str, Any]:
    """
    Load configuration from ~/.config/terma/config.toml.

    If the config file doesn't exist, create it with default values.

    Returns:
        Dictionary containing configuration settings.
    """
    config_dir = get_config_dir()
    config_file = config_dir / "config.toml"

    # Create config directory and default file if they don't exist
    if not config_file.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        config_file.write_text(get_default_config())
        print(f"Created default configuration at: {config_file}")
        print("Please edit this file to add your API key.")

    # Load and parse the config file
    with open(config_file, "rb") as f:
        config = tomllib.load(f)

    logger.debug("Configuration loaded from %s", config_file)
    return config


def get_default_role(role_name: str) -> str:
    """
    Return the default role content by reading from defaults/roles/{role_name}.md.

    Args:
        role_name: Name of the role (e.g., 'assistant', 'debug')

    Returns:
        The role content as a string.

    Raises:
        FileNotFoundError: If the default role file doesn't exist.
    """
    defaults_dir = Path(__file__).parent.parent / "defaults" / "roles"
    role_file = defaults_dir / f"{role_name}.md"

    if not role_file.exists():
        raise FileNotFoundError(
            f"Default role file for '{role_name}' not found at {role_file}. "
            "This indicates a broken installation. Please reinstall terma."
        )

    logger.debug("Loaded default role '%s' from %s", role_name, role_file)
    return role_file.read_text()


def ensure_default_roles() -> None:
    """Ensure default roles exist in the roles directory."""
    roles_dir = get_config_dir() / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    # Create assistant role if it doesn't exist
    assistant_role = roles_dir / "assistant.md"
    if not assistant_role.exists():
        assistant_role.write_text(get_default_role("assistant"))

    # Create debug role if it doesn't exist
    debug_role = roles_dir / "debug.md"
    if not debug_role.exists():
        debug_role.write_text(get_default_role("debug"))
    logger.debug("Ensured default roles exist at %s", roles_dir)


def parse_role_file(content: str) -> Tuple[Dict[str, Any], str]:
    """
    Parse a role file with YAML frontmatter and markdown body.

    Args:
        content: The full content of the role file.

    Returns:
        Tuple of (metadata dict, body string).

    Raises:
        ValueError: If the frontmatter is invalid.
    """
    # Check for YAML frontmatter
    if not content.startswith("---"):
        # No frontmatter, return empty metadata and full content as body
        return {}, content

    # Split frontmatter and body
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter format")

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    # Parse frontmatter YAML
    try:
        metadata = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}")

    logger.debug("Parsed role frontmatter with keys: %s", list(metadata.keys()))
    return metadata, body


def load_role(role_name: str = "assistant") -> Tuple[Dict[str, Any], str]:
    """
    Load a role from ~/.config/terma/roles/{role_name}.md.

    Args:
        role_name: Name of the role to load (without .md extension).

    Returns:
        Tuple of (metadata dict, system prompt string).

    Raises:
        FileNotFoundError: If the role file doesn't exist.
        ValueError: If the role file has invalid frontmatter.
    """
    # Ensure default roles exist
    ensure_default_roles()

    # Load the role file
    role_file = get_config_dir() / "roles" / f"{role_name}.md"
    if not role_file.exists():
        raise FileNotFoundError(f"Role '{role_name}' not found at: {role_file}")

    content = role_file.read_text()
    logger.debug("Loaded role '%s' from %s", role_name, role_file)
    return parse_role_file(content)
