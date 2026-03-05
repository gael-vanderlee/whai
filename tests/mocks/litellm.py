"""Mock litellm module for subprocess-based E2E tests.

Placed under tests/mocks and injected via PYTHONPATH from tests to avoid
network calls during `python -m whai` subprocess runs. This file is only
used in tests and never shipped with the package.
"""

from unittest.mock import MagicMock
import os


def _text_only_response(text, stream):
    """Build a text-only mock response (streaming or non-streaming)."""
    if stream:
        return iter([
            MagicMock(choices=[MagicMock(delta=MagicMock(content=text, tool_calls=None))]),
        ])
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock()
    resp.choices[0].message.content = text
    resp.choices[0].message.tool_calls = None
    return resp


def _tool_call_response(text, tool, stream):
    """Build a response containing text followed by a tool call."""
    if stream:
        return iter([
            MagicMock(choices=[MagicMock(delta=MagicMock(content=text, tool_calls=None))]),
            MagicMock(choices=[MagicMock(delta=MagicMock(content=None, tool_calls=[tool]))]),
        ])
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock()
    resp.choices[0].message.content = text
    resp.choices[0].message.tool_calls = [tool]
    return resp


def completion(**kwargs):  # pragma: no cover - exercised via subprocess
    """Return a deterministic mock completion response.

    Behavior is controlled by environment variables:
    - WHAI_MOCK_TOOLCALL=1: emit a single execute_shell tool call.
    - WHAI_MOCK_MCP_TOOLCALL=1: emit an MCP tool call (first call), then
      text-only follow-up (second call, after tool result is in messages).
    - otherwise: emit text-only streaming response.
    """
    import json as _json

    stream = kwargs.get("stream", True)

    if os.getenv("WHAI_MOCK_TOOLCALL") == "1":
        tool = MagicMock()
        tool.id = "call_e2e_1"
        tool.function = MagicMock()
        tool.function.name = "execute_shell"
        tool.function.arguments = _json.dumps({"command": 'echo "e2e-subprocess"'})
        return _tool_call_response("Let me run that.", tool, stream)

    if os.getenv("WHAI_MOCK_MCP_TOOLCALL") == "1":
        messages = kwargs.get("messages", [])
        has_tool_result = any(m.get("role") == "tool" for m in messages)
        if has_tool_result:
            return _text_only_response("The current time is mcp-e2e-done.", stream)

        tool = MagicMock()
        tool.id = "call_mcp_e2e_1"
        tool.function = MagicMock()
        tool.function.name = "mcp_time-server_get_current_time"
        tool.function.arguments = _json.dumps({})
        return _tool_call_response("Let me check that for you.", tool, stream)

    # Default: text-only reply
    return _text_only_response("This is a subprocess test.", stream)


