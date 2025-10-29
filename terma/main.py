"""Main CLI entry point for terma."""

import json
import sys
import time
from typing import Optional

import typer

from terma.config import load_config, load_role
from terma.constants import DEFAULT_LLM_MODEL
from terma.context import get_context
from terma.interaction import ShellSession, approval_loop
from terma.llm import LLMProvider, get_base_system_prompt
from terma.logging_setup import configure_logging, get_logger

app = typer.Typer(help="terma - Your terminal assistant powered by LLMs")

logger = get_logger(__name__)


def print_error(message: str):
    """Print an error message to stderr."""
    typer.echo(typer.style(f"Error: {message}", fg=typer.colors.RED), err=True)


def print_warning(message: str):
    """Print a warning message to stderr."""
    typer.echo(typer.style(f"Warning: {message}", fg=typer.colors.YELLOW), err=True)


def print_info(message: str):
    """Print an info message to stderr."""
    typer.echo(typer.style(f"Info: {message}", fg=typer.colors.BLUE), err=True)


@app.command()
def main(
    query: str = typer.Argument(..., help="Your question or request"),
    role: str = typer.Option(
        "assistant", "--role", "-r", help="Role to use (assistant, debug, etc.)"
    ),
    no_context: bool = typer.Option(False, "--no-context", help="Skip context capture"),
    model: Optional[str] = typer.Option(
        None, "--model", "-m", help="Override the LLM model"
    ),
    temperature: Optional[float] = typer.Option(
        None, "--temperature", "-t", help="Override temperature"
    ),
):
    """
    terma - Your terminal assistant powered by LLMs.

    Ask questions, get command suggestions, troubleshoot issues, and more.

    Examples:
        terma "what's the biggest folder here?"
        terma "why did my last command fail?" -r debug
        terma "how do I find all .py files modified today?"
    """
    # Configure logging first thing
    configure_logging()

    t0 = time.perf_counter()
    logger.debug("Startup: entered main()", extra={"category": "perf"})

    shell_session = None

    try:
        # 1. Load config and role
        try:
            config = load_config()
        except Exception as e:
            print_error(f"Failed to load config: {e}")
            raise typer.Exit(1)
        t_cfg = time.perf_counter()
        logger.debug(
            "Startup: load_config() completed in %.3f ms",
            (t_cfg - t0) * 1000,
            extra={"category": "perf"},
        )

        try:
            role_metadata, role_prompt = load_role(role)
        except FileNotFoundError as e:
            print_error(str(e))
            raise typer.Exit(1)
        except Exception as e:
            print_error(f"Failed to load role: {e}")
            raise typer.Exit(1)
        t_role = time.perf_counter()
        logger.debug(
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
            t_ctx0 = time.perf_counter()
            context_str, is_deep_context = get_context()
            t_ctx1 = time.perf_counter()
            logger.debug(
                "Startup: get_context() completed in %.3f ms (deep=%s, has_content=%s)",
                (t_ctx1 - t_ctx0) * 1000,
                is_deep_context,
                bool(context_str),
                extra={"category": "perf"},
            )

            if not is_deep_context and context_str:
                print_warning(
                    "Using shell history only (no tmux detected). Post-mortem analysis may be limited."
                )
            elif not context_str:
                print_info("No context available (no tmux, no history).")

        logger.debug(
            "Startup: context stage done, elapsed %.3f ms",
            (time.perf_counter() - t0) * 1000,
            extra={"category": "perf"},
        )

        # 3. Initialize LLM provider
        llm_model = (
            model
            or role_metadata.get("model")
            or config["llm"].get("default_model", DEFAULT_LLM_MODEL)
        )
        llm_temperature = (
            temperature
            if temperature is not None
            else role_metadata.get("temperature", None)
        )

        logger.debug(
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
            print_error(f"Failed to initialize LLM provider: {e}")
            raise typer.Exit(1)
        t_llm = time.perf_counter()
        logger.debug(
            "Startup: LLMProvider init completed in %.3f ms (model=%s, temp=%s)",
            (t_llm - t_role) * 1000,
            llm_model,
            llm_temperature,
            extra={"category": "perf"},
        )

        # 4. Create shell session
        try:
            shell_session = ShellSession()
        except Exception as e:
            print_error(f"Failed to create shell session: {e}")
            raise typer.Exit(1)
        t_shell = time.perf_counter()
        logger.debug(
            "Startup: ShellSession() completed in %.3f ms",
            (t_shell - t_llm) * 1000,
            extra={"category": "perf"},
        )

        # 5. Build initial message
        t_prompt0 = time.perf_counter()
        base_prompt = get_base_system_prompt(is_deep_context)
        system_message = f"{base_prompt}\n\n{role_prompt}"
        t_prompt1 = time.perf_counter()
        logger.debug(
            "Startup: get_base_system_prompt() completed in %.3f ms",
            (t_prompt1 - t_prompt0) * 1000,
            extra={"category": "perf"},
        )

        # Add context to user message if available
        if context_str:
            user_message = (
                f"TERMINAL CONTEXT:\n```\n{context_str}\n```\n\nUSER QUERY: {query}"
            )
        else:
            user_message = query

        messages = [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ]

        logger.debug(
            "Startup: conversation initialized (%d messages), total startup %.3f ms",
            len(messages),
            (time.perf_counter() - t0) * 1000,
            extra={"category": "perf"},
        )

        # 6. Main conversation loop
        while True:
            try:
                # Send to LLM with streaming
                response_stream = llm_provider.send_message(messages, stream=True)

                # Collect and display response
                response_chunks = []
                for chunk in response_stream:
                    response_chunks.append(chunk)

                    if chunk["type"] == "text":
                        # Stream text to stdout in real-time
                        print(chunk["content"], end="", flush=True)

                # Add newline after streaming text if we had any
                if any(c["type"] == "text" for c in response_chunks):
                    print()

                # Extract tool calls from chunks
                tool_calls = [c for c in response_chunks if c["type"] == "tool_call"]
                logger.debug(
                    "Received %d tool calls from stream",
                    len(tool_calls),
                    extra={"category": "api"},
                )

                if not tool_calls:
                    # No tool calls, conversation is done
                    break

                # Process each tool call
                tool_results = []
                for tool_call in tool_calls:
                    if tool_call["name"] == "execute_shell":
                        command = tool_call["arguments"].get("command", "")

                        if not command:
                            continue

                        # Get user approval
                        approved_command = approval_loop(command)

                        if approved_command is None:
                            # User rejected
                            tool_results.append(
                                {
                                    "tool_call_id": tool_call["id"],
                                    "output": "Command rejected by user.",
                                }
                            )
                            continue

                        # Execute the command
                        try:
                            logger.debug(
                                "Executing approved command: %s",
                                approved_command,
                                extra={"category": "cmd"},
                            )
                            stdout, stderr, returncode = shell_session.execute_command(
                                approved_command
                            )

                            # Format the result
                            result = f"Command: {approved_command}\n"
                            if stdout:
                                result += f"\nOutput:\n{stdout}"
                            if stderr:
                                result += f"\nErrors:\n{stderr}"

                            tool_results.append(
                                {"tool_call_id": tool_call["id"], "output": result}
                            )

                            # Display the output
                            print(f"\n{result}\n")

                        except Exception as e:
                            error_msg = f"Failed to execute command: {e}"
                            logger.exception("Command execution failed: %s", e)
                            print_error(error_msg)
                            tool_results.append(
                                {"tool_call_id": tool_call["id"], "output": error_msg}
                            )

                # Decide whether to end the conversation
                all_rejected = tool_results and all(
                    "rejected" in r["output"].lower() for r in tool_results
                )

                if not tool_results and tool_calls:
                    # Tool calls existed but none were runnable (e.g., empty/missing command)
                    print_info(
                        "No runnable tool calls were produced (missing command)."
                    )
                    break

                if not tool_results or all_rejected:
                    print("\nConversation ended.")
                    break

                # Build assistant message for history
                # Collect text content
                assistant_content = "".join(
                    c["content"] for c in response_chunks if c["type"] == "text"
                )

                assistant_message = {
                    "role": "assistant",
                    "content": assistant_content,
                }

                # Add tool_calls to assistant message if present
                if tool_calls:
                    assistant_message["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["arguments"]),
                            },
                        }
                        for tc in tool_calls
                    ]

                messages.append(assistant_message)

                # Add tool results to messages
                for result in tool_results:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": result["tool_call_id"],
                            "content": result["output"],
                        }
                    )

                # Continue loop to get LLM's next response

            except KeyboardInterrupt:
                print("\n\nInterrupted by user.")
                break
            except Exception as e:
                import traceback

                print_error(f"Unexpected error: {e}")
                print_error(f"Details: {traceback.format_exc()}")
                logger.exception("Unexpected error in conversation loop: %s", e)
                break

    except typer.Exit:
        raise
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(0)
    except Exception as e:
        print_error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        if shell_session:
            try:
                shell_session.close()
            except Exception:
                pass


if __name__ == "__main__":
    app()
