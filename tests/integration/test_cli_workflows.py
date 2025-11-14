"""Integration tests for whai.

These tests verify end-to-end functionality with real components.
They use mocked LLM responses to avoid API costs.
"""

from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from whai.cli.main import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def integration_test_config(tmp_path, monkeypatch):
    """
    Auto-applied fixture for integration tests.
    Sets up ephemeral config to avoid writing to user's config directory.
    """
    # Redirect config to temp directory
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    # Enable test mode to use ephemeral config (no disk writes)
    monkeypatch.setenv("WHAI_TEST_MODE", "1")


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
        patch("whai.context.get_context", return_value=("", False)),
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
    # Mock LLM - first call returns tool call, second call returns text only
    call_count = [0]

    def mock_completion_sequence(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_llm_with_tool_call(**kwargs)
        else:
            return mock_llm_text_only(**kwargs)

    # Mock execute_command to avoid real command execution
    with (
        patch("litellm.completion", side_effect=mock_completion_sequence),
        patch("whai.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),  # Approve the command
        patch("whai.core.executor.execute_command", return_value=("test output\n", "", 0)),
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
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_with_tool_call),
        patch("whai.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="r"),  # Reject the command
    ):
        result = runner.invoke(app, ["echo test", "--no-context"])

        assert result.exit_code == 0
        # info() outputs to stderr, check both stdout and stderr
        assert (
            "rejected" in result.stdout.lower() 
            or "Command rejected" in result.stdout
            or "Command rejected" in result.stderr
        )


def test_cli_with_role_option(mock_llm_text_only):
    """Test that --role option works correctly."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test query", "--role", "default", "--no-context"])

        assert result.exit_code == 0
        # Verify that role information is displayed
        output = result.stdout + result.stderr
        assert "default" in output.lower()


def test_cli_with_model_override(mock_llm_text_only):
    """Test that --model option works correctly."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(
            app, ["test query", "--model", "gpt-5-mini", "--no-context"]
        )

        assert result.exit_code == 0
        # Verify that model and role information is displayed
        output = result.stdout + result.stderr
        assert "gpt-5-mini" in output
        assert "default" in output.lower()


def test_cli_timeout_default_passed(mock_llm_with_tool_call, mock_llm_text_only):
    """Default timeout (60s) should be passed to execute_command."""
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
        patch("whai.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),
        patch("whai.core.executor.execute_command", return_value=("ok\n", "", 0)) as mock_exec,
    ):
        result = runner.invoke(
            app, ["echo test", "--no-context"]
        )  # no explicit --timeout
        assert result.exit_code == 0
        # Ensure default 60 was used
        assert mock_exec.called
        # Check that timeout=60 was passed
        call_kwargs = [call.kwargs for call in mock_exec.call_args_list]
        assert any(kw.get("timeout") == 60 for kw in call_kwargs)


def test_cli_timeout_override_passed(mock_llm_with_tool_call, mock_llm_text_only):
    """Override timeout via --timeout should be passed through."""
    call_count = [0]

    def mock_completion_sequence(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return mock_llm_with_tool_call(**kwargs)
        else:
            return mock_llm_text_only(**kwargs)

    with (
        patch("litellm.completion", side_effect=mock_completion_sequence),
        patch("whai.context.get_context", return_value=("", False)),
        patch("builtins.input", return_value="a"),
        patch("whai.core.executor.execute_command", return_value=("ok\n", "", 0)) as mock_exec,
    ):
        result = runner.invoke(app, ["echo test", "--no-context", "--timeout", "30"])
        assert result.exit_code == 0
        # Check that execute_command was called with timeout=30
        assert mock_exec.called, "execute_command was not called"
        # Check if any call has timeout=30
        call_kwargs = [call.kwargs for call in mock_exec.call_args_list]
        timeouts = [kw.get("timeout") for kw in call_kwargs]
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
        patch("whai.context.get_context") as mock_context,
    ):
        result = runner.invoke(app, ["test query", "--no-context"])

        # Context capture should not be called
        mock_context.assert_not_called()
        assert result.exit_code == 0


def test_cli_missing_config(monkeypatch):
    """Test that interactive config wizard is launched when config is missing."""
    # Disable test mode so MissingConfigError is raised
    monkeypatch.delenv("WHAI_TEST_MODE", raising=False)

    # Mock the wizard to simulate user canceling
    with patch(
        "whai.configuration.config_wizard.run_wizard", side_effect=typer.Abort()
    ):
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
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test", "--no-context"])

        # Should exit gracefully
        assert "Interrupted" in result.stdout or result.exit_code == 0


def test_cli_with_context_warning(mock_llm_text_only):
    """Test that warning is shown when only shallow context is available."""
    # Mock LLM
    # Patch where it's imported and used in main.py
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("whai.cli.main.get_context", return_value=("some history", False)),
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
        patch("whai.context.get_context", return_value=("", False)),
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
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["what is a .gitignore file?", "--no-context"])

        assert result.exit_code == 0
        assert "This is a test response" in result.stdout


def test_mixed_options_unquoted(mock_llm_text_only):
    """Test that options work correctly with unquoted arguments."""
    # Mock LLM
    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["--no-context", "what", "is", "this", "file"])

        assert result.exit_code == 0
        assert "This is a test response" in result.stdout


@pytest.mark.integration
def test_real_command_execution():
    """
    Integration test with real command execution (no LLM).

    Tests that commands can actually be executed.
    """
    import platform

    from whai.interaction import execute_command

    if platform.system() == "Windows":
        # Windows PowerShell echo behaves differently
        stdout, stderr, code = execute_command(
            'Write-Output "Hello from whai"', timeout=60
        )
    else:
        stdout, stderr, code = execute_command('echo "Hello from whai"', timeout=60)

    assert "Hello from whai" in stdout or "Hello" in stdout
    assert code == 0


def test_provider_precedence_cli_over_role(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that CLI provider override takes precedence over role provider."""
    from pathlib import Path
    from unittest.mock import patch

    from whai.configuration import user_config as config
    from whai.configuration.roles import ensure_default_roles

    # Set up config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    # Create config with multiple providers
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    test_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="sk-test-openai",
                    default_model="gpt-4",
                ),
                "anthropic": AnthropicConfig(
                    api_key="sk-test-anthropic",
                    default_model="claude-3-opus",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    config.save_config(test_config)

    # Create a role with provider="anthropic" in frontmatter
    ensure_default_roles()
    roles_dir = tmp_path / "roles"
    custom_role = roles_dir / "custom.md"
    custom_role.write_text("""---
provider: anthropic
model: claude-3-opus
---

You are a custom assistant.
""")

    # Mock LLM to capture which provider was used
    provider_used = []

    def mock_completion_with_provider_check(**kwargs):
        # Check the model to infer provider (simplified check)
        model = kwargs.get("model", "")
        if "claude" in model.lower():
            provider_used.append("anthropic")
        elif "gpt" in model.lower():
            provider_used.append("openai")
        return mock_llm_text_only(**kwargs)

    with (
        patch("litellm.completion", side_effect=mock_completion_with_provider_check),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Run CLI with --provider openai (should override role's anthropic)
        result = runner.invoke(
            app, ["test query", "--role", "custom", "--provider", "openai", "--no-context"]
        )

        assert result.exit_code == 0
        # Verify that openai was used (CLI override wins)
        # The model should be gpt-4 (from openai provider default)
        output = result.stdout + result.stderr
        assert "gpt-4" in output or "openai" in output.lower()


def test_provider_from_role_metadata(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that role provider is used when no CLI override is provided."""
    from pathlib import Path
    from unittest.mock import patch

    from whai.configuration import user_config as config
    from whai.configuration.roles import ensure_default_roles

    # Set up config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    # Create config with multiple providers, default is openai
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    test_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="sk-test-openai",
                    default_model="gpt-4",
                ),
                "anthropic": AnthropicConfig(
                    api_key="sk-test-anthropic",
                    default_model="claude-3-opus",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    config.save_config(test_config)

    # Create a role with provider="anthropic" in frontmatter
    ensure_default_roles()
    roles_dir = tmp_path / "roles"
    custom_role = roles_dir / "anthropic-role.md"
    custom_role.write_text("""---
provider: anthropic
model: claude-3-opus
---

You are an Anthropic assistant.
""")

    with (
        patch("litellm.completion", side_effect=mock_llm_text_only),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Run CLI with the role but NO --provider override
        # Should use anthropic from role metadata, not default openai
        result = runner.invoke(
            app, ["test query", "--role", "anthropic-role", "--no-context"]
        )

        assert result.exit_code == 0
        # Verify that anthropic provider/model was used (from role, not default)
        output = result.stdout + result.stderr
        # Should show claude-3-opus or anthropic (from role metadata)
        assert "claude-3-opus" in output or "anthropic" in output.lower()


def test_provider_without_model_uses_provider_default(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that --provider without --model uses the specified provider's default model, not the default provider's model."""
    from unittest.mock import patch

    from whai.configuration import user_config as config
    from whai.configuration.roles import ensure_default_roles

    # Set up config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    # Create config with multiple providers, default is openai
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    test_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="sk-test-openai",
                    default_model="gpt-4",
                ),
                "anthropic": AnthropicConfig(
                    api_key="sk-test-anthropic",
                    default_model="claude-3-opus",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    config.save_config(test_config)
    ensure_default_roles()

    # Track which model was actually used
    models_used = []

    def mock_completion_with_model_check(**kwargs):
        model = kwargs.get("model", "")
        models_used.append(model)
        return mock_llm_text_only(**kwargs)

    with (
        patch("litellm.completion", side_effect=mock_completion_with_model_check),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Run CLI with --provider anthropic but NO --model
        # Should use anthropic's default model (claude-3-opus), not openai's default (gpt-4)
        result = runner.invoke(
            app, ["test query", "--provider", "anthropic", "--no-context"]
        )

        assert result.exit_code == 0
        # Verify that claude-3-opus was used (anthropic's default), not gpt-4 (openai's default)
        assert len(models_used) > 0
        # The model should be claude-3-opus (from anthropic provider default)
        assert any("claude-3-opus" in model.lower() or "claude_3_opus" in model.lower() for model in models_used)
        # Should NOT use gpt-4 (which is the default provider's model)
        assert not any("gpt-4" in model.lower() or "gpt_4" in model.lower() for model in models_used)


def test_provider_with_model_uses_cli_model_override(mock_llm_text_only, tmp_path, monkeypatch):
    """Test that --provider X --model Y uses model Y (CLI override still works)."""
    from unittest.mock import patch

    from whai.configuration import user_config as config
    from whai.configuration.roles import ensure_default_roles

    # Set up config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    # Create config with multiple providers
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    test_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="sk-test-openai",
                    default_model="gpt-4",
                ),
                "anthropic": AnthropicConfig(
                    api_key="sk-test-anthropic",
                    default_model="claude-3-opus",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    config.save_config(test_config)
    ensure_default_roles()

    # Track which model was actually used
    models_used = []

    def mock_completion_with_model_check(**kwargs):
        model = kwargs.get("model", "")
        models_used.append(model)
        return mock_llm_text_only(**kwargs)

    with (
        patch("litellm.completion", side_effect=mock_completion_with_model_check),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Run CLI with --provider anthropic AND --model claude-3-sonnet
        # Should use claude-3-sonnet (CLI override), not claude-3-opus (provider default)
        result = runner.invoke(
            app, ["test query", "--provider", "anthropic", "--model", "claude-3-sonnet", "--no-context"]
        )

        assert result.exit_code == 0
        # Verify that claude-3-sonnet was used (CLI override), not claude-3-opus (provider default)
        assert len(models_used) > 0
        assert any("claude-3-sonnet" in model.lower() or "claude_3_sonnet" in model.lower() for model in models_used)
        # Should NOT use claude-3-opus (provider default)
        assert not any("claude-3-opus" in model.lower() or "claude_3_opus" in model.lower() for model in models_used)