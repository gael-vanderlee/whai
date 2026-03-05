"""Subprocess-based CLI end-to-end tests.

These tests invoke the real CLI via `python -m whai` to validate that
the packaging entrypoint, Typer parsing, config handling, and LLM/Shell
integration paths work together. Network calls are avoided by prepending
`tests/mocks` to `PYTHONPATH`, which provides a mock `litellm` module.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pytest


def _base_env(tmp_path: Path, *, toolcall: bool = False) -> Dict:
    """Construct a clean environment for subprocess CLI runs.

    - Adds tests directory to PYTHONPATH so sitecustomize is auto-imported.
    - Sets WHAI_TEST_MODE=1 to trigger ephemeral config and mocked LLM.
    - Redirects config base dir to tmp_path for isolation.
    - Optionally enables tool-call streaming via WHAI_MOCK_TOOLCALL=1.
    """
    env = {k: v for k, v in os.environ.items()}
    # From tests/e2e/test_cli_e2e.py: parents[0]=e2e, parents[1]=tests, parents[2]=project_root
    project_root = Path(__file__).resolve().parents[2]
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
    args: List[str], *, env: Dict, input_text: Optional[str] = None, timeout: int = 20
):
    """Run `python -m whai` with provided args as a subprocess."""
    cmd = [sys.executable, "-m", "whai", *args]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
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


def test_cli_module_default_query_when_no_args(tmp_path):
    """Running with no args uses default query and executes."""
    env = _base_env(tmp_path)
    code, out, err = _run_cli([], env=env)
    assert code == 0
    merged = (out or "") + (err or "")
    # Should execute with default query (confused about last thing)
    assert "subprocess test" in merged or "Model:" in merged


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


def test_cli_mcp_tool_call_e2e(tmp_path):
    """MCP tool-call flow: LLM proposes MCP tool; executor routes to real server; result shown."""
    uvx_path = shutil.which("uvx")
    if not uvx_path:
        pytest.skip("uvx not available, cannot run MCP server tests")

    try:
        result = subprocess.run(
            [uvx_path, "mcp-server-time", "--help"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0:
            pytest.skip("mcp-server-time not available via uvx")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pytest.skip("Cannot run mcp-server-time")

    env = _base_env(tmp_path)
    env["WHAI_MOCK_MCP_TOOLCALL"] = "1"

    # Write mcp.json into the isolated config dir (XDG_CONFIG_HOME/whai/)
    config_dir = tmp_path / "whai"
    config_dir.mkdir(parents=True, exist_ok=True)
    mcp_config = {
        "mcpServers": {
            "time-server": {
                "command": uvx_path,
                "args": ["mcp-server-time"],
                "env": {},
                "requires_approval": False,
            }
        }
    }
    (config_dir / "mcp.json").write_text(json.dumps(mcp_config))

    code, out, err = _run_cli(
        ["--no-context", "what time is it"], env=env, timeout=30
    )
    assert code == 0
    merged = (out or "") + (err or "")
    assert "let me check that" in merged.lower()
    assert "mcp-e2e-done" in merged
