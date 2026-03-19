"""Behavioral tests for conversation-loop recovery."""

from unittest.mock import MagicMock, patch

import pytest

from whai.core.executor import run_conversation_loop
from whai.llm import LLMProvider


def _stream(chunks):
    for chunk in chunks:
        yield chunk


def _assert_execute_shell_call(mock_exec, command: str, timeout: int) -> None:
    mock_exec.assert_called_once()
    args, kwargs = mock_exec.call_args
    assert args == (command,)
    assert kwargs["timeout"] == timeout
    assert callable(kwargs["on_input_needed"])


def test_no_tool_call_retries_with_required_tool_choice():
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream(
            [
                {"type": "text", "content": "Let me check that."},
            ]
        ),
        _stream(
            [
                {
                    "type": "tool_call",
                    "id": "done_1",
                    "name": "task_complete",
                    "arguments": {"summary": "Checked it."},
                },
            ]
        ),
    ]
    call_kwargs = []

    def _mock_send_message(
        messages, tools=None, stream=True, tool_choice=None, mcp_loop=None, **kwargs
    ):
        call_kwargs.append({"tool_choice": tool_choice})
        return responses.pop(0)

    mock_provider.send_message.side_effect = _mock_send_message

    run_conversation_loop(
        mock_provider,
        [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Check disk space."},
        ],
        timeout=30,
    )

    assert call_kwargs == [
        {"tool_choice": None},
        {"tool_choice": "required"},
    ]


def test_task_complete_runs_after_other_tool_calls_in_same_turn():
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream(
            [
                {"type": "text", "content": "Checking disk."},
                {
                    "type": "tool_call",
                    "id": "shell_1",
                    "name": "execute_shell",
                    "arguments": {"command": "df -h"},
                },
                {
                    "type": "tool_call",
                    "id": "done_1",
                    "name": "task_complete",
                    "arguments": {"summary": "Disk checked."},
                },
            ]
        ),
    ]

    mock_provider.send_message.side_effect = lambda *args, **kwargs: responses.pop(0)

    with (
        patch("whai.core.executor.approval_loop", side_effect=lambda cmd: cmd),
        patch(
            "whai.core.executor.execute_command", return_value=("ok\n", "", 0)
        ) as mock_exec,
    ):
        run_conversation_loop(
            mock_provider,
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Check disk space."},
            ],
            timeout=30,
        )

    _assert_execute_shell_call(mock_exec, "df -h", 30)
    assert mock_provider.send_message.call_count == 1


def test_multiple_execute_shell_calls_only_run_first_command():
    mock_provider = MagicMock(spec=LLMProvider)
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Check disk space."},
    ]

    responses = [
        _stream(
            [
                {"type": "text", "content": "Checking disk."},
                {
                    "type": "tool_call",
                    "id": "shell_1",
                    "name": "execute_shell",
                    "arguments": {"command": "df -h"},
                },
                {
                    "type": "tool_call",
                    "id": "shell_2",
                    "name": "execute_shell",
                    "arguments": {"command": "du -sh ."},
                },
                {
                    "type": "tool_call",
                    "id": "done_1",
                    "name": "task_complete",
                    "arguments": {"summary": "Disk checked."},
                },
            ]
        ),
    ]

    mock_provider.send_message.side_effect = lambda *args, **kwargs: responses.pop(0)

    with (
        patch("whai.core.executor.approval_loop", side_effect=lambda cmd: cmd),
        patch(
            "whai.core.executor.execute_command", return_value=("ok\n", "", 0)
        ) as mock_exec,
    ):
        run_conversation_loop(
            mock_provider,
            messages,
            timeout=30,
        )

    _assert_execute_shell_call(mock_exec, "df -h", 30)
    assert mock_provider.send_message.call_count == 1
    # task_complete is handled before tool results are appended to messages,
    # so the skipped shell_2 result won't appear in the message history.
    # The important behavior is that only one shell command ran and the loop
    # exited cleanly via task_complete (verified by call_count == 1).


def test_missing_execute_shell_command_is_recoverable():
    mock_provider = MagicMock(spec=LLMProvider)

    responses = [
        _stream(
            [
                {
                    "type": "tool_call",
                    "id": "shell_missing",
                    "name": "execute_shell",
                    "arguments": {},
                },
            ]
        ),
        _stream(
            [
                {
                    "type": "tool_call",
                    "id": "shell_valid",
                    "name": "execute_shell",
                    "arguments": {"command": "echo hi"},
                },
            ]
        ),
        _stream(
            [
                {
                    "type": "tool_call",
                    "id": "done_1",
                    "name": "task_complete",
                    "arguments": {},
                },
            ]
        ),
    ]

    mock_provider.send_message.side_effect = lambda *args, **kwargs: responses.pop(0)

    with (
        patch("whai.core.executor.approval_loop", return_value="echo hi"),
        patch(
            "whai.core.executor.execute_command", return_value=("hi\n", "", 0)
        ) as mock_exec,
    ):
        run_conversation_loop(
            mock_provider,
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Do something."},
            ],
            timeout=30,
        )

    _assert_execute_shell_call(mock_exec, "echo hi", 30)
    assert mock_provider.send_message.call_count == 3


def test_mcp_init_error_raises_runtimeerror_not_systemexit():
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider._mcp_manager = None
    mock_provider.send_message.side_effect = AssertionError(
        "send_message should not be called"
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
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.send_message.side_effect = RuntimeError("mcp.json is invalid")

    try:
        run_conversation_loop(
            mock_provider,
            [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Do something."},
            ],
            timeout=30,
            mcp_enabled=False,
        )
    except SystemExit as exc:  # pragma: no cover
        pytest.fail(f"run_conversation_loop should not call sys.exit, got {exc}")
