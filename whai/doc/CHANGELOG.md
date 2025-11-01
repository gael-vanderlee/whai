# Changelog

Format: [YYYY-MM-DD] [category] [scope]: description
Categories: feature, change, fix, docs, security, test, chore
Order: reverse chronological (newest at the top). Add your changes at the top!

[2025-11-01] [fix] [context]: fix tmux context capture to use scrollback buffer instead of visible window; use `-S -200` flag to capture up to 200 lines of scrollback history regardless of terminal window size; resolves issue where context amount varied with window dimensions on WSL
[2025-11-01] [feature] [context]: automatically filter whai command invocation from terminal context; removes last occurrence of command and all subsequent lines from tmux scrollback, or last matching command from history; handles quote differences between terminal and sys.argv, excludes log lines from matching; adds logging to verify filtering behavior
[2025-11-01] [fix] [ui]: display message when command produces no output; show exit code and "empty output" indicator to both user and LLM; prevents confusion when commands succeed silently
[2025-11-01] [test] [cli]: update test_cli_module_help_when_no_args to reflect default query behavior when no args provided
[2025-10-31] [feature] [llm]: add Google Gemini provider support with GEMINI_API_KEY environment variable; default model gemini/gemini-2.5-flash
[2025-10-31] [feature] [config]: add Gemini to config wizard provider list with API key configuration
[2025-10-31] [feature] [config]: add Gemini validation in validate_llm_config function
[2025-10-31] [test] [llm]: add Gemini API key configuration test coverage
[2025-10-31] [docs] [readme]: add Google Gemini configuration example in config section
[2025-10-31] [feature] [cli]: add --version flag to display version; read version from pyproject.toml (no __version__ in __init__.py); use importlib.metadata for installed packages, fallback to reading pyproject.toml in development mode
[2025-10-31] [feature] [config]: add structured RoleMetadata dataclass with validation for role metadata; only allow model and temperature fields with type and range validation; raise InvalidRoleMetadataError for invalid values; warn on unknown fields
[2025-10-31] [change] [config]: refactor model and temperature resolution into resolve_model() and resolve_temperature() functions for clearer precedence logic
[2025-10-31] [change] [logging]: change default logging level from ERROR to WARNING to show warnings by default
[2025-10-31] [feature] [llm]: add LM Studio provider support with OpenAI-compatible API; pass api_base directly to completion() call for custom endpoints
[2025-10-31] [feature] [config]: add LM Studio to provider list in config wizard with default settings (localhost:1234/v1, openai/ prefix)
[2025-10-31] [fix] [main]: fix model resolution to read from provider config instead of top-level llm section
[2025-10-31] [feature] [logging]: add INFO log showing loaded model and source (CLI override, role, provider config, or fallback)
[2025-10-31] [docs] [readme]: add LM Studio setup instructions with server configuration and model naming conventions
[2025-10-31] [docs] [readme]: simplify README for new users; add table of contents and video placeholder; replace generic examples with realistic output examples; emphasize roles as persistent context storage; update installation options (uv tool, pipx, pip, git); remove developer-focused content; streamline FAQ
[2025-10-31] [change] [cli]: update help text to mention shell glob characters (? * []) in addition to spaces and quotes
[2025-10-31] [change] [roles]: make default role instructions more concise
[2025-10-31] [change] [interaction]: refactor execute_command to use utility functions from utils.py for shell and OS detection
[2025-10-31] [change] [interaction]: remove persistent shell sessions; execute commands independently via subprocess.run() to fix Linux TTY suspension and simplify architecture
[2025-10-31] [fix] [linux]: resolve background process suspension issue by removing ShellSession subprocess that took foreground control
[2025-10-31] [change] [system_prompt]: update capabilities to reflect independent command execution; state no longer persists between commands
[2025-10-31] [test] [shell]: remove test_shell_detection.py and ShellSession-related tests; add execute_command tests
[2025-10-31] [fix] [llm]: improve error handling for API authentication, invalid models, and provider errors with user-friendly messages; redact API keys in error output; suggest --interactive-config for configuration issues
[2025-10-31] [change] [cli]: add --log-level/-v option; appears in help; preserve inline -v after query
[2025-10-31] [change] [repo]: rename package from terma to whai; update docs and references
[2025-10-31] [test] [cli]: add subprocess-based CLI E2E tests using mocked `litellm` via tests/mocks; remove sitecustomize hook
[2025-10-31] [docs] [dev]: document subprocess E2E testing approach and TERMA_MOCK_TOOLCALL usage
[2025-10-31] [fix] [context/windows]: use PSReadLine for pwsh history (wrong bash history shown). Detected shell was 'pwsh' after centralization; fallback only handled 'powershell' and 'unknown'. Updated Windows history branch to include 'pwsh'.
[2025-10-31] [change] [logging]: default level ERROR; add -v LEVEL; move performance timings to INFO; keep payload/system/user dumps under DEBUG; remove TERMA_DEBUG handling.
[2025-10-31] [change] [roles]: ship only one default role (default.md). Removed assumptions and tests referencing a built-in debug role.
[2025-10-30] [feature] [roles]: add role management CLI (list, create, edit, remove, set-default, reset-default, use, open-folder, interactive)
[2025-10-30] [feature] [roles]: implement role precedence (cli flag, env TERMA_ROLE, config default, fallback)
[2025-10-30] [feature] [roles]: support session roles via TERMA_ROLE across bash, zsh, fish, PowerShell
[2025-10-30] [change] [roles]: rename built-in role assistant.md to default.md and update references
[2025-10-30] [change] [roles]: make -r/--role optional and apply precedence when omitted
[2025-10-30] [change] [config]: include default role information in config summary
[2025-10-30] [change] [utils]: consolidate utilities into utils.py; standardize shell and OS detection
[2025-10-30] [fix] [windows/pwsh]: run via -EncodedCommand and filter CLIXML for reliable output capture
[2025-10-30] [fix] [shell]: align detected shell in context with ShellSession spawn to prevent timeouts
[2025-10-30] [test] [shell]: add regression tests for shell mismatch and timeouts
[2025-10-30] [feature] [ui]: display active model and role at startup
[2025-10-30] [feature] [context]: include OS, shell, and working directory in system context
[2025-10-30] [feature] [ui]: improve terminal output with Rich; auto-disable in non-TTY; support TERMA_PLAIN
[2025-10-30] [feature] [setup]: interactive configuration wizard for providers and API keys
[2025-10-30] [feature] [llm]: expand providers via LiteLLM (OpenAI, Anthropic, Azure, Ollama)
[2025-10-30] [chore] [deps]: add tomli-w for TOML writing
[2025-10-30] [test] [config]: use ephemeral configuration and TERMA_TEST_MODE for isolation
[2025-10-30] [change] [config]: remove fake auto-generated API keys; use wizard on first run
[2025-10-30] [change] [config]: load_config raises MissingConfigError when config file is missing (ephemeral excluded)
[2025-10-30] [change] [cli]: default per-command timeout 60s; add --timeout flag
[2025-10-30] [change] [config]: remove fallback config loading and fail fast if defaults missing
[2025-10-30] [change] [defaults]: store templates in defaults/ (config, roles, system_prompt)
[2025-10-30] [change] [llm]: enable streaming responses with real-time display
[2025-10-30] [feature] [cli]: support unquoted multi-word queries
[2025-10-30] [docs] [repo]: add TESTING.md and improve README
[2025-10-30] [feature] [logging]: structured logging; suppress noisy third-party logs; improve debug traces
[2025-10-30] [test] [llm]: add streaming behavior tests
[2025-10-30] [fix] [tests]: prevent writes to user config and isolate integration tests
[2025-10-30] [fix] [tests]: remove dangerous commands and fix hanging integration test
[2025-10-30] [fix] [llm]: correct streaming tool call buffering and empty-tools handling
[2025-10-30] [fix] [llm]: handle temperature parameter; drop unsupported params automatically
[2025-10-30] [fix] [ui]: wrap long proposed commands for readability
[2025-10-30] [security] [docs]: document API key security best practices
[2025-10-30] [feature] [core]: initial implementation of core modules, role system, streaming, and tests
