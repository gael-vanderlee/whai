"""Integration test for observing LLM user message context via real shell session.

This test:
1) Launches `whai shell` (interactive session recorder)
2) Sends several commands including a mistyped git command
3) Runs `whai hello -v DEBUG` inside that session
4) Captures the debug log to extract the 'LLM user message' content

It validates observable behavior across the real CLI boundary.

Skipped by default; enable with WHAI_RUN_SHELL_TEST=1. Requires PowerShell on Windows.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


def _has_pwsh() -> bool:
    return shutil.which("pwsh") is not None


@pytest.mark.skipif(
    os.name != "nt" or not _has_pwsh() or os.getenv("WHAI_RUN_SHELL_TEST") != "1",
    reason="Windows+PowerShell required and WHAI_RUN_SHELL_TEST=1 to run",
)
def test_cli_llm_user_message_contains_git_typo_error(tmp_path: Path):
    # Define commands and their expected substrings in the LLM user message
    commands_expectations: list[tuple[str, list[str]]] = [
        (
            "gti status",
            [
                "gti status",
                "gti: The term 'gti' is not recognized",
            ],
        ),
        (
            'git comit -m "msg"',
            [
                'git comit -m "msg"',
                "git: 'comit' is not a git command",
            ],
        ),
        (
            "sl",
            ["> sl"],  # visible in context even if no output
        ),
        (
            "cd /nonexistant/path/",
            [
                "cd /nonexistant/path/",
                "Set-Location: Cannot find path",
                "nonexistant",
            ],
        ),
        (
            "cp file.txt /etc/",
            [
                "cp file.txt /etc/",
                "Copy-Item: Cannot find path",
            ],
        ),
        (
            "cd myproject",
            [
                "cd myproject",
                "Set-Location: Cannot find path",
            ],
        ),
        (
            "./run_script.ps1",
            [
                "./run_script.ps1",
                "The term './run_script.ps1' is not recognized",
            ],
        ),
        (
            'export API_KEY="123"',
            [
                'export API_KEY="123"',
                "export: The term 'export' is not recognized",
            ],
        ),
        (
            'cat file.txt | grep "text"',
            [
                'cat file.txt | grep "text"',
                "Get-Content: Cannot find path",
            ],
        ),
        (
            "ls -l",
            [
                "ls -l",
                "Get-ChildItem: Missing an argument for parameter 'LiteralPath'",
            ],
        ),
    ]
    # Use the venv python to run the installed console script/module
    python_exe = sys.executable

    # Create a temporary stub for `litellm` to avoid real API calls
    stub_root = tmp_path / "stubs"
    (stub_root / "litellm").mkdir(parents=True)
    (stub_root / "litellm" / "__init__.py").write_text(
        (
            "class _Delta:\n"
            "    def __init__(self, content=None, tool_calls=None):\n"
            "        self.content = content\n"
            "        self.tool_calls = tool_calls\n"
            "\n"
            "class _ChoiceWrapper:\n"
            "    def __init__(self, delta=None, message=None):\n"
            "        self.delta = delta\n"
            "        self.message = message\n"
            "\n"
            "class _Chunk:\n"
            "    def __init__(self, text):\n"
            "        self.choices = [_ChoiceWrapper(delta=_Delta(content=text))]\n"
            "\n"
            "class _Message:\n"
            "    def __init__(self, content):\n"
            "        self.content = content\n"
            "        self.tool_calls = None\n"
            "\n"
            "class _Response:\n"
            "    def __init__(self, content):\n"
            "        self.choices = [_ChoiceWrapper(message=_Message(content))]\n"
            "\n"
            "def completion(**kwargs):\n"
            "    # Respect stream flag; yield a couple of text chunks for streaming\n"
            "    if kwargs.get('stream', True):\n"
            "        def _gen():\n"
            "            yield _Chunk('Hello from mock ')\n"
            "            yield _Chunk('LLM.')\n"
            "        return _gen()\n"
            "    return _Response('Hello from mock LLM.')\n"
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    # Prepend our stub directory to PYTHONPATH so child processes import it first
    env["PYTHONPATH"] = str(stub_root) + os.pathsep + env.get("PYTHONPATH", "")
    # Ensure UTF-8 for stdout/stderr from Python process
    env["PYTHONIOENCODING"] = "utf-8"

    # Launch `whai shell` and attach stdin/stdout
    proc = subprocess.Popen(
        [python_exe, "-m", "whai", "shell"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        cwd=str(tmp_path),
        bufsize=1,
        env=env,
    )

    assert proc.stdin is not None
    assert proc.stdout is not None

    def _read_until(substr: str, timeout_s: float = 10.0) -> str:
        deadline = time.time() + timeout_s
        buf: list[str] = []
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                time.sleep(0.01)
                continue
            buf.append(line)
            if substr in line:
                return "".join(buf)
        return "".join(buf)

    # Wait for shell to start
    _read_until("Shell session starting", timeout_s=15.0)

    def send(cmd: str) -> None:
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()

    # Send all commands in order
    for cmd, _ in commands_expectations:
        send(cmd)

    # Now run whai with DEBUG to log prompts; no real API call needed to get logs
    # Before API call, the provider logs the LLM user message
    send("whai hello -v DEBUG")

    # Collect output for a bit and search for the user message block
    output = _read_until("LLM user message:", timeout_s=20.0)
    # Read a few more lines to capture the content following the header
    extra = []
    start_deadline = time.time() + 5.0
    while time.time() < start_deadline and len(extra) < 500:
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.01)
            continue
        extra.append(line)
        # Stop early once we see tool definitions marker which follows prompt logs
        if "Tool definitions:" in line:
            break

    combined = output + "".join(extra)

    # Assert presence of all commands and their observable outputs
    for _, expected_substrings in commands_expectations:
        for expected in expected_substrings:
            assert expected in combined

    # Cleanup: best-effort terminate
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.kill()
    except Exception:
        pass

