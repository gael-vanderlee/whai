"""Integration tests for conversation-loop recovery behavior."""

from unittest.mock import MagicMock, patch

import pytest

from whai.core.executor import (
    _strip_thinking_tags,
    run_conversation_loop,
)
from whai.llm import LLMProvider


def _stream(chunks):
    for chunk in chunks:
        yield chunk


# ---------------------------------------------------------------------------
# Unit tests for _strip_thinking_tags
# ---------------------------------------------------------------------------


class TestStripThinkingTags:
    def test_removes_thinking_block(self):
        assert _strip_thinking_tags("<think>internal reasoning</think>Hello") == "Hello"

    def test_removes_multiple_blocks(self):
        text = "<think>a</think>Hello <think>b</think>world"
        assert _strip_thinking_tags(text) == "Hello world"

    def test_case_insensitive(self):
        assert _strip_thinking_tags("<THINK>stuff</THINK>ok") == "ok"

    def test_multiline(self):
        text = "<think>\nline1\nline2\n</think>result"
        assert _strip_thinking_tags(text) == "result"

    def test_no_tags_unchanged(self):
        assert _strip_thinking_tags("plain text") == "plain text"


# ---------------------------------------------------------------------------
# task_complete tool tests
# ---------------------------------------------------------------------------


def test_task_complete_tool_ends_loop():
    """Model calls task_complete -> loop exits cleanly."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "All done."},
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {},
            },
        ]),
    ]

    def _mock_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs):
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "What time is it?"},
    ]

    run_conversation_loop(mock_provider, messages, timeout=30)

    assert mock_provider.send_message.call_count == 1


def test_task_complete_with_summary_prints():
    """task_complete with summary text prints it."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {"summary": "Cleaned up 500MB of temp files."},
            },
        ]),
    ]

    printed = []

    def _mock_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs):
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Clean up."},
    ]

    with patch("whai.core.executor.SessionLogger") as MockSessionLogger:
        mock_sl = MockSessionLogger.return_value
        mock_sl.enabled = False
        mock_sl.print = MagicMock(side_effect=lambda *a, **kw: printed.append(a))
        mock_sl.log_command = MagicMock()
        run_conversation_loop(mock_provider, messages, timeout=30)

    # Summary was printed (first call with summary text)
    assert any("Cleaned up 500MB" in str(a) for a in printed)


def test_no_tool_call_always_retries():
    """Text-only response always triggers recovery (no pattern matching)."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        # Text-only, no continuation pattern — should still retry
        _stream([
            {"type": "text", "content": "The disk is 80% full."},
        ]),
        # After retry, model calls task_complete
        _stream([
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {"summary": "Disk is 80% full."},
            },
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Check disk space."},
    ]

    run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 2
    assert call_kwargs[0]["tool_choice"] is None
    assert call_kwargs[1]["tool_choice"] == "required"


def test_no_tool_call_retry_then_task_complete():
    """Retry leads to task_complete -> clean exit."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "Let me check that now."},
        ]),
        _stream([
            {"type": "text", "content": "The task is done."},
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {"summary": "Checked disk."},
            },
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Check disk space."},
    ]

    run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 2
    assert call_kwargs[1]["tool_choice"] == "required"


def test_task_complete_mid_conversation():
    """After execute_shell calls, task_complete exits the loop."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "Checking disk."},
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "execute_shell",
                "arguments": {"command": "df -h"},
            },
        ]),
        _stream([
            {"type": "text", "content": "Disk looks fine."},
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {"summary": "Disk has 50GB free."},
            },
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Check disk space."},
    ]

    with (
        patch("whai.core.executor.approval_loop", side_effect=lambda cmd: cmd),
        patch("whai.core.executor.execute_command", return_value=("ok\n", "", 0)),
    ):
        run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 2


# ---------------------------------------------------------------------------
# No-tool-call recovery tests (deterministic — no heuristics)
# ---------------------------------------------------------------------------


def test_no_tool_call_recovery_retries_with_required_tool_choice():
    """If assistant emits no tool call, loop retries once with tool_choice=required."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "Let me check the largest directories now."},
        ]),
        _stream([
            {"type": "text", "content": "Running command."},
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "execute_shell",
                "arguments": {"command": "echo ok"},
            },
        ]),
        _stream([
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {"summary": "Done."},
            },
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(
        messages,
        tools=None,
        stream=True,
        tool_choice=None,
        mcp_loop=None,
        **kwargs,
    ):
        call_kwargs.append({"tool_choice": tool_choice, "stream": stream})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Clean up disk space."},
    ]

    with (
        patch("whai.core.executor.approval_loop", return_value="echo ok"),
        patch("whai.core.executor.execute_command", return_value=("ok\n", "", 0)) as mock_exec,
    ):
        run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 3
    assert call_kwargs[0]["tool_choice"] is None
    assert call_kwargs[1]["tool_choice"] == "required"
    assert call_kwargs[2]["tool_choice"] is None
    mock_exec.assert_called_once_with("echo ok", timeout=30)


def test_missing_command_tool_call_does_not_end_conversation():
    """A tool call without command should produce tool error and continue loop."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "Running diagnostics."},
            {
                "type": "tool_call",
                "id": "call_missing",
                "name": "execute_shell",
                "arguments": {},
            },
        ]),
        _stream([
            {"type": "text", "content": "Retrying with a valid command."},
            {
                "type": "tool_call",
                "id": "call_valid",
                "name": "execute_shell",
                "arguments": {"command": "echo hi"},
            },
        ]),
        _stream([
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {},
            },
        ]),
    ]

    def _mock_send_message(
        messages,
        tools=None,
        stream=True,
        tool_choice=None,
        mcp_loop=None,
        **kwargs,
    ):
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Clean up disk space."},
    ]

    with (
        patch("whai.core.executor.approval_loop", return_value="echo hi"),
        patch("whai.core.executor.execute_command", return_value=("hi\n", "", 0)) as mock_exec,
    ):
        run_conversation_loop(mock_provider, messages, timeout=30)

    assert mock_provider.send_message.call_count == 3
    mock_exec.assert_called_once_with("echo hi", timeout=30)


def test_no_tool_call_recovery_stops_after_max_retry():
    """Recovery should not loop forever when model keeps returning text-only turns."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "Let me check that now."},
        ]),
        _stream([
            {"type": "text", "content": "I will run another check next."},
        ]),
        _stream([
            {"type": "text", "content": "Still no tool call."},
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(
        messages,
        tools=None,
        stream=True,
        tool_choice=None,
        mcp_loop=None,
        **kwargs,
    ):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Clean up disk space."},
    ]

    run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 3
    assert call_kwargs[0]["tool_choice"] is None
    assert call_kwargs[1]["tool_choice"] == "required"
    assert call_kwargs[2]["tool_choice"] == "required"


def test_empty_response_triggers_retry():
    """Empty response (text_len=0, tool_calls=0) should trigger recovery retry."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        # Empty response — no text, no tool calls
        _stream([]),
        # After retry, still empty — second retry
        _stream([]),
        # Third attempt also empty — exhausted retries, loop exits
        _stream([]),
    ]

    call_kwargs = []

    def _mock_send_message(
        messages,
        tools=None,
        stream=True,
        tool_choice=None,
        mcp_loop=None,
        **kwargs,
    ):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Do something."},
    ]

    run_conversation_loop(mock_provider, messages, timeout=30)

    # Should have retried twice then given up
    assert len(call_kwargs) == 3
    assert call_kwargs[0]["tool_choice"] is None
    assert call_kwargs[1]["tool_choice"] == "required"
    assert call_kwargs[2]["tool_choice"] == "required"


def test_empty_response_retry_then_tool_call():
    """Empty response -> retry -> model produces tool call -> success."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        # Empty response
        _stream([]),
        # After retry, model produces task_complete
        _stream([
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {"summary": "Recovered from empty response."},
            },
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(
        messages,
        tools=None,
        stream=True,
        tool_choice=None,
        mcp_loop=None,
        **kwargs,
    ):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Do something."},
    ]

    run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 2
    assert call_kwargs[0]["tool_choice"] is None
    assert call_kwargs[1]["tool_choice"] == "required"


# ---------------------------------------------------------------------------
# MCP error tests
# ---------------------------------------------------------------------------


def test_mcp_init_error_raises_runtimeerror_not_systemexit():
    """MCP init failures should raise RuntimeError (not call sys.exit)."""

    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider._mcp_manager = None
    mock_provider.send_message.side_effect = AssertionError(
        "send_message should not be called when MCP init fails"
    )

    class FakeMCPManager:
        def __init__(self):
            self._initialized = False

        def is_enabled(self):
            return True

        async def initialize(self):
            return [("broken-server", "MCP init failed")]

    with patch("whai.mcp.manager.MCPManager", FakeMCPManager):
        with pytest.raises(RuntimeError, match="MCP server initialization failed"):
            run_conversation_loop(
                mock_provider,
                [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}],
                timeout=30,
                mcp_enabled=True,
            )


def test_mcp_config_error_does_not_raise_systemexit():
    """MCP config errors in send_message path should not terminate via SystemExit."""
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.send_message.side_effect = RuntimeError("mcp.json is invalid")

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Do something."},
    ]

    try:
        run_conversation_loop(mock_provider, messages, timeout=30, mcp_enabled=False)
    except SystemExit as exc:  # pragma: no cover
        pytest.fail(f"run_conversation_loop should not call sys.exit, got {exc}")


# ---------------------------------------------------------------------------
# Thinking tag integration test
# ---------------------------------------------------------------------------


def test_thinking_tags_stripped_in_recovery():
    """<think>...</think> blocks should be stripped before deciding to retry."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "<think>done. I need to check more.</think>Let me check what's inside /var/lib:"},
        ]),
        _stream([
            {"type": "text", "content": "Here are the results."},
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "execute_shell",
                "arguments": {"command": "ls /var/lib"},
            },
        ]),
        _stream([
            {
                "type": "tool_call",
                "id": "tc_1",
                "name": "task_complete",
                "arguments": {"summary": "Listed /var/lib contents."},
            },
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Clean up disk space."},
    ]

    with (
        patch("whai.core.executor.approval_loop", return_value="ls /var/lib"),
        patch("whai.core.executor.execute_command", return_value=("lib files\n", "", 0)),
    ):
        run_conversation_loop(mock_provider, messages, timeout=30)

    # First call normal, second with required (recovery), third normal
    assert len(call_kwargs) == 3
    assert call_kwargs[0]["tool_choice"] is None
    assert call_kwargs[1]["tool_choice"] == "required"
