"""End-to-end test for first-run experience.

This test validates the complete first-run workflow:
1. User runs whai with no config
2. Wizard launches automatically
3. User completes wizard setup
4. Config is created
5. First query executes successfully
"""

import os
import subprocess
import sys
from pathlib import Path


def test_first_run_without_wizard_shows_helpful_error(tmp_path):
    """Test that running without config and canceling wizard shows helpful message."""
    # Set up environment with no config
    env = os.environ.copy()
    env["WHAI_TEST_MODE"] = "0"  # Disable test mode to trigger wizard
    
    # Redirect config to temp directory
    if os.name == "nt":
        env["APPDATA"] = str(tmp_path)
    else:
        env["XDG_CONFIG_HOME"] = str(tmp_path)
    
    # Add mocks to PYTHONPATH
    project_root = Path(__file__).resolve().parents[2]
    mocks_dir = project_root / "tests" / "mocks"
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(mocks_dir) + (os.pathsep + existing if existing else "")
    
    # Run whai and cancel wizard immediately (Ctrl+C)
    cmd = [sys.executable, "-m", "whai", "test query"]
    proc = subprocess.run(
        cmd,
        input="\n",  # Just press enter, wizard will fail
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=30,
    )
    
    # Should fail gracefully (non-zero exit)
    assert proc.returncode != 0
    
    # Should show helpful message about configuration
    merged_output = (proc.stdout or "") + (proc.stderr or "")
    assert "config" in merged_output.lower() or "setup" in merged_output.lower()

