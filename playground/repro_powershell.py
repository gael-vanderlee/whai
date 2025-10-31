import base64
import os
import queue
import random
import subprocess
import sys
import threading
import time

# Ensure we run from the project root (parent of this file's directory)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def main():
    # Helper to run and print results
    def run_and_print(sh: "ShellSession", label: str, cmd: str, timeout_s: int) -> None:
        print(f"\n[repro] ===== {label} =====")
        print(f"[repro] Timeout: {timeout_s}s")
        print(f"[repro] Command: {cmd}")
        try:
            stdout, stderr, rc = sh.execute_command(cmd, timeout=timeout_s)
            print("[repro] RETURN CODE:", rc)
            print(f"[repro] STDOUT ({len(stdout)} chars):\n" + stdout)
            print(f"[repro] STDERR ({len(stderr)} chars):\n" + stderr)
        except Exception as e:
            print("[repro] ERROR:", e)

    # Helper to manually send a command and read output WITHOUT marker
    def manual_test(sh: "ShellSession", cmd: str):
        print(f"\n[repro] ===== MANUAL TEST: {cmd} =====")
        sh.process.stdin.write(f"{cmd}\r\n")
        sh.process.stdin.flush()
        print("[repro] Waiting 0.5s for output...")
        time.sleep(0.5)
        lines = []
        for _ in range(20):
            line = sh._read_line_with_timeout(sh.process.stdout, 0.05)
            if line is None:
                break
            lines.append(line)
            print(f"[repro] Manual read line {len(lines)}: {repr(line)}")
        print(f"[repro] Manual test read {len(lines)} lines total")

    print("[repro] Starting ShellSession(powershell.exe)")
    with ShellSession(shell="powershell.exe") as sh:
        print(f"[repro] Shell session created, PID={sh.process.pid}")

        # MANUAL TEST: Send single command without marker
        manual_test(sh, "Write-Output 'MANUAL_TEST_1'")

        # 1) Simple command — should succeed quickly
        simple_cmd = "Write-Output 'OK_SIMPLE'"
        run_and_print(sh, "SIMPLE COMMAND", simple_cmd, timeout_s=5)

        # 2) Problematic command — the exact one reported to complete in ~2s manually
        problematic_cmd = (
            "Get-ChildItem -Directory | ForEach-Object { $sum = (Get-ChildItem -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue | "
            "Where-Object {!$_.PSIsContainer} | Measure-Object -Property Length -Sum).Sum; [PSCustomObject]@{Name=$_.Name; SizeBytes=$sum} } | "
            "Sort-Object SizeBytes -Descending | Select-Object -First 3 | "
            "Select-Object Name,@{Name='Size';Expression = { if ($_.SizeBytes -ge 1GB) { '{0:N2} GB' -f ($_.SizeBytes/1GB) } elseif ($_.SizeBytes -ge 1MB) { '{0:N2} MB' -f ($_.SizeBytes/1MB) } else { '{0:N0} KB' -f ($_.SizeBytes/1KB) } } }"
        )
        run_and_print(sh, "PROBLEMATIC COMMAND", problematic_cmd, timeout_s=5)


# ================================================================
# Below is a local, minimal copy of interaction.ShellSession
# (embedded here to iterate independently of terma/interaction.py)
# ================================================================


class ShellSession:
    def __init__(self, shell: str = None):
        if shell is None:
            shell = "powershell.exe" if os.name == "nt" else "/bin/bash"
        self.shell = shell
        self.process = None
        self._start_shell()

    def _start_shell(self) -> None:
        shell_lower = self.shell.lower()
        if "powershell" in shell_lower or "pwsh" in shell_lower:
            # Interactive PowerShell, line buffered text IO
            self.process = subprocess.Popen(
                [self.shell, "-NoProfile", "-NoLogo"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # Init: suppress prompt and progress
            init_script = (
                "function prompt {''}\r\n"
                "$ProgressPreference='SilentlyContinue'\r\n"
                "Set-PSReadLineOption -HistorySaveStyle SaveNothing -ErrorAction SilentlyContinue 2>$null\r\n"
                "$null\r\n"
            )
            print(f"[DEBUG INIT] Sending init script:\n{repr(init_script)}")
            self.process.stdin.write(init_script)
            self.process.stdin.flush()
            # Drain short burst of init output
            print("[DEBUG INIT] Sleeping 0.2s before drain...")
            time.sleep(0.2)
            deadline = time.time() + 0.5
            drain_count = 0
            while time.time() < deadline:
                line = self._read_line_with_timeout(self.process.stdout, 0.02)
                if line is None:
                    break
                drain_count += 1
                print(f"[DEBUG INIT] Drained line {drain_count}: {repr(line)}")
        elif os.name == "nt" and "cmd" in shell_lower:
            self.process = subprocess.Popen(
                [self.shell],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
        else:
            self.process = subprocess.Popen(
                [self.shell, "-i"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env={**os.environ, "PS1": ""},
            )

        time.sleep(0.1)
        print("[DEBUG INIT] Shell initialization complete")

    def execute_command(self, command: str, timeout: int = 60):
        # For PowerShell: use streaming hybrid approach with Popen + -NonInteractive -Command
        shell_lower = self.shell.lower()
        if "powershell" in shell_lower or "pwsh" in shell_lower:
            print("[DEBUG PS HYBRID] Using streaming Popen approach for PowerShell")
            # Wrap command to force materialization (prevents Format-Table hangs)
            ps_script = f"& {{ {command} }} | Out-String -Width 4096"
            print(f"[DEBUG PS HYBRID] Script to execute: {repr(ps_script)}")
            
            try:
                # Use Popen to enable streaming
                ps_process = subprocess.Popen(
                    [
                        self.shell,
                        "-NoProfile",
                        "-NoLogo",
                        "-NonInteractive",
                        "-Command",
                        ps_script,
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered for streaming
                    cwd=PROJECT_ROOT,
                )
                
                print(f"[DEBUG PS HYBRID] Process started, PID={ps_process.pid}")
                
                # Stream output as it arrives
                stdout_lines = []
                stderr_lines = []
                start_time = time.time()
                line_count = 0
                
                # Read until process completes
                while True:
                    # Check timeout
                    if time.time() - start_time > timeout:
                        ps_process.kill()
                        ps_process.wait()
                        raise RuntimeError(f"Command timed out after {timeout} seconds")
                    
                    # Check if process has exited
                    returncode = ps_process.poll()
                    
                    # Read from stdout
                    if ps_process.stdout:
                        line = self._read_line_with_timeout(ps_process.stdout, 0.1)
                        if line is not None:
                            line_count += 1
                            print(f"[DEBUG PS HYBRID] stdout line {line_count}: {repr(line[:100])}{'...' if len(line) > 100 else ''}")
                            stdout_lines.append(line)
                            # In real implementation, would yield here for streaming display
                    
                    # Read from stderr
                    if ps_process.stderr:
                        line = self._read_line_with_timeout(ps_process.stderr, 0.01)
                        if line is not None:
                            print(f"[DEBUG PS HYBRID] stderr line: {repr(line[:100])}{'...' if len(line) > 100 else ''}")
                            stderr_lines.append(line)
                    
                    # If process exited and no more output available, break
                    if returncode is not None:
                        # Drain any remaining output
                        print(f"[DEBUG PS HYBRID] Process exited with code {returncode}, draining remaining output")
                        while True:
                            line = self._read_line_with_timeout(ps_process.stdout, 0.05)
                            if line is None:
                                break
                            line_count += 1
                            print(f"[DEBUG PS HYBRID] drain stdout line {line_count}: {repr(line[:100])}")
                            stdout_lines.append(line)
                        while True:
                            line = self._read_line_with_timeout(ps_process.stderr, 0.05)
                            if line is None:
                                break
                            print(f"[DEBUG PS HYBRID] drain stderr line: {repr(line[:100])}")
                            stderr_lines.append(line)
                        break
                
                stdout = "".join(stdout_lines)
                stderr = "".join(stderr_lines)
                
                # Filter CLIXML progress noise
                if stderr.lstrip().startswith("#< CLIXML"):
                    stderr = ""
                
                print(f"[DEBUG PS HYBRID] Completed: rc={returncode} stdout_len={len(stdout)} stderr_len={len(stderr)}")
                return (stdout, stderr, returncode)
                
            except subprocess.TimeoutExpired:
                raise RuntimeError(f"Command timed out after {timeout} seconds")
        
        # For non-PowerShell shells: use existing marker-based approach
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("Shell process is not running")

        marker = f"___TERMA_CMD_DONE_{random.randint(100000, 999999)}___"
        print(f"[DEBUG] Generated marker: {marker}")

        # Windows cmd drive-change convenience
        if os.name == "nt" and "cmd" in shell_lower:
            stripped = command.strip()
            if stripped.lower().startswith("cd ") and "/d" not in stripped.lower():
                parts = stripped.split(maxsplit=1)
                command = f"cd /d {parts[1]}" if len(parts) == 2 else stripped

        if os.name == "nt" and "cmd" in shell_lower:
            full_command = f"{command}\necho {marker}\n"
        else:
            full_command = f"{command}\necho {marker}\n"

        print(f"[DEBUG] Full command to send:\n{repr(full_command)}")
        self.process.stdin.write(full_command)
        self.process.stdin.flush()
        print("[DEBUG] Command written and flushed")

        stdout_lines = []
        stderr_lines = []
        start_time = time.time()
        marker_found = False
        line_count = 0

        while not marker_found:
            if time.time() - start_time > timeout:
                print(f"[DEBUG] TIMEOUT: Read {line_count} stdout lines total")
                raise RuntimeError(f"Command timed out after {timeout} seconds")

            if self.process.stdout:
                line = self._read_line_with_timeout(self.process.stdout, 0.1)
                if line is not None:
                    line_count += 1
                    print(
                        f"[DEBUG] stdout line {line_count} (len={len(line)}): {repr(line)}"
                    )

                    if marker in line:
                        print(f"[DEBUG] MARKER FOUND in line {line_count}")
                        marker_found = True
                        continue

                    print(f"[DEBUG] Adding line {line_count} to stdout_lines")
                    stdout_lines.append(line)

            if self.process.stderr:
                line = self._read_line_with_timeout(self.process.stderr, 0.01)
                if line is not None:
                    print(f"[DEBUG] stderr line: {repr(line)}")
                    stderr_lines.append(line)
        
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
        print(f"[DEBUG] Command completed: stdout_len={len(stdout)} stderr_len={len(stderr)}")
        return (stdout, stderr, 0)

    def _read_line_with_timeout(self, stream, timeout: float):
        if os.name == "nt":
            q: "queue.Queue[str|None]" = queue.Queue()

            def reader():
                try:
                    q.put(stream.readline())
                except Exception:
                    q.put(None)

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            try:
                return q.get(timeout=timeout)
            except queue.Empty:
                return None
        else:
            import select

            ready, _, _ = select.select([stream], [], [], timeout)
            if ready:
                return stream.readline()
            return None

    def close(self):
        if self.process:
            try:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                self.process.kill()
            finally:
                self.process = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


if __name__ == "__main__":
    # Ignore argv; we want an exact, stable reproduction
    main()
