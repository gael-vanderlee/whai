"""Multi-provider integration tests.

These tests validate that whai works consistently across different LLM providers.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from tests.conftest import create_test_config, create_test_perf_logger
from whai.llm import LLMProvider

runner = CliRunner()


@pytest.fixture(autouse=True)
def test_env(tmp_path, monkeypatch):
    """Set up ephemeral test config."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setenv("WHAI_TEST_MODE", "1")


@pytest.mark.parametrize("provider_name,model_name", [
    ("openai", "gpt-4"),
    ("anthropic", "claude-3-sonnet-20240229"),
    ("gemini", "gemini-pro"),
])
def test_provider_tool_call_format_consistent(provider_name, model_name, mock_litellm_module):
    """Test that all LLM providers handle tool calls in a consistent format."""
    # Create config for specified provider
    config = create_test_config(
        default_provider=provider_name,
        default_model=model_name,
        api_key="test-key-123",
    )
    
    # Mock tool call response (consistent format)
    mock_tool_call = MagicMock()
    mock_tool_call.id = "call_test_123"
    mock_tool_call.function = MagicMock()
    mock_tool_call.function.name = "execute_shell"
    mock_tool_call.function.arguments = json.dumps({"command": "echo test"})
    
    # Mock streaming response
    mock_chunk = MagicMock()
    mock_chunk.choices = [MagicMock()]
    mock_chunk.choices[0].delta = MagicMock()
    mock_chunk.choices[0].delta.content = "Let me run that."
    mock_chunk.choices[0].delta.tool_calls = [mock_tool_call]
    
    with patch("litellm.completion", return_value=iter([mock_chunk])):
        provider = LLMProvider(config, perf_logger=create_test_perf_logger())
        messages = [{"role": "user", "content": "echo test"}]
        
        # Get streaming response
        chunks = list(provider.send_message(messages, stream=True))
        
        # Should parse tool call consistently regardless of provider
        tool_calls = [c for c in chunks if c.get("type") == "tool_call"]
        
        assert len(tool_calls) == 1
        assert tool_calls[0]["name"] == "execute_shell"
        assert tool_calls[0]["arguments"]["command"] == "echo test"


@pytest.mark.parametrize("provider_name", ["openai", "anthropic", "gemini"])
def test_provider_text_response_consistent(provider_name, mock_litellm_module):
    """Test that all LLM providers handle text-only responses consistently."""
    # Create config for specified provider
    config = create_test_config(
        default_provider=provider_name,
        default_model="test-model",
        api_key="test-key-123",
    )
    
    # Mock text response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Test response from provider"
    mock_response.choices[0].message.tool_calls = None
    
    with patch("litellm.completion", return_value=mock_response):
        provider = LLMProvider(config, perf_logger=create_test_perf_logger())
        messages = [{"role": "user", "content": "Hello"}]
        
        # Get non-streaming response
        result = provider.send_message(messages, stream=False)
        
        # Should return consistent format regardless of provider
        assert "content" in result
        assert result["content"] == "Test response from provider"
        assert "tool_calls" not in result or not result.get("tool_calls")

