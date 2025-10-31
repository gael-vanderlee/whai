"""Configuration management for terma."""

import os
from pathlib import Path
from typing import Any, Dict, Tuple

import tomllib  # Python 3.11+, use tomli for older versions
import yaml

from terma.logging_setup import get_logger

logger = get_logger(__name__)


class MissingConfigError(RuntimeError):
    """Raised when configuration file is missing and not in ephemeral mode."""

    pass


def get_config_dir() -> Path:
    """Get the terma configuration directory."""
    if os.name == "nt":  # Windows
        config_base = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
    else:  # Unix-like
        config_base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    return config_base / "terma"


def get_config_path() -> Path:
    """Get the path to the configuration file."""
    return get_config_dir() / "config.toml"


def load_config(*, allow_ephemeral: bool = False) -> Dict[str, Any]:
    """
    Load configuration from ~/.config/terma/config.toml.

    Args:
        allow_ephemeral: If True, return in-memory default config when file doesn't exist
                        instead of raising an error. Also enabled via TERMA_TEST_MODE=1.

    Returns:
        Dictionary containing configuration settings.

    Raises:
        MissingConfigError: If config file doesn't exist and ephemeral mode is disabled.
    """
    config_file = get_config_path()

    # Handle missing config file
    if not config_file.exists():
        # Check for test mode via environment variable
        is_test_mode = os.getenv("TERMA_TEST_MODE") == "1"

        if allow_ephemeral or is_test_mode:
            logger.warning("Config missing; returning ephemeral defaults for test mode")
            # Return minimal test config
            return {
                "llm": {
                    "default_provider": "openai",
                    "default_model": "gpt-5-mini",
                    "openai": {
                        "api_key": "test-key",
                        "default_model": "gpt-5-mini",
                    },
                }
            }

        raise MissingConfigError(
            f"Configuration file not found at {config_file}. "
            f"Run 'terma --interactive-config' to create your configuration."
        )

    # Load and parse the config file
    with open(config_file, "rb") as f:
        config = tomllib.load(f)

    logger.debug("Configuration loaded from %s", config_file)
    return config


def save_config(config: Dict[str, Any]) -> None:
    """
    Save configuration to ~/.config/terma/config.toml.

    Args:
        config: Configuration dictionary to save.
    """
    try:
        import tomli_w  # type: ignore
    except ImportError:
        raise ImportError(
            "tomli_w is required to write config files. "
            "Install it with: pip install tomli-w"
        )

    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "wb") as f:
        tomli_w.dump(config, f)

    logger.info("Configuration saved to %s", config_path)


def summarize_config(config: Dict[str, Any]) -> str:
    """
    Create a human-readable summary of the configuration.

    Args:
        config: Configuration dictionary.

    Returns:
        A formatted string summarizing the configuration.
    """
    llm = config.get("llm", {})
    default_provider = llm.get("default_provider") or "MISSING"
    default_model = llm.get("default_model") or "MISSING"

    providers = []
    for key, value in llm.items():
        if isinstance(value, dict):
            # Model display
            provider_model_raw = value.get("default_model")
            provider_model = provider_model_raw if provider_model_raw else "MISSING"

            # API key display
            raw_key = value.get("api_key")
            if raw_key and isinstance(raw_key, str) and raw_key.strip():
                masked_key = raw_key[:8] + "..." if len(raw_key) > 8 else "***"
            else:
                masked_key = "MISSING"

            providers.append(f"{key} (model: {provider_model}, key: {masked_key})")

    summary = f"Default provider: {default_provider}\n"
    summary += f"Default model: {default_model}\n"
    if providers:
        summary += "Configured providers:\n"
        for p in providers:
            summary += f"  - {p}\n"
    else:
        summary += "No providers configured.\n"

    return summary


def validate_llm_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate minimal LLM configuration needed to run terma.

    Returns:
        (is_valid, message). On failure, message explains what to fix.
    """
    llm = config.get("llm")
    if not isinstance(llm, dict):
        return False, "Invalid config: missing [llm] section."

    default_provider = llm.get("default_provider")
    if not default_provider:
        return (
            False,
            "No default provider configured. Set one via --interactive-config.",
        )

    provider_cfg = llm.get(default_provider)
    if not isinstance(provider_cfg, dict):
        return (
            False,
            f"Provider '{default_provider}' has no settings. Configure it via --interactive-config.",
        )

    # Minimal provider-specific checks
    if default_provider == "openai":
        api_key = provider_cfg.get("api_key", "").strip()
        if not api_key:
            return (
                False,
                "OpenAI provider configured but no api_key set. Add it via --interactive-config.",
            )
    elif default_provider == "anthropic":
        api_key = provider_cfg.get("api_key", "").strip()
        if not api_key:
            return (
                False,
                "Anthropic provider configured but no api_key set. Add it via --interactive-config.",
            )
    elif default_provider == "azure_openai":
        required = ["api_key", "api_base", "api_version"]
        missing = [k for k in required if not str(provider_cfg.get(k, "")).strip()]
        if missing:
            return (
                False,
                "Azure OpenAI provider is missing: "
                + ", ".join(missing)
                + ". Configure via --interactive-config.",
            )
    elif default_provider == "ollama":
        api_base = provider_cfg.get("api_base", "").strip()
        if not api_base:
            return (
                False,
                "Ollama provider configured but api_base is missing. Configure via --interactive-config.",
            )

    return True, "OK"


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
