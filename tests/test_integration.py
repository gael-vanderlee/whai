"""Integration tests for terma.

These tests verify end-to-end functionality with real components.
They use mocked LLM responses to avoid API costs.
"""

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from terma.main import app

runner = CliRunner()


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


def test_flow_1_qna_without_commands(mock_llm_text_only, tmp_path, monkeypatch):
    """
    Test Flow: Q&A without command execution.
    User asks a general question, LLM provides text-only answer.
    """
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["what is a .gitignore file?", "--no-context"])

        assert result.exit_code == 0
        assert "This is a test response" in result.stdout


def test_flow_2_command_generation_approved(
    mock_llm_text_only, mock_llm_with_tool_call, tmp_path, monkeypatch
):
    """
    Test Flow: Command generation and execution (approved).
    User asks for a command, approves it, sees output.
    """
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

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


def test_flow_3_command_generation_rejected(
    mock_llm_with_tool_call, tmp_path, monkeypatch
):
    """
    Test Flow: Command generation and execution (rejected).
    User asks for a command but rejects it.
    """
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

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


def test_cli_with_role_option(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that --role option works correctly."""
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(
            app, ["test query", "--role", "assistant", "--no-context"]
        )

        assert result.exit_code == 0


def test_cli_with_model_override(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that --model option works correctly."""
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(
            app, ["test query", "--model", "gpt-5-mini", "--no-context"]
        )

        assert result.exit_code == 0


def test_cli_with_no_context(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that --no-context flag works correctly."""
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context") as mock_context,
    ):
        result = runner.invoke(app, ["test query", "--no-context"])

        # Context capture should not be called
        mock_context.assert_not_called()
        assert result.exit_code == 0


def test_cli_missing_config(tmp_path, monkeypatch):
    """Test behavior when config file doesn't exist (should create it)."""
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

    # Don't create config beforehand
    # The app should create it on first run
    with (
        patch("litellm.completion"),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test", "--no-context"])
        assert result.exit_code == 0

        # Should have created config
        config_file = tmp_path / "config.toml"
        assert config_file.exists()


def test_cli_keyboard_interrupt(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that Ctrl+C is handled gracefully."""
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

    def mock_completion_with_interrupt(**kwargs):
        raise KeyboardInterrupt()

    with (
        patch("litellm.completion", side_effect=mock_completion_with_interrupt),
        patch("terma.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test", "--no-context"])

        # Should exit gracefully
        assert "Interrupted" in result.stdout or result.exit_code == 0


def test_cli_with_context_warning(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that warning is shown when only shallow context is available."""
    # Use temp directory for config
    monkeypatch.setattr("terma.config.get_config_dir", lambda: tmp_path)

    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("terma.context.get_context", return_value=("some history", False)),
    ):  # Shallow context
        result = runner.invoke(app, ["test query"])

        # Warning could be in stdout or stderr
        output = result.stdout + result.stderr
        assert "shell history only" in output.lower() or "warning" in output.lower()


@pytest.mark.integration
def test_real_shell_execution(tmp_path, monkeypatch):
    """
    Integration test with real shell execution (no LLM).

    Tests that the shell session can actually execute commands.
    """
    from terma.interaction import ShellSession

    with ShellSession() as session:
        stdout, stderr, code = session.execute_command('echo "Hello from terma"')

        assert "Hello from terma" in stdout
        assert code == 0


@pytest.mark.integration
def test_state_persistence_in_shell(tmp_path, monkeypatch):
    """
    Integration test verifying that cd and export persist in shell session.
    """
    import os

    from terma.interaction import ShellSession

    with ShellSession() as session:
        # Change directory
        if os.name == "nt":
            # Windows
            session.execute_command("cd C:\\")
            stdout, _, _ = session.execute_command("cd")
            assert "C:\\" in stdout
        else:
            # Unix
            session.execute_command("cd /tmp")
            stdout, _, _ = session.execute_command("pwd")
            assert "/tmp" in stdout
