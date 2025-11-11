import builtins
from pathlib import Path
from typing import List

import platform
import shutil
import subprocess

import pytest

from whai.shell.session import launch_shell_session


def test_bsd_variant_uses_qF_and_no_dashdash(monkeypatch, tmp_path: Path):
    """Test that BSD script variant uses -qF flags without -- separator."""
    # Force script present
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/script" if name == "script" else None)
    # Force platform darwin
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    # Force detector to say 'bsd'
    from whai.shell import session as sess
    monkeypatch.setattr(sess, "_detect_script_variant", lambda _: "bsd")

    called_cmd: List[str] = []
    def fake_call(cmd, env=None):
        nonlocal called_cmd
        called_cmd = cmd
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)

    log_path = tmp_path / "session.log"
    rc = launch_shell_session(shell="zsh", log_path=log_path, delete_on_exit=False)
    assert rc == 0
    # Expect: script -qF <log> zsh -l
    assert called_cmd[:2] == ["/usr/bin/script", "-qF"]
    assert called_cmd[2] == str(log_path)
    assert "--" not in called_cmd
    assert "-qf" not in called_cmd
    assert "zsh" in called_cmd
    assert called_cmd[-1] == "-l"


def test_unknown_variant_falls_back_to_bsd_style(monkeypatch, tmp_path: Path):
    """Test that unknown script variant falls back to BSD-style flags."""
    # Force script present
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/script" if name == "script" else None)
    # Force platform darwin
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    # Force detector to say 'unknown'
    from whai.shell import session as sess
    monkeypatch.setattr(sess, "_detect_script_variant", lambda _: "unknown")

    called_cmd: List[str] = []
    def fake_call(cmd, env=None):
        nonlocal called_cmd
        called_cmd = cmd
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)

    log_path = tmp_path / "session.log"
    rc = launch_shell_session(shell="zsh", log_path=log_path, delete_on_exit=False)
    assert rc == 0
    # Expect: script -qF <log> zsh -l
    assert called_cmd[:2] == ["/usr/bin/script", "-qF"]
    assert called_cmd[2] == str(log_path)
    assert "--" not in called_cmd
    assert "-qf" not in called_cmd
    assert "zsh" in called_cmd
    assert called_cmd[-1] == "-l"





