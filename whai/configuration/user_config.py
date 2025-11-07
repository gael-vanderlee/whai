"""User configuration management for whai."""

import contextlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

# Use tomllib for Python 3.11+, tomli for older versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

import tomli_w

from whai.constants import (
    CONFIG_FILENAME,
    DEFAULT_MODEL_OPENAI,
    DEFAULT_PROVIDER,
    DEFAULT_ROLE_NAME,
    ENV_WHAI_TEST_MODE,
)
from whai.logging_setup import get_logger

logger = get_logger(__name__)


@contextlib.contextmanager
def _suppress_stdout_stderr():
    """Context manager to suppress stdout and stderr output."""
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            sys.stdout = devnull
            sys.stderr = devnull
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class MissingConfigError(RuntimeError):
    """Raised when configuration file is missing and not in ephemeral mode."""

    pass


class InvalidProviderConfigError(ValueError):
    """Raised when provider configuration contains invalid values."""

    pass


# ============================================================================
# Validation Result Dataclass
# ============================================================================


@dataclass
class ValidationResult:
    """Result of provider configuration validation."""

    is_valid: bool
    checks_performed: List[str]
    issues: List[str]
    details: Dict[str, Any]


# ============================================================================
# Provider Configuration Dataclasses
# ============================================================================


@dataclass
class ProviderConfig:
    """
    Base configuration for LLM providers.

    Contains sensible defaults for all possible provider fields.
    Subclasses define provider_name and override validation as needed.
    """

    api_key: Optional[str] = None
    api_base: Optional[str] = None
    api_version: Optional[str] = None
    default_model: Optional[str] = None

    # Subclasses must define this
    provider_name: str = "unknown"

    def __post_init__(self) -> None:
        """Validate configuration values."""
        t0 = time.perf_counter()
        self._validate_api_base()
        self._validate_required_fields()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        # Use comma formatting for readability
        from whai.utils import _format_ms

    def _validate_api_base(self) -> None:
        """Validate URL format for api_base if provided."""
        if self.api_base is not None:
            if not isinstance(self.api_base, str) or not self.api_base.strip():
                raise InvalidProviderConfigError(
                    f"{self.provider_name} provider 'api_base' must be a non-empty string if provided."
                )
            # Basic URL validation
            if not (
                self.api_base.startswith("http://")
                or self.api_base.startswith("https://")
            ):
                raise InvalidProviderConfigError(
                    f"{self.provider_name} provider 'api_base' must be a valid HTTP/HTTPS URL, got: {self.api_base}"
                )

    def _validate_required_fields(self) -> None:
        """Validate required fields. Override in subclasses if needed."""
        pass

    def get_summary_fields(self) -> Dict[str, str]:
        """
        Get provider-specific fields for summary display.

        Returns a dictionary mapping field names to their display values.
        Sensitive values (like API keys) should be masked.
        Override in subclasses to customize which fields are shown.

        Returns:
            Dictionary of field_name -> display_value
        """
        fields = {}
        fields["model"] = self.default_model or "MISSING"
        if self.api_key:
            masked_key = self.api_key[:8] + "..." if len(self.api_key) > 8 else "***"
            fields["key"] = masked_key
        else:
            fields["key"] = "MISSING"
        return fields

    def validate(
        self, on_progress: Optional[Callable[[str, Optional[bool]], None]] = None
    ) -> ValidationResult:
        """
        Validate this provider configuration using external checks.

        Args:
            on_progress: Optional callback function(message: str, success: Optional[bool])
                        called for each validation step with progress updates.
                        None indicates check in progress, True/False indicate result.

        Returns:
            ValidationResult with validation outcomes.
        """
        if on_progress is None:
            # Default no-op callback
            def _noop_progress(msg: str, success: Optional[bool]) -> None:
                pass

            on_progress = _noop_progress

        checks_performed = ["Field validation"]
        issues = []
        details: Dict[str, Any] = {}

        # Field validation is already done in __post_init__, just report it
        # Instant check - print directly with result
        on_progress("Validating fields", True)
        checks_performed.append("Field validation")

        # API key validation (if applicable)
        if self.api_key:
            on_progress("Validating API key", None)
            checks_performed.append("API key format")
            try:
                from litellm import check_valid_key

                # Build model name for validation
                model = self._get_litellm_model_name()
                checks_performed.append(f"API key validation ({model})")

                # Check if key is valid (with timeout)
                import socket

                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(5.0)

                try:
                    # Suppress LiteLLM output during validation
                    with _suppress_stdout_stderr():
                        is_key_valid = check_valid_key(
                            model=model, api_key=self.api_key
                        )
                    if not is_key_valid:
                        issues.append(
                            f"API key validation failed for {self.provider_name}"
                        )
                        on_progress("Validating API key", False)
                    else:
                        details["api_key_valid"] = True
                        on_progress("Validating API key", True)
                except Exception as e:
                    issues.append(f"Could not validate API key: {str(e)}")
                    on_progress("Validating API key", False)
                finally:
                    socket.setdefaulttimeout(old_timeout)

            except ImportError:
                issues.append("LiteLLM not available for validation")
                on_progress("Validating API key", False)
            except Exception as e:
                issues.append(f"API key validation error: {str(e)}")
                on_progress("Validating API key", False)

        # Model validation
        if self.default_model:
            on_progress("Validating model", None)
            checks_performed.append("Model configuration")
            details["default_model"] = self.default_model

            model_valid, model_issue = self._validate_model()

            if not model_valid and model_issue:
                issues.append(model_issue)
                on_progress("Validating model", False)
            else:
                on_progress("Validating model", True)

        # API base validation (for local providers)
        if self.api_base:
            on_progress("Validating API base connectivity", None)
            checks_performed.append("API base configuration")
            details["api_base"] = self.api_base

            try:
                import urllib.error
                import urllib.request

                req = urllib.request.Request(self.api_base, method="HEAD")
                urllib.request.urlopen(req, timeout=5)
                details["api_base_reachable"] = True
                on_progress("Validating API base connectivity", True)
            except Exception as e:
                issues.append(f"API base not reachable: {str(e)}")
                details["api_base_reachable"] = False
                on_progress("Validating API base connectivity", False)

        is_valid = len(issues) == 0

        return ValidationResult(
            is_valid=is_valid,
            checks_performed=checks_performed,
            issues=issues,
            details=details,
        )

    def _validate_model(self) -> Tuple[bool, Optional[str]]:
        """
        Validate the model configuration.

        Returns:
            Tuple of (model_valid: bool, model_issue: Optional[str])
            If model_valid is False, model_issue contains the reason.

        This method can be overridden by subclasses to provide provider-specific
        model validation logic.
        """
        if not self.default_model:
            return True, None

        model_valid = False
        model_issue = None

        # Try to validate model using LiteLLM's get_model_info
        try:
            from litellm import get_model_info

            # Get model name in LiteLLM format
            model = self._get_litellm_model_name()

            # Use get_model_info to check if model exists
            # This raises an exception if the model doesn't exist
            try:
                # Suppress LiteLLM output during validation
                with _suppress_stdout_stderr():
                    get_model_info(model)
                # If we get here, model exists
                model_valid = True
            except Exception as e:
                # Model doesn't exist or not recognized by LiteLLM
                error_msg = str(e)
                if "isn't mapped yet" in error_msg or "not found" in error_msg.lower():
                    model_issue = f"Model '{self.default_model}' is not recognized"
                    model_valid = False
                else:
                    # Unknown error - assume valid (could be network issue, etc.)
                    model_issue = f"Could not validate model: {error_msg}"
                    model_valid = True
        except Exception as e:
            model_issue = f"Could not validate model: {str(e)}"
            # Assume valid if validation fails (new models, etc.)
            model_valid = True

        return model_valid, model_issue

    def _strip_provider_prefix(self, model: str, prefix: str) -> str:
        """
        Strip provider prefix from model name if present.

        Args:
            model: The model name (may include prefix).
            prefix: The prefix to strip (e.g., 'gemini/', 'lm_studio/').

        Returns:
            Model name without the prefix.
        """
        if model and model.startswith(prefix):
            return model[len(prefix) :]
        return model

    def _get_litellm_model_name(self) -> str:
        """Get the model name formatted for LiteLLM validation. Override in subclasses."""
        return self.default_model or "default"

    def sanitize_model_name(self, model: str) -> str:
        """
        Sanitize/transform a model name for use with LiteLLM.

        This method can be overridden by subclasses to handle provider-specific
        model name transformations (e.g., adding prefixes, stripping prefixes).

        Args:
            model: The raw model name to sanitize.

        Returns:
            The sanitized model name, by default returns the model unchanged.
        """
        return model

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TOML serialization, excluding None values."""
        result: Dict[str, Any] = {}
        if self.api_key is not None:
            result["api_key"] = self.api_key
        if self.api_base is not None:
            result["api_base"] = self.api_base
        if self.api_version is not None:
            result["api_version"] = self.api_version
        if self.default_model is not None:
            result["default_model"] = self.default_model
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProviderConfig":
        """Create ProviderConfig from dictionary."""
        return cls(
            api_key=data.get("api_key"),
            api_base=data.get("api_base"),
            api_version=data.get("api_version"),
            default_model=data.get("default_model"),
        )


@dataclass
class OpenAIConfig(ProviderConfig):
    """Configuration for OpenAI provider."""

    provider_name: str = "openai"

    def _validate_required_fields(self) -> None:
        """Validate OpenAI-specific requirements."""
        if not self.api_key or not self.api_key.strip():
            raise InvalidProviderConfigError("OpenAI provider requires 'api_key'")
        if not self.default_model or not self.default_model.strip():
            raise InvalidProviderConfigError("OpenAI provider requires 'default_model'")


@dataclass
class AnthropicConfig(ProviderConfig):
    """Configuration for Anthropic provider."""

    provider_name: str = "anthropic"

    def _validate_required_fields(self) -> None:
        """Validate Anthropic-specific requirements."""
        if not self.api_key or not self.api_key.strip():
            raise InvalidProviderConfigError("Anthropic provider requires 'api_key'")
        if not self.default_model or not self.default_model.strip():
            raise InvalidProviderConfigError(
                "Anthropic provider requires 'default_model'"
            )


@dataclass
class GeminiConfig(ProviderConfig):
    """Configuration for Gemini provider."""

    provider_name: str = "gemini"

    def __post_init__(self) -> None:
        """Strip gemini/ prefix from model name if present."""
        super().__post_init__()
        if self.default_model:
            self.default_model = self._strip_provider_prefix(self.default_model, "gemini/")

    def _validate_required_fields(self) -> None:
        """Validate Gemini-specific requirements."""
        if not self.api_key or not self.api_key.strip():
            raise InvalidProviderConfigError("Gemini provider requires 'api_key'")
        if not self.default_model or not self.default_model.strip():
            raise InvalidProviderConfigError("Gemini provider requires 'default_model'")

    def _get_litellm_model_name(self) -> str:
        """Get model name with gemini/ prefix."""
        model = self.default_model or "default"
        return f"gemini/{model}"

    def sanitize_model_name(self, model: str) -> str:
        """Strip gemini/ prefix if present, then add it back for LiteLLM."""
        base_model = self._strip_provider_prefix(model, "gemini/")
        return f"gemini/{base_model}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GeminiConfig":
        """Create GeminiConfig from dictionary, stripping gemini/ prefix if present."""
        default_model = data.get("default_model")
        if default_model and default_model.startswith("gemini/"):
            default_model = default_model[len("gemini/") :]
        return cls(
            api_key=data.get("api_key"),
            api_base=data.get("api_base"),
            api_version=data.get("api_version"),
            default_model=default_model,
        )


@dataclass
class AzureOpenAIConfig(ProviderConfig):
    """Configuration for Azure OpenAI provider."""

    provider_name: str = "azure_openai"

    def _validate_required_fields(self) -> None:
        """Validate Azure OpenAI-specific requirements."""
        if not self.api_key or not self.api_key.strip():
            raise InvalidProviderConfigError("Azure OpenAI provider requires 'api_key'")
        if not self.api_base or not self.api_base.strip():
            raise InvalidProviderConfigError(
                "Azure OpenAI provider requires 'api_base'"
            )
        if not self.api_version or not self.api_version.strip():
            raise InvalidProviderConfigError(
                "Azure OpenAI provider requires 'api_version'"
            )
        if not self.default_model or not self.default_model.strip():
            raise InvalidProviderConfigError(
                "Azure OpenAI provider requires 'default_model'"
            )

    def get_summary_fields(self) -> Dict[str, str]:
        """Get Azure OpenAI-specific fields for summary."""
        fields = {}
        fields["model"] = self.default_model or "MISSING"
        if self.api_key:
            masked_key = self.api_key[:8] + "..." if len(self.api_key) > 8 else "***"
            fields["key"] = masked_key
        else:
            fields["key"] = "MISSING"
        fields["api_base"] = self.api_base or "MISSING"
        fields["api_version"] = self.api_version or "MISSING"
        return fields

    def _get_litellm_model_name(self) -> str:
        """Get model name with azure/ prefix."""
        return f"azure/{self.default_model or 'default'}"


@dataclass
class OllamaConfig(ProviderConfig):
    """Configuration for Ollama provider (no API key required)."""

    provider_name: str = "ollama"

    def __post_init__(self) -> None:
        """Strip ollama/ prefix from model name if present."""
        super().__post_init__()
        if self.default_model:
            self.default_model = self._strip_provider_prefix(self.default_model, "ollama/")

    def _validate_required_fields(self) -> None:
        """Validate Ollama-specific requirements."""
        if not self.api_base or not self.api_base.strip():
            raise InvalidProviderConfigError("Ollama provider requires 'api_base'")
        if not self.default_model or not self.default_model.strip():
            raise InvalidProviderConfigError("Ollama provider requires 'default_model'")

    def get_summary_fields(self) -> Dict[str, str]:
        """Get Ollama-specific fields for summary."""
        fields = {}
        fields["model"] = self.default_model or "MISSING"
        fields["api_base"] = self.api_base or "MISSING"
        # API key is optional for Ollama, only show if present
        if self.api_key:
            masked_key = self.api_key[:8] + "..." if len(self.api_key) > 8 else "***"
            fields["key"] = masked_key
        return fields

    def _get_litellm_model_name(self) -> str:
        """Get model name with ollama/ prefix."""
        return f"ollama/{self.default_model or 'default'}"

    def sanitize_model_name(self, model: str) -> str:
        """Strip ollama/ prefix if present, then add it back for LiteLLM."""
        base_model = self._strip_provider_prefix(model, "ollama/")
        return f"ollama/{base_model}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OllamaConfig":
        """Create OllamaConfig from dictionary, stripping ollama/ prefix if present."""
        default_model = data.get("default_model")
        if default_model and default_model.startswith("ollama/"):
            default_model = default_model[len("ollama/") :]
        return cls(
            api_key=data.get("api_key"),
            api_base=data.get("api_base"),
            api_version=data.get("api_version"),
            default_model=default_model,
        )


@dataclass
class LMStudioConfig(ProviderConfig):
    """Configuration for LM Studio provider (no API key required)."""

    provider_name: str = "lm_studio"

    def __post_init__(self) -> None:
        """Strip lm_studio/ or openai/ prefix from model name if present."""
        super().__post_init__()
        if self.default_model:
            # Strip lm_studio/ prefix if present
            self.default_model = self._strip_provider_prefix(self.default_model, "lm_studio/")
            # Also strip openai/ prefix if present (for backward compatibility)
            self.default_model = self._strip_provider_prefix(self.default_model, "openai/")

    def _validate_required_fields(self) -> None:
        """Validate LM Studio-specific requirements."""
        if not self.api_base or not self.api_base.strip():
            raise InvalidProviderConfigError("LM Studio provider requires 'api_base'")
        if not self.default_model or not self.default_model.strip():
            raise InvalidProviderConfigError(
                "LM Studio provider requires 'default_model'"
            )

    def get_summary_fields(self) -> Dict[str, str]:
        """Get LM Studio-specific fields for summary."""
        fields = {}
        fields["model"] = self.default_model or "MISSING"
        fields["api_base"] = self.api_base or "MISSING"
        # API key is optional for LM Studio, only show if present
        if self.api_key:
            masked_key = self.api_key[:8] + "..." if len(self.api_key) > 8 else "***"
            fields["key"] = masked_key
        return fields

    def _get_litellm_model_name(self) -> str:
        """Get model name with openai/ prefix (LM Studio uses OpenAI-compatible API)."""
        return f"openai/{self.default_model or 'default'}"

    def sanitize_model_name(self, model: str) -> str:
        """
        Transform a model name to the format required by LiteLLM for LM Studio.

        LM Studio uses an OpenAI-compatible API, so LiteLLM expects 'openai/{model}' format.
        This method handles model names that may come with 'lm_studio/' or 'openai/' prefixes.

        Args:
            model: The model name to transform (may include 'lm_studio/' or 'openai/' prefix).

        Returns:
            Model name formatted as 'openai/{base_model}' for LiteLLM.
        """
        # Strip 'lm_studio/' prefix if present
        base_model = self._strip_provider_prefix(model, "lm_studio/")
        # Strip 'openai/' prefix if present (in case user already formatted it)
        base_model = self._strip_provider_prefix(base_model, "openai/")
        # Format as 'openai/{model}' for LiteLLM
        return f"openai/{base_model}"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LMStudioConfig":
        """Create LMStudioConfig from dictionary, stripping lm_studio/ or openai/ prefix if present."""
        default_model = data.get("default_model")
        if default_model:
            # Strip lm_studio/ prefix if present
            if default_model.startswith("lm_studio/"):
                default_model = default_model[len("lm_studio/") :]
            # Also strip openai/ prefix if present (for backward compatibility)
            elif default_model.startswith("openai/"):
                default_model = default_model[len("openai/") :]
        return cls(
            api_key=data.get("api_key"),
            api_base=data.get("api_base"),
            api_version=data.get("api_version"),
            default_model=default_model,
        )

    def _validate_model(self) -> Tuple[bool, Optional[str]]:
        """
        Validate the model by querying LM Studio's /models endpoint directly.

        LM Studio models are dynamically loaded locally and may not be in
        LiteLLM's model registry, so we validate against the actual LM Studio API.

        Returns:
            Tuple of (model_valid: bool, model_issue: Optional[str])
        """
        if not self.default_model:
            return True, None

        if not self.api_base:
            # Can't validate without API base
            return True, None

        try:
            import json
            import urllib.error
            import urllib.request

            # Query LM Studio's /models endpoint (OpenAI-compatible)
            models_url = f"{self.api_base.rstrip('/')}/models"
            req = urllib.request.Request(
                models_url, headers={"Content-Type": "application/json"}, method="GET"
            )

            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                available_models = [model.get("id") for model in data.get("data", [])]

                if self.default_model in available_models:
                    return True, None
                else:
                    if available_models:
                        available_str = ", ".join(available_models[:5]) + (
                            "..." if len(available_models) > 5 else ""
                        )
                        issue = (
                            f"Model '{self.default_model}' not found in LM Studio. "
                            f"Available models: {available_str}"
                        )
                    else:
                        issue = "No models found in LM Studio"
                    return False, issue

        except urllib.error.URLError:
            # Network error - assume model might be valid but we can't check
            return True, None
        except json.JSONDecodeError:
            # Invalid response - assume model might be valid
            return True, None
        except Exception:
            # Unknown error - assume valid
            return True, None


def get_provider_class(name: str) -> Type[ProviderConfig]:
    """
    Get the appropriate ProviderConfig subclass for a provider name.

    Args:
        name: Provider name (e.g., 'openai', 'anthropic')

    Returns:
        ProviderConfig subclass

    Raises:
        ValueError: If provider name is unknown
    """
    provider_classes = {
        "openai": OpenAIConfig,
        "anthropic": AnthropicConfig,
        "gemini": GeminiConfig,
        "azure_openai": AzureOpenAIConfig,
        "ollama": OllamaConfig,
        "lm_studio": LMStudioConfig,
    }

    if name not in provider_classes:
        raise ValueError(
            f"Unknown provider '{name}'. "
            f"Supported providers: {', '.join(provider_classes.keys())}"
        )

    return provider_classes[name]


# ============================================================================
# Main Configuration Dataclasses
# ============================================================================


@dataclass
class LLMConfig:
    """Configuration for LLM providers."""

    default_provider: Optional[str]
    providers: Dict[str, ProviderConfig]

    def __post_init__(self) -> None:
        """Validate that default_provider exists in providers if set."""
        if self.default_provider is not None and self.default_provider not in self.providers:
            logger.warning(
                f"Default provider '{self.default_provider}' is not configured in providers. "
                f"Available providers: {list(self.providers.keys()) if self.providers else 'none'}"
            )

    def get_provider(self, name: str) -> Optional[ProviderConfig]:
        """Get a provider configuration by name."""
        return self.providers.get(name)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TOML serialization."""
        result: Dict[str, Any] = {}
        if self.default_provider is not None:
            result["default_provider"] = self.default_provider
        # Add each provider's config
        for name, provider_config in self.providers.items():
            result[name] = provider_config.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMConfig":
        """Create LLMConfig from dictionary."""
        # Get default_provider from data, or None if not present
        default_provider = data.get("default_provider")

        # Parse providers
        providers: Dict[str, ProviderConfig] = {}
        for key, value in data.items():
            if key == "default_provider" or not isinstance(value, dict):
                continue

            # Get the appropriate provider class and instantiate
            try:
                provider_class = get_provider_class(key)
                providers[key] = provider_class.from_dict(value)
            except (ValueError, InvalidProviderConfigError) as e:
                logger.warning(f"Skipping invalid provider '{key}': {e}")

        config = cls(
            default_provider=default_provider,
            providers=providers,
        )
        return config


@dataclass
class RolesConfig:
    """Configuration for roles."""

    default_role: str = DEFAULT_ROLE_NAME

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TOML serialization."""
        return {"default_role": self.default_role}


@dataclass
class WhaiConfig:
    """Main whai configuration."""

    llm: LLMConfig
    roles: RolesConfig

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TOML serialization."""
        return {
            "llm": self.llm.to_dict(),
            "roles": self.roles.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WhaiConfig":
        """Create WhaiConfig from dictionary."""
        llm_data = data.get("llm", {})
        roles_data = data.get("roles", {})

        return cls(
            llm=LLMConfig.from_dict(llm_data),
            roles=RolesConfig(
                default_role=roles_data.get("default_role", DEFAULT_ROLE_NAME)
            ),
        )

    @classmethod
    def from_file(cls, path: Path) -> "WhaiConfig":
        """Load configuration from a file (TOML format)."""
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data)

    def to_file(self, path: Path) -> None:
        """Save configuration to a file (TOML format)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            tomli_w.dump(self.to_dict(), f)


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
    return (get_config_dir() / CONFIG_FILENAME).resolve()


def load_config(path: Optional[Path] = None) -> WhaiConfig:
    """
    Load configuration from default path or specified path.

    Args:
        path: Optional path to config file. If None, uses default path.

    Returns:
        WhaiConfig instance containing configuration settings.

    Raises:
        MissingConfigError: If config file doesn't exist.
    """
    if path is None:
        config_file = get_config_path()

        # Handle missing config file - return default config for tests
        if not config_file.exists():
            # Check for test mode (only honor when actually running pytest)
            is_test_mode_env = os.getenv(ENV_WHAI_TEST_MODE) == "1"
            is_running_pytest = "PYTEST_CURRENT_TEST" in os.environ

            if is_test_mode_env and is_running_pytest:
                logger.warning(
                    "Config missing; returning ephemeral defaults for test mode"
                )
                # Return minimal test config
                return WhaiConfig(
                    llm=LLMConfig(
                        default_provider=DEFAULT_PROVIDER,
                        providers={
                            "openai": OpenAIConfig(
                                api_key="test-key",
                                default_model=DEFAULT_MODEL_OPENAI,
                            )
                        },
                    ),
                    roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
                )

            raise MissingConfigError(
                f"Configuration file not found at {config_file}. "
                f"Run 'whai --interactive-config' to create your configuration."
            )

        path = config_file

    logger.debug("Configuration loaded from %s", path, extra={"category": "config"})
    return WhaiConfig.from_file(path)


def save_config(config: WhaiConfig, path: Optional[Path] = None) -> None:
    """
    Save configuration to default path or specified path.

    Args:
        config: WhaiConfig instance to save.
        path: Optional path to save to. If None, uses default path.
    """
    if path is None:
        path = get_config_path()

    config.to_file(path)
    logger.info("Configuration saved to %s", path)
