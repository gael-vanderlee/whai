"""Inline flag parsing for whai CLI."""

from typing import Dict, List, Optional, Tuple

import typer

from whai import ui


def extract_inline_overrides(
    tokens: List[str],
    *,
    role: Optional[str],
    no_context: bool,
    model: Optional[str],
    temperature: Optional[float],
    timeout: int,
) -> Tuple[List[str], Dict]:
    """Extract supported inline flags from free-form tokens.

    Returns a tuple of (cleaned_tokens, overrides_dict).
    """
    cleaned: List[str] = []
    i = 0
    # Local copies to mutate
    o_role = role
    o_no_context = no_context
    o_model = model
    o_temperature = temperature
    o_timeout = timeout
    o_log_level: Optional[str] = None

    while i < len(tokens):
        token = tokens[i]
        # --timeout <int>
        if token == "--timeout":
            if i + 1 >= len(tokens):
                ui.error("--timeout requires a value (seconds)")
                raise typer.Exit(2)
            value_token = tokens[i + 1]
            try:
                timeout_value = int(value_token)
                if timeout_value <= 0:
                    ui.error("--timeout must be a positive integer (seconds)")
                    raise typer.Exit(2)
                o_timeout = timeout_value
            except ValueError:
                ui.error("--timeout must be an integer (seconds)")
                raise typer.Exit(2)
            i += 2
            continue
        # --no-context
        if token == "--no-context":
            o_no_context = True
            i += 1
            continue
        # --model/-m <str>
        if token in ("--model", "-m"):
            if i + 1 >= len(tokens):
                ui.error("--model requires a value")
                raise typer.Exit(2)
            o_model = tokens[i + 1]
            i += 2
            continue
        # --temperature/-t <float>
        if token in ("--temperature", "-t"):
            if i + 1 >= len(tokens):
                ui.error("--temperature requires a value")
                raise typer.Exit(2)
            value_token = tokens[i + 1]
            try:
                o_temperature = float(value_token)
            except ValueError:
                ui.error("--temperature must be a number")
                raise typer.Exit(2)
            i += 2
            continue
        # --role/-r <str>
        if token in ("--role", "-r"):
            if i + 1 >= len(tokens):
                ui.error("--role requires a value")
                raise typer.Exit(2)
            o_role = tokens[i + 1]
            i += 2
            continue

        # -v [LEVEL]
        if token == "-v":
            # If followed by a level token, consume it; otherwise default to INFO
            level_token = None
            if i + 1 < len(tokens):
                candidate = tokens[i + 1].upper()
                if candidate in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
                    level_token = candidate
                    i += 2
                else:
                    i += 1
            else:
                i += 1
            o_log_level = level_token or "INFO"
            continue

        # Regular token
        cleaned.append(token)
        i += 1

    return cleaned, {
        "role": o_role,
        "no_context": o_no_context,
        "model": o_model,
        "temperature": o_temperature,
        "timeout": o_timeout
        if o_timeout is not None
        else None,  # Preserve 0 for validation
        "log_level": o_log_level,
    }
