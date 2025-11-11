"""Helpers for reading recorded session logs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple

import re

from whai.configuration.user_config import get_config_dir
from whai.logging_setup import get_logger

from .normalization import normalize_powershell_transcript, normalize_unix_log

logger = get_logger(__name__)


def read_session_context(
    max_bytes: int = 200_000,
    exclude_command: Optional[str] = None,
) -> Optional[str]:
    """Return the merged session context if available."""

    if os.environ.get("WHAI_SESSION_ACTIVE") != "1":
        return None

    sess_dir = get_config_dir() / "sessions"
    is_windows = os.name == "nt"

    transcript_log, whai_log = _locate_logs(sess_dir, is_windows)
    if transcript_log is None and whai_log is None:
        return None

    transcript_content = _read_log(transcript_log)
    whai_content = _read_log(whai_log) if whai_log else ""

    if not transcript_content and not whai_content:
        return None

    combined = _combine_logs(transcript_content, whai_content, is_windows)
    if not combined:
        return None

    combined = _apply_size_limit(combined, max_bytes)
    if not combined:
        return None

    combined = _normalize_platform_log(combined, is_windows)
    combined = _filter_excluded_command(combined, exclude_command)

    log_name = transcript_log.name if transcript_log else "none"
    whai_name = (whai_log.name if whai_log else "none") if is_windows else "none"
    logger.info(
        "Captured session log context from %s and %s (%d bytes)",
        log_name,
        whai_name,
        len(combined),
    )

    return combined


def _locate_logs(sess_dir: Path, is_windows: bool) -> Tuple[Optional[Path], Optional[Path]]:
    transcript_logs = [
        log for log in sess_dir.glob("session_*.log") if not log.name.endswith("_whai.log")
    ]

    if transcript_logs:
        transcript_log = sorted(transcript_logs, reverse=True)[0]
    else:
        transcript_log = None

    if is_windows:
        if transcript_log is not None:
            whai_log = transcript_log.parent / f"{transcript_log.stem}_whai{transcript_log.suffix}"
        else:
            whai_candidates = sorted(sess_dir.glob("session_*_whai.log"), reverse=True)
            whai_log = whai_candidates[0] if whai_candidates else None
    else:
        whai_log = None

    return transcript_log, whai_log


def _read_log(path: Optional[Path]) -> str:
    if path is None or not path.exists():
        return ""

    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size <= 0:
                return ""
            f.seek(0, os.SEEK_SET)
            return f.read().decode(errors="ignore")
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug("Could not read session log %s: %s", path, exc)
        return ""


def _combine_logs(transcript: str, whai: str, is_windows: bool) -> str:
    transcript = transcript.strip()
    whai = whai.strip()

    if is_windows and transcript and whai:
        return _merge_transcript_and_whai_log(transcript, whai)
    if transcript:
        return transcript
    if is_windows and whai:
        return whai
    return ""


def _apply_size_limit(content: str, max_bytes: int) -> str:
    if len(content.encode("utf-8")) <= max_bytes:
        return content

    combined_bytes = content.encode("utf-8")
    truncated = combined_bytes[-max_bytes:].decode("utf-8", errors="ignore")
    first_newline = truncated.find("\n")
    if first_newline >= 0:
        truncated = truncated[first_newline + 1 :]
    return truncated.strip()


def _normalize_platform_log(content: str, is_windows: bool) -> str:
    if is_windows and "PowerShell transcript start" in content:
        return normalize_powershell_transcript(content)
    if "Script started on" in content or "Script started," in content:
        return normalize_unix_log(content)
    return content


def _filter_excluded_command(content: str, exclude_command: Optional[str]) -> str:
    """Filter out the excluded command and everything after it.
    
    Finds the last 'whai' occurrence in the content (starting from the end),
    extracts the command from that line, and if it matches, removes everything
    from that line onwards.
    """
    if not exclude_command:
        return content

    normalized_exclude = _normalize_command_for_matching(exclude_command)
    if not normalized_exclude:
        return content

    lines = content.splitlines()
    
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        line_lower = line.lower()
        
        if "whai" not in line_lower:
            continue
        
        extracted_cmd = _extract_command_from_line(line)
        if not extracted_cmd:
            continue
        
        normalized_line = _normalize_command_for_matching(extracted_cmd)
        
        if normalized_line == normalized_exclude:
            excluded_count = len(lines) - i
            logger.info(
                "Filtered context: excluded %d lines using exclude_command='%s' (normalized to '%s')",
                excluded_count,
                exclude_command,
                normalized_exclude
            )
            return "\n".join(lines[:i]).strip()
        elif normalized_line.strip() == normalized_exclude.strip():
            excluded_count = len(lines) - i
            logger.info(
                "Filtered context: excluded %d lines using exclude_command='%s' (normalized to '%s')",
                excluded_count,
                exclude_command,
                normalized_exclude
            )
            return "\n".join(lines[:i]).strip()
    
    logger.info(
        "No lines excluded with exclude_command='%s' (normalized to '%s')",
        exclude_command,
        normalized_exclude,
    )
    return content


def _extract_command_from_line(line: str) -> Optional[str]:
    """Extract the command portion from a line, starting from the last 'whai' occurrence.
    
    Works with any prompt format by finding the last 'whai' word in the line.
    """
    line_lower = line.lower()
    whai_pos = line_lower.rfind("whai")
    if whai_pos == -1:
        return None
    
    return line[whai_pos:].strip()


def _normalize_command_for_matching(cmd: str) -> str:
    """Normalize a command string for matching by removing quotes, ANSI codes, and normalizing whitespace."""
    # Strip ANSI escape sequences first (before other processing)
    cmd = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", cmd)  # CSI sequences like \x1b[?1l, \x1b[0m
    cmd = re.sub(r"\x1b\][0-9]+;[^\x07\x1b\\]*[\x07\x1b\\]", "", cmd)  # OSC sequences
    cmd = re.sub(r"\x1b[=><OP]", "", cmd)  # Single escape sequences like \x1b>
    cmd = re.sub(r"\[\d+m", "", cmd)  # Color codes like [0m, [31m that might remain
    cmd = re.sub(r"[\x08\r\x07]", "", cmd)  # Control characters (backspace, carriage return, bell)
    
    # Normalize whitespace
    cmd = re.sub(r"\s+", " ", cmd).strip()

    # Remove quotes
    cmd = re.sub(r' "([^"]+)"', r" \1", cmd)
    cmd = re.sub(r'"([^"]+)" ', r"\1 ", cmd)
    cmd = re.sub(r'^"([^"]+)"', r"\1", cmd)
    cmd = re.sub(r'"([^"]+)"$', r"\1", cmd)

    cmd = re.sub(r" '([^']+)'", r" \1", cmd)
    cmd = re.sub(r"'([^']+)' ", r"\1 ", cmd)
    cmd = re.sub(r"^'([^']+)'", r"\1", cmd)
    cmd = re.sub(r"'([^']+)'$", r"\1", cmd)

    # Final whitespace normalization
    return re.sub(r"\s+", " ", cmd).strip()


def _merge_transcript_and_whai_log(transcript_content: str, whai_content: str) -> str:
    if not whai_content:
        return transcript_content

    whai_blocks = _parse_whai_log_blocks(whai_content)
    transcript_lines = transcript_content.splitlines()
    transcript_commands = _extract_whai_commands_from_transcript(transcript_lines)

    if not transcript_commands:
        return f"{transcript_content}\n\n{whai_content}".strip()

    result_lines = []
    whai_block_idx = 0
    pending_output: Optional[str] = None
    transcript_cmd_map = {idx: cmd for idx, cmd in transcript_commands}

    if whai_blocks and whai_blocks[0][0] == "__PRE_COMMAND__":
        _, pre_content = whai_blocks[0]
        result_lines.append(pre_content)
        whai_block_idx = 1

    for i, line in enumerate(transcript_lines):
        result_lines.append(line)

        if _is_prompt_line(line) and pending_output is not None:
            result_lines.append(pending_output)
            pending_output = None

        if i not in transcript_cmd_map:
            continue

        normalized_cmd = transcript_cmd_map[i]
        if normalized_cmd == "__PRE_COMMAND__":
            continue

        matched_idx = _match_whai_block(normalized_cmd, whai_blocks, whai_block_idx)

        if matched_idx is not None:
            _, output = whai_blocks[matched_idx]
            next_is_prompt = i + 1 < len(transcript_lines) and _is_prompt_line(
                transcript_lines[i + 1]
            )
            if next_is_prompt:
                pending_output = output
            else:
                result_lines.append(output)
            whai_block_idx = matched_idx + 1
        else:
            logger.warning(
                "No matching whai output found for command: %s (line %d)",
                normalized_cmd,
                i,
            )

    if pending_output is not None:
        result_lines.append(pending_output)

    if whai_block_idx < len(whai_blocks):
        result_lines.append("\n--- UNMATCHED WHAI OUTPUT ---")
        for idx in range(whai_block_idx, len(whai_blocks)):
            cmd, output = whai_blocks[idx]
            if cmd == "__PRE_COMMAND__":
                continue
            result_lines.append(f"Command: {cmd}")
            result_lines.append(output)
            result_lines.append("")

    return "\n".join(result_lines)


def _match_whai_block(
    normalized_cmd: str,
    whai_blocks: list[tuple[str, str]],
    start_idx: int,
) -> Optional[int]:
    for idx in range(start_idx, len(whai_blocks)):
        cmd, _ = whai_blocks[idx]
        if cmd == "__PRE_COMMAND__":
            continue
        if normalized_cmd == cmd:
            return idx

    # Fallback for chained commands
    parts = normalized_cmd.split()
    if "whai" not in parts:
        return None

    whai_index = parts.index("whai")
    command_segment = " ".join(parts[whai_index:])

    for idx in range(start_idx, len(whai_blocks)):
        cmd, _ = whai_blocks[idx]
        if cmd == "__PRE_COMMAND__":
            continue
        if cmd in command_segment or command_segment in cmd:
            return idx

    return None


def _parse_whai_log_blocks(whai_content: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    current_command: Optional[str] = None
    current_output: list[str] = []
    pre_command: list[str] = []

    for line in whai_content.splitlines():
        stripped = line.strip()
        if stripped.startswith("$ "):
            if current_command is not None:
                output_text = "\n".join(current_output).strip()
                if output_text:
                    blocks.append((current_command, output_text))
            current_command = _normalize_command_for_matching(stripped[2:].strip())
            current_output = []
        elif current_command is not None:
            current_output.append(line)
        else:
            pre_command.append(line)

    if current_command is not None:
        output_text = "\n".join(current_output).strip()
        if output_text:
            blocks.append((current_command, output_text))

    pre_text = "\n".join(pre_command).strip()
    if pre_text:
        blocks.insert(0, ("__PRE_COMMAND__", pre_text))

    return blocks


def _extract_whai_commands_from_transcript(transcript_lines: list[str]) -> list[tuple[int, str]]:
    """Extract whai commands from transcript lines.
    
    Works with any prompt format by finding where 'whai' appears in each line.
    """
    commands: list[tuple[int, str]] = []
    for idx, line in enumerate(transcript_lines):
        extracted_cmd = _extract_command_from_line(line)
        if not extracted_cmd:
            continue

        normalized = _normalize_command_for_matching(extracted_cmd)
        if normalized:
            commands.append((idx, normalized))

    return commands


def _is_prompt_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("[whai]") and stripped.endswith(">"):
        return True
    if stripped in {"PS>", "$"}:
        return True
    return False

