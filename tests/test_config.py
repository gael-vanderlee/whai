"""Tests for config module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from terma import config


def test_get_config_dir_windows():
    """Test config directory on Windows."""
    with (
        patch("os.name", "nt"),
        patch.dict("os.environ", {"APPDATA": "C:\\Users\\Test\\AppData\\Roaming"}),
    ):
        config_dir = config.get_config_dir()
        assert config_dir == Path("C:\\Users\\Test\\AppData\\Roaming") / "terma"


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
        assert config_dir == Path("/home/test/.config") / "terma"


def test_get_default_config():
    """Test that default config is valid TOML."""
    default_config = config.get_default_config()
    assert "[llm]" in default_config
    assert "default_provider" in default_config
    assert "api_key" in default_config


def test_load_config_creates_default(tmp_path, monkeypatch):
    """Test that load_config creates a default config if it doesn't exist."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Load config (should create default)
    cfg = config.load_config()

    # Check that config file was created
    config_file = tmp_path / "config.toml"
    assert config_file.exists()

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
    assistant_role = tmp_path / "roles" / "assistant.md"
    debug_role = tmp_path / "roles" / "debug.md"

    assert assistant_role.exists()
    assert debug_role.exists()

    # Check content
    assistant_content = assistant_role.read_text()
    assert "helpful terminal assistant" in assistant_content
    assert "execute_shell" in assistant_content


def test_load_role_default(tmp_path, monkeypatch):
    """Test loading the default assistant role."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Load the default role
    metadata, prompt = config.load_role("assistant")

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
