# whai Dev Cheatsheet

Compact commands for Windows, macOS, and Linux.

## uv venv

### Install (editable, with dev deps)
```bash
uv venv
uv sync
```

### Add packages
```bash
uv add package
```
or 
```bash
uv add --dev package
```

### Delete and recreate venv
```bash
# macOS/Linux
rm -rf .venv && uv venv && uv sync

# Windows PowerShell
Remove-Item .venv -Recurse -Force; uv venv; uv sync

# Windows CMD
rmdir /s /q .venv & uv venv & uv sync
```

### Activate venv
```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1

# Windows CMD
.venv\Scripts\activate.bat
```

### Run scripts/CLI via uv
```bash
# Run whai
uv run whai "your question"

# Run a module/script
uv run python -m whai "your question"
uv run python path/to/script.py
```

## Tests

### Quick test run (current Python version)
```bash
uv run pytest
# Optional
uv run pytest -v
uv run pytest --cov=whai --cov-report=term-missing
uv run pytest -m performance
```

### Testing across multiple Python versions (recommended)

Use `nox` to test against Python 3.8, 3.9, 3.10, 3.11, 3.12, and 3.13:
First time setup:
```bash
# One-time setup: Install Python versions with uv
uv python install 3.10 3.11 3.12 3.13

# Install nox
uv tool install "nox[uv]"
```

Run the tests
```bash
nox
```

Other useful commands
```bash
# Test specific Python version
nox -s tests-3.11

# Run linting across all versions
nox -s lint

# List all available sessions
nox -l
```

## Publishing Releases

### Automated Release Pipeline (Recommended)

The project uses GitHub Actions to automatically test, build, publish, and release new versions when you push a version tag.

#### Prerequisites

Set up GitHub repository secrets (one-time setup):
1. Go to your GitHub repository settings
2. Navigate to Secrets and variables → Actions
3. Add two secrets:
   - `TEST_PYPI_TOKEN` - Your TestPyPI API token ([get it here](https://test.pypi.org/manage/account/token/))
   - `PYPI_TOKEN` - Your PyPI API token ([get it here](https://pypi.org/manage/account/token/))

#### Release Process

1. Ensure `CHANGELOG.md` is up-to-date with all changes:
   - During development, continuously add entries at the top (after the format header)
   - Before releasing, add a version header: `## vX.Y.Z` (where X.Y.Z is your new version)
   - Add an empty line after all entries for this version (before the next version header)
   - The release workflow uses `python -m whai.doc.release_notes` to build GitHub notes, which sorts entries by category importance (Feature → Security → Fix → Change → Docs → Chore → Test) and removes the leading date in the published list.

2. Bump the version:

```bash
# Options: major | minor | patch | stable | alpha | beta | rc | post | dev
uv version --bump patch
```

3. Commit and tag the new version:

```bash
# Replace X.Y.Z with your new version number
git commit -am "Bump version to vX.Y.Z"
git tag vX.Y.Z
```

4. Push the commit and tag:

```bash
# Push the commit first
git push

# Then push the specific tag to trigger the workflow
git push origin vX.Y.Z
```

**Important**: Use `git push origin vX.Y.Z` to push the specific tag, NOT `git push --tags`. The `--tags` flag pushes all tags, and if a tag already exists on the remote, GitHub won't recognize it as a new tag push event and won't trigger the workflow.

That's it! GitHub Actions will automatically:
- Run tests across Python 3.10, 3.11, 3.12, 3.13
- Validate that the tag matches the version in `pyproject.toml`
- Build the package
- Publish to TestPyPI
- Verify the TestPyPI package with smoke tests
- Publish to PyPI
- Create a GitHub Release with CHANGELOG entries

You can monitor the progress in the "Actions" tab of your GitHub repository.

#### Troubleshooting: Workflow Didn't Trigger

If you pushed a tag but the workflow didn't trigger:

1. **Check if the tag was already on the remote**: `git ls-remote --tags origin | grep vX.Y.Z`
2. **If the tag exists, delete it from remote and push again**:
   ```bash
   git push --delete origin vX.Y.Z
   git push origin vX.Y.Z
   ```
3. **Verify the tag appears as `[new tag]`** in the push output - this confirms GitHub recognizes it as a new event.

#### Testing the Pipeline (Without Publishing)

Before your first real release, you can test the entire pipeline without actually publishing:

1. Go to your GitHub repository
2. Click on the "Actions" tab
3. Select "Build, Test, and Publish" workflow from the left sidebar
4. Click "Run workflow" button (top right)
5. Check the "Test mode (skip publishing)" checkbox
6. Click "Run workflow"

This will:
- Run all tests across Python 3.10, 3.11, 3.12, 3.13
- Build the package
- Verify the built package locally (install and run smoke tests)
- Skip all publishing steps (TestPyPI, PyPI, GitHub Release)

This is perfect for:
- Verifying the workflow works before your first release
- Testing changes to the workflow itself
- Validating that your package builds correctly

### Manual Publishing (Fallback)

<details>
<summary>Click to expand manual publishing instructions</summary>

Use these commands if you need to publish manually or the automated workflow fails.

The following commands work on Windows PowerShell. They bump the version, build artifacts, publish to TestPyPI, verify in a clean venv, then publish to PyPI.

### 1) Bump version

- Edit `pyproject.toml` and change `[project] version = "..."`, or use:

```powershell
# Options: major | minor | patch | stable | alpha | beta | rc | post | dev
uv version --bump patch
```

### 2) Build artifacts

```powershell
# Windows PowerShell
Remove-Item -Recurse .\dist
uv build
```

```bash
# macOS/Linux
rm -rf dist
uv build
```

### 3) Publish to TestPyPI

```powershell
# Windows PowerShell
# Load .env file and set UV_PUBLISH_TOKEN from TEST_PYPI_KEY
Get-Content .env | ForEach-Object { if ($_ -match '^TEST_PYPI_KEY=(.*)$') { $env:UV_PUBLISH_TOKEN = $matches[1].Trim('"') } }
uv publish --publish-url https://test.pypi.org/legacy/
```

```bash
# macOS/Linux
# Load .env file and set UV_PUBLISH_TOKEN from TEST_PYPI_KEY
export TEST_PYPI_KEY=$(grep '^TEST_PYPI_KEY=' .env | cut -d '=' -f2- | sed 's/^"//;s/"$//')
export UV_PUBLISH_TOKEN=$TEST_PYPI_KEY
uv publish --publish-url https://test.pypi.org/legacy/
```

### 4) Verify the TestPyPI upload in a clean venv

```powershell
# Windows PowerShell

# Create a temp venv for verification
uv venv .venv_testpypi

# Read current version from pyproject.toml without editing commands for each release
$ver = uv run --no-project -- python -c "import tomllib,sys;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
$ver = $ver.Trim()
echo $ver

# Check if version is available on TestPyPI (before attempting install)
# Note: It could take 2-5 minutes for TestPyPI to index after upload
uv run --no-project -- pip index versions whai --index-url https://test.pypi.org/simple/

# Activate the venv and install
.\.venv_testpypi\Scripts\activate  
uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple "whai==$ver" --index-strategy unsafe-best-match

# Smoke tests (module and console script)
python -c "import whai; print('import ok')"
python -m whai --help

# Test the installed console script directly (crucial for CLI verification)
.\.venv_testpypi\Scripts\whai --help
.\.venv_testpypi\Scripts\whai --version
```

```bash
# macOS/Linux

# Create a temp venv for verification
uv venv .venv_testpypi

# Read current version from pyproject.toml
ver=$(grep '^version = ' pyproject.toml | head -n1 | sed -E 's/^version = "(.*)"/\1/') 
echo "$ver"

# Check if version is available on TestPyPI (before attempting install)
# Note: It could take 2-5 minutes for TestPyPI to index after upload
uv run --no-project -- pip index versions whai --index-url https://test.pypi.org/simple/

# Activate the venv and install
source .venv_testpypi/bin/activate  
uv pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple "whai==$ver" --index-strategy unsafe-best-match

# Smoke tests (module and console script)
python -c "import whai; print('import ok')"
python -m whai --help

# Test the installed console script directly (crucial for CLI verification)
.venv_testpypi/bin/whai --help
.venv_testpypi/bin/whai --version
```

### 5) Publish to PyPI

```powershell
# Windows PowerShell

# Load .env file and set UV_PUBLISH_TOKEN from PYPI_KEY
Get-Content .env | ForEach-Object { if ($_ -match '^PYPI_KEY=(.*)$') { $env:UV_PUBLISH_TOKEN = $matches[1].Trim('"') } }
uv publish

# Clean up
Remove-Item -Recurse .\dist
Remove-Item -Recurse .\.venv_testpypi
Remove-Item -Recurse .\.nox
```

```bash
# macOS/Linux

# Load .env file and set UV_PUBLISH_TOKEN from PYPI_KEY
export PYPI_KEY=$(grep '^PYPI_KEY=' .env | cut -d '=' -f2- | sed 's/^"//;s/"$//')
export UV_PUBLISH_TOKEN=$PYPI_KEY
uv publish

# Clean up
rm -rf dist .venv_testpypi .nox
```


Notes:
- The `--index-strategy unsafe-best-match` flag is required when the package name exists on both TestPyPI and PyPI but the requested version is only on TestPyPI.
- Test from outside the repo root or use the console script; running `python -m whai` from the repo can import local sources instead of the installed wheel.

</details>

### Subprocess CLI E2E tests
The test suite includes end-to-end tests that invoke `python -m whai` in a subprocess. These tests avoid network calls by placing a mock `litellm` module under `tests/mocks` and prepending that directory to `PYTHONPATH` inside the test harness. You can force a tool-call flow by setting `WHAI_MOCK_TOOLCALL=1` in the subprocess environment. No test-related code lives in the `whai/` package.

## Flags

### Logging and output
```bash
# Default logging level is ERROR
uv run whai "test query"

# Increase verbosity to INFO (timings and key stages)
uv run whai "test query" -v

# Full debug (payloads, prompts, detailed traces)
uv run whai "test query" -vv

# Plain output (reduced styling)
WHAI_PLAIN=1 uv run whai "test query"
```

### CLI flags
```bash
uv run whai "explain git rebase" --no-context
uv run whai "why did my command fail?" --role debug
```

### Common mistakes for Testing:

```
# Common Cross-Platform Mistakes (Bash/Zsh/PowerShell)

gti status                  # 1. Command misspelling (git)
git comit -m "msg"          # 2. Sub-command/argument misspelling (commit)
sl                          # 3. Transposition typo (ls)
cd /nonexistant/path/       # 4. Invalid/non-existent path
rm "my file.txt             # 5. Unmatched quotes or syntax error
cp file.txt /etc/           # 6. Permission denied (requires elevation/sudo)
mkdir                       # 7. Missing required arguments
cd myproject                # 8. Case sensitivity error (e.g., directory is 'MyProject')

# OS-Specific Mistakes

# --- Unix-like (Linux/macOS: Bash/Zsh) ---
./my_script.sh              # 1. Permission denied (Forgot 'chmod +x')
apt install htop            # 2. Wrong package manager (e.g., using 'apt' on a 'yum'/'dnf' system)
yum update                  # 3. Wrong package manager (e.g., using 'yum' on a 'brew' system)
cd ~/documents              # 4. Directory case sensitivity (Actual path is '~/Documents')

# --- Windows (PowerShell) ---
ls -l                       # 5. Unix alias parameter mismatch ('ls' = Get-ChildItem, which has no '-l')
./run_script.ps1            # 6. Execution Policy restriction (Script execution is disabled)
export API_KEY="123"        # 7. Using Unix env variable syntax (PS uses '$env:API_KEY = "123"')
cat file.txt | grep "text"  # 8. Using Unix verbs for complex tasks (PS equivalent: Get-Content | Select-String)

```
