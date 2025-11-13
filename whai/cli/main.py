"""Main CLI entry point for whai."""

import os
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import List, Optional

import typer
from rich.text import Text

from whai import ui
from whai.cli.flags import extract_inline_overrides
from whai.cli.role import role_app
from whai.configuration import (
    InvalidRoleMetadataError,
    MissingConfigError,
    load_config,
    load_role,
    resolve_model,
    resolve_provider,
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
from whai.shell import launch_shell_session
from whai.utils import detect_shell, PerformanceLogger

app = typer.Typer(help="whai - Your terminal assistant powered by LLMs")
app.add_typer(role_app, name="role")

logger = get_logger(__name__)


@app.command(name="shell")
def shell_command(
    shell: Optional[str] = typer.Option(
        None,
        "--shell",
        "-s",
        help="Shell to launch (e.g., bash, zsh, pwsh). Defaults to current shell.",
    ),
    log_path: Optional[str] = typer.Option(
        None,
        "--log",
        "-l",
        help="Path to session log file. Defaults to timestamped file in cache.",
    ),
):
    """
    Launch an interactive shell with session recording.
    
    The shell behaves identically to your normal shell, but whai can access
    full command history and outputs (deep context) even without tmux.
    
    This also preloads the LLM library, making future whai calls faster.
    
    Examples:
        whai shell
        whai shell --shell zsh
        whai shell --log ~/my-session.log
    """
    # Prevent launching a nested whai shell session
    if os.environ.get("WHAI_SESSION_ACTIVE") == "1":
        ui.error("whai shell is already active in this terminal. Type 'exit' to leave the current session.")
        raise typer.Exit(2)

    # Show helpful tip about exiting
    ui.console.print(
        "\n[dim]Shell session starting with deep context recording enabled.[/dim]"
    )
    ui.console.print(
        "[dim]Tip: Type 'exit' to exit the shell and return to your previous terminal.[/dim]\n"
    )
    
    # Convert log_path string to Path if provided
    log_path_obj = Path(log_path) if log_path else None
    
    try:
        exit_code = launch_shell_session(
            shell=shell, log_path=log_path_obj, delete_on_exit=True
        )
        if exit_code and exit_code != 0:
            raise typer.Exit(exit_code)
        # On success (0), return normally so Typer exits with 0
        return
    except typer.Exit:
        # Re-raise typer.Exit to preserve exit codes
        raise
    except Exception as e:
        ui.error(f"Failed to launch shell session: {e}")
        raise typer.Exit(1)


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
    provider: Optional[str] = typer.Option(
        None, "--provider", "-p", help="Override the LLM provider"
    ),
    temperature: Optional[float] = typer.Option(
        None, "--temperature", "-t", help="Override temperature"
    ),
    timeout: int = typer.Option(
        None,
        "--timeout",
        help="Per-command timeout in seconds (applies to each approved command)",
    ),
    verbose: int = typer.Option(
        0,
        "--verbose",
        "-v",
        count=True,
        help="Increase verbosity (for debugging purposes): -v for INFO, -vv for DEBUG",
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

    # Route "shell" explicitly to the subcommand to avoid being parsed as free-form text
    if query and len(query) > 0 and query[0] == "shell":
        remaining_args = query[1:] if len(query) > 1 else []
        # Minimal parsing for supported options (--shell/-s, --log/-l)
        opt_shell: Optional[str] = None
        opt_log: Optional[str] = None
        i = 0
        while i < len(remaining_args):
            tok = remaining_args[i]
            if tok in ("--shell", "-s") and i + 1 < len(remaining_args):
                opt_shell = remaining_args[i + 1]
                i += 2
                continue
            if tok in ("--log", "-l") and i + 1 < len(remaining_args):
                opt_log = remaining_args[i + 1]
                i += 2
                continue
            # Skip unrecognized tokens
            i += 1

        # Call the subcommand directly and exit early
        shell_command(shell=opt_shell, log_path=opt_log)
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
            provider=provider,
        )
        role = overrides["role"]
        no_context = overrides["no_context"]
        model = overrides["model"]
        temperature = overrides["temperature"]
        timeout = overrides["timeout"]
        provider = overrides["provider"]

    # Set default timeout if not provided (before validation)
    if timeout is None:
        timeout = DEFAULT_COMMAND_TIMEOUT

    # Validate timeout after possible inline overrides
    if timeout <= 0:
        ui.error("--timeout must be a positive integer (seconds)")
        raise typer.Exit(2)

    # Determine effective log level from verbose count or inline overrides
    # Map count to log level: 0 = default (CRITICAL), 1 = INFO, 2+ = DEBUG
    inline_verbose_count = overrides.get("verbose_count", 0)
    total_verbose_count = verbose + inline_verbose_count
    
    if total_verbose_count == 0:
        effective_log_level = None  # Use default
    elif total_verbose_count == 1:
        effective_log_level = "INFO"
    else:  # 2 or more
        effective_log_level = "DEBUG"

    # Configure logging
    configure_logging(effective_log_level)

    final_detected_flags: List[str] = []
    if total_verbose_count >= 2:
        final_detected_flags.append("-vv")
    elif total_verbose_count == 1:
        final_detected_flags.append("-v")
    if no_context:
        final_detected_flags.append("--no-context")
    if interactive_config:
        final_detected_flags.append("--interactive-config")
    if version_flag:
        final_detected_flags.append("--version")
    if role is not None:
        final_detected_flags.append("--role")
    if model is not None:
        final_detected_flags.append("--model")
    if provider is not None:
        final_detected_flags.append("--provider")
    if temperature is not None:
        final_detected_flags.append("--temperature")
    if timeout is not None and timeout != DEFAULT_COMMAND_TIMEOUT:
        final_detected_flags.append("--timeout")

    logger.info(
        "CLI arguments parsed: query=%s role=%s verbose=%s flags=%s",
        query,
        role,
        total_verbose_count,
        final_detected_flags if final_detected_flags else ["<none>"],
    )

    # Detect and log shell
    detected_shell = detect_shell()
    logger.info(f"Detected shell: {detected_shell}")

    # Join query arguments with spaces
    query_str = " ".join(query)

    # Initialize performance logger for startup
    startup_perf = PerformanceLogger("Setup")
    startup_perf.start()

    try:
        # 1. Load config and role
        try:
            config = load_config()
            startup_perf.log_section("Config loading")
        except MissingConfigError:
            ui.warn("Configuration not found. Starting interactive setup...")
            try:
                run_wizard(existing_config=False)
                # Try loading again after wizard completes
                config = load_config()
                ui.info("Configuration complete! Continuing with your query...")
                startup_perf.log_section("Config loading (with wizard)")
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

        try:
            role_obj = load_role(role)
            startup_perf.log_section("Role loading", extra_info={"role": role})
        except FileNotFoundError as e:
            ui.error(str(e))
            raise typer.Exit(1)
        except InvalidRoleMetadataError as e:
            ui.error(f"Invalid role metadata: {e}")
            raise typer.Exit(1)
        except Exception as e:
            ui.error(f"Failed to load role: {e}")
            raise typer.Exit(1)

        # 2. Get context (tmux or history)
        if no_context:
            context_str = ""
            is_deep_context = False
            startup_perf.log_section("Context capture", extra_info={"skipped": True})
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
            else:
                logger.debug("No command arguments to exclude from context")

            context_str, is_deep_context = get_context(
                exclude_command=command_to_exclude
            )
            startup_perf.log_section(
                "Context capture",
                extra_info={
                    "deep": is_deep_context,
                    "has_content": bool(context_str),
                },
            )

            if not is_deep_context and context_str:
                ui.warn(
                    "Using shell history only (no tmux detected). History analysis will not include outputs."
                )
            elif not context_str:
                # Check if tmux is active but empty
                if "TMUX" in os.environ:
                    ui.info("Tmux session detected but no context available yet (new session).")
                else:
                    ui.info("No context available (no tmux, no history).")

        # 4. Initialize LLM provider
        # Resolve model, temperature, and provider using consolidated precedence logic
        llm_model, model_source = resolve_model(model, role_obj, config)
        llm_temperature = resolve_temperature(temperature, role_obj)
        llm_provider_name, provider_source = resolve_provider(provider, role_obj, config)

        logger.info(
            "Model loaded: %s (source: %s, temperature=%s)",
            llm_model,
            model_source,
            llm_temperature,
            extra={"category": "api"},
        )

        logger.info(
            "Initializing LLMProvider: provider=%s (source: %s), model=%s",
            llm_provider_name,
            provider_source,
            llm_model,
            extra={"category": "api"},
        )
        try:
            llm_provider = LLMProvider(
                config, model=llm_model, temperature=llm_temperature, perf_logger=startup_perf, provider=llm_provider_name
            )
            startup_perf.log_section(
                "LLM initialization",
                extra_info={"model": llm_model, "temperature": llm_temperature},
            )
        except RuntimeError as e:
            ui.error(str(e))
            raise typer.Exit(1)
        except Exception as e:
            ui.error(f"Failed to initialize LLM provider: {e}")
            raise typer.Exit(1)

        # Display loaded configuration
        ui.console.print(Text(f"Model: {llm_model} | Provider: {llm_provider.default_provider} | Role: {role}", style="blue"))

        # 5. Truncate context if needed (before building messages)
        if context_str:
            context_str, was_truncated = truncate_text_with_tokens(
                context_str, CONTEXT_MAX_TOKENS
            )
            startup_perf.log_section(
                "Context truncation", extra_info={"truncated": was_truncated}
            )
            if was_truncated:
                ui.warn(
                    "Terminal context was truncated to fit token limits. "
                    "Recent commands and output have been preserved."
                )
        else:
            startup_perf.log_section("Context truncation", extra_info={"skipped": True})

        # 6. Build initial message
        base_prompt = get_base_system_prompt(is_deep_context, timeout=timeout)
        role_header = f"=== ROLE INSTRUCTIONS (active role: {role_obj.name}) ==="
        system_message = "\n\n".join(
            [
                base_prompt.rstrip(),
                role_header,
                role_obj.body.strip(),
            ]
        )
        startup_perf.log_section("System prompt building")

        # Add context to user message if available
        if context_str:
            user_message = (
                f"TERMINAL CONTEXT:\n```\n{context_str}\n```\n\nUSER QUERY: {query_str}"
            )
        else:
            logger.info("No terminal context available; sending user query only")
            user_message = query_str

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        startup_perf.log_section("Message construction", extra_info={"message_count": len(messages)})
        startup_perf.log_complete()

        # 7. Reconstruct command string for logging
        # Use sys.argv to get the exact command as typed, including all flags
        command_string = None
        if len(sys.argv) > 1:
            # Normalize command name to "whai" for consistency
            argv0 = sys.argv[0]
            if "whai" in argv0.lower():
                command_name = "whai"
            else:
                command_name = Path(argv0).name
            
            # Join all arguments, preserving quotes and special characters
            args_str = " ".join(sys.argv[1:])
            command_string = f"{command_name} {args_str}"

        # 8. Main conversation loop
        run_conversation_loop(llm_provider, messages, timeout, command_string=command_string)

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
