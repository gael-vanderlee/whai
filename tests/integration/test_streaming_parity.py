"""Integration tests for streaming vs non-streaming parity.

These tests validate that streaming and non-streaming LLM responses
produce equivalent results from the user's perspective.
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import create_test_config, create_test_perf_logger
from whai.llm import LLMProvider


@pytest.fixture
def test_messages():
    """Standard test messages for LLM calls."""
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is a .gitignore file?"},
    ]


@pytest.fixture(autouse=True)
def _mock_litellm(mock_litellm_module):
    """Ensure litellm is mocked for all tests in this module to avoid slow imports."""
    return mock_litellm_module


def test_streaming_and_non_streaming_text_content_matches(test_messages):
    """Test that stream=True and stream=False produce equivalent text content."""
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    test_content = "A .gitignore file specifies files that Git should ignore."
    
    # Mock non-streaming response
    mock_response_non_stream = MagicMock()
    mock_response_non_stream.choices = [MagicMock()]
    mock_response_non_stream.choices[0].message = MagicMock()
    mock_response_non_stream.choices[0].message.content = test_content
    mock_response_non_stream.choices[0].message.tool_calls = None
    
    # Mock streaming response (split into chunks)
    chunks = [
        "A .gitignore file ",
        "specifies files ",
        "that Git should ignore.",
    ]
    mock_chunks = []
    for chunk_text in chunks:
        chunk = MagicMock()
        chunk.choices = [MagicMock()]
        chunk.choices[0].delta = MagicMock()
        chunk.choices[0].delta.content = chunk_text
        chunk.choices[0].delta.tool_calls = None
        mock_chunks.append(chunk)
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    # Test non-streaming
    with patch("litellm.completion", return_value=mock_response_non_stream):
        result_non_stream = provider.send_message(test_messages, stream=False)
    
    # Test streaming
    with patch("litellm.completion", return_value=iter(mock_chunks)):
        result_stream = list(provider.send_message(test_messages, stream=True))
    
    # Extract content from streaming chunks
    stream_content = "".join([
        chunk["content"] for chunk in result_stream if chunk.get("type") == "text"
    ])
    
    # Both should produce the same content
    assert result_non_stream["content"] == test_content
    assert stream_content == test_content


def test_streaming_and_non_streaming_tool_calls_match(test_messages):
    """Test that tool calls are equivalent in streaming and non-streaming modes."""
    import json
    
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    # Mock non-streaming tool call
    mock_tool_non_stream = MagicMock()
    mock_tool_non_stream.id = "call_123"
    mock_tool_non_stream.function = MagicMock()
    mock_tool_non_stream.function.name = "execute_shell"
    mock_tool_non_stream.function.arguments = json.dumps({"command": "ls -la"})
    
    mock_response_non_stream = MagicMock()
    mock_response_non_stream.choices = [MagicMock()]
    mock_response_non_stream.choices[0].message = MagicMock()
    mock_response_non_stream.choices[0].message.content = "Let me list the files."
    mock_response_non_stream.choices[0].message.tool_calls = [mock_tool_non_stream]
    
    # Mock streaming tool call
    mock_tool_stream = MagicMock()
    mock_tool_stream.id = "call_123"
    mock_tool_stream.function = MagicMock()
    mock_tool_stream.function.name = "execute_shell"
    mock_tool_stream.function.arguments = json.dumps({"command": "ls -la"})
    
    mock_chunks = [
        MagicMock(
            choices=[MagicMock(delta=MagicMock(content="Let me list the files.", tool_calls=None))]
        ),
        MagicMock(
            choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[mock_tool_stream]))]
        ),
    ]
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    # Test non-streaming
    with patch("litellm.completion", return_value=mock_response_non_stream):
        result_non_stream = provider.send_message(test_messages, stream=False, tools=[])
    
    # Test streaming
    with patch("litellm.completion", return_value=iter(mock_chunks)):
        result_stream = list(provider.send_message(test_messages, stream=True, tools=[]))
    
    # Extract tool calls from streaming
    stream_tool_calls = [chunk for chunk in result_stream if chunk.get("type") == "tool_call"]
    
    # Both should have the same tool call
    assert "tool_calls" in result_non_stream
    assert len(result_non_stream["tool_calls"]) == 1
    assert result_non_stream["tool_calls"][0]["name"] == "execute_shell"
    assert result_non_stream["tool_calls"][0]["arguments"]["command"] == "ls -la"
    
    assert len(stream_tool_calls) == 1
    assert stream_tool_calls[0]["name"] == "execute_shell"
    assert stream_tool_calls[0]["arguments"]["command"] == "ls -la"


def test_streaming_preserves_message_order(test_messages):
    """Test that streaming preserves the order of text and tool calls."""
    import json
    
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    # Mock streaming with text, then tool call, then more text
    mock_tool = MagicMock()
    mock_tool.id = "call_456"
    mock_tool.function = MagicMock()
    mock_tool.function.name = "execute_shell"
    mock_tool.function.arguments = json.dumps({"command": "pwd"})
    
    mock_chunks = [
        MagicMock(choices=[MagicMock(delta=MagicMock(content="Let me check. ", tool_calls=None))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[mock_tool]))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content="Done!", tool_calls=None))]),
    ]
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    with patch("litellm.completion", return_value=iter(mock_chunks)):
        result_stream = list(provider.send_message(test_messages, stream=True, tools=[]))
    
    # Verify order: text, tool_call, text
    assert result_stream[0]["type"] == "text"
    assert result_stream[0]["content"] == "Let me check. "
    
    assert result_stream[1]["type"] == "tool_call"
    assert result_stream[1]["name"] == "execute_shell"
    
    assert result_stream[2]["type"] == "text"
    assert result_stream[2]["content"] == "Done!"


def test_streaming_handles_empty_chunks_gracefully(test_messages):
    """Test that streaming handles empty/None content chunks without crashing."""
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    # Mock streaming with some empty chunks
    mock_chunks = [
        MagicMock(choices=[MagicMock(delta=MagicMock(content="Start ", tool_calls=None))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content=None, tool_calls=None))]),  # Empty
        MagicMock(choices=[MagicMock(delta=MagicMock(content="", tool_calls=None))]),  # Empty string
        MagicMock(choices=[MagicMock(delta=MagicMock(content="End", tool_calls=None))]),
    ]
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    with patch("litellm.completion", return_value=iter(mock_chunks)):
        result_stream = list(provider.send_message(test_messages, stream=True))
    
    # Should not crash; should only yield non-empty content
    text_chunks = [chunk for chunk in result_stream if chunk.get("type") == "text" and chunk.get("content")]
    combined = "".join(chunk["content"] for chunk in text_chunks)
    assert "Start" in combined
    assert "End" in combined


def test_non_streaming_response_format_consistency(test_messages):
    """Test that non-streaming responses have consistent format."""
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "Test response"
    mock_response.choices[0].message.tool_calls = None
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    with patch("litellm.completion", return_value=mock_response):
        result = provider.send_message(test_messages, stream=False)
    
    # Should have consistent keys
    assert "content" in result
    assert isinstance(result["content"], str)
    
    # Tool calls should be None or empty list (not missing key)
    assert "tool_calls" not in result or result.get("tool_calls") is None or result.get("tool_calls") == []


def test_streaming_response_format_consistency(test_messages):
    """Test that streaming responses have consistent format for each chunk."""
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    mock_chunks = [
        MagicMock(choices=[MagicMock(delta=MagicMock(content="Test ", tool_calls=None))]),
        MagicMock(choices=[MagicMock(delta=MagicMock(content="response", tool_calls=None))]),
    ]
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    with patch("litellm.completion", return_value=iter(mock_chunks)):
        result_stream = list(provider.send_message(test_messages, stream=True))
    
    # Every chunk should have consistent format
    for chunk in result_stream:
        assert "type" in chunk
        assert chunk["type"] in ["text", "tool_call"]
        
        if chunk["type"] == "text":
            assert "content" in chunk
            assert isinstance(chunk["content"], str)


def test_streaming_extracts_mcp_tool_calls_without_command_field(test_messages):
    """
    Test that streaming handler correctly extracts MCP tool calls that don't have a "command" field.
    
    This test would have caught the bug where the streaming handler only emitted tool calls
    with a "command" field (execute_shell), missing MCP tools with different parameter structures.
    """
    import json
    
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    # Mock MCP tool call (no "command" field - has "timezone" instead)
    mock_mcp_tool = MagicMock()
    mock_mcp_tool.id = "call_mcp_123"
    mock_mcp_tool.function = MagicMock()
    mock_mcp_tool.function.name = "mcp_time-server_get_current_time"
    mock_mcp_tool.function.arguments = json.dumps({"timezone": "Europe/Paris"})
    
    # Mock streaming response with MCP tool call
    mock_chunks = [
        MagicMock(
            choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[mock_mcp_tool]))]
        ),
    ]
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    # Test streaming
    with patch("litellm.completion", return_value=iter(mock_chunks)):
        result_stream = list(provider.send_message(test_messages, stream=True, tools=[]))
    
    # Extract tool calls from streaming
    stream_tool_calls = [chunk for chunk in result_stream if chunk.get("type") == "tool_call"]
    
    # Should extract the MCP tool call even though it doesn't have a "command" field
    assert len(stream_tool_calls) == 1, "MCP tool call should be extracted from stream"
    assert stream_tool_calls[0]["name"] == "mcp_time-server_get_current_time"
    assert stream_tool_calls[0]["arguments"] == {"timezone": "Europe/Paris"}
    assert "command" not in stream_tool_calls[0]["arguments"], "MCP tools don't have command field"


def test_streaming_extracts_tool_calls_with_empty_arguments(test_messages):
    """
    Test that streaming handler correctly extracts tool calls with empty arguments {}.
    
    Some tools may legitimately have no arguments, and the handler should still emit them.
    """
    import json
    
    config = create_test_config(
        default_provider="openai",
        default_model="gpt-4",
        api_key="test-key",
    )
    
    # Mock tool call with empty arguments
    mock_tool = MagicMock()
    mock_tool.id = "call_empty_123"
    mock_tool.function = MagicMock()
    mock_tool.function.name = "mcp_some-server_no_args_tool"
    mock_tool.function.arguments = json.dumps({})  # Empty dict
    
    # Mock streaming response
    mock_chunks = [
        MagicMock(
            choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[mock_tool]))]
        ),
    ]
    
    provider = LLMProvider(config, perf_logger=create_test_perf_logger())
    
    # Test streaming
    with patch("litellm.completion", return_value=iter(mock_chunks)):
        result_stream = list(provider.send_message(test_messages, stream=True, tools=[]))
    
    # Extract tool calls from streaming
    stream_tool_calls = [chunk for chunk in result_stream if chunk.get("type") == "tool_call"]
    
    # Should extract tool call even with empty arguments
    assert len(stream_tool_calls) == 1, "Tool call with empty arguments should be extracted"
    assert stream_tool_calls[0]["name"] == "mcp_some-server_no_args_tool"
    assert stream_tool_calls[0]["arguments"] == {}

