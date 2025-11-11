"""Tests for LLM module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import create_test_config, create_test_perf_logger
from whai import llm


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

    assert provider.default_provider == "openai"
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

    This test is skipped by default. Run with: pytest -m integration
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
