"""Tests for role CLI commands."""

from unittest.mock import patch

from typer.testing import CliRunner

from whai.configuration import user_config as config
from whai.configuration.roles import ensure_default_roles
from whai.role_cli import role_app

runner = CliRunner()


def test_list_roles_empty(tmp_path, monkeypatch):
    """Test list command with no roles."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)

    # Create roles dir but no files
    # Note: list calls ensure_default_roles(), so we skip that test
    # Instead, we test that list works with existing roles
    ensure_default_roles()

    result = runner.invoke(role_app, ["list"])
    assert result.exit_code == 0
    # Should have at least the default role
    assert "default" in result.stdout


def test_list_roles_with_defaults(tmp_path, monkeypatch):
    """Test list command with default roles."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)

    # Ensure default roles are created
    ensure_default_roles()

    result = runner.invoke(role_app, ["list"])
    assert result.exit_code == 0
    assert "default" in result.stdout


def test_create_role(tmp_path, monkeypatch):
    """Test creating a new role."""
    # Patch get_config_dir in both modules
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Mock click.edit to avoid opening an editor
    with patch("whai.role_cli.click.edit"):
        result = runner.invoke(role_app, ["create", "test-role"])

    assert result.exit_code == 0
    assert "Created role at" in result.stdout

    # Verify file was created
    role_path = tmp_path / "roles" / "test-role.md"
    assert role_path.exists()
    content = role_path.read_text()
    assert "test-role" in content


def test_create_role_duplicate(tmp_path, monkeypatch):
    """Test creating a role that already exists fails."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create role first time
    with patch("whai.role_cli.click.edit"):
        result1 = runner.invoke(role_app, ["create", "test-role"])
    assert result1.exit_code == 0

    # Try to create again
    with patch("whai.role_cli.click.edit"):
        result2 = runner.invoke(role_app, ["create", "test-role"])
    assert result2.exit_code != 0
    output = result2.stdout + result2.stderr
    assert "already exists" in output


def test_create_role_invalid_name(tmp_path, monkeypatch):
    """Test creating a role with invalid name fails."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)

    result = runner.invoke(role_app, ["create", "invalid name!"])
    assert result.exit_code != 0
    output = result.stdout + result.stderr
    assert "must match" in output


def test_edit_role(tmp_path, monkeypatch):
    """Test editing an existing role."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    with patch("whai.role_cli.click.edit"):
        result = runner.invoke(role_app, ["edit", "default"])

    assert result.exit_code == 0


def test_edit_role_not_found(tmp_path, monkeypatch):
    """Test editing a non-existent role fails."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, ["edit", "nonexistent"])
    assert result.exit_code != 0
    output = result.stdout + result.stderr
    assert "not found" in output


def test_remove_role(tmp_path, monkeypatch):
    """Test removing a role."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create a test role
    test_role = tmp_path / "roles" / "test-role.md"
    test_role.write_text("Test content")

    # Remove it (confirm with 'y')
    result = runner.invoke(role_app, ["remove", "test-role"], input="y\n")
    assert result.exit_code == 0
    assert "Removed" in result.stdout
    assert not test_role.exists()


def test_remove_role_cancelled(tmp_path, monkeypatch):
    """Test cancelling role removal."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create a test role
    test_role = tmp_path / "roles" / "test-role.md"
    test_role.write_text("Test content")

    # Try to remove but cancel (confirm with 'n')
    result = runner.invoke(role_app, ["remove", "test-role"], input="n\n")
    assert result.exit_code == 0
    # warn() outputs to stderr, check both stdout and stderr
    assert "Cancelled" in result.stdout or "Cancelled" in result.stderr
    assert test_role.exists()


def test_set_default_role(tmp_path, monkeypatch):
    """Test setting default role in config."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, ["set-default", "default"])
    assert result.exit_code == 0
    assert "Default role set to 'default'" in result.stdout

    # Verify config was updated
    cfg = config.load_config()
    assert cfg.roles.default_role == "default"


def test_set_default_role_not_found(tmp_path, monkeypatch):
    """Test setting default to non-existent role fails."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, ["set-default", "nonexistent"])
    assert result.exit_code != 0
    output = result.stdout + result.stderr
    assert "not found" in output


def test_reset_default(tmp_path, monkeypatch):
    """Test resetting default role from packaged defaults."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Modify the default role
    default_role = tmp_path / "roles" / "default.md"
    default_role.write_text("Modified content")

    # Reset it (confirm with 'y')
    result = runner.invoke(role_app, ["reset-default"], input="y\n")
    assert result.exit_code == 0
    assert "Reset default role" in result.stdout

    # Verify it was reset
    content = default_role.read_text()
    assert "helpful terminal assistant" in content

    # Verify config was updated
    cfg = config.load_config()
    assert cfg.roles.default_role == "default"


def test_reset_default_cancelled(tmp_path, monkeypatch):
    """Test cancelling default role reset."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Modify the default role
    default_role = tmp_path / "roles" / "default.md"
    default_role.write_text("Modified content")

    # Try to reset but cancel (confirm with 'n')
    result = runner.invoke(role_app, ["reset-default"], input="n\n")
    assert result.exit_code == 0
    # warn() outputs to stderr, check both stdout and stderr
    assert "Cancelled" in result.stdout or "Cancelled" in result.stderr

    # Verify it was NOT reset
    content = default_role.read_text()
    assert "Modified content" in content


def test_open_folder(tmp_path, monkeypatch):
    """Test opening roles folder."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Mock the system calls
    with (
        patch("subprocess.Popen") as mock_popen,
        patch("os.startfile") as mock_startfile,
    ):
        result = runner.invoke(role_app, ["open-folder"])

        assert result.exit_code == 0
        assert "Opened" in result.stdout or mock_popen.called or mock_startfile.called


def test_use_role(tmp_path, monkeypatch):
    """Test use command shows shell commands."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, ["use", "default", "--shell", "bash"])
    assert result.exit_code == 0
    assert 'export WHAI_ROLE="default"' in result.stdout
    assert "unset WHAI_ROLE" in result.stdout


def test_use_role_powershell(tmp_path, monkeypatch):
    """Test use command with PowerShell."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, ["use", "default", "--shell", "pwsh"])
    assert result.exit_code == 0
    assert '$env:WHAI_ROLE = "default"' in result.stdout
    assert "Remove-Item Env:WHAI_ROLE" in result.stdout


def test_use_role_fish(tmp_path, monkeypatch):
    """Test use command with fish shell."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, ["use", "default", "--shell", "fish"])
    assert result.exit_code == 0
    assert 'set -x WHAI_ROLE "default"' in result.stdout
    assert "set -e WHAI_ROLE" in result.stdout


def test_use_role_not_found(tmp_path, monkeypatch):
    """Test use command with non-existent role fails."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, ["use", "nonexistent", "--shell", "bash"])
    assert result.exit_code != 0
    output = result.stdout + result.stderr
    assert "not found" in output


def test_interactive_menu_cancel(tmp_path, monkeypatch):
    """Test interactive menu cancellation."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, [], input="cancel\n")
    assert result.exit_code == 0
    # warn() outputs to stderr, check both stdout and stderr
    assert "Cancelled" in result.stdout or "Cancelled" in result.stderr


def test_interactive_menu_list(tmp_path, monkeypatch):
    """Test interactive menu list action."""
    monkeypatch.setattr(
        "whai.configuration.user_config.get_config_dir", lambda: tmp_path
    )
    monkeypatch.setattr("whai.role_cli.get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    result = runner.invoke(role_app, [], input="list\n")
    assert result.exit_code == 0
    assert "default" in result.stdout
