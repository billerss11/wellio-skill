# Wellio Runtime and Build

Keep execution inside this skill. Never clone or install the separate `Wellio_CLI` repository.

## Choose execution

| Condition | Action |
|---|---|
| Windows and `scripts/wellio.exe` exists | Run the EXE first |
| EXE missing or Windows cannot launch it | Run the Python launcher |
| Non-Windows platform | Run the Python launcher |
| EXE runs but reports a command/data error | Report the error; do not fall back |

The EXE contains Python and all dependencies. It creates no environment and uses no network.

## Run the fallback

```text
python "<skill-dir>/scripts/run_wellio.py" -- COMMAND [ARGUMENTS] [OPTIONS]
```

The launcher:

1. Reuses or creates an environment marked as owned by this skill.
2. Prefers the Conda environment `wellio-skill`, then uv, then Python 3.12+ `venv`.
3. Installs `<skill-dir>/runtime` and dependencies from its `pyproject.toml`.
4. Uses the Tsinghua PyPI mirror, then retries official PyPI once.
5. Reinstalls when bundled runtime files change.
6. Runs the environment's `wellio` command without activation.

Use launcher options before `--`:

| Option | Meaning |
|---|---|
| `--env-dir PATH` | Use a user-requested managed environment location |
| `--manager auto\|conda\|uv\|venv` | Select environment manager |
| `--index-url URL` | Set primary package index |
| `--fallback-index-url URL` | Set retry index |

Equivalent environment variables are `WELLIO_ENV_DIR`, `WELLIO_ENV_MANAGER`, `WELLIO_PYPI_INDEX_URL`, and `WELLIO_PYPI_FALLBACK_INDEX_URL`.

Without an override, place non-Conda environments at:

- Windows: `%LOCALAPPDATA%\Wellio\venv`
- macOS: `~/Library/Application Support/Wellio/venv`
- Linux: `${XDG_DATA_HOME}/wellio/venv` or `~/.local/share/wellio/venv`

Never use system Python, Conda `base`, `VIRTUAL_ENV`, or `CONDA_PREFIX` as the managed environment. Refuse to modify an existing environment without the Wellio ownership marker.

## Build `wellio.exe`

After cloning or pulling the repository on Windows, run from the skill root:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\build_portable_exe.ps1"
```

Require Conda. The script:

1. Safely reuses or creates the managed `wellio-skill` environment.
2. Installs the bundled runtime and PyInstaller.
3. Builds one Windows executable with only required packages.
4. Writes `scripts/wellio.exe` and prints its size and SHA-256.

Expected result: a standalone EXE of about 59 MiB. PyInstaller writes temporary files under ignored `build/`; do not commit that directory or any environment. Commit/distribute only `scripts/wellio.exe` as the binary build artifact.

## Recover from setup errors

| Error | Response |
|---|---|
| No Conda/uv/Python 3.12+ for fallback | Ask before installing an environment manager |
| Unmanaged environment already exists | Choose a new `--env-dir`; do not adopt or delete it |
| Primary package index fails | Let the launcher retry official PyPI |
| EXE missing/corrupt/incompatible | Use the launcher, then rebuild on Windows if desired |
| Build reports missing Conda | Install/use Conda; do not build from base Python |
