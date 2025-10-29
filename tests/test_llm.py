"""Tests for LLM module."""

import json
from unittest.mock import MagicMock, patch

import pytest

from terma import llm


def test_get_base_system_prompt_deep_context():
    """Test base system prompt with deep context."""
    prompt = llm.get_base_system_prompt(is_deep_context=True)
    assert "full terminal scrollback" in prompt
    assert "terma" in prompt
    assert "execute_shell" in prompt


def test_get_base_system_prompt_shallow_context():
    """Test base system prompt with shallow context."""
    prompt = llm.get_base_system_prompt(is_deep_context=False)
    assert "command history only" in prompt
    assert "no command output" in prompt


def test_execute_shell_tool_schema():
    """Test that the execute_shell tool schema is valid."""
    tool = llm.EXECUTE_SHELL_TOOL

    assert tool["type"] == "function"
    assert tool["function"]["name"] == "execute_shell"
    assert "command" in tool["function"]["parameters"]["properties"]
    assert "command" in tool["function"]["parameters"]["required"]


def test_llm_provider_init():
    """Test LLMProvider initialization."""
    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
            "openai": {"api_key": "test-key-123"},
        }
    }

    provider = llm.LLMProvider(config)

    assert provider.default_provider == "openai"
    assert provider.model == "gpt-5-mini"
    # Default: temperature should not be set for gpt-5 models
    assert provider.temperature is None


def test_llm_provider_init_with_overrides():
    """Test LLMProvider initialization with overrides."""
    config = {"llm": {"default_provider": "openai", "default_model": "gpt-5-mini"}}

    provider = llm.LLMProvider(config, model="gpt-5-mini", temperature=0.5)

    assert provider.model == "gpt-5-mini"
    assert provider.temperature == 0.5


def test_llm_provider_configure_api_keys():
    """Test API key configuration."""
    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
            "openai": {"api_key": "sk-test-123"},
            "anthropic": {"api_key": "sk-ant-test-456"},
        }
    }

    with patch.dict("os.environ", {}, clear=True):
        provider = llm.LLMProvider(config)

        import os

        assert os.environ.get("OPENAI_API_KEY") == "sk-test-123"
        assert os.environ.get("ANTHROPIC_API_KEY") == "sk-ant-test-456"


def test_send_message_non_streaming():
    """Test sending a non-streaming message."""
    config = {"llm": {"default_provider": "openai", "default_model": "gpt-5-mini"}}

    # Mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Hello, I can help you with that."
    mock_response.choices[0].message.tool_calls = None

    with patch("litellm.completion", return_value=mock_response):
        provider = llm.LLMProvider(config)
        messages = [{"role": "user", "content": "Hello"}]

        result = provider.send_message(messages, stream=False)

        assert result["content"] == "Hello, I can help you with that."
        assert result["tool_calls"] == []


def test_send_message_with_tool_calls():
    """Test sending a message that returns tool calls."""
    config = {"llm": {"default_provider": "openai", "default_model": "gpt-5-mini"}}

    # Mock response with tool call
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_123"
    mock_tool_call.function = MagicMock()
    mock_tool_call.function.name = "execute_shell"
    mock_tool_call.function.arguments = json.dumps({"command": "ls -la"})

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Let me list the files."
    mock_response.choices[0].message.tool_calls = [mock_tool_call]

    with patch("litellm.completion", return_value=mock_response):
        provider = llm.LLMProvider(config)
        messages = [{"role": "user", "content": "List files"}]

        result = provider.send_message(messages, stream=False)

        assert result["content"] == "Let me list the files."
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0]["name"] == "execute_shell"
        assert result["tool_calls"][0]["arguments"]["command"] == "ls -la"


def test_send_message_streaming():
    """Test streaming message response."""
    config = {"llm": {"default_provider": "openai", "default_model": "gpt-5-mini"}}

    # Mock streaming response
    mock_chunks = []

    # Create text chunks
    for text in ["Hello", " there", "!"]:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock()
        chunk.choices[0].delta.content = text
        chunk.choices[0].delta.tool_calls = None
        mock_chunks.append(chunk)

    with patch("litellm.completion", return_value=iter(mock_chunks)):
        provider = llm.LLMProvider(config)
        messages = [{"role": "user", "content": "Hello"}]

        results = list(provider.send_message(messages, stream=True))

        assert len(results) == 3
        assert all(r["type"] == "text" for r in results)
        assert "".join(r["content"] for r in results) == "Hello there!"


def test_send_message_streaming_with_tool_call():
    """Test streaming message with tool call."""
    config = {"llm": {"default_provider": "openai", "default_model": "gpt-4"}}

    # Mock streaming response with tool call
    mock_chunks = []

    # Text chunk
    chunk1 = MagicMock()
    chunk1.choices = [MagicMock()]
    chunk1.choices[0].delta = MagicMock()
    chunk1.choices[0].delta.content = "Let me run that."
    chunk1.choices[0].delta.tool_calls = None
    mock_chunks.append(chunk1)

    # Tool call chunk
    chunk2 = MagicMock()
    chunk2.choices = [MagicMock()]
    chunk2.choices[0].delta = MagicMock()
    chunk2.choices[0].delta.content = None

    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_456"
    mock_tool_call.function = MagicMock()
    mock_tool_call.function.name = "execute_shell"
    mock_tool_call.function.arguments = json.dumps({"command": "pwd"})

    chunk2.choices[0].delta.tool_calls = [mock_tool_call]
    mock_chunks.append(chunk2)

    with patch("litellm.completion", return_value=iter(mock_chunks)):
        provider = llm.LLMProvider(config)
        messages = [{"role": "user", "content": "Where am I?"}]

        results = list(provider.send_message(messages, stream=True))

        assert len(results) == 2
        assert results[0]["type"] == "text"
        assert results[0]["content"] == "Let me run that."
        assert results[1]["type"] == "tool_call"
        assert results[1]["name"] == "execute_shell"
        assert results[1]["arguments"]["command"] == "pwd"


def test_send_message_api_error():
    """Test that API errors are properly raised."""
    config = {"llm": {"default_provider": "openai", "default_model": "gpt-4"}}

    with patch("litellm.completion", side_effect=Exception("API Error")):
        provider = llm.LLMProvider(config)
        messages = [{"role": "user", "content": "Hello"}]

        with pytest.raises(RuntimeError, match="LLM API error"):
            provider.send_message(messages, stream=False)


@pytest.mark.integration
def test_send_message_real_api():
    """
    Integration test with real API.

    This test is skipped by default. Run with: pytest -m integration
    Requires a valid API key in the environment.
    """
    import os

    from terma import config as terma_config

    # Determine API key from environment or terma config
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        try:
            loaded = terma_config.load_config()
            api_key = loaded.get("llm", {}).get("openai", {}).get("api_key")
        except Exception:
            api_key = None

    # Skip if no API key from env or config, or if it's a dummy/test key
    if not api_key or api_key in ("test-key-123", "your-api-key-here"):
        pytest.skip("No valid OpenAI API key in environment or terma config")

    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
            "openai": {"api_key": api_key},
        }
    }

    provider = llm.LLMProvider(config)
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": 'Say "test successful" and nothing else.'},
    ]

    result = provider.send_message(messages, stream=False, tools=[])

    assert "test successful" in result["content"].lower()
