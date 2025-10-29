"""Tests for LLM temperature handling and parameter support."""

from terma import llm


def test_llm_provider_accepts_no_temperature():
    """Test that LLMProvider works without temperature parameter."""
    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
            "openai": {"api_key": "test-key"},
        }
    }

    provider = llm.LLMProvider(config)
    assert provider.temperature is None
    assert provider.model == "gpt-5-mini"


def test_llm_provider_accepts_explicit_temperature():
    """Test that LLMProvider accepts an explicit temperature."""
    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
            "openai": {"api_key": "test-key"},
        }
    }

    provider = llm.LLMProvider(config, temperature=0.5)
    assert provider.temperature == 0.5


def test_send_message_includes_drop_params():
    """Test that send_message uses drop_params=True to handle unsupported parameters."""
    from unittest.mock import Mock, patch

    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
            "openai": {"api_key": "test-key"},
        }
    }

    provider = llm.LLMProvider(config, temperature=0.7)
    messages = [{"role": "user", "content": "test"}]

    with patch("litellm.completion") as mock_completion:
        # Create a mock response object matching LiteLLM's response structure
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "response"
        mock_message.role = "assistant"
        mock_message.tool_calls = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_completion.return_value = mock_response

        provider.send_message(messages, stream=False, tools=[])

        # Verify completion was called with drop_params=True
        call_kwargs = mock_completion.call_args[1]
        assert call_kwargs["drop_params"] is True
        # gpt-5-mini may not support temperature; it should be omitted
        assert "temperature" not in call_kwargs


def test_send_message_no_temperature_when_none():
    """Test that temperature is not included in API call when set to None."""
    from unittest.mock import Mock, patch

    config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-5-mini",
            "openai": {"api_key": "test-key"},
        }
    }

    provider = llm.LLMProvider(config)  # No temperature
    messages = [{"role": "user", "content": "test"}]

    with patch("litellm.completion") as mock_completion:
        # Create a mock response object matching LiteLLM's response structure
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = "response"
        mock_message.role = "assistant"
        mock_message.tool_calls = None
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_completion.return_value = mock_response

        provider.send_message(messages, stream=False, tools=[])

        # Verify completion was called without temperature parameter
        call_kwargs = mock_completion.call_args[1]
        assert "temperature" not in call_kwargs
        assert call_kwargs["drop_params"] is True
