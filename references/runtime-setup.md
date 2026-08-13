# Executable and Runtime Setup

The skill is self-contained. Its runnable Wellio source is stored under `runtime/`; never clone, pull, or install the separate `Wellio_CLI` repository.

## Normal operation

On Windows, run the bundled executable first:

```text
"<skill-dir>/scripts/wellio.exe" info "<log-file>"
```

The executable includes Python and all Wellio dependencies. It does not create an environment or access a package index.

Use `scripts/run_wellio.py` only when `wellio.exe` is missing, the platform is not Windows, or the operating system cannot launch the executable. A Wellio command or input-file error from a successfully launched EXE is not a reason to fall back.

Pass Wellio arguments to the fallback launcher after `--`:

```text
python "<skill-dir>/scripts/run_wellio.py" -- info "<log-file>"
```

The launcher performs these steps automatically:

1. Honor an explicit environment path or `WELLIO_ENV_DIR`.
2. Otherwise prefer a dedicated Conda environment named `wellio-skill`, allowing Conda's configured `envs_dirs` to determine its location.
3. If Conda is unavailable, use the platform default with `uv` or Python `venv`.
4. Reuse only an environment marked as managed by this skill; never adopt an unrelated environment.
5. Install the local package at `<skill-dir>/runtime` plus its third-party dependencies.
6. Use the Tsinghua PyPI mirror by default and retry official PyPI once if the mirror fails.
7. Detect changes to the bundled runtime and reinstall it when its content changes.
8. Run the bundled `wellio` executable directly without activating the environment.

## Build the Windows executable

After cloning or pulling the skill repository on Windows, run:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\build_portable_exe.ps1"
```

The build script requires Conda. It safely reuses or creates the managed `wellio-skill` Conda environment, installs the bundled runtime and PyInstaller, and writes the one-file build to `scripts/wellio.exe`. It refuses to modify an existing `wellio-skill` environment unless that environment carries this skill's ownership marker.

PyInstaller's generated `build/` directory is ignored by Git. Commit or distribute `scripts/wellio.exe`; do not commit the generated build directory or a Conda environment.

## Environment location

Resolve the location in this order:

1. `--env-dir "<path>"` supplied because the user requested that location.
2. The `WELLIO_ENV_DIR` environment variable when it contains a path.
3. When Conda is installed, the location selected by Conda for the named environment `wellio-skill`. This respects `.condarc` and `envs_dirs`.
4. When Conda is unavailable, the platform default:
   - Windows: `%LOCALAPPDATA%\Wellio\venv`
   - macOS: `~/Library/Application Support/Wellio/venv`
   - Linux: `${XDG_DATA_HOME}/wellio/venv`, falling back to `~/.local/share/wellio/venv`.

Do not ask the user for a location when the safe default is available. If the user naturally says “put the environment on `D:\Tools\Wellio`,” pass that path with `--env-dir`; the user does not need to know about environment variables.

Never install into system Python, Conda `base`, `VIRTUAL_ENV`, or `CONDA_PREFIX`. Never create the environment beside the user's log file. If the chosen directory or named Conda environment already exists but is not marked as managed by this skill, stop rather than modify it.

## Environment manager

Use `--manager auto` unless the user requests `uv`, `venv`, or Conda. Automatic selection prefers Conda, then an already installed `uv`, then a compatible Python 3.12+ interpreter with `venv`.

If none is available, explain that a Python runtime manager is missing and ask before installing one. Do not fall back to a base or system installation.

## Package indexes

Use Tsinghua as the primary Python package index:

```text
https://pypi.tuna.tsinghua.edu.cn/simple
```

If installation from Tsinghua fails, retry once with official PyPI:

```text
https://pypi.org/simple
```

Use `--index-url` and `--fallback-index-url` when the user requests different indexes. The equivalent environment variables are `WELLIO_PYPI_INDEX_URL` and `WELLIO_PYPI_FALLBACK_INDEX_URL`.

## Bundled package requirements

The bundled package requires Python 3.12+ and declares these third-party dependencies in `runtime/pyproject.toml`:

- `defusedxml >=0.7.1,<0.8`
- `dlisio >=1.0.4,<2`
- `lasio >=0.32,<0.33`
- `pandas >=3.0,<4`
- `pyarrow >=18,<26`
- `typer >=0.12`

Install the local runtime package and let its package metadata resolve these dependencies. Do not install them into the interpreter used only to launch `run_wellio.py`.
