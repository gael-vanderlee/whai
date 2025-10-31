# PowerShell Command Execution Issue

## Target Command (primary objective)

When using whai normally, I noticed a command generated when running `python -m whai list the 3 biggest directories here --no-context` never worked.
This is the exact command that must run successfully:

```
Get-ChildItem -Directory | ForEach-Object { $sum = (Get-ChildItem -Path $_.FullName -Recurse -Force -ErrorAction SilentlyContinue | Where-Object {!$_.PSIsContainer} | Measure-Object -Property Length -Sum).Sum; [PSCustomObject]@{Name=$_.Name; SizeBytes=$sum} } | Sort-Object SizeBytes -Descending | Select-Object -First 3 | Select-Object Name,@{Name='Size';Expression = { if ($_.SizeBytes -ge 1GB) { '{0:N2} GB' -f ($_.SizeBytes/1GB) } elseif ($_.SizeBytes -ge 1MB) { '{0:N2} MB' -f ($_.SizeBytes/1MB) } else { '{0:N0} KB' -f ($_.SizeBytes/1KB) } } }
```

When run manually in the user's PowerShell in the whai project root directory, this command completes in about 2 seconds. Therefore, the slowness/timeout observed through `whai` is not due to the command's inherent complexity; the program should be able to execute it within a 5-second timeout.

## Issue Description

PowerShell commands executed via `whai.interaction.ShellSession` were timing out and not returning expected output. The tool would wait for a completion marker that never appeared, eventually hitting the timeout.

## Environment

- OS: Windows 11
- Shell: PowerShell (powershell.exe)
- Python subprocess with `text=True` mode
- Project: E:\PycharmProjects\whai

## Initial Symptom

Running: `python -m whai "list the 3 biggest directories here" --no-context`

Result: Command timed out after 60 seconds with error:
```
RuntimeError: Command timed out after 60 seconds
```

Debug output showed:
- Marker: `___WHAI_CMD_DONE_916193___`
- Command submitted successfully
- No stdout lines captured
- Timeout occurred

## Reproduction Setup

Created `playground/repro_powershell.py` to test `ShellSession` directly:
If we get this to run with the original command, than we're good.

## Testing Phase 1: Line Endings

### Test 1.1: Simple command with LF endings
Command: `Write-Output 'Hello from PowerShell'`
Line ending: `\n` (LF only)
Marker sent with: `echo <marker>\n`

Result:
- Garbled output: "WDONE_" or "ONE_" instead of full text
- Marker never found
- Timeout after 10s
- Debug showed: Only 1-2 stdout lines captured containing fragments

### Test 1.2: Simple command with CRLF endings  
Command: `Write-Output 'Hello from PowerShell'`
Line ending: Changed to `\r\n` (CRLF)
Marker sent with: `Write-Output <marker>\r\n`

Result:
- Still garbled initially
- Suggested encoding mismatch

## Testing Phase 2: Encoding

### Test 2.1: Explicit UTF-8 encoding
Changed subprocess.Popen to include:
```python
encoding="utf-8"
```

Result:
- Still garbled output
- Characters appearing as fragments

### Test 2.2: UTF-16LE encoding
Changed to:
```python
encoding="utf-16-le"
```

Result:
- Different error: `'charmap' codec can't encode characters`
- stdin.write() failed because stdin expects different encoding than stdout

### Test 2.3: System default encoding
Removed explicit encoding, used system default

Result:
- Still garbled

## Testing Phase 3: Buffering

### Test 3.1: Change from unbuffered to line buffered
Original: `bufsize=0` (unbuffered)
Changed to: `bufsize=1` (line buffered)

Command: `Write-Output 'Hello from PowerShell'`

Result: **SUCCESS**
```
[repro] STDOUT:
Hello from PowerShell
PS E:\PycharmProjects\whai> 

[repro] STDERR:
```

Marker was found. Command executed and completed.

**Key finding**: Combination of CRLF line endings (`\r\n`) + line buffering (`bufsize=1`) + system encoding = working execution

## Testing Phase 4: Complex Commands

### Test 4.1: Directory listing with Format-Table
Command:
```powershell
Get-ChildItem -Directory | Select-Object Name, @{Name='SizeMB';Expression={(Get-ChildItem -Path $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB}} | Sort-Object SizeMB -Descending | Select-Object -First 3 | Format-Table -AutoSize
```

Timeout: 15 seconds

Result:
- Timeout after 15 seconds
- No output captured
- Marker never found

### Test 4.2: Same command without Format-Table -AutoSize
Command: Same pipeline but ending with `| Select-Object -First 3` (no Format-Table)

Result:
- Partial success
- Returned some data but incomplete/unformatted:
```
tests       0.285097122192383
```

### Test 4.3: Fast command with Format-Table
Command: `Get-Process | Select-Object -First 5 Name, CPU, WS | Format-Table -AutoSize`

Timeout: 5 seconds

Result: Initially timed out (before Out-String wrapping was added)

## Testing Phase 5: Out-String Wrapping

### Hypothesis
Format-Table -AutoSize buffers all input to calculate column widths, potentially blocking marker emission.

### Test 5.1: Manual Out-String in command
Command: `Get-ChildItem -Directory | ... | Format-Table -AutoSize | Out-String -Width 4096`

Result:
- Still timed out with heavy recursive directory scan
- Suggested the scan itself was slow, not necessarily a Format-Table issue

### Test 5.2: Automatic wrapping in interaction.py
Modified `execute_command()` to wrap ALL PowerShell commands:
```python
wrapped_cmd = f"& {{ {command} }} | Out-String -Width 4096"
full_command = f"{wrapped_cmd}\r\nWrite-Output {marker}\r\n"
```

Command: `Get-Process | Select-Object -First 5 Name, CPU, WS | Format-Table -AutoSize`

Result: **SUCCESS**
```
Name            CPU              WS
----            ---              --
AggregatorHost             15798272
AlienFXSubAgent 6.5625    176422912
...
```

Table formatted correctly, marker found, command completed.

**Issue**: Extra "PS>" prompts appearing in output, and command echo visible

## Testing Phase 6: Prompt Suppression

### Test 6.1: PowerShell initialization
Added init script at shell startup:
```powershell
function prompt {''}
$ProgressPreference='SilentlyContinue'
Set-PSReadLineOption -HistorySaveStyle SaveNothing -ErrorAction SilentlyContinue
```

Drain output for 0.5 seconds after init.

### Test 6.2: Fast command after init
Command: `Get-Process | Select-Object -First 5 Name, CPU, WS | Format-Table -AutoSize`

Result:
- Command completed
- Return code: 0
- STDOUT: Only 6 characters: `\n\n\nPS>\n`
- **No table output captured**

This is the current state - the command appears to execute but output is missing.

## Current Code State

### whai/interaction.py - PowerShell startup (lines ~48-74)
```python
if "powershell" in shell_lower or "pwsh" in shell_lower:
    self.process = subprocess.Popen(
        [self.shell, "-NoProfile", "-NoLogo"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
    )
    # Initialize PowerShell: suppress prompt and progress bars
    init_script = (
        "function prompt {''}\r\n"
        "$ProgressPreference='SilentlyContinue'\r\n"
        "Set-PSReadLineOption -HistorySaveStyle SaveNothing -ErrorAction SilentlyContinue 2>$null\r\n"
        "$null\r\n"
    )
    self.process.stdin.write(init_script)
    self.process.stdin.flush()
    # Drain all initialization output for up to 0.5s
    time.sleep(0.2)
    drain_deadline = time.time() + 0.5
    while time.time() < drain_deadline:
        line = self._read_line_with_timeout(self.process.stdout, 0.02)
        if line is None:
            break
```

### whai/interaction.py - Command execution (lines ~144-148)
```python
elif "powershell" in shell_lower or "pwsh" in shell_lower:
    # PowerShell needs CRLF line endings for interactive stdin
    # Wrap command to force output materialization (prevents Format-Table hangs)
    wrapped_cmd = f"& {{ {command} }} | Out-String -Width 4096"
    full_command = f"{wrapped_cmd}\r\nWrite-Output {marker}\r\n"
```

## Confirmed Facts

1. ✅ PowerShell requires CRLF (`\r\n`) line endings for interactive stdin
2. ✅ Line buffering (`bufsize=1`) is required - unbuffered mode (`bufsize=0`) causes issues
3. ✅ Simple commands work with these two fixes
4. ✅ `Format-Table -AutoSize` commands complete successfully when wrapped with `| Out-String -Width 4096`
5. ✅ Recursive directory scanning commands are genuinely slow (30+ seconds on large directories like `.venv`)
6. ❌ Current issue: After adding prompt suppression init, command output disappears (only 6 chars captured: `\n\n\nPS>\n`)
7. ✅ PowerShell echoes subsequent commands when multiple are sent via stdin: when two commands are written in one batch, the second appears as a `PS>...` echo line before execution
8. ✅ Manual single-command test (no marker) returns expected output followed by `PS>` prompt: `MANUAL_TEST_1` then `PS>`
9. ❌ When sending two commands (user command + marker) in sequence, the first command's output is reduced to a lone newline, and the marker is first seen in the echo line (`PS>Write-Output <marker>`) and later as a standalone line
10. ✅ Skipping lines that start with `PS>` avoids falsely detecting the marker in command echoes
11. ✅ Root cause: interactive PowerShell over stdin echoes and reflows multi-line input, causing missing/fragmented output and interleaving with prompts/echoes. Any attempt to send two commands (command + marker) via stdin results in the first command’s output being lost or truncated, and the marker often appearing first in the echo. Scriptblock wrapping and two-phase writes did not fix this because the underlying stdin-driven interactive host still reorders/echoes lines.

## Open Questions

1. Why does the init drain or the wrapped execution cause output to disappear?
2. Is the scriptblock wrapping `& { command }` causing the command to fail silently?
3. Is the drain consuming output from the actual command execution?
4. Do we need a different approach for prompt suppression that doesn't interfere with command output?
5. (Closed) Invoking a single scriptblock `& { <command>; Write-Output <marker> }` still did not reliably produce correct output with the interactive stdin approach.

## Next Steps to Debug

1. Test if removing the `& { }` scriptblock wrapper fixes output (just use `| Out-String -Width 4096` directly)
2. Test if removing the drain loop fixes output
3. Add temporary debug logging inside `execute_command()` to see what lines are being read
4. Test if the init is actually working by checking for prompt in a simple command before init modifications
5. Verify the marker is actually being written and appearing in stdout
6. Implement marker emission within a single invoked scriptblock to avoid echo: `& { <command>; Write-Output <marker> }` and compare behavior with/without `Out-String`
7. If `Format-Table -AutoSize` hangs, re-introduce `| Out-String -Width 4096` inside the scriptblock only for commands that use formatting cmdlets

## Resolution (Confirmed)

We switched PowerShell execution to a non-interactive, one-shot model:

- Construct a script: `& { <command> } | Out-String -Width 4096`
- Encode as UTF-16LE Base64 and run: `powershell.exe -NoProfile -NoLogo -NonInteractive -EncodedCommand <b64>`
- Capture stdout/stderr from the child process; no marker protocol required (process exit is definitive)

Results:
- Simple output: correctly returns `OK_SIMPLE` followed by newlines
- Heavy pipeline (top 3 directories): returns a formatted table within a few seconds
- CLIXML ‘Preparing modules for first use’ progress records sometimes appeared on stderr; we filtered them out (recognized by `#< CLIXML` prefix)

## Plain-English Explanation

- Root issue: PowerShell in an interactive stdin session echoes and rearranges lines when multiple commands are sent. The prompt and command echoes (`PS>...`) interleave with output, and the first command’s output can be dropped or fragmented when followed by a second command (the marker). Attempts to mitigate (CRLF, line buffering, Out-String, prompt suppression, scriptblocks, two-phase writes) did not consistently prevent echo/reflow.
- Solution: Avoid interactive stdin entirely for PowerShell. Execute each command in its own non-interactive PowerShell process using `-EncodedCommand`. This produces stable, fully-materialized output that we can capture reliably.

## Consequences of the Fix

- Pros:
  - Reliable output capture with correct formatting
  - No need for custom markers or prompt suppression
  - Works for both simple and complex pipelines
- Cons:
  - Loss of persistent session state in PowerShell (no cross-command `cd`, environment changes, functions/aliases). Each command runs in a clean process.
  - If persistent state is needed, it must be emulated per command (e.g., prefix with `Set-Location <dir>` or set `$env:FOO` inline).

## Alternatives Considered

- Keep interactive stdin and fight echoes with scriptblocks, Out-String, or phased writes: repeatedly failed due to echo/reflow and timeouts.
- Write temporary `.ps1` files and run via `-File`: likely to work similarly to `-EncodedCommand`, but requires filesystem writes and path hygiene.
- Use named pipes or a PowerShell Remoting runspace: potentially robust, but adds complexity and dependencies beyond the project’s lightweight goals.

## New Debug Artifacts (from repro_powershell.py)

- Manual test (single command):
  - Input: `Write-Output 'MANUAL_TEST_1'`
  - Output lines:
    - `MANUAL_TEST_1\n`
    - `PS>\n`
- Two-command behavior (command + marker):
  - Observed lines:
    - `\n` (first command output reduced to newline)
    - `PS>\n` (prompt)
    - `PS>Write-Output ___WHAI_CMD_DONE_xxx___\n` (echo of marker)
    - `___WHAI_CMD_DONE_xxx___\n` (actual marker output)

