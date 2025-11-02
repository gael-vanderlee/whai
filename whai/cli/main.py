"""Main CLI entry point for whai."""

import os
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import List, Optional

import typer

from whai import ui
from whai.cli.flags import extract_inline_overrides
from whai.cli.role import role_app
from whai.configuration import (
    InvalidRoleMetadataError,
    MissingConfigError,
    load_config,
    load_role,
    resolve_model,
    resolve_role,
    resolve_temperature,
)
from whai.configuration.config_wizard import run_wizard
from whai.constants import (
    CONTEXT_MAX_TOKENS,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_QUERY,
)
from whai.context import get_context
from whai.core.executor import run_conversation_loop
from whai.llm import LLMProvider, get_base_system_prompt
from whai.llm.token_utils import truncate_text_with_tokens
from whai.logging_setup import configure_logging, get_logger
from whai.utils import detect_shell

app = typer.Typer(help="whai - Your terminal assistant powered by LLMs")
app.add_typer(role_app, name="role")

logger = get_logger(__name__)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    query: List[str] = typer.Argument(
        None, help="Your question or request (can be multiple words)"
    ),
    role: Optional[str] = typer.Option(
        None, "--role", "-r", help="Role to use (default, debug, etc.)"
    ),
    no_context: bool = typer.Option(False, "--no-context", help="Skip context capture"),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Override the LLM model"
    ),
    temperature: Optional[float] = typer.Option(
        None, "--temperature", "-t", help="Override temperature"
    ),
    timeout: int = typer.Option(
        None,
        "--timeout",
        help="Per-command timeout in seconds (applies to each approved command)",
    ),
    log_level: Optional[str] = typer.Option(
        None,
        "--log-level",
        "-v",
        help="Set log level: CRITICAL|ERROR|WARNING|INFO|DEBUG",
    ),
    interactive_config: bool = typer.Option(
        False,
        "--interactive-config",
        help="Run interactive configuration wizard and exit",
    ),
    version_flag: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit",
    ),
):
    """
    whai - Your terminal assistant powered by LLMs.

    Ask questions, get command suggestions, troubleshoot issues, and more.

    Examples:
        whai what is the biggest folder here?
        whai "what's the biggest folder here?"
        whai why did my last command fail? -r debug
        whai "how do I find all .py files modified today?"

    Note: If your query contains spaces, apostrophes ('), quotation marks, or shell glob characters (? * []), always wrap it in double quotes to avoid shell parsing errors.
    """
    # Handle --version flag
    if version_flag:
        # Try to get version from installed package metadata
        try:
            v = version("whai")
        except Exception:
            # Fallback: read from pyproject.toml (development mode)
            try:
                # Find pyproject.toml relative to this file
                pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
                if not pyproject_path.exists():
                    # Try current directory as fallback
                    pyproject_path = Path("pyproject.toml")

                # Try tomllib (Python 3.11+)
                try:
                    import tomllib

                    with open(pyproject_path, "rb") as f:
                        data = tomllib.load(f)
                except ImportError:
                    # Fallback to tomli for Python 3.10
                    try:
                        import tomli as tomllib  # pyright: ignore[reportMissingImports]

                        with open(pyproject_path, "rb") as f:
                            data = tomllib.load(f)
                    except ImportError:
                        raise ImportError("Neither tomllib nor tomli available")

                v = data["project"]["version"]
            except Exception:
                ui.error("Could not determine version")
                raise typer.Exit(1)
        typer.echo(v)
        raise typer.Exit(0)

    # If a subcommand is invoked, let it handle everything
    if ctx.invoked_subcommand is not None:
        return

    # Check if first word is "role" - if so, it should be handled as a subcommand
    # This is needed because query is greedy and consumes all args before subcommand detection
    if query and len(query) > 0 and query[0] == "role":
        # Get the Click group command for role_app
        role_click_group = typer.main.get_command(role_app)
        remaining_args = query[1:] if len(query) > 1 else []

        # Create a new context for the subcommand and invoke it
        with role_click_group.make_context(
            "role", list(remaining_args), parent=ctx
        ) as subctx:
            role_click_group.invoke(subctx)
        return

    # Handle interactive config flag
    if interactive_config:
        try:
            run_wizard(existing_config=True)
        except typer.Abort:
            ui.console.print("\nConfiguration cancelled.")
            raise typer.Exit(0)
        except Exception as e:
            ui.error(f"Configuration error: {e}")
            raise typer.Exit(1)
        return

    # No query provided and no subcommand - use default query
    if not query:
        query = [
            DEFAULT_QUERY
        ]

    # Workaround for Click/Typer parsing with variadic arguments:
    # If users place options after the free-form query, those tokens land in `query`.
    # Extract supported inline options from `query` and apply them.
    if query:
        query, overrides = extract_inline_overrides(
            query,
            role=role,
            no_context=no_context,
            model=model,
            temperature=temperature,
            timeout=timeout,
        )
        role = overrides["role"]
        no_context = overrides["no_context"]
        model = overrides["model"]
        temperature = overrides["temperature"]
        timeout = overrides["timeout"]

    # Set default timeout if not provided (before validation)
    if timeout is None:
        timeout = DEFAULT_COMMAND_TIMEOUT

    # Validate timeout after possible inline overrides
    if timeout <= 0:
        ui.error("--timeout must be a positive integer (seconds)")
        raise typer.Exit(2)

    # Determine effective log level: explicit option takes precedence over inline
    effective_log_level = log_level or overrides.get("log_level")
    if effective_log_level is not None:
        effective_log_level = effective_log_level.strip().upper()
        if effective_log_level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            ui.error(
                "--log-level must be one of: CRITICAL, ERROR, WARNING, INFO, DEBUG"
            )
            raise typer.Exit(2)

    # Configure logging
    configure_logging(effective_log_level)

    # Detect and log shell
    detected_shell = detect_shell()
    logger.info(f"Detected shell: {detected_shell}")

    # Join query arguments with spaces
    query_str = " ".join(query)

    t0 = time.perf_counter()
    logger.info("Startup: entered main()")

    try:
        # 1. Load config and role
        try:
            config = load_config()
        except MissingConfigError:
            ui.warn("Configuration not found. Starting interactive setup...")
            try:
                run_wizard(existing_config=False)
                # Try loading again after wizard completes
                config = load_config()
                ui.info("Configuration complete! Continuing with your query...")
            except typer.Abort:
                ui.error("Configuration is required to use whai.")
                raise typer.Exit(1)
            except Exception as wizard_error:
                ui.error(f"Configuration failed: {wizard_error}")
                raise typer.Exit(1)
        except Exception as e:
            ui.error(f"Failed to load config: {e}")
            raise typer.Exit(1)

        # Resolve role using shared function (CLI > env > config > default)
        role = resolve_role(role, config)

        t_cfg = time.perf_counter()
        logger.info(
            "Startup: load_config() completed in %.3f ms",
            (t_cfg - t0) * 1000,
            extra={"category": "perf"},
        )

        try:
            role_obj = load_role(role)
        except FileNotFoundError as e:
            ui.error(str(e))
            raise typer.Exit(1)
        except InvalidRoleMetadataError as e:
            ui.error(f"Invalid role metadata: {e}")
            raise typer.Exit(1)
        except Exception as e:
            ui.error(f"Failed to load role: {e}")
            raise typer.Exit(1)
        t_role = time.perf_counter()
        logger.info(
            "Startup: load_role('%s') completed in %.3f ms",
            role,
            (t_role - t_cfg) * 1000,
            extra={"category": "perf"},
        )

        # 2. Get context (tmux or history)
        if no_context:
            context_str = ""
            is_deep_context = False
        else:
            # Reconstruct the command that invoked whai to exclude it from context
            command_to_exclude = None
            if len(sys.argv) > 1:
                # Reconstruct the full command as it would appear in history/tmux
                # Handle cases where sys.argv[0] might be full path, alias, or just "whai"
                argv0 = sys.argv[0]

                # Normalize the command name: if it ends with "whai" or contains "whai",
                # use just "whai" to match what typically appears in history
                if argv0.endswith("whai") or argv0.endswith(os.sep + "whai"):
                    # Extract just "whai" from path
                    command_name = "whai"
                elif "whai" in argv0.lower():
                    # Fallback: if "whai" appears anywhere, try to extract it
                    # This handles edge cases like aliases
                    command_name = "whai"
                else:
                    # Use the basename if it's not obviously whai
                    # This handles aliases or other executable names
                    command_name = Path(argv0).name

                # Join arguments, preserving quotes as they might appear in history
                args_str = " ".join(sys.argv[1:])
                command_to_exclude = f"{command_name} {args_str}"
                logger.info("Will exclude command from context: %s", command_to_exclude)
            else:
                logger.debug("No command arguments to exclude from context")

            t_ctx0 = time.perf_counter()
            context_str, is_deep_context = get_context(
                exclude_command=command_to_exclude
            )
            t_ctx1 = time.perf_counter()
            logger.info(
                "Startup: get_context() completed in %.3f ms (deep=%s, has_content=%s)",
                (t_ctx1 - t_ctx0) * 1000,
                is_deep_context,
                bool(context_str),
                extra={"category": "perf"},
            )

            if not is_deep_context and context_str:
                ui.warn(
                    "Using shell history only (no tmux detected). History analysis will not include outputs."
                )
            elif not context_str:
                ui.info("No context available (no tmux, no history).")

        logger.info(
            "Startup: context stage done, elapsed %.3f ms",
            (time.perf_counter() - t0) * 1000,
            extra={"category": "perf"},
        )

        # 4. Initialize LLM provider
        # Resolve model and temperature using consolidated precedence logic
        llm_model, model_source = resolve_model(model, role_obj, config)
        llm_temperature = resolve_temperature(temperature, role_obj)

        logger.info(
            "Model loaded: %s (source: %s)",
            llm_model,
            model_source,
            extra={"category": "api"},
        )
        logger.info(
            "Initializing LLMProvider with model=%s, temperature=%s",
            llm_model,
            llm_temperature,
            extra={"category": "api"},
        )

        try:
            llm_provider = LLMProvider(
                config, model=llm_model, temperature=llm_temperature
            )
        except Exception as e:
            ui.error(f"Failed to initialize LLM provider: {e}")
            raise typer.Exit(1)
        t_llm = time.perf_counter()
        logger.info(
            "Startup: LLMProvider init completed in %.3f ms (model=%s, temp=%s)",
            (t_llm - t_role) * 1000,
            llm_model,
            llm_temperature,
            extra={"category": "perf"},
        )

        # Display loaded configuration
        ui.info(f"Model: {llm_model} | Role: {role}")

        # 5. Truncate context if needed (before building messages)
        if context_str:
            t_trunc0 = time.perf_counter()
            context_str, was_truncated = truncate_text_with_tokens(
                context_str, CONTEXT_MAX_TOKENS
            )
            t_trunc1 = time.perf_counter()
            logger.info(
                "Startup: context truncation completed in %.3f ms (truncated=%s)",
                (t_trunc1 - t_trunc0) * 1000,
                was_truncated,
                extra={"category": "perf"},
            )
            if was_truncated:
                ui.warn(
                    "Terminal context was truncated to fit token limits. "
                    "Recent commands and output have been preserved."
                )

        # 6. Build initial message
        t_prompt0 = time.perf_counter()
        base_prompt = get_base_system_prompt(is_deep_context, timeout=timeout)
        system_message = f"{base_prompt}\n\n{role_obj.body}"
        t_prompt1 = time.perf_counter()
        logger.info(
            "Startup: get_base_system_prompt() completed in %.3f ms",
            (t_prompt1 - t_prompt0) * 1000,
            extra={"category": "perf"},
        )

        # Add context to user message if available
        if context_str:
            user_message = (
                f"TERMINAL CONTEXT:\n```\n{context_str}\n```\n\nUSER QUERY: {query_str}"
            )
        else:
            user_message = query_str

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        logger.info(
            "Startup: conversation initialized (%d messages), total startup %.3f ms",
            len(messages),
            (time.perf_counter() - t0) * 1000,
            extra={"category": "perf"},
        )

        # 7. Main conversation loop
        run_conversation_loop(llm_provider, messages, timeout)

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        ui.console.print("\n\nInterrupted by user.")
        sys.exit(130)
    except Exception as e:
        ui.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    app()
