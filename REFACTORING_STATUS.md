# Dataclass Refactoring Status

## Completed ✅

### Core Data Structures
1. **Provider Dataclasses** (`whai/config.py`)
   - Created base `ProviderConfig` with sensible defaults
   - Created provider-specific subclasses:
     - `OpenAIConfig`
     - `AnthropicConfig`
     - `GeminiConfig`
     - `AzureOpenAIConfig`
     - `OllamaConfig`
     - `LMStudioConfig`
   - Each has custom validation in `__post_init__`
   - Helper function `get_provider_class()` for dynamic instantiation

2. **Main Config Dataclasses** (`whai/config.py`)
   - `LLMConfig`: Contains default_provider and providers dict
   - `RolesConfig`: Contains default_role
   - `WhaiConfig`: Main config containing LLM and roles

3. **Role Dataclass** (`whai/config.py`)
   - Renamed `RoleMetadata` to `Role`
   - Added `name` and `body` fields
   - Added `to_markdown()` method for serialization
   - Added `from_dict()` and `from_default()` classmethods
   - Backward compatibility alias: `RoleMetadata = Role`

4. **Validation Functions** (`whai/config.py`)
   - `ValidationResult` dataclass
   - `validate_provider_config()` using LiteLLM:
     - API key validation
     - Model availability checks
     - API reachability tests

### Config Loading/Saving
5. **Updated `load_config()`** (`whai/config.py`)
   - Now returns `WhaiConfig` instead of `Dict[str, Any]`
   - Removed `allow_ephemeral` complexity
   - Simplified test mode handling

6. **Updated `save_config()`** (`whai/config.py`)
   - Now accepts `WhaiConfig` instead of `Dict[str, Any]`
   - Uses `config.to_dict()` for TOML serialization

7. **Updated Helper Functions** (`whai/config.py`)
   - `summarize_config()`: Now accepts `WhaiConfig`
   - `parse_role_file()`: Now returns `Role` object
   - `load_role()`: Now returns `Role` object
   - `resolve_role()`: Now accepts `WhaiConfig`
   - `resolve_model()`: Now accepts `Role` and `WhaiConfig`
   - `resolve_temperature()`: Now accepts `Role`
   - **Removed** `validate_llm_config()` (replaced by dataclass validation)

### Main Application
8. **Updated `main.py`**
   - Removed `validate_llm_config` import and usage
   - Changed `role_metadata, role_prompt = load_role()` to `role_obj = load_role()`
   - Updated all usages of `role_metadata` to `role_obj`
   - Updated `role_prompt` to `role_obj.body`
   - Passes `WhaiConfig` to all functions

9. **Updated `llm.py`**
   - `LLMProvider.__init__()` now accepts `WhaiConfig`
   - Updated all config access to use dataclass attributes
   - `_configure_api_keys()` uses dataclass methods

## Remaining Work ⏳

### 1. Config Wizard (High Priority)
File: `whai/config_wizard.py`

**Tasks:**
- Update imports to include dataclasses
- Change `_get_provider_config()` to return `ProviderConfig` subclass
- Update `_quick_setup()` to use `WhaiConfig`
- Update `_add_or_edit_provider()` to use `WhaiConfig`
- Update `_remove_provider()` to use `WhaiConfig`
- Update `_set_default_provider()` to use `WhaiConfig`
- Update `_reset_default()` to create `WhaiConfig`
- Update `run_wizard()` to use `WhaiConfig` throughout
- **Add validation menu option** with `_validate_config()` function

**Validation Menu Function:**
```python
def _validate_config(config: WhaiConfig) -> None:
    """Validate all configured providers."""
    typer.echo("\n=== Validating Configuration ===\n")
    
    for name, provider_config in config.llm.providers.items():
        typer.echo(f"Validating {name}...")
        result = validate_provider_config(provider_config, name)
        
        if result.is_valid:
            typer.echo(f"  ✓ {name} validation passed")
        else:
            typer.echo(f"  ✗ {name} validation failed:")
            for issue in result.issues:
                typer.echo(f"    - {issue}")
        
        typer.echo(f"  Checks performed: {', '.join(result.checks_performed)}")
        typer.echo()
```

### 2. Role CLI (Medium Priority)
File: `whai/role_cli.py`

**Tasks:**
- Remove `_template()` function
- Update `create_role()` to use `Role.from_default(name, body).to_markdown()`
- Generate default body from packaged defaults
- Ensure all role operations use `Role` dataclass

**Example change:**
```python
# OLD:
path.write_text(_template(name))

# NEW:
default_body = f"You are a helpful terminal assistant with the '{name}' specialization.\nDescribe behaviors, tone, and constraints here."
role = Role.from_default(name, default_body)
path.write_text(role.to_markdown())
```

### 3. Tests (High Priority)
File: `tests/test_config.py` (and others)

**Tasks:**
- Update all tests to use `WhaiConfig` instead of dicts
- Update tests for provider dataclasses
- Add tests for validation functions
- Update mock fixtures to return `WhaiConfig`
- Test serialization/deserialization
- Test Role dataclass methods

### 4. Cleanup (Low Priority)
Files: `whai/config.py`, others

**Tasks:**
- Remove any remaining dict-based helper functions
- Remove backward compatibility code after tests are updated
- Simplify any remaining dict manipulation code

## Testing the Current State

The core system should work now. To test:

```bash
# Load config (returns WhaiConfig)
config = load_config()

# Load role (returns Role)
role = load_role("default")

# Use in main flow
llm_model, source = resolve_model(None, role, config)
llm_temperature = resolve_temperature(None, role)
llm_provider = LLMProvider(config, model=llm_model, temperature=llm_temperature)
```

## Breaking Changes

1. `load_config()` now returns `WhaiConfig` instead of `Dict[str, Any]`
2. `save_config()` now accepts `WhaiConfig` instead of `Dict[str, Any]`
3. `load_role()` now returns `Role` instead of `Tuple[RoleMetadata, str]`
4. `parse_role_file()` now returns `Role` instead of tuple
5. `validate_llm_config()` removed (validation done by dataclasses)
6. `LLMProvider.__init__()` now accepts `WhaiConfig`

## Notes

- Validation is now done at two points:
  1. Dataclass `__post_init__` (format/structure validation)
  2. `validate_provider_config()` (API/network validation - optional)
- All dataclasses have `to_dict()` for TOML serialization
- All dataclasses have `from_dict()` for loading from TOML
- Backward compatibility maintained via `RoleMetadata = Role` alias

