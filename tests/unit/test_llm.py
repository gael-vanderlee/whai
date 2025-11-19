"""Tests for LLM module."""

import os
import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import create_test_config, create_test_perf_logger
from whai import llm
from whai.configuration.user_config import (
    AnthropicConfig,
    AzureOpenAIConfig,
    LMStudioConfig,
    OllamaConfig,
    OpenAIConfig,
)


def test_get_base_system_prompt_deep_context():
    """Test base system prompt with deep context."""
    prompt = llm.get_base_system_prompt(is_deep_context=True)
    assert "terminal scrollback" in prompt
    assert "commands and their output" in prompt
    assert "whai" in prompt
    assert "execute_shell" in prompt
    # Should include system information
    assert "System:" in prompt
    assert "OS:" in prompt
    assert "DateTime:" in prompt


def test_get_base_system_prompt_shallow_context():
    """Test base system prompt with shallow context."""
    prompt = llm.get_base_system_prompt(is_deep_context=False)
    assert "command history" in prompt
    assert "commands only, no command outputs" in prompt
    # Should include system information
    assert "System:" in prompt
    assert "OS:" in prompt
    assert "DateTime:" in prompt


def test_get_base_system_prompt_with_timeout():
    """Test base system prompt includes timeout information when provided."""
    prompt = llm.get_base_system_prompt(is_deep_context=True, timeout=60)
    assert "60 seconds timeout" in prompt
    assert "doesn't finish executing in that time it will be interrupted" in prompt


def test_get_base_system_prompt_without_timeout():
    """Test base system prompt doesn't include timeout information when not provided."""
    prompt = llm.get_base_system_prompt(is_deep_context=True, timeout=None)
    assert "seconds timeout" not in prompt


def test_execute_shell_tool_schema():
    """Test that the execute_shell tool schema is valid."""
    tool = llm.EXECUTE_SHELL_TOOL

    assert tool["type"] == "function"
    assert tool["function"]["name"] == "execute_shell"
    assert "command" in tool["function"]["parameters"]["properties"]
    assert "command" in tool["function"]["parameters"]["required"]


def test_llm_provider_init():
    """Test LLMProvider initialization."""
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-5-mini",
        api_key="test-key-123",
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert provider.configured_provider == "openai"
    assert provider.model == "gpt-5-mini"
    # Default: temperature should not be set for gpt-5 models
    assert provider.temperature is None


def test_llm_provider_init_with_overrides():
    """Test LLMProvider initialization with overrides."""
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-5-mini",
    )

    provider = llm.LLMProvider(config, model="gpt-5-mini", temperature=0.5, perf_logger=create_test_perf_logger())

    assert provider.model == "gpt-5-mini"
    assert provider.temperature == 0.5




@pytest.mark.integration
def test_send_message_real_api():
    """
    Integration test with real API.

    Requires a valid API key in the environment.
    """
    import os

    from whai.configuration import user_config as whai_config

    # Determine API key from environment or whai config
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        try:
            loaded = whai_config.load_config()
            openai_cfg = loaded.llm.get_provider("openai")
            api_key = openai_cfg.api_key if openai_cfg else None
        except Exception:
            api_key = None

    # Skip if no API key from env or config, or if it's a dummy/test key
    if not api_key or api_key in ("test-key-123", "your-api-key-here"):
        pytest.skip("No valid OpenAI API key in environment or whai config")

    config = create_test_config(
        default_provider="openai",
        default_model="gpt-5-mini",
        api_key=api_key,
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": 'Say "test successful" and nothing else.'},
    ]

    result = provider.send_message(messages, stream=False, tools=[])

    assert "test successful" in result["content"].lower()


# ============================================================================
# Environment Variable Configuration Tests
# ============================================================================


def _clear_provider_env_vars():
    """
    Clear all provider-related environment variables.
    
    This ensures tests start with a clean environment and can verify
    that only the expected variables are set by the provider.
    """
    env_vars_to_clear = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "AZURE_API_KEY",
        "AZURE_API_BASE",
        "AZURE_API_VERSION",
        "OLLAMA_API_BASE",
        "LM_STUDIO_API_BASE",
        "LM_STUDIO_API_KEY",
    ]
    for var in env_vars_to_clear:
        os.environ.pop(var, None)


def test_configure_api_keys_openai_sets_openai_key():
    """Test that OpenAI provider sets OPENAI_API_KEY environment variable."""
    _clear_provider_env_vars()

    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="sk-test-openai-key",
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert os.environ.get("OPENAI_API_KEY") == "sk-test-openai-key"
    # Other provider keys should not be set
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "LM_STUDIO_API_BASE" not in os.environ


def test_configure_api_keys_anthropic_sets_anthropic_key():
    """Test that Anthropic provider sets ANTHROPIC_API_KEY environment variable."""
    _clear_provider_env_vars()

    config = create_test_config(
        default_provider="anthropic",
        default_model="claude-3-opus",
        api_key="sk-ant-test-anthropic-key",
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-anthropic-key"
    # Other provider keys should not be set
    assert "OPENAI_API_KEY" not in os.environ
    assert "LM_STUDIO_API_BASE" not in os.environ


def test_configure_api_keys_gemini_sets_gemini_key():
    """Test that Gemini provider sets GEMINI_API_KEY environment variable."""
    _clear_provider_env_vars()

    config = create_test_config(
        default_provider="gemini",
        default_model="gemini-2.5-flash",
        api_key="AIza-test-gemini-key",
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert os.environ.get("GEMINI_API_KEY") == "AIza-test-gemini-key"
    # Other provider keys should not be set
    assert "OPENAI_API_KEY" not in os.environ
    assert "LM_STUDIO_API_BASE" not in os.environ


def test_configure_api_keys_azure_sets_azure_vars():
    """Test that Azure OpenAI provider sets all Azure environment variables."""
    _clear_provider_env_vars()

    config = create_test_config(
        default_provider="azure_openai",
        default_model="gpt-4",
        providers={
            "azure_openai": AzureOpenAIConfig(
                api_key="test-azure-key",
                api_base="https://test.openai.azure.com",
                api_version="2023-05-15",
                default_model="gpt-4",
            )
        },
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert os.environ.get("AZURE_API_KEY") == "test-azure-key"
    assert os.environ.get("AZURE_API_BASE") == "https://test.openai.azure.com"
    assert os.environ.get("AZURE_API_VERSION") == "2023-05-15"
    # Other provider keys should not be set
    assert "OPENAI_API_KEY" not in os.environ


def test_configure_api_keys_ollama_sets_ollama_base():
    """Test that Ollama provider sets OLLAMA_API_BASE environment variable."""
    _clear_provider_env_vars()

    config = create_test_config(
        default_provider="ollama",
        default_model="mistral",
        providers={
            "ollama": OllamaConfig(
                api_base="http://localhost:11434",
                default_model="mistral",
            )
        },
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert os.environ.get("OLLAMA_API_BASE") == "http://localhost:11434"
    # Other provider keys should not be set
    assert "OPENAI_API_KEY" not in os.environ
    assert "LM_STUDIO_API_BASE" not in os.environ


def test_configure_api_keys_lm_studio_sets_lm_studio_vars():
    """Test that LM Studio provider sets LM_STUDIO_API_BASE and LM_STUDIO_API_KEY."""
    _clear_provider_env_vars()

    config = create_test_config(
        default_provider="lm_studio",
        default_model="qwen3-30b",
        providers={
            "lm_studio": LMStudioConfig(
                api_base="http://localhost:1234/v1",
                default_model="qwen3-30b",
                api_key=None,  # No API key configured
            )
        },
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert os.environ.get("LM_STUDIO_API_BASE") == "http://localhost:1234/v1"
    assert os.environ.get("LM_STUDIO_API_KEY") == ""  # Should default to empty string
    # Other provider keys should not be set
    assert "OPENAI_API_KEY" not in os.environ


def test_configure_api_keys_lm_studio_with_custom_key():
    """Test that LM Studio provider uses custom API key when provided."""
    _clear_provider_env_vars()

    config = create_test_config(
        default_provider="lm_studio",
        default_model="qwen3-30b",
        providers={
            "lm_studio": LMStudioConfig(
                api_base="http://localhost:1234/v1",
                default_model="qwen3-30b",
                api_key="custom-lm-studio-key",
            )
        },
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    assert os.environ.get("LM_STUDIO_API_BASE") == "http://localhost:1234/v1"
    assert os.environ.get("LM_STUDIO_API_KEY") == "custom-lm-studio-key"
    assert "OPENAI_API_KEY" not in os.environ


def test_configure_api_keys_only_active_provider():
    """Test that only the active provider's environment variables are set."""
    _clear_provider_env_vars()

    # Create config with multiple providers
    config = create_test_config(
        default_provider="lm_studio",
        default_model="qwen3-30b",
        providers={
            "openai": OpenAIConfig(
                api_key="sk-openai-key-should-not-be-set",
                default_model="gpt-4",
            ),
            "anthropic": AnthropicConfig(
                api_key="sk-ant-anthropic-key-should-not-be-set",
                default_model="claude-3-opus",
            ),
            "lm_studio": LMStudioConfig(
                api_base="http://localhost:1234/v1",
                default_model="qwen3-30b",
            ),
        },
    )

    # Initialize with LM Studio as active provider
    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    # LM Studio keys should be set
    assert os.environ.get("LM_STUDIO_API_BASE") == "http://localhost:1234/v1"
    assert os.environ.get("LM_STUDIO_API_KEY") == ""

    # Other providers' keys should NOT be set (this is the key fix!)
    assert "OPENAI_API_KEY" not in os.environ
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_configure_api_keys_switching_providers():
    """Test that switching providers correctly updates environment variables."""
    _clear_provider_env_vars()

    # Create config with multiple providers
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        providers={
            "openai": OpenAIConfig(
                api_key="sk-openai-key",
                default_model="gpt-4",
            ),
            "lm_studio": LMStudioConfig(
                api_base="http://localhost:1234/v1",
                default_model="qwen3-30b",
            ),
        },
    )

    # First, use OpenAI
    provider1 = llm.LLMProvider(
        config, provider="openai", perf_logger=create_test_perf_logger()
    )
    assert os.environ.get("OPENAI_API_KEY") == "sk-openai-key"
    assert "LM_STUDIO_API_BASE" not in os.environ

    # Clear and switch to LM Studio
    for var in ["OPENAI_API_KEY", "LM_STUDIO_API_BASE", "LM_STUDIO_API_KEY"]:
        os.environ.pop(var, None)

    provider2 = llm.LLMProvider(
        config, provider="lm_studio", perf_logger=create_test_perf_logger()
    )
    assert os.environ.get("LM_STUDIO_API_BASE") == "http://localhost:1234/v1"
    assert "OPENAI_API_KEY" not in os.environ


def test_configure_api_keys_no_keys_when_not_configured():
    """Test that environment variables are not set when provider has no keys."""
    _clear_provider_env_vars()

    # Ollama doesn't require API key, only api_base
    config = create_test_config(
        default_provider="ollama",
        default_model="mistral",
        providers={
            "ollama": OllamaConfig(
                api_base="http://localhost:11434",
                default_model="mistral",
            )
        },
    )

    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())

    # Should set api_base
    assert os.environ.get("OLLAMA_API_BASE") == "http://localhost:11434"
    # Should not set any API keys
    assert "OPENAI_API_KEY" not in os.environ


# ============================================================================
# End-to-End Integration Tests (Require Running Services)
# ============================================================================


def _check_service_running(url: str, timeout: float = 2.0, is_ollama: bool = False) -> bool:
    """
    Check if a local service is running by attempting to connect to it.
    
    Args:
        url: The base URL to check (e.g., "http://localhost:1234/v1")
        timeout: Connection timeout in seconds
        is_ollama: If True, check Ollama's /api/tags endpoint instead of /models
        
    Returns:
        True if service is reachable, False otherwise
    """
    try:
        import urllib.error
        import urllib.request
        
        if is_ollama:
            # Ollama uses /api/tags endpoint
            check_url = f"{url.rstrip('/')}/api/tags"
        else:
            # LM Studio and other OpenAI-compatible services use /models
            check_url = f"{url.rstrip('/')}/models"
        
        req = urllib.request.Request(check_url, method="GET")
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception:
        return False


def _load_user_config_or_defaults(provider_name: str):
    """
    Load user's actual configuration for a provider, or return defaults.
    
    Args:
        provider_name: Name of the provider (e.g., "lm_studio", "ollama")
        
    Returns:
        Tuple of (api_base, default_model, api_key) from user config or defaults
    """
    from whai.constants import (
        DEFAULT_LM_STUDIO_API_BASE,
        DEFAULT_OLLAMA_API_BASE,
        DEFAULT_MODEL_LM_STUDIO,
        DEFAULT_MODEL_OLLAMA,
    )
    from whai.configuration import user_config as whai_config
    
    # Try to load user's actual config
    try:
        loaded = whai_config.load_config()
        provider_cfg = loaded.llm.get_provider(provider_name)
        
        if provider_cfg:
            api_base = provider_cfg.api_base
            default_model = provider_cfg.default_model
            api_key = getattr(provider_cfg, "api_key", None)
            
            # Return user's config if available
            if api_base and default_model:
                return api_base, default_model, api_key
    except Exception:
        # Config doesn't exist or provider not configured, use defaults
        pass
    
    # Fall back to defaults
    if provider_name == "lm_studio":
        return DEFAULT_LM_STUDIO_API_BASE, DEFAULT_MODEL_LM_STUDIO, None
    elif provider_name == "ollama":
        return DEFAULT_OLLAMA_API_BASE, DEFAULT_MODEL_OLLAMA, None
    else:
        raise ValueError(f"Unknown provider: {provider_name}")


@pytest.mark.integration
def test_send_message_lm_studio():
    """
    End-to-end integration test with LM Studio.
    
    Requires LM Studio to be running with a model loaded.
    
    Uses your actual LM Studio configuration from ~/.config/whai/config.toml if available,
    otherwise falls back to defaults.
    
    To run this test:
    1. Start LM Studio
    2. Load a model
    3. Enable the local server in the Developer menu
    4. (Optional) Configure LM Studio in whai: whai --interactive-config
    """
    # Load user's actual config or use defaults
    api_base, configured_model, api_key = _load_user_config_or_defaults("lm_studio")
    
    # Check if LM Studio is running at the configured endpoint
    if not _check_service_running(api_base):
        pytest.skip(
            f"LM Studio is not running at {api_base}. "
            "To run this test:\n"
            "1. Start LM Studio\n"
            "2. Load a model\n"
            "3. Enable the local server in the Developer menu\n"
            f"4. Ensure the server is running at {api_base}\n"
            "5. (Optional) Configure in whai: whai --interactive-config"
        )
    
    # Try to get available models from LM Studio
    import json
    import urllib.request
    
    try:
        models_url = f"{api_base.rstrip('/')}/models"
        req = urllib.request.Request(models_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            available_models = [model.get("id") for model in data.get("data", [])]
            
            if not available_models:
                pytest.skip(
                    f"LM Studio is running at {api_base} but no models are loaded. "
                    "Please load a model in LM Studio and try again."
                )
            
            # Try to use the configured model if it's available, otherwise use first available
            model_name = None
            for model_id in available_models:
                # Strip any prefix
                base_model = model_id.split("/", 1)[-1] if "/" in model_id else model_id
                if base_model == configured_model or model_id == configured_model:
                    model_name = base_model
                    break
            
            # If configured model not found, use first available
            if model_name is None:
                model_name = available_models[0]
                if "/" in model_name:
                    model_name = model_name.split("/", 1)[-1]
    except Exception as e:
        pytest.skip(
            f"Could not query LM Studio at {api_base} for available models: {e}. "
            "Please ensure LM Studio is running and a model is loaded."
        )
    
    # Clear environment variables that might interfere with the test
    _clear_provider_env_vars()
    
    # Create config with LM Studio using user's settings
    config = create_test_config(
        default_provider="lm_studio",
        default_model=model_name,
        providers={
            "lm_studio": LMStudioConfig(
                api_base=api_base,
                default_model=model_name,
                api_key=api_key,
            )
        },
    )
    
    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())
    
    # Verify environment variables are set correctly
    assert os.environ.get("LM_STUDIO_API_BASE") == api_base
    assert "OPENAI_API_KEY" not in os.environ  # Should not be set!
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": 'Say "LM Studio test successful" and nothing else.'},
    ]
    
    result = provider.send_message(messages, stream=False, tools=[])
    
    assert "lm studio test successful" in result["content"].lower()


@pytest.mark.integration
def test_send_message_ollama():
    """
    End-to-end integration test with Ollama.
    
    Requires Ollama to be running with a model available.
    
    Uses your actual Ollama configuration from ~/.config/whai/config.toml if available,
    otherwise falls back to defaults.
    
    To run this test:
    1. Start Ollama (usually runs automatically)
    2. Pull a model: ollama pull mistral
    3. (Optional) Configure Ollama in whai: whai --interactive-config
    """
    # Load user's actual config or use defaults
    api_base, configured_model, _ = _load_user_config_or_defaults("ollama")
    
    # Check if Ollama is running at the configured endpoint
    if not _check_service_running(api_base, is_ollama=True):
        pytest.skip(
            f"Ollama is not running at {api_base}. "
            "To run this test:\n"
            "1. Start Ollama (usually runs automatically)\n"
            "2. Pull a model: ollama pull mistral\n"
            f"3. Ensure Ollama is accessible at {api_base}\n"
            "4. (Optional) Configure in whai: whai --interactive-config"
        )
    
    # Try to get available models from Ollama
    import json
    import urllib.request
    
    try:
        models_url = f"{api_base.rstrip('/')}/api/tags"
        req = urllib.request.Request(models_url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            # Keep full model names including tags (e.g., "mistral-small3.2:24b")
            # Ollama requires the full name with tag for proper model identification
            available_models = [model.get("name", "") for model in data.get("models", [])]
            
            if not available_models:
                pytest.skip(
                    f"Ollama is running at {api_base} but no models are available. "
                    "Please pull a model (e.g., 'ollama pull mistral') and try again."
                )
            
            # For integration tests, always use the first available model
            # This ensures the test works even if the configured model isn't fully loaded
            # Model names can include tags (e.g., "mistral-small3.2:24b"), which we preserve
            configured_base = configured_model.split(":")[0] if ":" in configured_model else configured_model
            
            # Use first available model (most reliable for testing)
            # Keep the full name including tag if present
            model_name = available_models[0]
            
            # Log if we're using a different model than configured
            model_name_base = model_name.split(":")[0] if ":" in model_name else model_name
            if configured_base != model_name_base:
                import warnings
                warnings.warn(
                    f"Configured model '{configured_model}' not selected. "
                    f"Using first available model '{model_name}' for test.",
                    UserWarning
                )
    except Exception as e:
        pytest.skip(
            f"Could not query Ollama at {api_base} for available models: {e}. "
            "Please ensure Ollama is running and at least one model is available."
        )
    
    # Clear environment variables that might interfere with the test
    _clear_provider_env_vars()
    
    # Create config with Ollama using user's settings
    config = create_test_config(
        default_provider="ollama",
        default_model=model_name,
        providers={
            "ollama": OllamaConfig(
                api_base=api_base,
                default_model=model_name,
            )
        },
    )
    
    provider = llm.LLMProvider(config, perf_logger=create_test_perf_logger())
    
    # Verify environment variables are set correctly
    assert os.environ.get("OLLAMA_API_BASE") == api_base
    assert "OPENAI_API_KEY" not in os.environ  # Should not be set!
    
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": 'Say "Ollama test successful" and nothing else.'},
    ]
    
    result = provider.send_message(messages, stream=False, tools=[])
    
    assert "ollama test successful" in result["content"].lower()
