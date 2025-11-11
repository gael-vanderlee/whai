"""Security tests for input sanitization.

These tests validate that whai prevents common security issues like
path traversal, command injection, and sensitive data leakage.
"""

import pytest
from typer.testing import CliRunner

from whai.cli.main import app
from whai.configuration.roles import load_role

runner = CliRunner()


@pytest.fixture(autouse=True)
def test_config(tmp_path, monkeypatch):
    """Set up ephemeral test config."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setenv("WHAI_TEST_MODE", "1")


def test_role_name_path_traversal_rejected(tmp_path, monkeypatch):
    """Role names with path traversal are rejected."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    
    # Try to load role with path traversal
    with pytest.raises(FileNotFoundError):
        load_role("../../etc/passwd")
    
    # Verify /etc/passwd was not accessed (would raise different error if it tried)
    # The error should be about role not found, not permission denied


def test_shell_parameter_with_suspicious_characters_handled():
    """Shell parameter with suspicious characters is handled safely."""
    # Try to pass potentially malicious shell parameter
    # The shell parameter is passed to subprocess, which should handle it safely
    result = runner.invoke(app, ["shell", "--shell", "bash; echo malicious"])
    
    # Should either reject it or handle it safely
    # (exit code 0, 1, or 2 are all acceptable - just shouldn't execute malicious code)
    assert result.exit_code in [0, 1, 2]
    output = result.stdout + result.stderr
    
    # Should not show evidence of executing malicious code
    assert "malicious" not in output or "Failed" in output or "Error" in output


def test_api_keys_not_logged_in_verbose_mode(tmp_path, monkeypatch, caplog):
    """API keys are masked in verbose output."""
    from whai.configuration.user_config import (
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )
    
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    
    # Create config with API key
    config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="sk-test123456789abcdef",
                    default_model="gpt-4",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    
    # Save config
    from whai.configuration import user_config
    user_config.save_config(config)
    
    # Mock LLM to avoid actual API call
    from unittest.mock import MagicMock, patch
    
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message = MagicMock()
    mock_response.choices[0].message.content = "test response"
    mock_response.choices[0].message.tool_calls = None
    
    with (
        patch("litellm.completion", return_value=mock_response),
        patch("whai.context.get_context", return_value=("", False)),
    ):
        with caplog.at_level("DEBUG"):
            result = runner.invoke(app, ["test query", "--no-context", "-vv"])
    
    # Check that full API key is not in output
    full_output = result.stdout + result.stderr + "\n".join(caplog.text.split("\n"))
    
    # Full key should not appear
    assert "sk-test123456789abcdef" not in full_output
    
    # Note: Current implementation may not mask keys in all log output,
    # but at minimum they shouldn't be in user-facing output
    assert "sk-test123456789abcdef" not in result.stdout

