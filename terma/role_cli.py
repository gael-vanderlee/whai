"""Role management CLI for terma."""

import os
import re
import sys
from pathlib import Path
from typing import Optional

import click
import typer

from terma.config import (
    ensure_default_roles,
    get_config_dir,
    get_default_role,
    load_config,
    resolve_role,
    save_config,
)
from terma.logging_setup import get_logger
from terma.utils import SUPPORTED_SHELLS, ShellType, detect_shell

logger = get_logger(__name__)
role_app = typer.Typer(help="Manage terma roles", no_args_is_help=False)

ROLE_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _roles_dir() -> Path:
    """Get the roles directory, creating it if needed."""
    d = get_config_dir() / "roles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _role_path(name: str) -> Path:
    """Get the path to a role file."""
    return _roles_dir() / f"{name}.md"


def _validate_role_name(name: str) -> None:
    """Validate a role name."""
    if not ROLE_NAME_RE.match(name):
        raise typer.BadParameter(
            "Role name must match ^[a-zA-Z0-9_-]+$ (letters, digits, underscore, hyphen)."
        )


def _template(name: str) -> str:
    """Generate a template for a new role."""
    return f"""---
model: gpt-5-mini
# Optional parameter you can add here (uncomment if needed):
# temperature: 0.3               # Only used when supported by the selected model
---
You are a helpful terminal assistant with the '{name}' specialization.
Describe behaviors, tone, and constraints here.
"""


def _open_in_editor(path: Path) -> None:
    """Open a file in the user's editor."""
    click.edit(filename=str(path))


def _get_set_command(shell: ShellType, role_name: str) -> str:
    """Get the command to set TERMA_ROLE for the given shell."""
    if shell == "pwsh":
        return f'$env:TERMA_ROLE = "{role_name}"'
    elif shell == "fish":
        return f'set -x TERMA_ROLE "{role_name}"'
    else:  # bash/zsh
        return f'export TERMA_ROLE="{role_name}"'


def _get_clear_command(shell: ShellType) -> str:
    """Get the command to clear TERMA_ROLE for the given shell."""
    if shell == "pwsh":
        return "Remove-Item Env:TERMA_ROLE -ErrorAction SilentlyContinue"
    elif shell == "fish":
        return "set -e TERMA_ROLE"
    else:  # bash/zsh
        return "unset TERMA_ROLE"


@role_app.command("list")
def list_roles() -> None:
    """List available roles."""
    ensure_default_roles()
    roles = sorted(p.stem for p in _roles_dir().glob("*.md"))
    if not roles:
        typer.echo("No roles found.")
        raise typer.Exit(0)
    for r in roles:
        typer.echo(r)


@role_app.command("create")
def create_role(
    name: str = typer.Argument(..., help="Role name (without .md)"),
) -> None:
    """Create a new role and open it in editor."""
    try:
        _validate_role_name(name)
    except typer.BadParameter as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2)

    ensure_default_roles()
    path = _role_path(name)
    if path.exists():
        typer.echo(f"Role '{name}' already exists: {path}", err=True)
        raise typer.Exit(2)
    path.write_text(_template(name))
    typer.echo(f"Created role at {path}")
    _open_in_editor(path)


@role_app.command("edit")
def edit_role(name: str = typer.Argument(...)) -> None:
    """Edit an existing role."""
    try:
        _validate_role_name(name)
    except typer.BadParameter as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2)

    ensure_default_roles()
    path = _role_path(name)
    if not path.exists():
        typer.echo(f"Role '{name}' not found at {path}", err=True)
        raise typer.Exit(2)
    _open_in_editor(path)


@role_app.command("remove")
def remove_role(name: str = typer.Argument(...)) -> None:
    """Remove a role file."""
    try:
        _validate_role_name(name)
    except typer.BadParameter as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2)

    ensure_default_roles()
    path = _role_path(name)
    if not path.exists():
        typer.echo(f"Role '{name}' not found.", err=True)
        raise typer.Exit(2)
    if not typer.confirm(f"Delete role '{name}' at {path}?", default=False):
        typer.echo("Cancelled.")
        raise typer.Exit(0)
    path.unlink()
    typer.echo(f"Removed {path}")


@role_app.command("set-default")
def set_default_role(name: str = typer.Argument(...)) -> None:
    """Set the default role in config."""
    try:
        _validate_role_name(name)
    except typer.BadParameter as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2)

    ensure_default_roles()
    if not _role_path(name).exists():
        typer.echo(f"Role '{name}' not found.", err=True)
        raise typer.Exit(2)
    cfg = load_config(allow_ephemeral=True)
    roles_cfg = cfg.setdefault("roles", {})
    roles_cfg["default_role"] = name
    save_config(cfg)
    typer.echo(f"Default role set to '{name}'")


@role_app.command("reset-default")
def reset_default() -> None:
    """
    Reset the default role to the packaged default.md and set it as config default.
    This will overwrite the local default.md file.
    """
    ensure_default_roles()
    path = _role_path("default")

    if path.exists():
        if not typer.confirm(
            f"This will overwrite '{path}' with the packaged default. Continue?",
            default=False,
        ):
            typer.echo("Cancelled.")
            raise typer.Exit(0)

    # Write packaged default
    default_content = get_default_role("default")
    path.write_text(default_content)
    typer.echo(f"Reset default role at {path}")

    # Set as config default
    cfg = load_config(allow_ephemeral=True)
    roles_cfg = cfg.setdefault("roles", {})
    roles_cfg["default_role"] = "default"
    save_config(cfg)
    typer.echo("Set 'default' as the default role in config")


@role_app.command("open-folder")
def open_folder() -> None:
    """Open the roles folder in the system file explorer."""
    d = _roles_dir()
    try:
        import subprocess

        if sys.platform.startswith("win"):
            os.startfile(str(d))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(d)])
        else:
            subprocess.Popen(["xdg-open", str(d)])
        typer.echo(f"Opened {d}")
    except Exception as e:
        typer.echo(f"Failed to open folder {d}: {e}", err=True)


@role_app.command("use")
def use_role(
    name: str = typer.Argument(..., help="Role name to use for this session"),
    shell: Optional[ShellType] = typer.Option(
        None,
        "--shell",
        click_type=click.Choice(SUPPORTED_SHELLS, case_sensitive=False),
        help="Shell type (bash, zsh, fish, pwsh). Auto-detected if not specified.",
    ),
) -> None:
    """
    Show how to set the role for the current shell session.

    This prints the command to set TERMA_ROLE for your shell.
    Copy and run it, or use eval/Invoke-Expression.
    """
    try:
        _validate_role_name(name)
    except typer.BadParameter as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(2)

    ensure_default_roles()
    if not _role_path(name).exists():
        typer.echo(f"Role '{name}' not found.", err=True)
        raise typer.Exit(2)

    detected_shell = shell or detect_shell()
    set_cmd = _get_set_command(detected_shell, name)
    clear_cmd = _get_clear_command(detected_shell)

    typer.echo(f"To use role '{name}' for this session, run:\n")
    typer.echo(f"  {set_cmd}\n")
    typer.echo("To clear the session role:\n")
    typer.echo(f"  {clear_cmd}")


@role_app.command("which")
def which_role() -> None:
    """Print the role currently in use based on precedence."""
    # Reuse the shared resolver to avoid duplicating logic
    try:
        cfg = load_config(allow_ephemeral=True)
    except Exception:
        cfg = {}
    current = resolve_role(None, cfg)
    typer.echo(current)


@role_app.callback(invoke_without_command=True)
def role_manager(ctx: typer.Context) -> None:
    """
    Interactive role manager.

    If no subcommand is provided, launches an interactive menu.
    """
    if ctx.invoked_subcommand:
        return

    # Detect accidental "role <free text>" usage
    # In Typer/Click, extra args after the command might be accessible via ctx.args
    # For safety, check if we have unrecognized tokens
    if hasattr(ctx, "args") and ctx.args:
        bad = " ".join(ctx.args)
        typer.echo(
            f"'{bad}' is not a recognized role command.\n"
            "If you want to send a message starting with the word 'role', wrap it in quotes:\n"
            '  terma "role play as a bad assistant"\n',
            err=True,
        )
        raise typer.Exit(2)

    ensure_default_roles()
    actions = [
        "list",
        "create",
        "edit",
        "remove",
        "set-default",
        "reset-default",
        "open-folder",
        "cancel",
    ]
    action = typer.prompt(
        "\nChoose an action",
        type=click.Choice(actions),
        default="list",
    )
    if action == "cancel":
        typer.echo("Cancelled.")
        raise typer.Exit(0)

    if action == "list":
        list_roles()
    elif action == "create":
        name = typer.prompt("Enter role name")
        create_role(name)  # type: ignore[arg-type]
    elif action == "edit":
        name = typer.prompt("Enter role name to edit")
        edit_role(name)  # type: ignore[arg-type]
    elif action == "remove":
        name = typer.prompt("Enter role name to remove")
        remove_role(name)  # type: ignore[arg-type]
    elif action == "set-default":
        name = typer.prompt("Enter role name to set as default")
        set_default_role(name)  # type: ignore[arg-type]
    elif action == "reset-default":
        reset_default()
    elif action == "open-folder":
        open_folder()
