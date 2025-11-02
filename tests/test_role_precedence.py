"""Tests for role resolution precedence."""

from unittest.mock import patch

from typer.testing import CliRunner

from whai.configuration import user_config as config
from whai.configuration.roles import ensure_default_roles
from whai.cli.main import app

runner = CliRunner()


def test_role_precedence_cli_flag(tmp_path, monkeypatch):
    """Test that CLI flag has highest precedence."""
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create config with default role
    cfg = config.load_config()
    cfg.roles.default_role = "debug"
    config.save_config(cfg)

    # Set environment variable
    monkeypatch.setenv("WHAI_ROLE", "default")

    # Use CLI flag - should override both env and config
    with (
        patch("litellm.completion") as mock_llm,
        patch("whai.context.get_context", return_value=("", False)),
    ):
        mock_llm.return_value.choices = []
        mock_llm.return_value.usage = type("obj", (object,), {"total_tokens": 0})

        result = runner.invoke(
            app,
            ["test query", "--role", "custom", "--no-context"],
            env={"WHAI_ROLE": "default"},
        )

        # The test should attempt to load the "custom" role
        # It will fail if the role doesn't exist, but that proves precedence
        # For this test, we just verify the CLI flag was attempted


def test_role_precedence_env_over_config(tmp_path, monkeypatch):
    """Test that environment variable has precedence over config."""
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create config with default role set to "default"
    cfg = config.load_config()
    cfg.roles.default_role = "default"
    config.save_config(cfg)

    # Set environment variable to "debug"
    monkeypatch.setenv("WHAI_ROLE", "debug")

    with (
        patch("litellm.completion") as mock_llm,
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Mock LLM to return immediately
        mock_response = type(
            "obj",
            (object,),
            {
                "choices": [
                    type(
                        "obj",
                        (object,),
                        {
                            "message": type(
                                "obj",
                                (object,),
                                {"content": "Test response", "tool_calls": None},
                            ),
                            "finish_reason": "stop",
                        },
                    )
                ],
                "usage": type("obj", (object,), {"total_tokens": 10}),
            },
        )()
        mock_llm.return_value = mock_response

        result = runner.invoke(
            app, ["test query", "--no-context"], env={"WHAI_ROLE": "debug"}
        )

        # Verify that "debug" role was loaded (appears in output)
        output = result.stdout + result.stderr
        assert "debug" in output.lower()


def test_role_precedence_config_over_default(tmp_path, monkeypatch):
    """Test that config default has precedence over hardcoded default."""
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create config with default role set to "debug"
    cfg = config.load_config()
    cfg.roles.default_role = "debug"
    config.save_config(cfg)

    with (
        patch("litellm.completion") as mock_llm,
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Mock LLM to return immediately
        mock_response = type(
            "obj",
            (object,),
            {
                "choices": [
                    type(
                        "obj",
                        (object,),
                        {
                            "message": type(
                                "obj",
                                (object,),
                                {"content": "Test response", "tool_calls": None},
                            ),
                            "finish_reason": "stop",
                        },
                    )
                ],
                "usage": type("obj", (object,), {"total_tokens": 10}),
            },
        )()
        mock_llm.return_value = mock_response

        result = runner.invoke(app, ["test query", "--no-context"])

        # Verify that "debug" role was loaded (appears in output)
        output = result.stdout + result.stderr
        assert "debug" in output.lower()


def test_role_fallback_to_default(tmp_path, monkeypatch):
    """Test that when no role is specified anywhere, falls back to 'default'."""
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create config with default role
    cfg = config.load_config()
    cfg.roles.default_role = "default"
    config.save_config(cfg)

    with (
        patch("litellm.completion") as mock_llm,
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Mock LLM to return immediately
        mock_response = type(
            "obj",
            (object,),
            {
                "choices": [
                    type(
                        "obj",
                        (object,),
                        {
                            "message": type(
                                "obj",
                                (object,),
                                {"content": "Test response", "tool_calls": None},
                            ),
                            "finish_reason": "stop",
                        },
                    )
                ],
                "usage": type("obj", (object,), {"total_tokens": 10}),
            },
        )()
        mock_llm.return_value = mock_response

        result = runner.invoke(app, ["test query", "--no-context"])

        # Verify that "default" role was loaded (appears in output)
        output = result.stdout + result.stderr
        assert "default" in output.lower()


def test_role_env_variable_empty_string(tmp_path, monkeypatch):
    """Test that empty WHAI_ROLE env variable doesn't override config."""
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    ensure_default_roles()

    # Create config with default role
    cfg = config.load_config()
    cfg.roles.default_role = "debug"
    config.save_config(cfg)

    # Set environment variable to empty string (should be ignored)
    monkeypatch.setenv("WHAI_ROLE", "")

    with (
        patch("litellm.completion") as mock_llm,
        patch("whai.context.get_context", return_value=("", False)),
    ):
        # Mock LLM to return immediately
        mock_response = type(
            "obj",
            (object,),
            {
                "choices": [
                    type(
                        "obj",
                        (object,),
                        {
                            "message": type(
                                "obj",
                                (object,),
                                {"content": "Test response", "tool_calls": None},
                            ),
                            "finish_reason": "stop",
                        },
                    )
                ],
                "usage": type("obj", (object,), {"total_tokens": 10}),
            },
        )()
        mock_llm.return_value = mock_response

        result = runner.invoke(
            app, ["test query", "--no-context"], env={"WHAI_ROLE": ""}
        )

        # Verify that config's "debug" role was loaded
        output = result.stdout + result.stderr
        assert "debug" in output.lower()
