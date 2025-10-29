# Changelog

All notable changes to terma will be documented in this file.

## [Unreleased]

### Changed
- **BREAKING**: Removed all fallback configuration loading. If default config files are missing, terma will now crash with a clear error message instead of using hardcoded fallbacks. This helps detect broken installations early.
- Configuration defaults are now stored in easy-to-edit files in `defaults/` directory:
  - `defaults/config.toml` - Default configuration template
  - `defaults/roles/assistant.md` - Default assistant role
  - `defaults/roles/debug.md` - Default debug role
  - `defaults/system_prompt.txt` - Base system prompt template
- LLM responses now use streaming mode with real-time text display (improved from non-streaming)

### Added
- Created `TESTING.md` with comprehensive guide for setting up API keys
- All default configuration can now be easily customized by editing files in `defaults/` directory
- Integration test now loads API key from terma config if not found in environment
- Comprehensive logging system with debug and production modes:
  - Development: `TERMA_DEBUG=1` enables detailed DEBUG logging
  - Production: Silent by default, only errors logged
  - Third-party logs suppressed by default (use `TERMA_VERBOSE_DEPS=1` to re-enable)
- Added `tests/test_llm_streaming.py` to verify streaming tool call buffering behavior

### Fixed
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

