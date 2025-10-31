"""Tests for config module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from whai import config


def test_get_config_dir_windows():
    """Test config directory on Windows."""
    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"APPDATA": "C:\\Users\\Test\\AppData\\Roaming"}),
    ):
        config_dir = config.get_config_dir()
        assert config_dir == Path("C:\\Users\\Test\\AppData\\Roaming") / "whai"


def test_get_config_dir_unix():
    """Test config directory on Unix-like systems."""
    # On Windows, we can't properly test Unix paths, so skip this test
    import sys

    if sys.platform == "win32":
        pytest.skip("Unix path test not applicable on Windows")

    with (
        patch("os.name", "posix"),
        patch.dict("os.environ", {"XDG_CONFIG_HOME": "/home/test/.config"}),
    ):
        config_dir = config.get_config_dir()
        assert config_dir == Path("/home/test/.config") / "whai"


# Removed test_get_default_config - no longer needed as default config is not part of main codebase


def test_load_config_missing_raises_error(tmp_path, monkeypatch):
    """Test that load_config raises MissingConfigError if config doesn't exist."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Load config without ephemeral mode should raise
    with pytest.raises(config.MissingConfigError, match="Configuration file not found"):
        config.load_config()


def test_load_config_ephemeral_mode(tmp_path, monkeypatch):
    """Test that load_config returns default config in ephemeral mode."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Load config with ephemeral mode should return defaults
    cfg = config.load_config(allow_ephemeral=True)

    # Check that config file was NOT created
    config_file = tmp_path / "config.toml"
    assert not config_file.exists()

    # Check that config has expected structure
    assert "llm" in cfg
    assert cfg["llm"]["default_provider"] == "openai"


def test_load_config_test_mode_env(tmp_path, monkeypatch):
    """Test that load_config respects WHAI_TEST_MODE environment variable."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    monkeypatch.setenv("WHAI_TEST_MODE", "1")

    # Load config should return defaults due to env var
    cfg = config.load_config()

    # Check that config file was NOT created
    config_file = tmp_path / "config.toml"
    assert not config_file.exists()

    # Check that config has expected structure
    assert "llm" in cfg
    assert cfg["llm"]["default_provider"] == "openai"


def test_load_config_reads_existing(tmp_path, monkeypatch):
    """Test that load_config reads an existing config file."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Create a custom config
    tmp_path.mkdir(parents=True, exist_ok=True)
    config_file = tmp_path / "config.toml"
    config_file.write_text("""
[llm]
default_provider = "anthropic"
default_model = "claude-3-sonnet"

[llm.anthropic]
api_key = "test-key-123"
""")

    # Load config
    cfg = config.load_config()

    # Verify it loaded correctly
    assert cfg["llm"]["default_provider"] == "anthropic"
    assert cfg["llm"]["default_model"] == "claude-3-sonnet"
    assert cfg["llm"]["anthropic"]["api_key"] == "test-key-123"


def test_parse_role_file_with_frontmatter():
    """Test parsing a role file with YAML frontmatter."""
    content = """---
model: gpt-5-mini
temperature: 0.7
---

This is the system prompt.
It can have multiple lines.
"""

    metadata, body = config.parse_role_file(content)

    assert metadata["model"] == "gpt-5-mini"
    assert metadata["temperature"] == 0.7
    assert "This is the system prompt." in body
    assert "multiple lines" in body


def test_parse_role_file_without_frontmatter():
    """Test parsing a role file without frontmatter."""
    content = "Just a simple prompt without frontmatter."

    metadata, body = config.parse_role_file(content)

    assert metadata == {}
    assert body == content


def test_parse_role_file_invalid_frontmatter():
    """Test that invalid frontmatter raises ValueError."""
    content = """---
invalid: yaml: syntax: here
---

Body text.
"""

    with pytest.raises(ValueError, match="Invalid YAML"):
        config.parse_role_file(content)


def test_parse_role_file_incomplete_frontmatter():
    """Test that incomplete frontmatter raises ValueError."""
    content = """---
model: gpt-5-mini
No closing delimiter"""

    with pytest.raises(ValueError, match="Invalid frontmatter format"):
        config.parse_role_file(content)


def test_ensure_default_roles(tmp_path, monkeypatch):
    """Test that default roles are created."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Ensure default roles
    config.ensure_default_roles()

    # Check that roles were created
    default_role = tmp_path / "roles" / "default.md"
    assert default_role.exists()

    # Check content
    default_content = default_role.read_text()
    assert "helpful terminal assistant" in default_content
    assert "execute_shell" in default_content


def test_load_role_default(tmp_path, monkeypatch):
    """Test loading the default role."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Load the default role
    metadata, prompt = config.load_role("default")

    # Verify metadata is empty by default (defaults do not include frontmatter)
    assert metadata == {}

    # Verify prompt
    assert "terminal assistant" in prompt.lower()


def test_load_role_custom(tmp_path, monkeypatch):
    """Test loading a custom role."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Create a custom role
    roles_dir = tmp_path / "roles"
    roles_dir.mkdir(parents=True, exist_ok=True)
    custom_role = roles_dir / "custom.md"
    custom_role.write_text("""---
model: gpt-3.5-turbo
temperature: 0.9
---

You are a custom assistant.
""")

    # Load the custom role
    metadata, prompt = config.load_role("custom")

    # Verify metadata
    assert metadata["model"] == "gpt-3.5-turbo"
    assert metadata["temperature"] == 0.9

    # Verify prompt
    assert "custom assistant" in prompt.lower()


def test_load_role_not_found(tmp_path, monkeypatch):
    """Test that loading a non-existent role raises FileNotFoundError."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Ensure default roles exist
    config.ensure_default_roles()

    # Try to load a role that doesn't exist
    with pytest.raises(FileNotFoundError, match="Role 'nonexistent' not found"):
        config.load_role("nonexistent")


def test_save_config(tmp_path, monkeypatch):
    """Test saving configuration to file."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Create a config
    test_config = {
        "llm": {
            "default_provider": "anthropic",
            "default_model": "claude-3-opus",
            "anthropic": {
                "api_key": "sk-test-123",
                "default_model": "claude-3-opus",
            },
        }
    }

    # Save it
    config.save_config(test_config)

    # Verify file was created
    config_file = tmp_path / "config.toml"
    assert config_file.exists()

    # Load it back and verify
    loaded = config.load_config()
    assert loaded["llm"]["default_provider"] == "anthropic"
    assert loaded["llm"]["anthropic"]["api_key"] == "sk-test-123"


def test_summarize_config():
    """Test config summarization."""
    test_config = {
        "llm": {
            "default_provider": "openai",
            "default_model": "gpt-4",
            "openai": {
                "api_key": "sk-verylongapikey123456",
                "default_model": "gpt-4",
            },
            "anthropic": {
                "api_key": "sk-ant-short",
                "default_model": "claude-3-opus",
            },
        }
    }

    summary = config.summarize_config(test_config)

    # Check summary contains expected elements
    assert "Default provider: openai" in summary
    assert "Default model: gpt-4" in summary
    assert "openai" in summary
    assert "anthropic" in summary
    # Check that API keys are masked
    assert "sk-veryl..." in summary
    assert "sk-verylongapikey123456" not in summary


def test_get_config_path(tmp_path, monkeypatch):
    """Test get_config_path returns correct path."""
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    config_path = config.get_config_path()
    assert config_path == tmp_path / "config.toml"
