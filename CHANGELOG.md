# Changelog

All notable changes to terma will be documented in this file.

## [Unreleased]

### Fixed
- PowerShell execution reliability on Windows by switching to non-interactive `-EncodedCommand` in `interaction.py`. This avoids stdin echo/reflow and ensures correctly formatted output capture for both simple and complex pipelines. CLIXML progress noise is filtered from stderr.
- **Critical: Shell mismatch causing timeouts and command failures on Windows**
  - **Root Cause**: Shell detection in `context.py` detected PowerShell from environment variables for the system prompt, but `ShellSession` in `interaction.py` was spawned with default `cmd.exe` on Windows. This caused PowerShell commands suggested by the LLM to fail or timeout.
  - **Symptoms**: 
    - PowerShell cmdlets like `Get-ChildItem` would fail with "not recognized as internal or external command"
    - Nested PowerShell invocations (e.g., `powershell -Command "..."`) had escaping issues between cmd.exe and PowerShell
    - Commands would timeout after 60 seconds even for simple operations
  - **Fix**:
    - Added `get_shell_executable()` function in `context.py` to detect shell and resolve executable path
    - Updated `main.py` to call `get_shell_executable()` and pass the result to `ShellSession`
    - Fixed PowerShell subprocess initialization in `interaction.py` to use `-NoProfile -NoLogo -Command "-"` instead of `-i` flag
    - Added fallback to `cmd` on Windows when no specific shell is detected (instead of `unknown`)
  - **Testing**: Added comprehensive unit tests in `tests/test_shell_detection.py` with regression test for the mismatch bug
  - **Impact**: PowerShell commands now execute correctly without timeouts or escaping issues

### Added
- System prompt caveat noting that PowerShell runs as one-shot processes; cross-command state (location, env vars, aliases) does not persist and should be set inline when needed.
- **Display loaded model and role**: terma now prints the active model and role at startup for transparency (October 30, 2024)
- **Enriched System Context**: LLM now receives OS, shell, and working directory information (October 30, 2024)
  - Context note includes OS name and version (e.g., "Windows 11", "Linux 5.15")
  - Shell type detection (bash, zsh, PowerShell, cmd.exe)
  - Current working directory path
  - Improves LLM's ability to provide platform-specific and context-aware assistance
- **Pretty Terminal Output**: Enhanced visual experience with Rich library (October 30, 2024)
  - Spinner animation while waiting for LLM responses
  - Syntax-highlighted code blocks for shell commands and output
  - Colored panels for errors, warnings, and info messages
  - Auto-disables in non-TTY environments (pipes, CI/CD)
  - Environment variable `TERMA_PLAIN=1` to force plain text output
  - Maintains backward compatibility - all plain text content preserved for LLM
- **Interactive Configuration Wizard**: New `terma --interactive-config` flag provides guided setup for API keys and provider settings
  - Automatically launches on first run when configuration is missing
  - Supports quick-setup for first-time users
  - Allows adding, editing, removing, and setting default providers
  - Masks API keys in configuration summaries for security
- Enhanced provider support with full LiteLLM compatibility:
  - OpenAI with default model `gpt-4o-mini`
  - Anthropic with Claude 3.5 Sonnet
  - Azure OpenAI with api_base, api_version, and api_key support
  - Ollama for local models
- Added `tomli-w` dependency for TOML file writing
- Test suite now uses ephemeral configuration to prevent disk writes during testing
- New `TERMA_TEST_MODE` environment variable for test isolation

### Changed
- **BREAKING**: Configuration no longer auto-generates with fake API keys. Interactive wizard runs on first use instead
- **BREAKING**: `load_config()` now raises `MissingConfigError` when config file is missing (unless in ephemeral mode)
- Default per-command timeout is now 60 seconds, configurable via CLI
- **BREAKING**: Removed all fallback configuration loading. If default config files are missing, terma will now crash with a clear error message instead of using hardcoded fallbacks. This helps detect broken installations early.
- Configuration defaults are now stored in easy-to-edit files in `defaults/` directory:
  - `defaults/config.toml` - Default configuration template
  - `defaults/roles/assistant.md` - Default assistant role
  - `defaults/roles/debug.md` - Default debug role
  - `defaults/system_prompt.txt` - Base system prompt template
- LLM responses now use streaming mode with real-time text display (improved from non-streaming)

### Added
- CLI `--timeout` flag to control per-command timeout (e.g., `--timeout 30`)
- **Unquoted argument support**: Users can now type `terma what is that file` without quotes around multi-word queries. Both `terma what is this` and `terma "what is this"` work identically. This improves usability across all platforms (Windows, Linux, Mac) while maintaining full backward compatibility.
- Created `TESTING.md` with comprehensive guide for setting up API keys
- All default configuration can now be easily customized by editing files in `defaults/` directory
- Integration test now loads API key from terma config if not found in environment
- Comprehensive logging system with debug and production modes:
  - Development: `TERMA_DEBUG=1` enables detailed DEBUG logging
  - Production: Silent by default, only errors logged
  - Third-party logs suppressed by default (use `TERMA_VERBOSE_DEPS=1` to re-enable)
- Added `tests/test_llm_streaming.py` to verify streaming tool call buffering behavior

### Fixed
- Unit tests no longer write configuration files to user's config directory
- Integration tests now properly isolated with auto-applied test fixture
- Removed dangerous `rm -rf /` command from tests
- Fixed hanging integration test by properly mocking shell session and LLM responses
- Integration test now completes in ~5 seconds instead of hanging indefinitely
- **Fixed streaming tool call handling**: LLM provider now correctly tracks tool call id and name across chunks even when subsequent chunks have `None` for both fields (real OpenAI streaming behavior)
- Fixed LLM API calls when tools=[] is passed - now properly omits tools parameter instead of passing empty list
- Real API integration tests now work correctly with API keys from terma config
- Fixed JSON parsing errors in streaming mode when tool call arguments arrive in chunks:
  - Tool call arguments now properly buffered across multiple chunks
  - Only emits tool calls when JSON is complete and contains a non-empty command
- Improved system prompt to explicitly instruct LLM to use execute_shell tool instead of showing commands in markdown
  - Prevents duplicate emissions and empty command errors
- **Fixed temperature parameter handling**:
  - Temperature is now optional (defaults to None, letting models use their default)
  - Added `drop_params=True` to automatically drop unsupported parameters for models
  - Fixes `UnsupportedParamsError` for models that don't support temperature (like some gpt-5 variants)
- Note: LiteLLM doesn't provide reliable upfront model validation; invalid models will be caught when making API calls
- Fixed noisy third-party logs (LiteLLM, OpenAI, httpcore, etc.) flooding debug output
- Added detailed error tracebacks to help debug issues when they occur
 - Proposed command panel now wraps long commands across lines for better readability

### Security
- Documented API key security best practices in TESTING.md

## [0.1.0] - Initial Implementation

### Added
- Core terma functionality with 7 implemented phases:
  1. Project foundation (uv, pyproject.toml, file structure)
  2. Configuration module with config.toml and role loading
  3. Context capture from tmux or shell history
  4. LLM module with LiteLLM and tool calling
  5. Shell session management and approval loop
  6. Main CLI integrating all modules
  7. Role system, integration tests, and polish

- Features:
  - Natural language command generation
  - Post-mortem analysis (with tmux)
  - Collaborative execution with approval loop
  - Context-aware responses
  - Multi-LLM support (OpenAI, Anthropic, local models)
  - Customizable roles
  - Stateful shell sessions

- Test coverage:
  - 73 unit tests
  - 2 integration tests (marked separately)
  - Platform-specific tests for Windows/Unix

- Documentation:
  - Comprehensive README.md
  - TESTING.md for API setup
  - Inline code documentation

