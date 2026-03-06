"""Tests for --command-only CLI behavior.

These tests focus on observable behavior:
- exit codes
- stdout contents (single shell command or empty)
"""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from whai.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def test_config(tmp_path, monkeypatch):
    """Set up ephemeral test config."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setenv("WHAI_TEST_MODE", "1")


def _invoke(args: list[str], input_text: str | None = None):
    return runner.invoke(app, args, input=input_text)


def test_command_only_success_prints_single_command(monkeypatch):
    """whai --command-only ... prints exactly one shell command and exits 0."""

    def fake_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None):
        return {
            "content": "ignored",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "execute_shell",
                    "arguments": {"command": "ls -la"},
                }
            ],
        }

    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    with (
        patch("whai.context.get_context", return_value=("", False)),
        patch("whai.llm.provider.LLMProvider.send_message", side_effect=fake_send_message),
    ):
        result = _invoke(["--no-context", "--command-only", "list", "current", "directory", "contents"])

    assert result.exit_code == 0
    # In command-only mode stdout should be exactly the command plus newline.
    assert result.stdout == "ls -la\n"


def test_command_only_no_tool_call_returns_non_zero_and_no_stdout(monkeypatch):
    """If the model does not return an execute_shell tool call, no command is printed."""

    def fake_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None):
        return {
            "content": "no tools",
            "tool_calls": [],
        }

    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    with (
        patch("whai.context.get_context", return_value=("", False)),
        patch("whai.llm.provider.LLMProvider.send_message", side_effect=fake_send_message),
    ):
        result = _invoke(["--no-context", "--command-only", "list", "current", "directory", "contents"])

    assert result.exit_code != 0
    assert result.stdout == ""


def test_command_only_empty_command_is_failure(monkeypatch):
    """Empty or whitespace-only command should be treated as failure."""

    def fake_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "execute_shell",
                    "arguments": {"command": "   "},
                }
            ],
        }

    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    with (
        patch("whai.context.get_context", return_value=("", False)),
        patch("whai.llm.provider.LLMProvider.send_message", side_effect=fake_send_message),
    ):
        result = _invoke(["--no-context", "--command-only", "list", "current", "directory", "contents"])

    assert result.exit_code != 0
    assert result.stdout == ""


def test_command_only_uses_stdin_when_no_query(monkeypatch):
    """whai --command-only reads prompt from stdin when no query args are given."""

    def fake_send_message(messages, tools=None, stream=True, tool_choice=None, mcp_loop=None):
        return {
            "content": "ignored",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "execute_shell",
                    "arguments": {"command": "ls -la"},
                }
            ],
        }

    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    with (
        patch("whai.context.get_context", return_value=("", False)),
        patch("whai.llm.provider.LLMProvider.send_message", side_effect=fake_send_message),
    ):
        # No free-form query args; prompt is supplied via stdin
        result = _invoke(["--no-context", "--command-only"], input_text="list current directory contents")

    assert result.exit_code == 0
    assert result.stdout == "ls -la\n"

