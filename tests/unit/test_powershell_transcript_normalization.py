"""
Tests for PowerShell transcript normalization with real transcripts.

These tests use actual transcript output from PowerShell 5.1 and PowerShell 7
to ensure the normalization function correctly:
1. Extracts metadata (username, version, etc.)
2. Preserves command output
3. Handles both transcript formats
"""

import pytest

from whai.context.normalization import normalize_powershell_transcript


# Real transcript format from PowerShell 7.5.4
POWERSHELL_7_TRANSCRIPT = """**********************
PowerShell transcript start
Start time: 20251120150000
Username: DOMAIN\\TestUser
RunAs User: DOMAIN\\TestUser
Configuration Name: 
Machine: TESTMACHINE (Microsoft Windows NT 10.0.26100.0)
Host Application: C:\\Program Files\\PowerShell\\7\\pwsh.exe
Process ID: 12345
PSVersion: 7.5.4
PSEdition: Core
GitCommitId: 7.5.4
OS: Microsoft Windows 10.0.26100
Platform: Win32NT
PSCompatibleVersions: 1.0, 2.0, 3.0, 4.0, 5.0, 5.1, 6.0, 7.0
PSRemotingProtocolVersion: 2.3
SerializationVersion: 1.1.0.1
WSManStackVersion: 3.0
**********************
Transcript started, output file is C:\\Users\\TestUser\\transcript.txt
PowerShell Version: 7.5.4
Running test commands...

    Directory: C:\\Users\\TestUser\\Documents

Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
d----          15/11/2025    10:00                folder_one
d----          15/11/2025    11:30                folder_two
d----          16/11/2025    09:15                folder_three
Hello from PowerShell!

Drive        : C
Provider     : Microsoft.PowerShell.Core\\FileSystem
ProviderPath : C:\\Users\\TestUser\\Documents
Path         : C:\\Users\\TestUser\\Documents

2 + 2 = 4
TestUser
**********************
PowerShell transcript end
End time: 20251120150500
**********************"""


# Real transcript format from PowerShell 5.1
POWERSHELL_5_TRANSCRIPT = """**********************
Windows PowerShell transcript start
Start time: 20251120150000
Username: DOMAIN\\TestUser
RunAs User: DOMAIN\\TestUser
Configuration Name: 
Machine: TESTMACHINE (Microsoft Windows NT 10.0.26100.0)
Host Application: C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe
Process ID: 54321
PSVersion: 5.1.26100.1000
PSEdition: Desktop
PSCompatibleVersions: 1.0, 2.0, 3.0, 4.0, 5.0, 5.1.26100.1000
BuildVersion: 10.0.26100.1000
CLRVersion: 4.0.30319.42000
WSManStackVersion: 3.0
PSRemotingProtocolVersion: 2.3
SerializationVersion: 1.1.0.1
**********************
Transcript started, output file is C:\\Users\\TestUser\\transcript.txt
PowerShell Version: 5.1.26100.1000
Running test commands...


    Directory: C:\\Users\\TestUser\\Documents


Mode                 LastWriteTime         Length Name
----                 -------------         ------ ----
d-----        11/15/2025  10:00 AM                folder_one
d-----        11/15/2025  11:30 AM                folder_two
d-----        11/16/2025  09:15 AM                folder_three
Hello from PowerShell!

Drive        : C
Provider     : Microsoft.PowerShell.Core\\FileSystem
ProviderPath : C:\\Users\\TestUser\\Documents
Path         : C:\\Users\\TestUser\\Documents

2 + 2 = 4
TestUser
**********************
Windows PowerShell transcript end
End time: 20251120150500
**********************"""


def test_powershell_7_extracts_metadata():
    """Test that metadata is correctly extracted from PowerShell 7 transcript."""
    result = normalize_powershell_transcript(POWERSHELL_7_TRANSCRIPT)
    
    # Should contain metadata section
    assert "--- PowerShell Session ---" in result
    assert "Session: PowerShell transcript" in result
    assert "Start time: 20251120150000" in result
    assert "Username: DOMAIN\\TestUser" in result
    assert "PSVersion: 7.5.4" in result
    assert "---" in result


def test_powershell_7_preserves_command_output():
    """Test that command output is preserved from PowerShell 7 transcript."""
    result = normalize_powershell_transcript(POWERSHELL_7_TRANSCRIPT)
    
    # Should contain all command outputs
    assert "PowerShell Version: 7.5.4" in result
    assert "Running test commands..." in result
    assert "Directory: C:\\Users\\TestUser\\Documents" in result
    assert "folder_one" in result
    assert "folder_two" in result
    assert "folder_three" in result
    assert "Hello from PowerShell!" in result
    assert "Drive        : C" in result
    assert "2 + 2 = 4" in result
    assert "TestUser" in result


def test_powershell_7_excludes_end_metadata():
    """Test that end metadata is excluded from PowerShell 7 transcript."""
    result = normalize_powershell_transcript(POWERSHELL_7_TRANSCRIPT)
    
    # Should NOT contain end metadata
    assert "PowerShell transcript end" not in result
    assert "End time:" not in result


def test_powershell_5_extracts_metadata():
    """Test that metadata is correctly extracted from PowerShell 5.1 transcript."""
    result = normalize_powershell_transcript(POWERSHELL_5_TRANSCRIPT)
    
    # Should contain metadata section
    assert "--- PowerShell Session ---" in result
    assert "Session: PowerShell transcript" in result
    assert "Start time: 20251120150000" in result
    assert "Username: DOMAIN\\TestUser" in result
    assert "PSVersion: 5.1.26100.1000" in result
    assert "---" in result


def test_powershell_5_preserves_command_output():
    """Test that command output is preserved from PowerShell 5.1 transcript."""
    result = normalize_powershell_transcript(POWERSHELL_5_TRANSCRIPT)
    
    # Should contain all command outputs
    assert "PowerShell Version: 5.1.26100.1000" in result
    assert "Running test commands..." in result
    assert "Directory: C:\\Users\\TestUser\\Documents" in result
    assert "folder_one" in result
    assert "folder_two" in result
    assert "folder_three" in result
    assert "Hello from PowerShell!" in result
    assert "Drive        : C" in result
    assert "2 + 2 = 4" in result
    assert "TestUser" in result


def test_powershell_5_excludes_end_metadata():
    """Test that end metadata is excluded from PowerShell 5.1 transcript."""
    result = normalize_powershell_transcript(POWERSHELL_5_TRANSCRIPT)
    
    # Should NOT contain end metadata
    assert "Windows PowerShell transcript end" not in result
    assert "End time:" not in result


def test_both_versions_produce_similar_output():
    """Test that both PowerShell versions produce similar normalized output."""
    result_7 = normalize_powershell_transcript(POWERSHELL_7_TRANSCRIPT)
    result_5 = normalize_powershell_transcript(POWERSHELL_5_TRANSCRIPT)
    
    # Both should have metadata sections
    assert result_7.count("--- PowerShell Session ---") == 1
    assert result_5.count("--- PowerShell Session ---") == 1
    
    # Both should preserve command output
    assert "Hello from PowerShell!" in result_7
    assert "Hello from PowerShell!" in result_5
    
    assert "2 + 2 = 4" in result_7
    assert "2 + 2 = 4" in result_5
    
    # Both should exclude end metadata
    assert "transcript end" not in result_7.lower()
    assert "transcript end" not in result_5.lower()


def test_powershell_7_no_asterisks_in_output():
    """Test that asterisk separators are removed from PowerShell 7 output."""
    result = normalize_powershell_transcript(POWERSHELL_7_TRANSCRIPT)
    
    # Should not contain the asterisk separators
    assert "**********************" not in result


def test_powershell_5_no_asterisks_in_output():
    """Test that asterisk separators are removed from PowerShell 5.1 output."""
    result = normalize_powershell_transcript(POWERSHELL_5_TRANSCRIPT)
    
    # Should not contain the asterisk separators
    assert "**********************" not in result


def test_metadata_comes_before_output_powershell_7():
    """Test that metadata appears before command output in PowerShell 7."""
    result = normalize_powershell_transcript(POWERSHELL_7_TRANSCRIPT)
    
    metadata_pos = result.find("--- PowerShell Session ---")
    output_pos = result.find("Hello from PowerShell!")
    
    assert metadata_pos < output_pos, "Metadata should appear before command output"


def test_metadata_comes_before_output_powershell_5():
    """Test that metadata appears before command output in PowerShell 5.1."""
    result = normalize_powershell_transcript(POWERSHELL_5_TRANSCRIPT)
    
    metadata_pos = result.find("--- PowerShell Session ---")
    output_pos = result.find("Hello from PowerShell!")
    
    assert metadata_pos < output_pos, "Metadata should appear before command output"


def test_complex_output_preserved_powershell_7():
    """Test that complex multi-line output is preserved in PowerShell 7."""
    result = normalize_powershell_transcript(POWERSHELL_7_TRANSCRIPT)
    
    # Check that table-like output is preserved
    lines = result.split("\n")
    
    # Find the directory listing section
    dir_line_idx = None
    for i, line in enumerate(lines):
        if "Directory:" in line:
            dir_line_idx = i
            break
    
    assert dir_line_idx is not None, "Directory listing should be present"
    
    # Next few lines should contain the table headers and data
    remaining_lines = lines[dir_line_idx:]
    assert any("Mode" in line for line in remaining_lines), "Table headers should be preserved"
    assert any("folder_one" in line for line in remaining_lines), "Table data should be preserved"


def test_complex_output_preserved_powershell_5():
    """Test that complex multi-line output is preserved in PowerShell 5.1."""
    result = normalize_powershell_transcript(POWERSHELL_5_TRANSCRIPT)
    
    # Check that table-like output is preserved
    lines = result.split("\n")
    
    # Find the directory listing section
    dir_line_idx = None
    for i, line in enumerate(lines):
        if "Directory:" in line:
            dir_line_idx = i
            break
    
    assert dir_line_idx is not None, "Directory listing should be present"
    
    # Next few lines should contain the table headers and data
    remaining_lines = lines[dir_line_idx:]
    assert any("Mode" in line for line in remaining_lines), "Table headers should be preserved"
    assert any("folder_one" in line for line in remaining_lines), "Table data should be preserved"


@pytest.mark.parametrize("transcript,version", [
    (POWERSHELL_7_TRANSCRIPT, "7.5.4"),
    (POWERSHELL_5_TRANSCRIPT, "5.1.26100.1000"),
])
def test_version_specific_metadata_preserved(transcript, version):
    """Test that version-specific metadata is preserved."""
    result = normalize_powershell_transcript(transcript)
    
    assert f"PSVersion: {version}" in result


@pytest.mark.parametrize("transcript", [
    POWERSHELL_7_TRANSCRIPT,
    POWERSHELL_5_TRANSCRIPT,
])
def test_no_empty_metadata_blocks(transcript):
    """Test that there are no empty metadata blocks in the output."""
    result = normalize_powershell_transcript(transcript)
    
    # Split into sections
    sections = result.split("--- PowerShell Session ---")
    
    # Should have exactly 2 sections (before metadata and after)
    assert len(sections) == 2, "Should have exactly one metadata block"
    
    # The metadata section should not be empty
    metadata_section = sections[1].split("---")[0]
    assert metadata_section.strip(), "Metadata section should not be empty"
