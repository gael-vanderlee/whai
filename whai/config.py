"""Configuration management for whai."""

import os
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import tomllib  # Python 3.11+, use tomli for older versions
import yaml

from whai.logging_setup import get_logger

logger = get_logger(__name__)


class MissingConfigError(RuntimeError):
    """Raised when configuration file is missing and not in ephemeral mode."""

    pass


class InvalidRoleMetadataError(ValueError):
    """Raised when role metadata contains invalid values."""

    pass


@dataclass
class RoleMetadata:
    """
    Structured metadata for a role file.

    Attributes:
        model: Optional LLM model name to use for this role.
               If not set, falls back to provider config or default.
        temperature: Optional temperature setting (0.0 to 2.0).
                     Only used when supported by the selected model.
                     If not set, uses provider default or CLI override.
    """

    model: Optional[str] = None
    temperature: Optional[float] = None

    def __post_init__(self) -> None:
        """Validate metadata values after initialization."""
        if self.model is not None:
            if not isinstance(self.model, str) or not self.model.strip():
                raise InvalidRoleMetadataError(
                    "Role metadata 'model' must be a non-empty string if provided."
                )

        if self.temperature is not None:
            if not isinstance(self.temperature, (int, float)):
                raise InvalidRoleMetadataError(
                    "Role metadata 'temperature' must be a number if provided."
                )
            temp_float = float(self.temperature)
            if temp_float < 0.0 or temp_float > 2.0:
                raise InvalidRoleMetadataError(
                    f"Role metadata 'temperature' must be between 0.0 and 2.0, got {temp_float}."
                )
            # Normalize to float if it was an int
            if isinstance(self.temperature, int):
                object.__setattr__(self, "temperature", float(self.temperature))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleMetadata":
        """
        Create RoleMetadata from a dictionary, validating and extracting only known fields.

        Args:
            data: Dictionary containing role metadata (may contain unknown keys).

        Returns:
            RoleMetadata instance with validated fields.

        Raises:
            InvalidRoleMetadataError: If any field has an invalid value.
        """
        # Only extract known fields; ignore unknown ones with a warning
        known_fields = {"model", "temperature"}
        unknown_fields = set(data.keys()) - known_fields
        if unknown_fields:
            logger.warning(
                "Role metadata contains unknown fields (ignored): %s",
                ", ".join(unknown_fields),
            )

        return cls(
            model=data.get("model"),
            temperature=data.get("temperature"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert RoleMetadata to a dictionary, including only non-None fields.

        Returns:
            Dictionary with non-None metadata fields.
        """
        result: Dict[str, Any] = {}
        if self.model is not None:
            result["model"] = self.model
        if self.temperature is not None:
            result["temperature"] = self.temperature
        return result


def get_config_dir() -> Path:
    """Get the whai configuration directory."""
    if os.name == "nt":  # Windows
        config_base = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
    else:  # Unix-like
        config_base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))

    return config_base / "whai"


def get_config_path() -> Path:
    """Get the path to the configuration file."""
    return get_config_dir() / "config.toml"


def load_config(*, allow_ephemeral: bool = False) -> Dict[str, Any]:
    """
    Load configuration from ~/.config/whai/config.toml.

    Args:
        allow_ephemeral: If True, return in-memory default config when file doesn't exist
                        instead of raising an error. Also enabled via WHAI_TEST_MODE=1.

    Returns:
        Dictionary containing configuration settings.

    Raises:
        MissingConfigError: If config file doesn't exist and ephemeral mode is disabled.
    """
    config_file = get_config_path()

    # Handle missing config file
    if not config_file.exists():
        # Check for test mode via environment variable, but only honor it when tests are running
        # This prevents accidental activation during real CLI usage.
        is_test_mode_env = os.getenv("WHAI_TEST_MODE") == "1"
        is_running_pytest = "PYTEST_CURRENT_TEST" in os.environ
        is_test_mode = is_test_mode_env and is_running_pytest

        if allow_ephemeral or is_test_mode:
            logger.warning("Config missing; returning ephemeral defaults for test mode")
            # Return minimal test config without any secrets
            return {
                "llm": {
                    "default_provider": "openai",
                    "openai": {
                        # Ephemeral config includes a dummy key to satisfy validation in tests
                        "api_key": "test-key",
                        "default_model": "gpt-5-mini",
                    },
                }
            }

        raise MissingConfigError(
            f"Configuration file not found at {config_file}. "
            f"Run 'whai --interactive-config' to create your configuration."
        )

    # Load and parse the config file
    with open(config_file, "rb") as f:
        config = tomllib.load(f)

    logger.debug("Configuration loaded from %s", config_file)
    return config


def save_config(config: Dict[str, Any]) -> None:
    """
    Save configuration to ~/.config/whai/config.toml.

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
    default_role = config.get("roles", {}).get("default_role") or "default"

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
    # Show effective model from the default provider, if available
    effective_model = (
        llm.get(default_provider, {}).get("default_model") if default_provider else None
    ) or "MISSING"
    summary += f"Default model: {effective_model}\n"
    summary += f"Default role: {default_role}\n"
    if providers:
        summary += "Configured providers:\n"
        for p in providers:
            summary += f"  - {p}\n"
    else:
        summary += "No providers configured.\n"

    return summary


def validate_llm_config(config: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate minimal LLM configuration needed to run whai.

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
    elif default_provider == "lm_studio":
        api_base = provider_cfg.get("api_base", "").strip()
        if not api_base:
            return (
                False,
                "LM Studio provider configured but api_base is missing. Configure via --interactive-config.",
            )

    return True, "OK"


def get_default_role(role_name: str) -> str:
    """
    Return the default role content by reading from defaults/roles/{role_name}.md.

    Args:
        role_name: Name of the role (e.g., 'default', 'debug')

    Returns:
        The role content as a string.

    Raises:
        FileNotFoundError: If the default role file doesn't exist.
    """
    roles_dir = files("whai").joinpath("defaults", "roles")
    role_file = roles_dir / f"{role_name}.md"

    if not role_file.exists():
        raise FileNotFoundError(
            f"Default role file for '{role_name}' not found at {role_file}. "
            "This indicates a broken installation. Please reinstall whai."
        )

    logger.debug("Loaded default role '%s' from %s", role_name, role_file)
    return role_file.read_text()


def ensure_default_roles() -> None:
    """Ensure default roles exist in the roles directory."""
    roles_dir = get_config_dir() / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    # Create default role if it doesn't exist
    default_role = roles_dir / "default.md"
    if not default_role.exists():
        default_role.write_text(get_default_role("default"))


def parse_role_file(content: str) -> Tuple[RoleMetadata, str]:
    """
    Parse a role file with YAML frontmatter and markdown body.

    Args:
        content: The full content of the role file.

    Returns:
        Tuple of (RoleMetadata, body string).

    Raises:
        ValueError: If the frontmatter is invalid.
        InvalidRoleMetadataError: If the metadata contains invalid values.
    """
    # Check for YAML frontmatter
    if not content.startswith("---"):
        # No frontmatter, return empty metadata and full content as body
        return RoleMetadata(), content

    # Split frontmatter and body
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid frontmatter format")

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    # Parse frontmatter YAML
    try:
        metadata_dict = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in frontmatter: {e}")

    if not isinstance(metadata_dict, dict):
        raise ValueError("Role frontmatter must be a YAML object/mapping")

    # Create structured metadata with validation
    try:
        metadata = RoleMetadata.from_dict(metadata_dict)
    except InvalidRoleMetadataError as e:
        raise InvalidRoleMetadataError(f"Invalid role metadata: {e}") from e

    logger.debug("Parsed role frontmatter: %s", metadata.to_dict())
    return metadata, body


def load_role(role_name: str = "default") -> Tuple[RoleMetadata, str]:
    """
    Load a role from ~/.config/whai/roles/{role_name}.md.

    Args:
        role_name: Name of the role to load (without .md extension).

    Returns:
        Tuple of (RoleMetadata, system prompt string).

    Raises:
        FileNotFoundError: If the role file doesn't exist.
        ValueError: If the role file has invalid frontmatter.
        InvalidRoleMetadataError: If the role metadata contains invalid values.
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


def resolve_role(
    cli_role: Optional[str] = None, config: Optional[Dict[str, Any]] = None
) -> str:
    """Resolve the role to use based on precedence.

    Precedence: explicit CLI value > WHAI_ROLE env var > config default > "default".

    Args:
        cli_role: Role name provided explicitly by CLI options.
        config: Application config dict. If None, it will be loaded in ephemeral mode.

    Returns:
        The resolved role name.
    """
    # 1) Explicit CLI flag wins
    if cli_role:
        return cli_role

    # 2) Environment variable
    env_role = os.getenv("WHAI_ROLE")
    if env_role:
        return env_role

    # 3) Config default
    if config is None:
        try:
            config = load_config(allow_ephemeral=True)
        except Exception:
            config = {}
    cfg_default_role = (config or {}).get("roles", {}).get("default_role")
    if cfg_default_role:
        return cfg_default_role

    # 4) Hardcoded fallback
    return "default"


def resolve_model(
    cli_model: Optional[str] = None,
    role_metadata: Optional[RoleMetadata] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[str, str]:
    """Resolve the LLM model to use based on precedence.

    Precedence: CLI override > role metadata > provider config > built-in fallback.

    Args:
        cli_model: Model name provided explicitly by CLI options.
        role_metadata: RoleMetadata instance from the active role.
        config: Application config dict. If None, it will be loaded in ephemeral mode.

    Returns:
        Tuple of (model_name, source_description) where source_description indicates
        where the model came from for logging purposes.
    """
    # 1) CLI override has highest precedence
    if cli_model:
        return cli_model, "CLI override"

    # 2) Role metadata
    if role_metadata and role_metadata.model:
        return role_metadata.model, "role metadata"

    # 3) Provider config from config.toml
    if config is None:
        try:
            config = load_config(allow_ephemeral=True)
        except Exception:
            config = {}

    default_provider = (config or {}).get("llm", {}).get("default_provider")
    if default_provider:
        provider_config = (config or {}).get("llm", {}).get(default_provider, {})
        default_model = provider_config.get("default_model")
        if default_model:
            return default_model, f"provider config '{default_provider}'"

    # 4) Built-in fallback
    from whai.constants import DEFAULT_LLM_MODEL

    return DEFAULT_LLM_MODEL, "built-in fallback"


def resolve_temperature(
    cli_temperature: Optional[float] = None,
    role_metadata: Optional[RoleMetadata] = None,
) -> Optional[float]:
    """Resolve the temperature setting to use based on precedence.

    Precedence: CLI override > role metadata > None.

    Args:
        cli_temperature: Temperature value provided explicitly by CLI options.
        role_metadata: RoleMetadata instance from the active role.

    Returns:
        The resolved temperature value, or None if not set.
    """
    # 1) CLI override has highest precedence
    if cli_temperature is not None:
        return cli_temperature

    # 2) Role metadata
    if role_metadata and role_metadata.temperature is not None:
        return role_metadata.temperature

    # 3) No temperature set
    return None
