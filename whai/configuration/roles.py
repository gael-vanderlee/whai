"""Role management for whai."""

import os
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml

from whai.configuration.user_config import WhaiConfig
from whai.constants import (
    DEFAULT_MODEL_OPENAI,
    DEFAULT_PROVIDER,
    DEFAULT_ROLE_FILENAME,
    DEFAULT_ROLE_NAME,
    ENV_WHAI_ROLE,
    get_default_model_for_provider,
)
from whai.logging_setup import get_logger
from whai.ui import warn

logger = get_logger(__name__)

NEW_ROLE_TEMPLATE_FILENAME = "new.md"
ROLE_TEMPLATE_PLACEHOLDER = "{{role_name}}"
ROLE_TEMPLATE_MODEL_PLACEHOLDER = "{{default_model}}"
ROLE_TEMPLATE_PROVIDER_PLACEHOLDER = "{{default_provider}}"


class InvalidRoleMetadataError(ValueError):
    """Raised when role metadata contains invalid values."""

    pass


@dataclass
class Role:
    """
    Structured role definition with metadata and body.

    Attributes:
        name: Role name (e.g., 'default', 'debug').
        body: Markdown body containing the role instructions.
        model: Optional LLM model name to use for this role.
               If not set, falls back to provider config or default.
        temperature: Optional temperature setting (0.0 to 2.0).
                     Only used when supported by the selected model.
                     If not set, uses provider default or CLI override.
        provider: Optional LLM provider name to use for this role.
                  If not set, falls back to default provider from config.
    """

    name: str
    body: str
    model: Optional[str] = None
    temperature: Optional[float] = None
    provider: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate role values after initialization."""
        if not self.name or not self.name.strip():
            raise InvalidRoleMetadataError("Role 'name' must be a non-empty string")

        if not self.body or not self.body.strip():
            raise InvalidRoleMetadataError("Role 'body' must be a non-empty string")

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

        if self.provider is not None:
            if not isinstance(self.provider, str) or not self.provider.strip():
                raise InvalidRoleMetadataError(
                    "Role metadata 'provider' must be a non-empty string if provided."
                )

    def to_markdown(self) -> str:
        """
        Serialize role to markdown with YAML frontmatter.

        Returns:
            Markdown string with frontmatter and body.
        """
        # Build frontmatter
        frontmatter_parts = []
        if self.model is not None:
            frontmatter_parts.append(f"model: {self.model}")
        if self.temperature is not None:
            frontmatter_parts.append(f"temperature: {self.temperature}")
        if self.provider is not None:
            frontmatter_parts.append(f"provider: {self.provider}")

        # If no frontmatter, return just the body
        if not frontmatter_parts:
            return self.body

        frontmatter = "\n".join(frontmatter_parts)
        return f"---\n{frontmatter}\n---\n{self.body}"

    @classmethod
    def from_dict(cls, name: str, body: str, metadata: Dict[str, Any]) -> "Role":
        """
        Create Role from name, body, and metadata dictionary.

        Args:
            name: Role name.
            body: Role markdown body.
            metadata: Dictionary containing role metadata (may contain unknown keys).

        Returns:
            Role instance with validated fields.

        Raises:
            InvalidRoleMetadataError: If any field has an invalid value.
        """
        # Only extract known fields; ignore unknown ones with a warning
        known_fields = {"model", "temperature", "provider"}
        unknown_fields = set(metadata.keys()) - known_fields
        if unknown_fields:
            warn(f"Role metadata contains unknown fields (ignored): {unknown_fields}")

        return cls(
            name=name,
            body=body,
            model=metadata.get("model"),
            temperature=metadata.get("temperature"),
            provider=metadata.get("provider"),
        )

    @classmethod
    def from_default(cls, name: str, body: str) -> "Role":
        """
        Create a default role with no custom metadata.

        Args:
            name: Role name.
            body: Role body text.

        Returns:
            Role instance with default values.
        """
        return cls(name=name, body=body)

    @classmethod
    def from_file(cls, path: Path, name: Optional[str] = None) -> "Role":
        """
        Load a role from a markdown file.

        Args:
            path: Path to the markdown file.
            name: Role name (if None, inferred from filename).

        Returns:
            Role instance parsed from the file.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            ValueError: If the frontmatter is invalid.
            InvalidRoleMetadataError: If the metadata contains invalid values.
        """
        if not path.exists():
            raise FileNotFoundError(f"Role file not found: {path}")

        if name is None:
            name = path.stem

        content = path.read_text(encoding="utf-8")
        logger.debug("Loading role '%s' from %s", name, path, extra={"category": "config"})
        return cls.from_markdown(name, content)

    @classmethod
    def from_markdown(cls, name: str, content: str) -> "Role":
        """
        Parse a role from markdown content with optional YAML frontmatter.

        Args:
            name: Role name.
            content: The full markdown content.

        Returns:
            Role instance.

        Raises:
            ValueError: If the frontmatter is invalid.
            InvalidRoleMetadataError: If the metadata contains invalid values.
        """
        # Check for YAML frontmatter
        if not content.startswith("---"):
            # No frontmatter, return role with just body
            return cls(name=name, body=content.strip())

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

        # Create Role with validation
        try:
            role = cls.from_dict(name, body, metadata_dict)
        except InvalidRoleMetadataError as e:
            raise InvalidRoleMetadataError(f"Invalid role metadata: {e}") from e

        logger.debug(
            "Parsed role: %s (model=%s, temp=%s, provider=%s)",
            name,
            role.model,
            role.temperature,
            role.provider,
        )
        return role

    def to_file(self, path: Path) -> None:
        """
        Save this role to a markdown file.

        Args:
            path: Path where to save the role file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_markdown(), encoding="utf-8")
        logger.debug("Saved role '%s' to %s", self.name, path)


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


def get_new_role_template() -> str:
    """
    Return the packaged template used when creating a new role.

    Returns:
        The raw template content.

    Raises:
        FileNotFoundError: If the template file is missing from the installation.
    """
    roles_dir = files("whai").joinpath("defaults", "roles")
    template_file = roles_dir / NEW_ROLE_TEMPLATE_FILENAME

    if not template_file.exists():
        raise FileNotFoundError(
            f"New role template not found at {template_file}. "
            "This indicates a broken installation. Please reinstall whai."
        )

    logger.debug("Loaded new role template from %s", template_file, extra={"category": "config"})
    return template_file.read_text()


def render_new_role_template(role_name: str) -> str:
    """
    Render the new role template with the provided role name.

    Args:
        role_name: The role name to embed into the template.

    Returns:
        The rendered template text.

    Raises:
        RuntimeError: If the template placeholder is missing.
    """
    template = get_new_role_template()

    if ROLE_TEMPLATE_PLACEHOLDER not in template:
        raise RuntimeError(
            f"New role template missing placeholder '{ROLE_TEMPLATE_PLACEHOLDER}'. "
        )

    rendered = template.replace(ROLE_TEMPLATE_PLACEHOLDER, role_name)

    if ROLE_TEMPLATE_MODEL_PLACEHOLDER in rendered:
        rendered = rendered.replace(
            ROLE_TEMPLATE_MODEL_PLACEHOLDER, DEFAULT_MODEL_OPENAI
        )

    if ROLE_TEMPLATE_PROVIDER_PLACEHOLDER in rendered:
        rendered = rendered.replace(
            ROLE_TEMPLATE_PROVIDER_PLACEHOLDER, DEFAULT_PROVIDER
        )

    logger.info("Rendered new role template for '%s'", role_name, extra={"category": "config"})
    return rendered


def ensure_default_roles() -> None:
    """Ensure default roles exist in the roles directory."""
    from whai.configuration.user_config import get_config_dir

    roles_dir = get_config_dir() / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)

    # Create default role if it doesn't exist
    default_role = roles_dir / DEFAULT_ROLE_FILENAME
    if not default_role.exists():
        logger.info(
            "No default role found, creating default role '%s' at %s",
            DEFAULT_ROLE_NAME,
            default_role,
        )
        default_role.write_text(get_default_role(DEFAULT_ROLE_NAME))


def load_role(role_name: str = DEFAULT_ROLE_NAME) -> Role:
    """
    Load a role from ~/.config/whai/roles/{role_name}.md.

    Args:
        role_name: Name of the role to load (without .md extension).

    Returns:
        Role object with metadata and body.

    Raises:
        FileNotFoundError: If the role file doesn't exist.
        ValueError: If the role file has invalid frontmatter.
        InvalidRoleMetadataError: If the role metadata contains invalid values.
    """
    from whai.configuration.user_config import get_config_dir

    # Ensure default roles exist
    ensure_default_roles()

    # Load the role file
    role_file = get_config_dir() / "roles" / f"{role_name}.md"
    role = Role.from_file(role_file, role_name)
    logger.info("Loaded role '%s' from %s", role_name, role_file)
    return role


def resolve_role(
    cli_role: Optional[str] = None, config: Optional[WhaiConfig] = None
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
    env_role = os.getenv(ENV_WHAI_ROLE)
    if env_role:
        return env_role

    # 3) Config default
    if config is None:
        try:
            from whai.configuration.user_config import load_config

            config = load_config()
        except Exception:
            pass
    if config and config.roles.default_role:
        return config.roles.default_role

    # 4) Hardcoded fallback
    return DEFAULT_ROLE_NAME


def resolve_model(
    cli_model: Optional[str] = None,
    role: Optional[Role] = None,
    config: Optional[WhaiConfig] = None,
) -> Tuple[str, str]:
    """Resolve the LLM model to use based on precedence.

    Precedence: CLI override > role metadata > provider config.

    Args:
        cli_model: Model name provided explicitly by CLI options.
        role: Role instance from the active role.
        config: WhaiConfig instance. If None, it will be loaded.

    Returns:
        Tuple of (model_name, source_description) where source_description indicates
        where the model came from for logging purposes.

    Raises:
        RuntimeError: If no providers are configured and no model can be resolved.
    """
    # 1) CLI override has highest precedence
    if cli_model:
        return cli_model, "CLI override"

    # 2) Role metadata
    if role and role.model:
        return role.model, "role metadata"

    # 3) Provider config from config.toml
    if config is None:
        try:
            from whai.configuration.user_config import load_config

            config = load_config()
        except Exception:
            pass

    if config:
        # Check if any providers are configured
        if not config.llm.providers:
            raise RuntimeError(
                "No LLM providers configured. Run 'whai --interactive-config' to set up a provider."
            )

        # Check if default_provider is set and exists
        default_provider = config.llm.default_provider
        if default_provider is None:
            raise RuntimeError(
                "No default provider configured. Run 'whai --interactive-config' to set up a provider."
            )

        provider_config = config.llm.get_provider(default_provider)
        if not provider_config:
            available = list(config.llm.providers.keys())
            raise RuntimeError(
                f"Default provider '{default_provider}' is not configured. "
                f"Available providers: {available if available else 'none'}. "
                "Run 'whai --interactive-config' to fix this."
            )

        if provider_config.default_model:
            return (
                provider_config.default_model,
                f"provider config '{default_provider}'",
            )
        else:
            raise RuntimeError(
                f"Default provider '{default_provider}' has no default model configured. "
                "Run 'whai --interactive-config' to fix this."
            )

    # No config available
    raise RuntimeError(
        "No configuration found. Run 'whai --interactive-config' to set up a provider."
    )


def resolve_temperature(
    cli_temperature: Optional[float] = None,
    role: Optional[Role] = None,
) -> Optional[float]:
    """Resolve the temperature setting to use based on precedence.

    Precedence: CLI override > role metadata > None.

    Args:
        cli_temperature: Temperature value provided explicitly by CLI options.
        role: Role instance from the active role.

    Returns:
        The resolved temperature value, or None if not set.
    """
    # 1) CLI override has highest precedence
    if cli_temperature is not None:
        return cli_temperature

    # 2) Role metadata
    if role and role.temperature is not None:
        return role.temperature

    # 3) No temperature set
    return None


def resolve_provider(
    cli_provider: Optional[str] = None,
    role: Optional[Role] = None,
    config: Optional[WhaiConfig] = None,
) -> Tuple[Optional[str], str]:
    """Resolve the LLM provider to use based on precedence.

    Precedence: CLI override > role metadata > default provider from config.

    Args:
        cli_provider: Provider name provided explicitly by CLI options.
        role: Role instance from the active role.
        config: WhaiConfig instance. If None, it will be loaded.

    Returns:
        Tuple of (provider_name, source_description) where source_description indicates
        where the provider came from for logging purposes.
    """
    # 1) CLI override has highest precedence
    if cli_provider:
        return cli_provider, "CLI override"

    # 2) Role metadata
    if role and role.provider:
        return role.provider, "role metadata"

    # 3) Default provider from config
    if config is None:
        try:
            from whai.configuration.user_config import load_config

            config = load_config()
        except Exception:
            pass

    if config and config.llm.default_provider:
        return config.llm.default_provider, f"default provider '{config.llm.default_provider}'"

    # No provider resolved
    return None, "none (will use LLMProvider default)"
