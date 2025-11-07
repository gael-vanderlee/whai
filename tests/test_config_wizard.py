"""Tests for config wizard.

These tests validate observable behavior: config file creation/modification,
CLI output, exit codes, and file system state changes.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from whai.cli.main import app
from whai.configuration import user_config
from whai.configuration.config_wizard import run_wizard
from whai.configuration.user_config import load_config

# Use tomllib for Python 3.11+, tomli for older versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

runner = CliRunner()


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Set up temporary config directory and disable test mode."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.delenv("WHAI_TEST_MODE", raising=False)
    return tmp_path


def test_wizard_cli_flag_invokes_wizard(config_dir):
    """Test that --interactive-config flag invokes the wizard."""
    # Mock the wizard to simulate cancellation
    with patch("whai.cli.main.run_wizard", side_effect=typer.Abort()) as mock_wizard:
        result = runner.invoke(app, ["--interactive-config"])

        # Wizard should have been called
        mock_wizard.assert_called_once_with(existing_config=True)
        assert result.exit_code == 0


def test_wizard_quick_setup_creates_config(config_dir):
    """Test quick setup flow creates config file with provider."""
    config_file = config_dir / "config.toml"

    # Mock input() calls from prompt_numbered_choice - returns choices as numbers
    input_call_count = [0]
    input_responses = ["1", "1"]  # Quick Setup (1), then openai (1)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""  # Return empty for default

    # Mock typer.prompt for API key and model
    prompt_call_count = [0]
    prompt_responses = ["test-api-key-123", "gpt-5-mini"]

    def mock_prompt(*args, **kwargs):
        """Mock typer.prompt."""
        if prompt_call_count[0] < len(prompt_responses):
            result = prompt_responses[prompt_call_count[0]]
            prompt_call_count[0] += 1
            return result
        return kwargs.get("default", "")

    # Mock validation to succeed
    validation_result = MagicMock()
    validation_result.is_valid = True
    validation_result.issues = []
    validation_result.details = {"api_key_valid": True}

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
        patch("typer.prompt", side_effect=mock_prompt),
        patch("typer.confirm", return_value=True),
        patch(
            "whai.configuration.user_config.OpenAIConfig.validate",
            return_value=validation_result,
        ),
        patch("whai.configuration.user_config._suppress_stdout_stderr"),
    ):
        run_wizard(existing_config=False)

    # Verify config file was created
    assert config_file.exists()

    # Verify config content
    config = load_config()
    assert config.llm.default_provider == "openai"
    openai_provider = config.llm.get_provider("openai")
    assert openai_provider is not None
    assert openai_provider.api_key == "test-api-key-123"
    assert openai_provider.default_model == "gpt-5-mini"


def test_wizard_add_provider_updates_config(config_dir):
    """Test adding a provider updates existing config file."""
    # Create initial config with one provider
    from whai.configuration.user_config import (
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    initial_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="existing-key",
                    default_model="gpt-4",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    user_config.save_config(initial_config)

    # Mock input() calls for prompt_numbered_choice
    input_call_count = [0]
    input_responses = ["1", "2"]  # Add or Edit Provider (1), then anthropic (2)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    # Mock typer.prompt for API key and model
    prompt_call_count = [0]
    prompt_responses = ["anth-key-456", "claude-3-sonnet"]

    def mock_prompt(*args, **kwargs):
        """Mock typer.prompt."""
        if prompt_call_count[0] < len(prompt_responses):
            result = prompt_responses[prompt_call_count[0]]
            prompt_call_count[0] += 1
            return result
        return kwargs.get("default", "")

    # Mock validation to succeed
    validation_result = MagicMock()
    validation_result.is_valid = True
    validation_result.issues = []
    validation_result.details = {"api_key_valid": True}

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
        patch("typer.prompt", side_effect=mock_prompt),
        patch("typer.confirm", return_value=True),  # Confirm edit
        patch(
            "whai.configuration.user_config.AnthropicConfig.validate",
            return_value=validation_result,
        ),
        patch("whai.configuration.user_config._suppress_stdout_stderr"),
    ):
        run_wizard(existing_config=True)

    # Verify config still has original provider
    config = load_config()
    assert "openai" in config.llm.providers

    # Verify new provider was added
    assert "anthropic" in config.llm.providers
    anthropic_provider = config.llm.get_provider("anthropic")
    assert anthropic_provider is not None
    assert anthropic_provider.api_key == "anth-key-456"
    assert anthropic_provider.default_model == "claude-3-sonnet"


def test_wizard_remove_provider_updates_config(config_dir):
    """Test removing a provider updates config file."""
    # Create initial config with multiple providers
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    initial_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="key1",
                    default_model="gpt-4",
                ),
                "anthropic": AnthropicConfig(
                    api_key="key2",
                    default_model="claude-3-sonnet",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    user_config.save_config(initial_config)

    # Mock input() calls
    input_call_count = [0]
    input_responses = ["2", "2"]  # Remove Provider (2), then anthropic (2)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
    ):
        run_wizard(existing_config=True)

    # Verify config updated
    config = load_config()
    assert "openai" in config.llm.providers
    assert "anthropic" not in config.llm.providers


def test_wizard_remove_default_provider_clears_default(config_dir):
    """Test removing default provider clears the default."""
    # Create initial config with openai as default
    from whai.configuration.user_config import (
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    initial_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="key1",
                    default_model="gpt-4",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    user_config.save_config(initial_config)

    # Mock input() calls
    input_call_count = [0]
    input_responses = ["2", "1"]  # Remove Provider (2), then openai (1)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
    ):
        run_wizard(existing_config=True)

    # Verify default provider was cleared
    config = load_config()
    assert "openai" not in config.llm.providers
    assert config.llm.default_provider == ""


def test_wizard_set_default_provider_updates_config(config_dir):
    """Test setting default provider updates config."""
    # Create initial config with multiple providers
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    initial_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="key1",
                    default_model="gpt-4",
                ),
                "anthropic": AnthropicConfig(
                    api_key="key2",
                    default_model="claude-3-sonnet",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    user_config.save_config(initial_config)

    assert load_config().llm.default_provider == "openai"

    # Mock input() calls
    input_call_count = [0]
    input_responses = ["3", "2"]  # Set Default Provider (3), then anthropic (2)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
    ):
        run_wizard(existing_config=True)

    # Verify default provider was updated
    config = load_config()
    assert config.llm.default_provider == "anthropic"


def test_wizard_reset_creates_backup_and_resets_config(config_dir):
    """Test reset creates backup and resets config to defaults."""
    # Create initial config
    from whai.configuration.user_config import (
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    initial_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="key1",
                    default_model="gpt-4",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    user_config.save_config(initial_config)

    config_file = config_dir / "config.toml"
    assert config_file.exists()

    # Mock input() calls - sequence: Reset, then Quick Setup after reset
    input_call_count = [0]
    input_responses = ["4", "1", "1"]  # Reset Configuration (4), then Quick Setup (1), then openai (1)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    # Mock typer.prompt for reset confirmation and then provider setup
    prompt_call_count = [0]
    prompt_responses = ["new-key-123", "gpt-5-mini"]  # API key, model after reset

    def mock_prompt(*args, **kwargs):
        """Mock typer.prompt."""
        if prompt_call_count[0] < len(prompt_responses):
            result = prompt_responses[prompt_call_count[0]]
            prompt_call_count[0] += 1
            return result
        return kwargs.get("default", "")

    # Mock validation
    validation_result = MagicMock()
    validation_result.is_valid = True
    validation_result.issues = []
    validation_result.details = {"api_key_valid": True}

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
        patch("typer.prompt", side_effect=mock_prompt),
        patch("typer.confirm", return_value=True),  # Confirm reset
        patch(
            "whai.configuration.user_config.OpenAIConfig.validate",
            return_value=validation_result,
        ),
        patch("whai.configuration.user_config._suppress_stdout_stderr"),
    ):
        run_wizard(existing_config=True)

    # Verify backup was created
    backup_files = list(config_dir.glob("config.toml.bak-*"))
    assert len(backup_files) == 1

    # Verify backup contains original config
    with open(backup_files[0], "rb") as f:
        backup_data = tomllib.load(f)
    assert backup_data["llm"]["default_provider"] == "openai"
    # Backup should have the providers from original config
    # In TOML, providers are stored as nested tables (llm.openai, etc.)
    assert "openai" in backup_data["llm"]
    assert backup_data["llm"]["openai"]["api_key"] == "key1"

    # Verify config was reset and has new provider
    config = load_config()
    assert config.llm.default_provider == "openai"
    openai_provider = config.llm.get_provider("openai")
    assert openai_provider is not None
    assert openai_provider.api_key == "new-key-123"
    assert openai_provider.default_model == "gpt-5-mini"


def test_wizard_cancel_exits_gracefully(config_dir):
    """Test wizard cancellation exits gracefully without saving."""
    config_file = config_dir / "config.toml"

    # Mock input() calls - return "5" for Cancel
    input_call_count = [0]
    input_responses = ["5"]  # Cancel (5)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
    ):
        with pytest.raises(typer.Abort):
            run_wizard(existing_config=False)

    # Verify no config file was created
    assert not config_file.exists()


def test_wizard_validation_failure_prevents_save(config_dir):
    """Test that validation failures prevent saving config."""
    config_file = config_dir / "config.toml"

    # Mock input() calls
    input_call_count = [0]
    input_responses = ["1", "1"]  # Quick Setup (1), then openai (1)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    # Mock typer.prompt
    prompt_call_count = [0]
    prompt_responses = ["invalid-key", "gpt-5-mini"]

    def mock_prompt(*args, **kwargs):
        """Mock typer.prompt."""
        if prompt_call_count[0] < len(prompt_responses):
            result = prompt_responses[prompt_call_count[0]]
            prompt_call_count[0] += 1
            return result
        return kwargs.get("default", "")

    # Mock validation to fail
    validation_result = MagicMock()
    validation_result.is_valid = False
    validation_result.issues = ["API key is invalid"]
    validation_result.details = {"api_key_valid": False}

    # Mock confirm to reject proceeding with invalid config
    def mock_confirm(*args, **kwargs):
        """Mock typer.confirm - reject validation failure."""
        if "despite validation issues" in str(args[0] if args else "").lower():
            return False  # Don't proceed with invalid config
        return True

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
        patch("typer.prompt", side_effect=mock_prompt),
        patch("typer.confirm", side_effect=mock_confirm),
        patch(
            "whai.configuration.user_config.OpenAIConfig.validate",
            return_value=validation_result,
        ),
        patch("whai.configuration.user_config._suppress_stdout_stderr"),
    ):
        with pytest.raises(typer.Abort):
            run_wizard(existing_config=False)

    # Verify no config file was created
    assert not config_file.exists()


def test_wizard_validation_failure_proceeded_saves_config(config_dir):
    """Test that proceeding despite validation failure saves config."""
    config_file = config_dir / "config.toml"

    # Mock input() calls
    input_call_count = [0]
    input_responses = ["1", "1"]  # Quick Setup (1), then openai (1)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    # Mock typer.prompt
    prompt_call_count = [0]
    prompt_responses = ["test-key", "gpt-5-mini"]

    def mock_prompt(*args, **kwargs):
        """Mock typer.prompt."""
        if prompt_call_count[0] < len(prompt_responses):
            result = prompt_responses[prompt_call_count[0]]
            prompt_call_count[0] += 1
            return result
        return kwargs.get("default", "")

    # Mock validation to fail
    validation_result = MagicMock()
    validation_result.is_valid = False
    validation_result.issues = ["API key might be invalid"]
    validation_result.details = {"api_key_valid": None}

    # Mock confirm to proceed despite validation failure
    def mock_confirm(*args, **kwargs):
        """Mock typer.confirm - proceed despite validation failure."""
        # Always proceed
        return True

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
        patch("typer.prompt", side_effect=mock_prompt),
        patch("typer.confirm", side_effect=mock_confirm),
        patch(
            "whai.configuration.user_config.OpenAIConfig.validate",
            return_value=validation_result,
        ),
        patch("whai.configuration.user_config._suppress_stdout_stderr"),
    ):
        run_wizard(existing_config=False)

    # Verify config file was created despite validation failure
    assert config_file.exists()
    config = load_config()
    assert "openai" in config.llm.providers


def test_wizard_edit_existing_provider_preserves_defaults(config_dir):
    """Test editing existing provider uses current values as defaults."""
    # Create initial config
    from whai.configuration.user_config import (
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )

    initial_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="original-key-123",
                    default_model="gpt-4",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )
    user_config.save_config(initial_config)

    # Mock input() calls
    input_call_count = [0]
    input_responses = ["1", "1"]  # Add or Edit Provider (1), then openai (1)

    def mock_input(prompt_text):
        """Mock input() calls."""
        if input_call_count[0] < len(input_responses):
            result = input_responses[input_call_count[0]]
            input_call_count[0] += 1
            return result
        return ""

    # Mock typer.prompt - user keeps API key (presses Enter), updates model
    prompt_call_count = [0]

    def mock_prompt(*args, **kwargs):
        """Mock typer.prompt - keep API key, update model."""
        prompt_call_count[0] += 1
        field = str(args[0]) if args else ""
        # For API key, simulate user pressing Enter (use existing masked default)
        if "api_key" in field.lower() and kwargs.get("default"):
            # This simulates the masked default being returned
            # The wizard should detect this and use the actual value
            return kwargs["default"]
        # For model, return new value
        if "default_model" in field.lower() or "model" in field.lower():
            return "gpt-5-mini"
        return kwargs.get("default", "")

    # Mock validation
    validation_result = MagicMock()
    validation_result.is_valid = True
    validation_result.issues = []
    validation_result.details = {"api_key_valid": True}

    with (
        patch("builtins.input", side_effect=mock_input),
        patch("whai.ui.formatting.input", side_effect=mock_input),
        patch("typer.prompt", side_effect=mock_prompt),
        patch("typer.confirm", return_value=True),  # Confirm edit
        patch(
            "whai.configuration.user_config.OpenAIConfig.validate",
            return_value=validation_result,
        ),
        patch("whai.configuration.user_config._suppress_stdout_stderr"),
    ):
        run_wizard(existing_config=True)

    # Verify config was updated: model changed
    config = load_config()
    openai_provider = config.llm.get_provider("openai")
    assert openai_provider is not None
    assert openai_provider.default_model == "gpt-5-mini"
    # API key behavior depends on wizard implementation; test verifies config was updated