"""Tests for config module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from whai.configuration import user_config as config
from whai.configuration.roles import (
    InvalidRoleMetadataError,
    Role,
    ensure_default_roles,
    get_default_role,
    load_role,
)


def test_get_config_dir_windows():
    """Test config directory on Windows."""
    # On Linux, we can't properly test Windows paths, so skip this test
    import sys

    if sys.platform != "win32":
        pytest.skip("Windows path test not applicable on non-Windows platforms")

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

    # Disable test mode for this test
    monkeypatch.delenv("WHAI_TEST_MODE", raising=False)

    # Load config without ephemeral mode should raise
    with pytest.raises(config.MissingConfigError, match="Configuration file not found"):
        config.load_config()


def test_load_config_ephemeral_mode(tmp_path, monkeypatch):
    """Test that load_config returns default config in ephemeral mode."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Load config with ephemeral mode should return defaults
    cfg = config.load_config()

    # Check that config file was NOT created
    config_file = tmp_path / "config.toml"
    assert not config_file.exists()

    # Check that config has expected structure (dataclass)
    assert cfg.llm.default_provider == "openai"
    assert "openai" in cfg.llm.providers


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

    # Check that config has expected structure (dataclass)
    assert cfg.llm.default_provider == "openai"
    assert "openai" in cfg.llm.providers


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

[llm.anthropic]
api_key = "test-key-123"
default_model = "claude-3-sonnet"
""")

    # Load config
    cfg = config.load_config()

    # Verify it loaded correctly
    assert cfg.llm.default_provider == "anthropic"
    anthropic_cfg = cfg.llm.get_provider("anthropic")
    assert anthropic_cfg is not None
    assert anthropic_cfg.default_model == "claude-3-sonnet"
    assert anthropic_cfg.api_key == "test-key-123"


def test_parse_role_file_with_frontmatter():
    """Test parsing a role file with YAML frontmatter."""
    from whai.configuration.roles import Role

    content = """---
model: gpt-5-mini
temperature: 0.7
---

This is the system prompt.
It can have multiple lines.
"""

    role = Role.from_markdown("test", content)

    assert isinstance(role, Role)
    assert role.model == "gpt-5-mini"
    assert role.temperature == 0.7
    assert "This is the system prompt." in role.body
    assert "multiple lines" in role.body


def test_parse_role_file_without_frontmatter():
    """Test parsing a role file without frontmatter."""
    from whai.configuration.roles import Role

    content = "Just a simple prompt without frontmatter."

    role = Role.from_markdown("test", content)

    assert isinstance(role, Role)
    assert role.model is None
    assert role.temperature is None
    assert role.body == content


def test_parse_role_file_invalid_frontmatter():
    """Test that invalid frontmatter raises ValueError."""
    from whai.configuration.roles import Role

    content = """---
invalid: yaml: syntax: here
---

Body text.
"""

    with pytest.raises(ValueError, match="Invalid YAML"):
        Role.from_markdown("test", content)


def test_parse_role_file_incomplete_frontmatter():
    """Test that incomplete frontmatter raises ValueError."""
    from whai.configuration.roles import Role

    content = """---
model: gpt-5-mini
No closing delimiter"""

    with pytest.raises(ValueError, match="Invalid frontmatter format"):
        Role.from_markdown("test", content)


def test_ensure_default_roles(tmp_path, monkeypatch):
    """Test that default roles are created."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Ensure default roles
    ensure_default_roles()

    # Check that roles were created
    default_role = tmp_path / "roles" / "default.md"
    assert default_role.exists()

    # Check content matches the packaged default
    default_content = default_role.read_text()
    assert default_content == get_default_role("default")
    assert "execute_shell" in default_content


def test_load_role_default(tmp_path, monkeypatch):
    """Test loading the default role."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Load the default role
    role = load_role("default")

    # Verify role is Role with no values (defaults do not include frontmatter)
    assert isinstance(role, Role)
    assert role.model is None
    assert role.temperature is None

    # Verify prompt matches the packaged default (body is stripped, so strip the file content too)
    assert role.body == get_default_role("default").strip()


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
    role = load_role("custom")

    # Verify role
    assert isinstance(role, Role)
    assert role.model == "gpt-3.5-turbo"
    assert role.temperature == 0.9

    # Verify prompt
    assert "custom assistant" in role.body.lower()


def test_load_role_not_found(tmp_path, monkeypatch):
    """Test that loading a non-existent role raises FileNotFoundError."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Ensure default roles exist
    ensure_default_roles()

    # Try to load a role that doesn't exist
    with pytest.raises(FileNotFoundError, match="Role file not found"):
        load_role("nonexistent")


def test_role_metadata_validation_invalid_temperature():
    """Test that invalid temperature values raise InvalidRoleMetadataError."""
    with pytest.raises(
        InvalidRoleMetadataError, match="temperature.*between 0.0 and 2.0"
    ):
        Role(name="test", body="body", temperature=3.0)

    with pytest.raises(
        InvalidRoleMetadataError, match="temperature.*between 0.0 and 2.0"
    ):
        Role(name="test", body="body", temperature=-0.1)


def test_role_metadata_validation_invalid_model():
    """Test that invalid model values raise InvalidRoleMetadataError."""
    with pytest.raises(InvalidRoleMetadataError, match="model.*non-empty string"):
        Role(name="test", body="body", model="")

    with pytest.raises(InvalidRoleMetadataError, match="model.*non-empty string"):
        Role(name="test", body="body", model="   ")


def test_role_metadata_valid():
    """Test that valid metadata values are accepted."""
    metadata = Role(name="test", body="body", model="gpt-5-mini", temperature=0.7)
    assert metadata.model == "gpt-5-mini"
    assert metadata.temperature == 0.7

    # Test edge cases for temperature
    metadata_min = Role(name="test", body="body", temperature=0.0)
    assert metadata_min.temperature == 0.0

    metadata_max = Role(name="test", body="body", temperature=2.0)
    assert metadata_max.temperature == 2.0

    # Test None values
    metadata_none = Role(name="test", body="body")
    assert metadata_none.model is None
    assert metadata_none.temperature is None


def test_role_metadata_from_dict():
    """Test creating Role from dictionary."""
    data = {"model": "gpt-4", "temperature": 0.5}
    metadata = Role.from_dict("test", "body", data)
    assert metadata.model == "gpt-4"
    assert metadata.temperature == 0.5

    # Test with unknown fields (should warn but not fail)
    data_with_unknown = {"model": "gpt-4", "temperature": 0.5, "unknown": "value"}
    metadata_with_unknown = Role.from_dict("test", "body", data_with_unknown)
    assert metadata_with_unknown.model == "gpt-4"
    assert metadata_with_unknown.temperature == 0.5


def test_role_metadata_to_dict():
    """Test converting Role to markdown."""
    metadata = Role(name="test", body="body", model="gpt-4", temperature=0.5)
    result = metadata.to_markdown()
    assert "model: gpt-4" in result
    assert "temperature: 0.5" in result
    assert "body" in result

    # Test with None values (should not be in frontmatter)
    metadata_none = Role(name="test", body="body")
    result_none = metadata_none.to_markdown()
    assert result_none == "body"

    # Test with partial values
    metadata_partial = Role(name="test", body="body", model="gpt-4")
    result_partial = metadata_partial.to_markdown()
    assert "model: gpt-4" in result_partial
    assert "temperature" not in result_partial


def test_parse_role_file_invalid_metadata():
    """Test that invalid metadata in role file raises InvalidRoleMetadataError."""
    from whai.configuration.roles import InvalidRoleMetadataError, Role

    content = """---
model: 
temperature: 3.0
---

Body text.
"""

    with pytest.raises(InvalidRoleMetadataError):
        Role.from_markdown("test", content)


def test_save_config(tmp_path, monkeypatch):
    """Test saving configuration to file."""
    # Use a temporary directory as the config directory
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)

    # Create a config using dataclasses
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        RolesConfig,
        WhaiConfig,
    )

    test_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="anthropic",
            providers={
                "anthropic": AnthropicConfig(
                    api_key="sk-test-123",
                    default_model="claude-3-opus",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )

    # Save it
    config.save_config(test_config)

    # Verify file was created
    config_file = tmp_path / "config.toml"
    assert config_file.exists()

    # Load it back and verify
    loaded = config.load_config()
    assert loaded.llm.default_provider == "anthropic"
    anthropic_cfg = loaded.llm.get_provider("anthropic")
    assert anthropic_cfg is not None
    assert anthropic_cfg.api_key == "sk-test-123"


def test_summarize_config(capsys):
    """Test config summarization."""
    from whai.configuration.user_config import (
        AnthropicConfig,
        LLMConfig,
        OpenAIConfig,
        RolesConfig,
        WhaiConfig,
    )
    from whai.ui import print_configuration_summary

    test_config = WhaiConfig(
        llm=LLMConfig(
            default_provider="openai",
            providers={
                "openai": OpenAIConfig(
                    api_key="sk-verylongapikey123456",
                    default_model="gpt-4",
                ),
                "anthropic": AnthropicConfig(
                    api_key="sk-ant-short",
                    default_model="claude-3-opus",
                ),
            },
        ),
        roles=RolesConfig(default_role="default"),
    )

    print_configuration_summary(test_config)
    captured = capsys.readouterr()
    summary = captured.out

    # Check summary contains expected elements
    assert "Default provider: openai" in summary or "Default provider" in summary
    assert "Default model: gpt-4" in summary or "gpt-4" in summary
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


