"""Utilities for normalizing captured session logs."""

from __future__ import annotations

import re


def apply_backspaces(text: str) -> str:
    """Apply backspace characters to reconstruct intended text."""
    result: list[str] = []
    for ch in text:
        if ch in ("\b", "\x08"):
            if result:
                result.pop()
        else:
            result.append(ch)
    return "".join(result)


_CSI_PATTERN = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_OSC_PATTERN = re.compile(r"\x1b\][0-9]+;[^\x07\x1b\\]*[\x07\x1b\\]")
_SINGLE_ESC_PATTERN = re.compile(r"\x1b[=><OP]")
_CONTROL_ONLY_PATTERN = re.compile(r"^[\x1b\[\]\x08\r\x07\s]*$")
_SPINNER_CHARS = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_SPINNER_LINE_PATTERN = re.compile(
    rf"^.*[{_SPINNER_CHARS}].*Thinking.*$|^.*Thinking.*\[2K.*$",
    re.IGNORECASE,
)


def normalize_unix_log(text: str) -> str:
    """Normalize Unix/Linux script output by removing terminal artefacts."""
    lines = text.splitlines()
    cleaned: list[str] = []

    for line in lines:
        if "\x08" in line or "\b" in line:
            line = apply_backspaces(line)

        line = _CSI_PATTERN.sub("", line)
        line = _OSC_PATTERN.sub("", line)
        line = _SINGLE_ESC_PATTERN.sub("", line)
        line = re.sub(r"\[\d+m", "", line)
        line = re.sub(r"[\x08\r\x07]", "", line)

        if _SPINNER_LINE_PATTERN.match(line):
            continue

        if _CONTROL_ONLY_PATTERN.match(line):
            continue

        if re.match(rf"^[{_SPINNER_CHARS}\s]*$", line):
            continue

        if re.match(rf"^[{_SPINNER_CHARS}]\s*Thinking\s*$", line, re.IGNORECASE):
            continue

        if re.match(r"^\[2K|\[1A|\[25h|\[25l|\[\?1h|\[\?1l|\[\?2004h|\[\?2004l$", line):
            continue

        if re.search(r"\[2K$|\[1A$|\[25h$|\[25l$", line):
            stripped = re.sub(r"\[2K|\[1A|\[25h|\[25l", "", line).strip()
            if stripped.lower() in ("thinking", ""):
                continue

        line = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", line)

        stripped_line = line.strip()
        if stripped_line in {"%", "\\"}:
            continue

        if not stripped_line:
            continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def normalize_powershell_transcript(text: str) -> str:
    """
    Normalize PowerShell transcript while preserving useful metadata.
    
    This function handles both PowerShell 5.1 and PowerShell 7+ transcript formats,
    which use different numbers of asterisk blocks. It identifies metadata by content
    rather than structure, making it robust to future PowerShell versions.
    """
    lines = text.splitlines()
    cleaned: list[str] = []
    
    # State tracking
    in_asterisk_block = False
    in_initial_metadata = False
    seen_initial_metadata = False
    current_block_is_metadata = False
    metadata: dict[str, str] = {}
    
    # Metadata indicators - these lines only appear in metadata blocks
    METADATA_INDICATORS = {
        "PowerShell transcript start",
        "Windows PowerShell transcript start",
        "Start time:",
        "Username:",
        "RunAs User:",
        "Configuration Name:",
        "Machine:",
        "Host Application:",
        "Process ID:",
        "PSVersion:",
        "PSEdition:",
        "PSCompatibleVersions:",
        "BuildVersion:",
        "CLRVersion:",
        "WSManStackVersion:",
        "PSRemotingProtocolVersion:",
        "SerializationVersion:",
        "OS:",
    }
    
    # End indicators - these mark the end of transcript
    END_INDICATORS = {
        "PowerShell transcript end",
        "Windows PowerShell transcript end",
        "End time:",
    }
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Handle asterisk lines
        if line.strip().startswith("**********************"):
            if not in_asterisk_block:
                # Opening asterisk - look ahead to determine block type
                in_asterisk_block = True
                
                # Check if next block is metadata by looking at content
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    is_metadata = any(indicator in next_line for indicator in METADATA_INDICATORS)
                    is_end = any(indicator in next_line for indicator in END_INDICATORS)
                    
                    if is_metadata and not seen_initial_metadata:
                        # This is the initial metadata block
                        in_initial_metadata = True
                        current_block_is_metadata = True
                    elif is_end:
                        # This is the end block - skip it
                        current_block_is_metadata = True
                    else:
                        # This is content - preserve it
                        current_block_is_metadata = False
                
                i += 1
                continue
            else:
                # Closing asterisk
                if in_initial_metadata:
                    # End of initial metadata - output it
                    if metadata:
                        cleaned.append("--- PowerShell Session ---")
                        for key, value in metadata.items():
                            cleaned.append(f"{key}: {value}")
                        cleaned.append("---")
                        metadata = {}
                    in_initial_metadata = False
                    seen_initial_metadata = True
                
                in_asterisk_block = False
                current_block_is_metadata = False
                i += 1
                continue
        
        # Handle content based on current state
        if in_initial_metadata:
            # Extract metadata
            if line.startswith("PowerShell transcript start") or line.startswith("Windows PowerShell transcript start"):
                metadata["Session"] = "PowerShell transcript"
            elif line.startswith("Start time:"):
                metadata["Start time"] = line.replace("Start time:", "").strip()
            elif line.startswith("Username:"):
                metadata["Username"] = line.replace("Username:", "").strip()
            elif line.startswith("RunAs User:"):
                metadata["RunAs User"] = line.replace("RunAs User:", "").strip()
            elif line.startswith("Machine:"):
                metadata["Machine"] = line.replace("Machine:", "").strip()
            elif line.startswith("OS:"):
                metadata["OS"] = line.replace("OS:", "").strip()
            elif line.startswith("PSVersion:"):
                metadata["PSVersion"] = line.replace("PSVersion:", "").strip()
            i += 1
            continue
        
        # Skip content that's marked as metadata (like end blocks)
        if in_asterisk_block and current_block_is_metadata:
            i += 1
            continue
        
        # Handle command timestamps
        if line.startswith("Command start time:"):
            timestamp = line.replace("Command start time:", "").strip()
            cleaned.append(f"[Command timestamp: {timestamp}]")
            i += 1
            continue
        
        # Skip PowerShell continuation lines
        if line.startswith(">> "):
            i += 1
            continue
        
        # Keep everything else (actual content)
        cleaned.append(line)
        i += 1
    
    # Handle case where we ended in metadata block
    if in_initial_metadata and metadata:
        cleaned.append("--- PowerShell Session ---")
        for key, value in metadata.items():
            cleaned.append(f"{key}: {value}")
        cleaned.append("---")
    
    return "\n".join(cleaned).strip()

