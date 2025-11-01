"""Pytest configuration for whai tests."""

import os

import pytest

from whai.configuration.user_config import (
    AnthropicConfig,
    GeminiConfig,
    LLMConfig,
    OpenAIConfig,
    RolesConfig,
    WhaiConfig,
)


@pytest.fixture(scope="session", autouse=True)
def plain_mode_for_tests():
    """Force plain mode (no Rich styling) for all tests."""
    original = os.environ.get("WHAI_PLAIN")
    os.environ["WHAI_PLAIN"] = "1"
    yield
    if original is None:
        os.environ.pop("WHAI_PLAIN", None)
    else:
        os.environ["WHAI_PLAIN"] = original


@pytest.fixture(scope="session", autouse=True)
def test_mode_for_config():
    """Enable test mode for config loading."""
    from whai.constants import ENV_WHAI_TEST_MODE
    
    original = os.environ.get(ENV_WHAI_TEST_MODE)
    os.environ[ENV_WHAI_TEST_MODE] = "1"
    yield
    if original is None:
        os.environ.pop(ENV_WHAI_TEST_MODE, None)
    else:
        os.environ[ENV_WHAI_TEST_MODE] = original


def create_test_config(
    default_provider: str = "openai",
    default_model: str = "gpt-5-mini",
    api_key: str = "test-key-123",
    providers: dict = None,
) -> WhaiConfig:
    """
    Helper function to create a test WhaiConfig object.
    
    Args:
        default_provider: Default provider name.
        default_model: Default model name.
        api_key: API key for the default provider.
        providers: Optional dict of provider configs to add.
    
    Returns:
        WhaiConfig instance for testing.
    """
    from whai.constants import DEFAULT_PROVIDER, DEFAULT_ROLE_NAME
    
    provider_configs = {}
    
    # Add default provider
    if default_provider == "openai":
        provider_configs["openai"] = OpenAIConfig(
            api_key=api_key,
            default_model=default_model,
        )
    elif default_provider == "anthropic":
        provider_configs["anthropic"] = AnthropicConfig(
            api_key=api_key,
            default_model=default_model,
        )
    elif default_provider == "gemini":
        provider_configs["gemini"] = GeminiConfig(
            api_key=api_key,
            default_model=default_model,
        )
    
    # Add any additional providers
    if providers:
        provider_configs.update(providers)
    
    return WhaiConfig(
        llm=LLMConfig(
            default_provider=default_provider or DEFAULT_PROVIDER,
            providers=provider_configs,
        ),
        roles=RolesConfig(default_role=DEFAULT_ROLE_NAME),
    )
