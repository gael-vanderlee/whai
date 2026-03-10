"""Integration tests for conversation-loop recovery behavior."""

from unittest.mock import MagicMock, patch

import pytest

from whai.core.executor import (
    _looks_like_continuation_without_tool_call,
    _looks_like_final_answer,
    _strip_thinking_tags,
    run_conversation_loop,
)
from whai.llm import LLMProvider


def _stream(chunks):
    for chunk in chunks:
        yield chunk


def test_no_tool_call_recovery_retries_with_required_tool_choice():
    """If assistant implies continuation but emits no tool call, loop retries once."""
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
            {"type": "text", "content": "Done."},
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
            {"type": "text", "content": "Done."},
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

    assert len(call_kwargs) == 2
    assert call_kwargs[0]["tool_choice"] is None
    assert call_kwargs[1]["tool_choice"] == "required"


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
# Unit tests for heuristic helpers
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


class TestLooksLikeFinalAnswer:
    def test_done_at_end(self):
        assert _looks_like_final_answer("All cleanup is done.") is True

    def test_done_mid_sentence_not_matched(self):
        assert _looks_like_final_answer("Cleanup is done. Now let me check more.") is False

    def test_task_is_complete(self):
        assert _looks_like_final_answer("The task is complete.") is True

    def test_task_is_not_complete_negation(self):
        assert _looks_like_final_answer("The task is not complete yet.") is False

    def test_task_isnt_complete_negation(self):
        assert _looks_like_final_answer("The task isn't complete yet.") is False

    def test_youre_all_set(self):
        assert _looks_like_final_answer("You're all set!") is True

    def test_empty_string(self):
        assert _looks_like_final_answer("") is False

    def test_no_further_action(self):
        assert _looks_like_final_answer("There is no further action needed.") is True


class TestLooksLikeContinuation:
    def test_let_me_check(self):
        assert _looks_like_continuation_without_tool_call("Let me check the files.") is True

    def test_colon_ending(self):
        assert _looks_like_continuation_without_tool_call("Let me check what's inside /var/lib:") is True

    def test_now_ill(self):
        assert _looks_like_continuation_without_tool_call("Now I'll examine the logs.") is True

    def test_now_let_me(self):
        assert _looks_like_continuation_without_tool_call("Now let me verify the result.") is True

    def test_first_ill(self):
        assert _looks_like_continuation_without_tool_call("First, I'll scan the directory.") is True

    def test_let_me_start_by(self):
        assert _looks_like_continuation_without_tool_call("Let me start by checking the disk.") is True

    def test_plain_text_no_match(self):
        assert _looks_like_continuation_without_tool_call("The disk is 80% full.") is False

    def test_empty_string(self):
        assert _looks_like_continuation_without_tool_call("") is False


# ---------------------------------------------------------------------------
# Integration tests for new recovery behaviors
# ---------------------------------------------------------------------------


def test_thinking_tags_stripped_before_heuristics():
    """<think>done.</think>Let me check: should trigger recovery, not exit."""
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
            {"type": "text", "content": "All done."},
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


def test_final_answer_done_not_matched_mid_sentence():
    """'done. Now let me check' should NOT be detected as final answer."""
    assert _looks_like_final_answer("Cleanup is done. Now let me check the logs.") is False


def test_final_answer_negation_not_matched():
    """'task is not complete' should NOT be detected as final answer."""
    assert _looks_like_final_answer("The task is not complete, more work needed.") is False


def test_mid_conversation_retries_unless_final():
    """After successful tool calls, generic text-only response should be retried."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        # Turn 1: tool call succeeds
        _stream([
            {"type": "text", "content": "Checking disk."},
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "execute_shell",
                "arguments": {"command": "df -h"},
            },
        ]),
        # Turn 2: generic text, no tool call — should retry (mid-conversation)
        _stream([
            {"type": "text", "content": "The disk is 80% full, I see some large files."},
        ]),
        # Turn 3: recovery produces tool call
        _stream([
            {"type": "text", "content": "Removing temp files."},
            {
                "type": "tool_call",
                "id": "call_2",
                "name": "execute_shell",
                "arguments": {"command": "rm -rf /tmp/old"},
            },
        ]),
        # Turn 4: final answer
        _stream([
            {"type": "text", "content": "All done."},
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
        patch("whai.core.executor.approval_loop", side_effect=lambda cmd: cmd),
        patch("whai.core.executor.execute_command", return_value=("ok\n", "", 0)),
    ):
        run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 4
    # Turn 2 text-only should trigger recovery with required tool_choice
    assert call_kwargs[2]["tool_choice"] == "required"


def test_mid_conversation_does_not_retry_on_final():
    """After tool calls, a clear final answer should exit without retry."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        # Turn 1: tool call succeeds
        _stream([
            {"type": "text", "content": "Checking disk."},
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "execute_shell",
                "arguments": {"command": "df -h"},
            },
        ]),
        # Turn 2: clear final answer — should NOT retry
        _stream([
            {"type": "text", "content": "You're all set! The disk has plenty of space."},
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

    # Only 2 calls — no retry attempted
    assert len(call_kwargs) == 2
    assert call_kwargs[1]["tool_choice"] is None


def test_colon_ending_triggers_continuation():
    """Text ending with ':' should be detected as continuation."""
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream([
            {"type": "text", "content": "Here's what I found in the directory:"},
        ]),
        _stream([
            {"type": "text", "content": "Listing files."},
            {
                "type": "tool_call",
                "id": "call_1",
                "name": "execute_shell",
                "arguments": {"command": "ls"},
            },
        ]),
        _stream([
            {"type": "text", "content": "All done."},
        ]),
    ]

    call_kwargs = []

    def _mock_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "List files."},
    ]

    with (
        patch("whai.core.executor.approval_loop", return_value="ls"),
        patch("whai.core.executor.execute_command", return_value=("file1\nfile2\n", "", 0)),
    ):
        run_conversation_loop(mock_provider, messages, timeout=30)

    assert len(call_kwargs) == 3
    assert call_kwargs[1]["tool_choice"] == "required"
