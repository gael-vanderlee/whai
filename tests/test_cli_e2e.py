"""Subprocess-based CLI end-to-end tests.

These tests invoke the real CLI via `python -m whai` to validate that
the packaging entrypoint, Typer parsing, config handling, and LLM/Shell
integration paths work together. Network calls are avoided by prepending
`tests/mocks` to `PYTHONPATH`, which provides a mock `litellm` module.
"""

import os
import subprocess
import sys
from pathlib import Path


def _base_env(tmp_path: Path, *, toolcall: bool = False) -> dict:
    """Construct a clean environment for subprocess CLI runs.

    - Adds tests directory to PYTHONPATH so sitecustomize is auto-imported.
    - Sets WHAI_TEST_MODE=1 to trigger ephemeral config and mocked LLM.
    - Redirects config base dir to tmp_path for isolation.
    - Optionally enables tool-call streaming via WHAI_MOCK_TOOLCALL=1.
    """
    env = {k: v for k, v in os.environ.items()}
    project_root = Path(__file__).resolve().parents[1]
    mocks_dir = project_root / "tests" / "mocks"

    # Ensure mocks dir comes first so `import litellm` resolves to our mock
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(mocks_dir) + (os.pathsep + existing if existing else "")

    env["WHAI_TEST_MODE"] = "1"

    # Redirect config location
    if os.name == "nt":
        env["APPDATA"] = str(tmp_path)
    else:
        env["XDG_CONFIG_HOME"] = str(tmp_path)

    if toolcall:
        env["WHAI_MOCK_TOOLCALL"] = "1"

    return env


def _run_cli(
    args: list[str], *, env: dict, input_text: str | None = None, timeout: int = 20
):
    """Run `python -m whai` with provided args as a subprocess."""
    cmd = [sys.executable, "-m", "whai", *args]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    try:
        stdout, stderr = proc.communicate(input=input_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise
    return proc.returncode, stdout, stderr


def test_cli_module_text_only(tmp_path):
    """`python -m whai` prints mocked text-only response and exits 0."""
    env = _base_env(tmp_path)
    code, out, err = _run_cli(["--no-context", "what is a .gitignore file?"], env=env)
    assert code == 0
    merged = (out or "") + (err or "")
    assert "subprocess test" in merged


def test_cli_module_help_when_no_args(tmp_path):
    """Running with no args prints help and exits 0."""
    env = _base_env(tmp_path)
    code, out, err = _run_cli([], env=env)
    assert code == 0
    merged = (out or "") + (err or "")
    assert "Your question or request" in merged


def test_cli_role_list_subcommand(tmp_path):
    """`python -m whai role list` works in isolated config dir."""
    env = _base_env(tmp_path)
    code, out, err = _run_cli(["role", "list"], env=env)
    assert code == 0
    merged = (out or "") + (err or "")
    assert "default" in merged.lower()


def test_cli_tool_call_and_approval(tmp_path):
    """Tool-call flow: LLM proposes a command; user approves; output shown."""
    env = _base_env(tmp_path, toolcall=True)
    # Approve when prompted
    code, out, err = _run_cli(
        ["--no-context", "echo", "e2e"], env=env, input_text="a\n"
    )
    assert code == 0
    merged = (out or "") + (err or "")
    # Should show proposal text and echo result
    assert "let me run that" in merged.lower()
    assert "e2e-subprocess" in merged
