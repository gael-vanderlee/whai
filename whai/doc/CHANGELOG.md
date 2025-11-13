# Changelog

Format: [YYYY-MM-DD] [category] [scope]: short and concise description of the high level changes.
Categories: feature, change, fix, docs, security, test, chore
Order: reverse chronological (newest at the top).
When making changes, always add them at the very top of the "In Progress" section.
When ready to publish, change to version header: `## vX.Y.Z` (where X.Y.Z is your version) with empty lines above and below.

## In Progress

[2025-11-13] [change] [roles]: add default provider placeholder to new role template
[2025-11-13] [feature] [release]: add helper to extract and format release notes from the changelog
[2025-11-13] [change] [ci]: update GitHub release workflow to use release notes helper and prioritize categories
[2025-11-13] [test] [release]: add unit tests covering release note formatting and ordering
[2025-11-13] [docs] [dev]: document automated release notes formatting in developer guide

## v0.8.0

[2025-11-13] [change] [prompt]: add separators around examples and explicit role instructions header in system prompt
[2025-11-13] [fix] [context]: record command timeouts and failures in session log so subsequent whai calls receive deep context
[2025-11-13] [test] [context]: add unit and integration coverage for session timeout logging
[2025-11-13] [fix] [execution]: fix Windows command timeout by removing shell=True; subprocess.run with shell=True creates nested process hierarchy (cmd.exe → PowerShell) where killing parent doesn't terminate child, causing timeouts to fail; invoke shell directly to allow proper timeout handling
[2025-11-13] [fix] [execution]: fix UnicodeDecodeError warnings in subprocess calls by explicitly using utf-8 encoding with errors=replace; Windows defaults to cp1252 which fails on UTF-8 bytes from subprocess output
[2025-11-13] [feature] [ui]: add spinner indicator during command execution; shows "Executing command..." with animated spinner while shell commands run
[2025-11-13] [test] [context]: fix test_get_context_combines_history_and_additional_context to properly mock session context check
[2025-11-13] [feature] [cli]: warn users when unrecognized flags are passed inline; flags are still passed to model as part of query
[2025-11-12] [chore] [license]: add MIT license file to repository

## v0.7.2

[2025-11-12] [docs] [readme]: document available providers in role definition section; add help command references for CLI options and role commands
[2025-11-12] [feature] [roles]: add provider field to role frontmatter; roles can specify provider to use models from non-default providers; precedence: CLI override > role metadata > default provider; resolve_provider() returns tuple with source for logging
[2025-11-12] [feature] [ci]: add GitHub Actions workflow for automated releases; tests across Python versions, validates version, builds package, publishes to TestPyPI and PyPI, creates GitHub releases with changelog extraction
[2025-11-12] [docs] [dev]: update release documentation with automated pipeline instructions and test mode workflow
[2025-11-12] [change] [changelog]: add version headers to changelog based on git tags; update format guidelines for version sections
[2025-11-12] [change] [roles]: move new role template to defaults folder; template now loaded from whai/defaults/roles/new.md with placeholder substitution for role name and default model
[2025-11-12] [test] [config]: fix tests to match actual default role content instead of hardcoded strings

## v0.7.1

[2025-11-12] [fix] [config]: fix config wizard to display summary on each loop iteration
[2025-11-12] [feature] [logging]: add info log when role is loaded from file
[2025-11-11] [fix] [context]: fix command exclusion in whai shell sessions; strip ANSI escape sequences from extracted commands before matching to prevent exclusion failures when commands contain terminal control codes
[2025-11-11] [test] [tests]: reorganize tests into unit/integration/e2e/performance/security subdirectories; add behavioral tests for CLI parsing, error recovery, multi-provider, cross-platform, performance, security; remove implementation-detail tests; mark Windows-only tests for SessionLogger
[2025-11-11] [fix] [shell]: fix shell session script detection for BSD compatibility on macOS; detect script variant (util-linux vs BSD) and use appropriate flags (-qF for BSD, -qf for util-linux)
[2025-11-11] [fix] [cli]: improve inline flag parsing to support flags placed after query; extract --role, --model, --provider, --temperature, --timeout, --no-context, and -v/-vv from query tokens

## v0.6.0

[2025-11-07] [fix] [context]: fix tmux empty capture detection; when tmux is active but capture is empty (new session), correctly identify tmux as active instead of showing "no tmux detected" message; return empty string with is_deep_context=True to indicate tmux presence
[2025-11-07] [change] [config]: config wizard loops back to menu after each action; re-displays configuration summary each iteration; exit option saves config before exiting
[2025-11-07] [feature] [cli]: add --provider flag to override default provider; supports inline flag parsing when placed after query; LLMProvider accepts provider parameter to use specified provider instead of default
[2025-11-07] [fix] [llm]: improve error messages for invalid models; catch "LLM Provider NOT provided" errors and show clear messages; improve executor error handling to recognize LLM-related errors without traceback
[2025-11-07] [fix] [llm]: fix model fallback when model=None to use provider's default model instead of None
[2025-11-07] [change] [config]: store model names without provider prefixes in config; prefixes are automatically stripped when saving and added back at runtime; users can enter model names with or without prefixes (e.g., gemini/gemini-2.5-flash or gemini-2.5-flash); applies to gemini, lm_studio, and ollama providers; move prefix stripping logic from base class to subclasses for better separation of concerns
[2025-11-07] [change] [cli]: change verbosity flag from -v DEBUG to count-based -vv; use -v for INFO level and -vv for DEBUG level; remove support for -v DEBUG pattern
[2025-11-07] [change] [logging]: replace manual performance logs with structured PerformanceLogger system; track elapsed time and total time since program start for all pipeline stages; format large numbers with commas for readability; add config category for initialization logs; LLMProvider now requires PerformanceLogger for consistent timing
[2025-11-07] [test] [shell]: add integration test for whai shell that replicates manual usage; test runs commands in recorded shell and verifies context contains all commands, outputs, and whai responses; uses actual shell recording mechanism (Start-Transcript/script) instead of manually writing logs
[2025-11-06] [fix] [context]: fix context capture in whai shell sessions; LLM responses from previous commands are now properly logged and available as context for subsequent commands; implement SessionLogger that writes whai output to both console and session log file, bypassing PowerShell transcript limitations that don't capture subprocess stdout
[2025-11-06] [feature] [core]: add whai shell to capture full terminal output.

## v0.5.0

[2025-11-02] [change] [structure]: Restructured the context to have shell specific objects for flexibility.
[2025-11-02] [change] [llm]: optimize LiteLLM import with SSL context caching patch; cache ssl.create_default_context() calls to avoid reloading certificates 184 times during import; reduces import time from ~4s to ~1.3s on Windows
[2025-11-02] [fix] [llm]: add token-based truncation for context and tool outputs to prevent exceeding model limits; truncate terminal context (150k tokens) and command outputs (50k tokens) preserving most recent content with truncation notice; use character-based token estimation (1 token ≈ 4 chars) for fast truncation; show user warnings when truncation occurs
[2025-11-02] [feature] [ui]: add terminal output truncation limiting displayed lines to 500; truncates stdout/stderr keeping most recent lines with truncation notice; configurable via TERMINAL_OUTPUT_MAX_LINES constant
[2025-11-02] [change] [constants]: add token limits (CONTEXT_MAX_TOKENS, TOOL_OUTPUT_MAX_TOKENS) and terminal output limit (TERMINAL_OUTPUT_MAX_LINES) to constants.py
[2025-11-02] [test] [token_utils]: add comprehensive unit tests for token truncation covering empty text, within/exceeds limits, end preservation, notice format, edge cases, and large text scenarios
[2025-11-02] [change] [llm]: add token_utils module with truncate_text_with_tokens() function for reusable token-based text truncation; includes performance logging for truncation operations
[2025-11-02] [change] [llm]: add examples to system prompt showing shallow/deep context formats and expected responses; improve shallow context note clarity to emphasize no follow-up questions when context is limited
[2025-11-02] [docs] [readme]: document calling whai without arguments feature; add example showing calling whai after git push error; update Core Features section to mention no-argument usage
[2025-11-02] [fix] [config]: remove built-in fallback for missing provider config; set default_provider=None when resetting config with no providers; resolve_model() now raises clear RuntimeError when no providers configured instead of silently using gpt-5-mini; config summary shows MISSING when default_provider is None or doesn't exist in providers dict; add validation in LLMConfig.__post_init__() to warn when default_provider is invalid; config wizard displays warning for invalid default_provider; aligns with fail-fast philosophy
[2025-11-02] [change] [structure]: reorganize codebase into domain-based modules; split large files (main.py, llm.py, interaction.py, context.py, ui.py) into focused submodules under cli/, core/, llm/, interaction/, context/, and ui/ directories; entry point moved from whai.main to whai.cli.main
[2025-11-02] [test] [tests]: remove implementation detail tests; delete 36 tests of private functions to align with behavioral testing philosophy
[2025-11-02] [fix] [config]: fix LM Studio model validation by querying API directly; LM Studio models are dynamically loaded locally and not in LiteLLM's model registry; extract _validate_model() method from ProviderConfig base class that uses LiteLLM's get_model_info(); LMStudioConfig overrides _validate_model() to query /models endpoint and check against available models; handles network errors and invalid JSON gracefully by assuming valid; resolves validation failures for valid LM Studio models
[2025-11-02] [test] [config]: add comprehensive unit tests for provider validation; add tests for API key validation (OpenAI), model validation (Anthropic, Gemini, LM Studio), API base validation (Ollama), field validation (Azure OpenAI, OpenAI), and model name sanitization (Ollama, Gemini); all tests use mocked dependencies and work without actual API connections; each validation type and provider is covered at least once
[2025-11-02] [feature] [ui]: add star indicator next to default provider in configuration summary; show ⭐ in rich mode and * in plain mode to clearly identify the default provider in the configured providers list
[2025-11-02] [fix] [llm]: fix LM Studio model name transformation for LiteLLM compatibility; LM Studio uses OpenAI-compatible API requiring 'openai/{model}' format; add sanitize_model_name() method to ProviderConfig base class that returns model unchanged by default; LMStudioConfig overrides it to strip 'lm_studio/' or 'openai/' prefixes and format as 'openai/{model}'; LLMProvider now calls sanitize_model_name() for all providers, eliminating branching logic; resolves "LLM Provider NOT provided" errors when using LM Studio models
[2025-11-02] [feature] [ui]: enhance config wizard with Rich UI components; add numbered choice prompts replacing click.Choice; use colored success/failure/warning messages with emojis; improve section headers with DOUBLE box styling; add celebration message when config is complete
[2025-11-02] [feature] [ui]: add provider-specific configuration summary; each provider config class implements get_summary_fields() to show relevant fields (e.g., api_base for LM Studio instead of optional api_key); display summary in Rich Table with double-line borders and per-field formatting

## v0.4.0

[2025-11-02] [change] [ui]: move configuration summary printing to ui.py as print_configuration_summary(); remove summarize() method from WhaiConfig; use Rich Table for pretty formatting with provider-specific fields displayed on separate lines
[2025-11-02] [change] [ui]: centralize UI functions throughout codebase; replace typer.echo error/success messages with ui.error/ui.success/ui.failure/ui.warn; add emoji support (✅ success, ❌ failure, ⚠️ warning, 🎉 celebration)
[2025-11-02] [change] [config]: remove "view" action from config wizard menu; configuration is already displayed when wizard launches
[2025-11-02] [fix] [tests]: update tests to check stderr for warn/info messages since UI functions output to stderr
[2025-11-01] [feature] [config]: add dynamic validation with progress feedback in config wizard; display validation steps in real-time with checkmarks aligned; validate API keys, models, and API base connectivity during provider configuration; show validation warnings and prompt user to proceed or cancel
[2025-11-01] [feature] [config]: add actual model validation using litellm.get_model_info(); checks if model exists in LiteLLM's model registry; validates model name format and availability for configured providers; shows clear error messages for unrecognized models
[2025-11-01] [change] [config]: add performance logging for provider config validation; measure and log duration of _validate_api_base and _validate_required_fields combined; use perf category for visibility in debug logs
[2025-11-01] [fix] [config]: suppress LiteLLM stdout/stderr output during validation to prevent "Provider List" messages from breaking alignment; use context manager to temporarily redirect stdout/stderr to devnull during validation calls
[2025-11-01] [change] [config]: improve validation message alignment in wizard; dynamically pad messages with dots to align checkmarks at fixed width (38 characters); handle both instant and async validation checks with consistent formatting
[2025-11-01] [fix] [ui]: fix syntax error in ui.py import statement (missing import keyword)
[2025-11-01] [change] [imports]: remove unnecessary TYPE_CHECKING guard from roles.py; import WhaiConfig directly since there is no circular dependency between roles.py and user_config.py; simplifies type hints by removing forward reference quotes
[2025-11-01] [change] [config]: refactor configuration to use dataclasses instead of dictionaries; move all config-related code to whai/configuration module (user_config.py, roles.py, config_wizard.py); implement file I/O methods directly in Role and WhaiConfig dataclasses (from_file, to_file); move provider validation into ProviderConfig subclasses as validate() method; remove backward compatibility shims; update all tests and code to use dataclass API instead of dictionary access
[2025-11-01] [change] [constants]: centralize all configuration defaults into constants.py; move LLM provider defaults, timeouts, context limits, UI styling, file names, and environment variable names to single source of truth; replace hardcoded values across codebase with constants for better maintainability
[2025-11-01] [fix] [main]: fix timeout validation in inline parsing; validate timeout <= 0 before converting to None to prevent 0 from being treated as default value; ensures invalid timeout values fail fast with clear error message
[2025-11-01] [change] [imports]: move all imports to top of files; relocate function-level imports to module level for better readability and adherence to Python best practices while preserving necessary lazy imports for performance
[2025-11-01] [change] [config]: refactor default model selection to be provider-specific; use get_default_model_for_provider() helper function instead of single global default; each provider has its own default model with fallback to DEFAULT_PROVIDER default
[2025-11-01] [change] [functions]: use default values directly in function signatures instead of Optional[Type] = None followed by None checks; simplifies code and improves type hints while maintaining backward compatibility
[2025-11-01] [fix] [context]: fix tmux context capture to use scrollback buffer instead of visible window; use `-S -200` flag to capture up to 200 lines of scrollback history regardless of terminal window size; resolves issue where context amount varied with window dimensions on WSL
[2025-11-01] [feature] [context]: automatically filter whai command invocation from terminal context; removes last occurrence of command and all subsequent lines from tmux scrollback, or last matching command from history; handles quote differences between terminal and sys.argv, excludes log lines from matching; adds logging to verify filtering behavior
[2025-11-01] [fix] [ui]: display message when command produces no output; show exit code and "empty output" indicator to both user and LLM; prevents confusion when commands succeed silently
[2025-11-01] [test] [cli]: update test_cli_module_help_when_no_args to reflect default query behavior when no args provided

## v0.3.1

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

## v0.1.1

[2025-10-31] [change] [repo]: rename package from terma to whai; update docs and references
[2025-10-31] [test] [cli]: add subprocess-based CLI E2E tests using mocked `litellm` via tests/mocks; remove sitecustomize hook
[2025-10-31] [docs] [dev]: document subprocess E2E testing approach and TERMA_MOCK_TOOLCALL usage
[2025-10-31] [fix] [context/windows]: use PSReadLine for pwsh history (wrong bash history shown). Detected shell was 'pwsh' after centralization; fallback only handled 'powershell' and 'unknown'. Updated Windows history branch to include 'pwsh'.
[2025-10-31] [change] [logging]: default level ERROR; add -v LEVEL; move performance timings to INFO; keep payload/system/user dumps under DEBUG; remove TERMA_DEBUG handling.
[2025-10-31] [change] [roles]: ship only one default role (default.md). Removed assumptions and tests referencing a built-in debug role.

## v0.1.0

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

