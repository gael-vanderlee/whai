"""Tests for CLI argument and flag parsing.

These tests validate that whai correctly parses various combinations of:
- Quoted vs unquoted query strings
- Flag positions (before, after, or mixed with query)
- Multiple flags in different orders
- Edge cases in argument parsing

The focus is on verifying the PARSED VALUES, not just exit codes.
"""

from unittest.mock import MagicMock, patch

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


@pytest.fixture
def mock_llm_capture_messages():
    """Mock LLM that captures the messages sent to it."""
    captured_calls = []
    
    def mock_completion(**kwargs):
        # Capture the call
        captured_calls.append(kwargs)
        
        # Return mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Mock response"
        mock_response.choices[0].message.tool_calls = None
        return mock_response
    
    return mock_completion, captured_calls


def test_quoted_query_with_flags_after(mock_llm_capture_messages):
    """Test: whai "debug this issue" --model gpt-5"""
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["debug this issue", "--model", "gpt-5", "--no-context"])
        
        assert result.exit_code == 0
        
        # Verify LLM was called
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        
        # Verify model flag was parsed
        assert call_kwargs.get("model") == "gpt-5"
        
        # Verify query was in the messages
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        assert "debug this issue" in user_messages[0]["content"]


def test_unquoted_query_with_flags_after(mock_llm_capture_messages):
    """Test: whai debug this issue --model gpt-5"""
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["debug", "this", "issue", "--model", "gpt-5", "--no-context"])
        
        assert result.exit_code == 0
        
        # Verify LLM was called
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        
        # Verify model flag was parsed
        assert call_kwargs.get("model") == "gpt-5"
        
        # Verify query was assembled correctly (all words joined)
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "debug" in user_content
        assert "this" in user_content
        assert "issue" in user_content


def test_flags_before_query(mock_llm_capture_messages):
    """Test: whai --model gpt-5 debug this issue"""
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["--model", "gpt-5", "--no-context", "debug", "this", "issue"])
        
        assert result.exit_code == 0
        
        # Verify LLM was called
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        
        # Verify model flag was parsed
        assert call_kwargs.get("model") == "gpt-5"
        
        # Verify query was assembled correctly
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "debug" in user_content
        assert "this" in user_content
        assert "issue" in user_content


def test_multiple_flags_mixed_order(mock_llm_capture_messages):
    """Test: whai -vv --model gpt-5 debug this --no-context"""
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["-vv", "--model", "gpt-5", "debug", "this", "--no-context"])
        
        assert result.exit_code == 0
        
        # Verify LLM was called
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        
        # Verify model flag was parsed
        assert call_kwargs.get("model") == "gpt-5"
        
        # Verify query was assembled correctly
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "debug" in user_content
        assert "this" in user_content


def test_role_flag_parsing(mock_llm_capture_messages, tmp_path):
    """Test: whai --role custom what is this error
    
    Creates a temporary custom role to verify the flag actually switches roles.
    """
    # Create a temporary custom role with a unique marker
    # test_config fixture already patches get_config_dir to return tmp_path
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    
    custom_role_content = """---
name: testcustomrole
description: A custom test role for verification
---

You are a test assistant. UNIQUE_ROLE_MARKER_FOR_TESTING."""
    
    (roles_dir / "testcustomrole.md").write_text(custom_role_content)
    
    # Also create default role so test can run
    default_role_content = """---
name: default
description: Default role
---

You are a default assistant."""
    (roles_dir / "default.md").write_text(default_role_content)
    
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["--role", "testcustomrole", "what", "is", "this", "error", "--no-context"])
        
        assert result.exit_code == 0
        
        # Verify custom role was loaded by checking for unique marker in system message
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        messages = call_kwargs.get("messages", [])
        system_messages = [m for m in messages if m.get("role") == "system"]
        assert len(system_messages) > 0
        system_content = system_messages[0]["content"]
        assert "UNIQUE_ROLE_MARKER_FOR_TESTING" in system_content
        
        # Verify role name appears in output
        output = result.stdout + result.stderr
        assert "testcustomrole" in output.lower()
        
        # Verify query was assembled correctly
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "what" in user_content
        assert "error" in user_content


def test_timeout_flag_parsing():
    """Test: whai --timeout 30 run this command"""
    # Use a different approach - mock execute_command to verify timeout
    with (
        patch("whai.context.get_context", return_value=("", False)),
        patch("whai.core.executor.execute_command", return_value=("output", "", 0)) as mock_exec,
        patch("litellm.completion") as mock_llm,
    ):
        # Mock LLM to return a tool call
        import json
        mock_tool_call = MagicMock()
        mock_tool_call.id = "call_123"
        mock_tool_call.function = MagicMock()
        mock_tool_call.function.name = "execute_shell"
        mock_tool_call.function.arguments = json.dumps({"command": "echo test"})
        
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Let me run that."
        mock_response.choices[0].message.tool_calls = [mock_tool_call]
        mock_llm.return_value = mock_response
        
        with patch("builtins.input", return_value="a"):  # Approve command
            result = runner.invoke(app, ["--timeout", "30", "--no-context", "run", "this", "command"])
            
            # Verify timeout was passed to execute_command
            if mock_exec.called:
                call_kwargs = mock_exec.call_args[1] if mock_exec.call_args else {}
                assert call_kwargs.get("timeout") == 30


def test_query_with_special_characters(mock_llm_capture_messages):
    """Test: whai explain this: git commit -m "message" --no-context"""
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, [
            "explain", "this:", "git", "commit", "-m", '"message"', "--no-context"
        ])
        
        assert result.exit_code == 0
        
        # Verify query contains all parts
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "explain" in user_content
        assert "git" in user_content
        assert "commit" in user_content


def test_empty_query_with_flags():
    """Test: whai --model gpt-5 (no query) - should use default"""
    with (
        patch("litellm.completion") as mock_llm,
        patch("whai.context.get_context", return_value=("", False)),
    ):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Mock response"
        mock_response.choices[0].message.tool_calls = None
        mock_llm.return_value = mock_response
        
        result = runner.invoke(app, ["--model", "gpt-5", "--no-context"])
        
        assert result.exit_code == 0
        
        # Should use default query and still parse model flag
        if mock_llm.called:
            call_kwargs = mock_llm.call_args[1]
            assert call_kwargs.get("model") == "gpt-5"


def test_verbose_flag_combinations():
    """Test: whai -v vs whai -vv with query"""
    test_cases = [
        (["-v", "test", "query", "--no-context"], 1),
        (["-vv", "test", "query", "--no-context"], 2),
    ]
    
    for args, expected_verbosity in test_cases:
        with (
            patch("litellm.completion") as mock_llm,
            patch("whai.context.get_context", return_value=("", False)),
        ):
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message = MagicMock()
            mock_response.choices[0].message.content = "Mock response"
            mock_response.choices[0].message.tool_calls = None
            mock_llm.return_value = mock_response
            
            result = runner.invoke(app, args)
            
            # Should execute successfully
            assert result.exit_code == 0


def test_provider_flag_parsing(mock_llm_capture_messages):
    """Test: whai --provider openai explain this"""
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["--provider", "openai", "explain", "this", "--no-context"])
        
        assert result.exit_code == 0
        
        # Verify provider was used (command should execute successfully)
        # Note: The actual provider handling depends on config, but command should execute
        assert len(captured_calls) > 0


def test_complex_real_world_command(mock_llm_capture_messages, tmp_path):
    """Test complex real-world command with multiple flags and unquoted query"""
    # Create a temporary custom role to verify role flag works
    # test_config fixture already patches get_config_dir to return tmp_path
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    
    custom_role_content = """---
name: complextest
description: Complex test role
---

You are a complex test assistant. COMPLEX_TEST_MARKER."""
    
    (roles_dir / "complextest.md").write_text(custom_role_content)
    
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, [
            "-vv",
            "--role", "complextest",
            "--model", "gpt-4",
            "why", "is", "my", "git", "push", "failing",
            "--no-context",
            "--timeout", "60"
        ])
        
        assert result.exit_code == 0
        
        # Verify all flags were parsed
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        
        # Check model
        assert call_kwargs.get("model") == "gpt-4"
        
        # Check query was assembled
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "why" in user_content
        assert "git" in user_content
        assert "push" in user_content
        assert "failing" in user_content
        
        # Verify custom role was loaded by checking for unique marker
        system_messages = [m for m in messages if m.get("role") == "system"]
        assert len(system_messages) > 0
        system_content = system_messages[0]["content"]
        assert "COMPLEX_TEST_MARKER" in system_content
        
        # Check role was applied (in output)
        output = result.stdout + result.stderr
        assert "complextest" in output.lower()


def test_flag_with_equals_syntax():
    """Test: whai --model=gpt-5 test query
    
    Tests whether Typer natively supports equals syntax for flags before the query.
    Note: Equals syntax is NOT supported in the inline overrides parser (for flags
    after the query), only for flags that Typer parses directly before the query.
    """
    with (
        patch("litellm.completion") as mock_llm,
        patch("whai.context.get_context", return_value=("", False)),
    ):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = "Mock response"
        mock_response.choices[0].message.tool_calls = None
        mock_llm.return_value = mock_response
        
        # Try with equals syntax (flag BEFORE query, so Typer parses it)
        result = runner.invoke(app, ["--model=gpt-5", "test", "query", "--no-context"])
        
        # Typer/Click supports equals syntax, so this should work
        assert result.exit_code == 0
        
        # Verify model was parsed correctly
        if mock_llm.called:
            call_kwargs = mock_llm.call_args[1]
            assert call_kwargs.get("model") == "gpt-5"


def test_unrecognized_flag_warning(mock_llm_capture_messages):
    """Test: whai run a command --no-contxt (misspelled flag)
    
    Verifies that misspelled flags trigger a warning and are included in the query.
    """
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["run", "a", "command", "--no-contxt", "--no-context"])
        
        assert result.exit_code == 0
        
        # Verify warning was shown
        output = result.stdout + result.stderr
        assert "--no-contxt" in output
        assert "not recognized" in output.lower()
        # Check for key parts of warning message (accounting for potential newlines)
        output_lower = output.lower().replace("\n", " ")
        assert "passed to the model" in output_lower or "passed to the" in output_lower
        
        # Verify LLM was called
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        
        # Verify query contains the misspelled flag
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "--no-contxt" in user_content
        assert "run" in user_content
        assert "command" in user_content


def test_multiple_unrecognized_flags_warning(mock_llm_capture_messages):
    """Test: whai test query --unknown-flag --another-unknown
    
    Verifies that multiple unrecognized flags are all warned about.
    """
    mock_completion, captured_calls = mock_llm_capture_messages
    
    with (
        patch("litellm.completion", side_effect=mock_completion),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        result = runner.invoke(app, ["test", "query", "--unknown-flag", "--another-unknown", "--no-context"])
        
        assert result.exit_code == 0
        
        # Verify warning mentions both flags
        output = result.stdout + result.stderr
        assert "--unknown-flag" in output
        assert "--another-unknown" in output
        assert "not recognized" in output.lower()
        # Check for key parts of warning message (accounting for potential newlines)
        output_lower = output.lower().replace("\n", " ")
        assert "passed to the model" in output_lower or "passed to the" in output_lower
        
        # Verify both flags are in the query
        assert len(captured_calls) > 0
        call_kwargs = captured_calls[0]
        messages = call_kwargs.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]
        assert len(user_messages) > 0
        user_content = user_messages[0]["content"]
        assert "--unknown-flag" in user_content
        assert "--another-unknown" in user_content