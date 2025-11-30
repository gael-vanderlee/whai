"""Tests for MCP configuration dataclasses."""

import json
from pathlib import Path

import pytest

from whai.mcp.config import MCPConfig, MCPServerConfig, load_mcp_config


class TestMCPServerConfig:
    """Tests for MCPServerConfig dataclass."""

    def test_valid_config(self):
        """Test creating valid MCPServerConfig."""
        config = MCPServerConfig(
            command="echo",
            args=["test"],
            env={"KEY": "value"},
        )
        assert config.command == "echo"
        assert config.args == ["test"]
        assert config.env == {"KEY": "value"}

    def test_minimal_config(self):
        """Test creating MCPServerConfig with only required field."""
        config = MCPServerConfig(command="echo")
        assert config.command == "echo"
        assert config.args is None
        assert config.env is None

    def test_empty_command_raises_error(self):
        """Test that empty command raises ValueError."""
        with pytest.raises(ValueError, match="command.*must be a non-empty string"):
            MCPServerConfig(command="")

    def test_whitespace_command_raises_error(self):
        """Test that whitespace-only command raises ValueError."""
        with pytest.raises(ValueError, match="command.*must be a non-empty string"):
            MCPServerConfig(command="   ")

    def test_invalid_args_type_raises_error(self):
        """Test that non-list args raises ValueError."""
        with pytest.raises(ValueError, match="args.*must be a list"):
            MCPServerConfig(command="echo", args="not-a-list")

    def test_invalid_env_type_raises_error(self):
        """Test that non-dict env raises ValueError."""
        with pytest.raises(ValueError, match="env.*must be a dictionary"):
            MCPServerConfig(command="echo", env="not-a-dict")

    def test_to_dict(self):
        """Test serialization to dictionary."""
        config = MCPServerConfig(
            command="echo",
            args=["test"],
            env={"KEY": "value"},
        )
        result = config.to_dict()
        assert result == {
            "command": "echo",
            "args": ["test"],
            "env": {"KEY": "value"},
        }

    def test_to_dict_minimal(self):
        """Test serialization with only required fields."""
        config = MCPServerConfig(command="echo")
        result = config.to_dict()
        assert result == {"command": "echo"}

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "command": "echo",
            "args": ["test"],
            "env": {"KEY": "value"},
        }
        config = MCPServerConfig.from_dict(data)
        assert config.command == "echo"
        assert config.args == ["test"]
        assert config.env == {"KEY": "value"}

    def test_from_dict_minimal(self):
        """Test deserialization with only required fields."""
        data = {"command": "echo"}
        config = MCPServerConfig.from_dict(data)
        assert config.command == "echo"
        assert config.args is None
        assert config.env is None


class TestMCPConfig:
    """Tests for MCPConfig dataclass."""

    def test_empty_config(self):
        """Test creating empty MCPConfig."""
        config = MCPConfig()
        assert config.mcp_servers == {}

    def test_config_with_servers(self):
        """Test creating MCPConfig with servers."""
        server1 = MCPServerConfig(command="echo", args=["test1"])
        server2 = MCPServerConfig(command="cat", args=["test2"])
        config = MCPConfig(mcp_servers={"server1": server1, "server2": server2})
        assert len(config.mcp_servers) == 2
        assert "server1" in config.mcp_servers
        assert "server2" in config.mcp_servers

    def test_to_dict(self):
        """Test serialization to dictionary."""
        server = MCPServerConfig(command="echo", args=["test"])
        config = MCPConfig(mcp_servers={"test-server": server})
        result = config.to_dict()
        assert result == {
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["test"],
                }
            }
        }

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["test"],
                }
            }
        }
        config = MCPConfig.from_dict(data)
        assert len(config.mcp_servers) == 1
        assert "test-server" in config.mcp_servers
        assert config.mcp_servers["test-server"].command == "echo"

    def test_from_dict_empty(self):
        """Test deserialization with empty servers."""
        data = {"mcpServers": {}}
        config = MCPConfig.from_dict(data)
        assert config.mcp_servers == {}

    def test_from_dict_missing_mcp_servers(self):
        """Test deserialization with missing mcpServers key."""
        data = {}
        config = MCPConfig.from_dict(data)
        assert config.mcp_servers == {}

    def test_from_dict_invalid_mcp_servers_type(self):
        """Test that invalid mcpServers type raises ValueError."""
        data = {"mcpServers": "not-a-dict"}
        with pytest.raises(ValueError, match="mcpServers.*must be a JSON object"):
            MCPConfig.from_dict(data)

    def test_from_dict_invalid_server_config(self):
        """Test that invalid server config raises ValueError."""
        data = {
            "mcpServers": {
                "test-server": "not-a-dict"
            }
        }
        with pytest.raises(ValueError, match="configuration must be a JSON object"):
            MCPConfig.from_dict(data)

    def test_from_dict_missing_command(self):
        """Test that missing command raises ValueError."""
        data = {
            "mcpServers": {
                "test-server": {
                    "args": ["test"]
                }
            }
        }
        with pytest.raises(ValueError, match="missing required 'command' field"):
            MCPConfig.from_dict(data)

    def test_from_file(self, tmp_path):
        """Test loading from JSON file."""
        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["test"],
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        config = MCPConfig.from_file(config_file)
        assert len(config.mcp_servers) == 1
        assert "test-server" in config.mcp_servers

    def test_to_file(self, tmp_path):
        """Test saving to JSON file."""
        server = MCPServerConfig(command="echo", args=["test"])
        config = MCPConfig(mcp_servers={"test-server": server})
        config_file = tmp_path / "mcp.json"

        config.to_file(config_file)

        assert config_file.exists()
        loaded = json.loads(config_file.read_text())
        assert loaded == {
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["test"],
                }
            }
        }


class TestLoadMCPConfig:
    """Tests for load_mcp_config function."""

    def test_load_missing_file(self, tmp_path, monkeypatch):
        """Test that missing config file returns None."""
        def mock_get_config_dir():
            return tmp_path

        monkeypatch.setattr("whai.mcp.config.get_config_dir", mock_get_config_dir)

        config = load_mcp_config()
        assert config is None

    def test_load_valid_config(self, tmp_path, monkeypatch):
        """Test loading valid config file."""
        def mock_get_config_dir():
            return tmp_path

        monkeypatch.setattr("whai.mcp.config.get_config_dir", mock_get_config_dir)

        config_file = tmp_path / "mcp.json"
        config_data = {
            "mcpServers": {
                "test-server": {
                    "command": "echo",
                    "args": ["test"],
                }
            }
        }
        config_file.write_text(json.dumps(config_data))

        config = load_mcp_config()
        assert config is not None
        assert len(config.mcp_servers) == 1

    def test_load_invalid_json(self, tmp_path, monkeypatch):
        """Test that invalid JSON raises ValueError."""
        def mock_get_config_dir():
            return tmp_path

        monkeypatch.setattr("whai.mcp.config.get_config_dir", mock_get_config_dir)

        config_file = tmp_path / "mcp.json"
        config_file.write_text("{ invalid json }")

        with pytest.raises(ValueError, match="Invalid JSON"):
            load_mcp_config()

