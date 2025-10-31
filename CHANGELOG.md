# Changelog

Format: [YYYY-MM-DD] [category] [scope]: description
Categories: feature, change, fix, docs, security, test, chore
Order: reverse chronological (newest at the top). Add your changes at the top!

[2025-10-31] [fix] [context/windows]: use PSReadLine for pwsh history (wrong bash history shown). Detected shell was 'pwsh' after centralization; fallback only handled 'powershell' and 'unknown'. Updated Windows history branch to include 'pwsh'.
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
