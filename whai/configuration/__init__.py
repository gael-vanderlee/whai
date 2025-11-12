"""Configuration management for whai."""

# Re-export main classes and functions for backward compatibility
from whai.configuration.roles import (
    InvalidRoleMetadataError,
    Role,
    ensure_default_roles,
    load_role,
    resolve_model,
    resolve_provider,
    resolve_role,
    resolve_temperature,
)
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

__all__ = [
    # Roles
    "Role",
    "InvalidRoleMetadataError",
    "load_role",
    "resolve_role",
    "resolve_model",
    "resolve_provider",
    "resolve_temperature",
    "ensure_default_roles",
    # User Config
    "WhaiConfig",
    "LLMConfig",
    "RolesConfig",
    "ProviderConfig",
    "InvalidProviderConfigError",
    "MissingConfigError",
    "load_config",
    "save_config",
    "get_config_path",
    "get_provider_class",
]
