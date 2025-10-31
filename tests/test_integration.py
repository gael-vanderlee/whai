"""Integration tests for terma.

These tests verify end-to-end functionality with real components.
They use mocked LLM responses to avoid API costs.
"""

from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from terma.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def integration_test_config(tmp_path, monkeypatch):
    """
    Auto-applied fixture for integration tests.
    Sets up ephemeral config to avoid writing to user's config directory.
    """
    # Redirect config to temp directory
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)
    # Enable test mode to use ephemeral config (no disk writes)
    monkeypatch.setenv("TERMA_TEST_MODE", "1")


@pytest.fixture
def mock_llm_text_only():
    """Mock LLM that returns text-only responses (no tool calls)."""

    def mock_completion(**kwargs):
        if kwargs.get("stream"):
            # Streaming response
            chunks = [
                MagicMock(
                    choices=[
                        MagicMock(delta=MagicMock(content="This ", tool_calls=None))
                    ]
                ),
                MagicMock(
                    choices=[
                        MagicMock(delta=MagicMock(content="is a ", tool_calls=None))
                    ]
                ),
                MagicMock(
                    choices=[
                        MagicMock(
                            delta=MagicMock(content="test response.", tool_calls=None)
                        )
                    ]
                ),
            ]
            return iter(chunks)
        else:
            # Non-streaming response
            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message = MagicMock()
            response.choices[0].message.content = "This is a test response."
            response.choices[0].message.tool_calls = None
            return response

    return mock_completion


@pytest.fixture
def mock_llm_with_tool_call():
    """Mock LLM that returns a tool call."""

    def mock_completion(**kwargs):
        import json

        if kwargs.get("stream"):
            # Streaming response with tool call
            mock_tool = MagicMock()
            mock_tool.id = "call_test_123"
            mock_tool.function = MagicMock()
            mock_tool.function.name = "execute_shell"
            mock_tool.function.arguments = json.dumps({"command": 'echo "test"'})

            chunks = [
                MagicMock(
                    choices=[
                        MagicMock(
                            delta=MagicMock(content="Let me run that.", tool_calls=None)
                        )
                    ]
                ),
                MagicMock(
                    choices=[
                        MagicMock(delta=MagicMock(content=None, tool_calls=[mock_tool]))
                    ]
                ),
            ]
            return iter(chunks)
        else:
            # Non-streaming response with tool call
            mock_tool = MagicMock()
            mock_tool.id = "call_test_123"
            mock_tool.function = MagicMock()
            mock_tool.function.name = "execute_shell"
            mock_tool.function.arguments = json.dumps({"command": 'echo "test"'})

            response = MagicMock()
            response.choices = [MagicMock()]
            response.choices[0].message = MagicMock()
            response.choices[0].message.content = "Let me run that."
            response.choices[0].message.tool_calls = [mock_tool]
            return response

    return mock_completion


def test_flow_1_qna_without_commands(mock_llm_text_only):
    """
    Test Flow: Q&A without command execution.
    User asks a general question, LLM provides text-only answer.
    """
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["what is a .gitignore file?", "--no-context"])

        assert result.exit_code == 0
        assert "This is a test response" in result.stdout


def test_flow_2_command_generation_approved(
    mock_llm_text_only, mock_llm_with_tool_call
):
    """
    Test Flow: Command generation and execution (approved).
    User asks for a command, approves it, sees output.
    """
    # Mock ShellSession to avoid real command execution
    mock_session = MagicMock()
    mock_session.execute_command.return_value = ("test output\n", "", 0)
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # Mock LLM - first call returns tool call, second call returns text only
    call_count = [0]

    def mock_completion_sequence(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_llm_with_tool_call(**kwargs)
        else:
            return mock_llm_text_only(**kwargs)

    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_completion_sequence),
        patch("terma.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),  # Approve the command
        patch("terma.main.ShellSession", return_value=mock_session),
    ):
        result = runner.invoke(app, ["echo test", "--no-context"])

        assert result.exit_code == 0
        assert "Let me run that" in result.stdout
        assert "Proposed command" in result.stdout


def test_flow_3_command_generation_rejected(mock_llm_with_tool_call):
    """
    Test Flow: Command generation and execution (rejected).
    User asks for a command but rejects it.
    """
    # Mock ShellSession to avoid real command execution
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)

    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_with_tool_call),
        patch("terma.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="r"),  # Reject the command
        patch("terma.main.ShellSession", return_value=mock_session),
    ):
        result = runner.invoke(app, ["echo test", "--no-context"])

        assert result.exit_code == 0
        assert (
            "rejected" in result.stdout.lower() or "Command rejected" in result.stdout
        )


def test_cli_with_role_option(mock_llm_text_only):
    """Test that --role option works correctly."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(
            app, ["test query", "--role", "assistant", "--no-context"]
        )

        assert result.exit_code == 0
        # Verify that role information is displayed
        output = result.stdout + result.stderr
        assert "assistant" in output.lower()


def test_cli_with_model_override(mock_llm_text_only):
    """Test that --model option works correctly."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(
            app, ["test query", "--model", "gpt-5-mini", "--no-context"]
        )

        assert result.exit_code == 0
        # Verify that model and role information is displayed
        output = result.stdout + result.stderr
        assert "gpt-5-mini" in output
        assert "assistant" in output.lower()


def test_cli_timeout_default_passed(mock_llm_with_tool_call, mock_llm_text_only):
    """Default timeout (60s) should be passed to execute_command."""

    # Mock ShellSession
    mock_session = MagicMock()
    mock_session.execute_command.return_value = ("ok\n", "", 0)

    # Sequence: tool call first, then text only
    call_count = [0]

    def mock_completion_sequence(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_llm_with_tool_call(**kwargs)
        else:
            return mock_llm_text_only(**kwargs)

    with (
        patch("litellm.completion", side_effect=mock_completion_sequence),
        patch("terma.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),
        patch("terma.main.ShellSession", return_value=mock_session),
    ):
        result = runner.invoke(
            app, ["echo test", "--no-context"]
        )  # no explicit --timeout
        assert result.exit_code == 0
        # Ensure default 60 was used
        assert any(
            kwargs.get("timeout") == 60
            for args, kwargs in mock_session.execute_command.call_args_list
        )


def test_cli_timeout_override_passed(mock_llm_with_tool_call, mock_llm_text_only):
    """Override timeout via --timeout should be passed through."""
    mock_session = MagicMock()
    mock_session.execute_command.return_value = ("ok\n", "", 0)

    call_count = [0]

    def mock_completion_sequence(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_llm_with_tool_call(**kwargs)
        else:
            return mock_llm_text_only(**kwargs)

    with (
        patch("litellm.completion", side_effect=mock_completion_sequence),
        patch("terma.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),
        patch("terma.main.ShellSession", return_value=mock_session),
    ):
        result = runner.invoke(app, ["echo test", "--no-context", "--timeout", "30"])
        assert result.exit_code == 0
        # Check that execute_command was called with timeout=30
        assert mock_session.execute_command.called, "execute_command was not called"
        # Get the actual calls
        calls = mock_session.execute_command.call_args_list
        assert len(calls) > 0, "No calls to execute_command"
        # Check if any call has timeout=30
        timeouts = [call.kwargs.get("timeout") for call in calls]
        assert 30 in timeouts, f"Expected timeout=30, got timeouts: {timeouts}"


def test_cli_timeout_invalid_value(mock_llm_text_only):
    """Invalid timeout values should fail fast with clear error."""
    # No mocks needed - validation happens before any LLM/context code
    result = runner.invoke(app, ["test query", "--no-context", "--timeout", "0"])
    assert result.exit_code == 2
    assert "timeout" in (result.stdout + result.stderr).lower()


def test_cli_with_no_context(mock_llm_text_only):
    """Test that --no-context flag works correctly."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context") as mock_context,
    ):
        result = runner.invoke(app, ["test query", "--no-context"])

        # Context capture should not be called
        mock_context.assert_not_called()
        assert result.exit_code == 0


def test_cli_missing_config(monkeypatch):
    """Test that interactive config wizard is launched when config is missing."""
    # Disable test mode so MissingConfigError is raised
    monkeypatch.delenv("TERMA_TEST_MODE", raising=False)

    # Mock the wizard to simulate user canceling
    with patch("terma.config_wizard.run_wizard", side_effect=typer.Abort()):
        result = runner.invoke(app, ["test query"])

    assert result.exit_code == 1
    # Should show config setup message (check both stdout and stderr)
    output = result.stdout + result.stderr
    assert "Configuration" in output or "config" in output.lower()


def test_cli_keyboard_interrupt(mock_llm_text_only):
    """Test that Ctrl+C is handled gracefully."""

    def mock_completion_with_interrupt(**kwargs):
        raise KeyboardInterrupt()

    with (
        patch("litellm.completion", side_effect=mock_completion_with_interrupt),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test", "--no-context"])

        # Should exit gracefully
        assert "Interrupted" in result.stdout or result.exit_code == 0


def test_cli_with_context_warning(mock_llm_text_only):
    """Test that warning is shown when only shallow context is available."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("some history", False)),
    ):  # Shallow context
        result = runner.invoke(app, ["test query"])

        # Warning could be in stdout or stderr
        output = result.stdout + result.stderr
        assert "shell history only" in output.lower() or "warning" in output.lower()


def test_unquoted_arguments(mock_llm_text_only):
    """Test that unquoted multi-word queries work correctly."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(
            app, ["what", "is", "a", ".gitignore", "file?", "--no-context"]
        )

        assert result.exit_code == 0
        assert "This is a test response" in result.stdout


def test_quoted_arguments_backward_compat(mock_llm_text_only):
    """Test that quoted single argument still works (backward compatibility)."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["what is a .gitignore file?", "--no-context"])

        assert result.exit_code == 0
        assert "This is a test response" in result.stdout


def test_mixed_options_unquoted(mock_llm_text_only):
    """Test that options work correctly with unquoted arguments."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["--no-context", "what", "is", "this", "file"])

        assert result.exit_code == 0
        assert "This is a test response" in result.stdout


@pytest.mark.integration
def test_real_shell_execution():
    """
    Integration test with real shell execution (no LLM).

    Tests that the shell session can actually execute commands.
    """
    from terma.interaction import ShellSession

    with ShellSession() as session:
        stdout, stderr, code = session.execute_command(
            'echo "Hello from terma"', timeout=60
        )

        assert "Hello from terma" in stdout
        assert code == 0


@pytest.mark.integration
def test_state_persistence_in_shell():
    """
    Integration test verifying that cd and export persist in shell session.
    """
    import os

    from terma.interaction import ShellSession

    with ShellSession() as session:
        # Change directory
        if os.name == "nt":
            # Windows
            session.execute_command("cd C:\\", timeout=60)
            stdout, _, _ = session.execute_command("cd", timeout=60)
            assert "C:\\" in stdout
        else:
            # Unix
            session.execute_command("cd /tmp", timeout=60)
            stdout, _, _ = session.execute_command("pwd", timeout=60)
            assert "/tmp" in stdout
