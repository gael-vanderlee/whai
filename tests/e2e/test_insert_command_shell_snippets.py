"""End-to-end tests for insert-command shell snippets (bash).

These tests exercise the real bash insert-command widget function, while
mocking `whai` itself so no LLM calls are made. The goal is to verify that
the readline line is replaced with the command produced by `whai
--command-only`, without touching the user's real shell configuration.
"""

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

from whai.configuration import config_wizard as cw


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("bash") is None,
    reason="Bash insert-command snippet test only runs on POSIX with bash available.",
)
def test_bash_insert_command_snippet_invokes_whai_and_replaces_line(tmp_path: Path):
    """Bash insert-command widget should replace the current line with whai's command.

    This test:
    - Creates a temporary fake `whai` executable that always prints `echo from-whai`.
    - Embeds the real bash insert-command snippet from the config wizard.
    - Sets READLINE_LINE to a natural-language prompt.
    - Calls the widget function `_whai_bash_cmd_only`.
    - Asserts that READLINE_LINE is replaced with the command from `whai`.
    """

    # Create a fake `whai` earlier in PATH that ignores stdin/args and prints a simple command.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_whai = bin_dir / "whai"
    fake_whai.write_text(
        "#!/usr/bin/env bash\n"
        "echo \"echo from-whai\"\n",
        encoding="utf-8",
    )
    fake_whai.chmod(0o755)

    # Get the actual bash snippet so the test uses the same widget implementation.
    snippet = cw._get_insert_command_snippet("bash")
    assert "_whai_bash_cmd_only" in snippet

    # Build a script that:
    # - Prepends our fake `whai` to PATH
    # - Defines the widget function and binding from the snippet
    # - Sets READLINE_LINE and invokes the widget
    # - Prints the final READLINE_LINE for assertion
    script = tmp_path / "bash_insert_test.sh"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            export PATH="{bin_dir}:{os.environ.get("PATH", "")}"

            {snippet}

            READLINE_LINE="list current directory contents"
            READLINE_POINT=${{#READLINE_LINE}}
            _whai_bash_cmd_only
            printf '%s\\n' "$READLINE_LINE"
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)

    # Run the script in a fresh bash process.
    result = subprocess.run(
        ["bash", str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert (
        result.returncode == 0
    ), f"bash exited with {result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"

    # The last line of stdout should be the command printed by our fake `whai`.
    stdout_lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    assert stdout_lines, f"Expected non-empty stdout, got: {result.stdout!r}, stderr={result.stderr!r}"
    assert stdout_lines[-1] == "echo from-whai"


@pytest.mark.skipif(
    os.name == "nt" or shutil.which("zsh") is None,
    reason="Zsh insert-command snippet test only runs on POSIX with zsh available.",
)
def test_zsh_insert_command_snippet_invokes_whai_and_replaces_buffer(tmp_path: Path):
    """Zsh insert-command widget should replace BUFFER with whai's command.

    This test mirrors the bash test but targets the zsh snippet:
    - Creates a fake `whai` that always prints `echo from-whai`.
    - Embeds the real zsh insert-command snippet from the config wizard.
    - Stubs out `zle` so the widget can run in a non-interactive shell.
    - Sets BUFFER to a natural-language prompt and calls `_whai_zsh_cmd_only`.
    - Asserts that BUFFER is replaced with the command from `whai`.
    """

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake_whai = bin_dir / "whai"
    fake_whai.write_text(
        "#!/usr/bin/env zsh\n"
        "echo \"echo from-whai\"\n",
        encoding="utf-8",
    )
    fake_whai.chmod(0o755)

    snippet = cw._get_insert_command_snippet("zsh")
    assert "_whai_zsh_cmd_only" in snippet

    script = tmp_path / "zsh_insert_test.zsh"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env zsh
            export PATH="{bin_dir}:{os.environ.get("PATH", "")}"

            # Stub zle so the widget can call zle -I / redisplay / end-of-line.
            function zle() {{ :; }}

            {snippet}

            BUFFER="list current directory contents"
            CURSOR=${{#BUFFER}}
            _whai_zsh_cmd_only
            print -r -- "$BUFFER"
            """
        ),
        encoding="utf-8",
    )
    script.chmod(0o755)

    result = subprocess.run(
        ["zsh", str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert (
        result.returncode == 0
    ), f"zsh exited with {result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"

    stdout_lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    assert stdout_lines, f"Expected non-empty stdout, got: {result.stdout!r}, stderr={result.stderr!r}"
    assert stdout_lines[-1] == "echo from-whai"

