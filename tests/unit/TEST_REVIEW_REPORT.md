# Test Review Report: MCP Approval Feature Tests

## Summary

The MCP approval feature tests have **violations of the core testing philosophy**. Two test files test implementation details rather than observable behavior.

## Tests Flagged for Deletion/Refactoring

### Type B (Implementation-Detail Tests) - Priority #1

#### 1. `tests/unit/test_approval_tool.py` - **ALL TESTS**

**Violations:**
- Mocks internal UI functions (`whai.ui.print_tool`, `whai.ui.info`, `whai.ui.warn`)
- Asserts on internal implementation (that `print_tool` was called) rather than observable behavior
- Tests *how* the function works rather than *what* it returns
- Brittle: Will break if internal UI implementation changes

**Comparison with existing tests:**
- `test_interaction.py::test_approval_loop_approve()` only patches `builtins.input` and asserts on return value
- No UI mocking in existing approval tests

**Recommendation:** Refactor to match `approval_loop` test pattern:
- Only patch `builtins.input` (necessary for testing user input)
- Assert on return values (True/False) - this is the observable behavior
- Remove all UI function mocking

#### 2. `tests/unit/test_ui_output.py` - **ALL TESTS**

**Violations:**
- Mocks internal `console.print` 
- Only asserts that `console.print` was called, not what was printed
- Tests implementation (that print was called) rather than behavior (what user sees)
- Brittle: Will break if Rich console implementation changes

**Recommendation:** 
- Use a real Console with StringIO/file output to capture actual printed content
- Assert on the actual output content, not that print was called
- Or: Delete if covered by integration/E2E tests that verify actual CLI output

## Tests That Follow Philosophy ✓

### `tests/unit/test_mcp_config.py` (new field tests)
- Tests observable behavior: serialization/deserialization results
- Tests public API (`to_dict()`, `from_dict()`)
- No mocking of internal implementation
- **Status:** Keep as-is

### `tests/unit/test_mcp_manager.py::test_get_server_config`
- Tests observable behavior: return value (config object or None)
- Uses real MCP server fixture
- Asserts on public API return values
- **Status:** Keep as-is

## Proposed Refactored Tests

### For `approve_tool` (matching `approval_loop` pattern):

```python
def test_approve_tool_approve():
    """Test approving a tool call returns True."""
    with patch("builtins.input", return_value="a"):
        result = approve_tool(
            "mcp_time-server_get_current_time",
            {"timezone": "UTC"},
            display_name="time-server/get_current_time",
        )
        assert result is True

def test_approve_tool_reject():
    """Test rejecting a tool call returns False."""
    with patch("builtins.input", return_value="r"):
        result = approve_tool(
            "mcp_time-server_get_current_time",
            {},
            display_name="time-server/get_current_time",
        )
        assert result is False
```

### For `print_tool` (if needed):

Either:
1. **Delete** if covered by integration/E2E tests
2. **Refactor** to capture actual output:
```python
from io import StringIO
from rich.console import Console

def test_print_tool_output():
    """Test print_tool produces expected output."""
    output = StringIO()
    console = Console(file=output, force_terminal=False)
    # ... test actual output content
```

## Critical Gaps

1. **Integration test for approval workflow**: Need E2E test that:
   - Runs actual CLI with MCP tool requiring approval
   - Verifies user sees approval prompt
   - Verifies tool executes after approval
   - Verifies tool is rejected when user rejects

2. **Integration test for auto-approval**: Need test that:
   - Runs CLI with `requires_approval=False`
   - Verifies tool executes without prompt
   - Verifies user sees tool execution message

## Action Items

1. ✅ **Refactored** `test_approval_tool.py` - Removed UI mocking, now only tests return values (observable behavior)
2. ✅ **Deleted** `test_ui_output.py` - UI output is better tested at integration/E2E level where actual CLI output can be verified
3. **Add** Integration tests for approval workflow (if not already covered)
4. **Add** Integration test for auto-approval workflow

## Implementation Status

✅ **Completed:**
- Refactored `test_approval_tool.py` to match `approval_loop` test pattern
- Removed all UI function mocking
- Tests now only assert on return values (True/False) - the observable behavior
- Deleted `test_ui_output.py` as UI output is better tested at integration level

**All tests passing** ✓

