# Bundled Runtime Setup

The skill is self-contained. Its runnable Wellio source is stored under `runtime/`; never clone, pull, or install the separate `Wellio_CLI` repository.

## Normal operation

Run `scripts/run_wellio.py` with Wellio arguments after `--`:

```text
python "<skill-dir>/scripts/run_wellio.py" -- info "<log-file>"
```

The launcher performs these steps automatically:

1. Resolve a dedicated environment directory.
2. Reuse a recognized environment at that location, or create one with `uv`, Python `venv`, or a dedicated Conda prefix.
3. Install the local package at `<skill-dir>/runtime` plus its third-party dependencies.
4. Detect changes to the bundled runtime and reinstall it when its content changes.
5. Run the bundled `wellio` executable directly without activating the environment.

## Environment location

Resolve the location in this order:

1. `--env-dir "<path>"` supplied because the user requested that location.
2. The `WELLIO_ENV_DIR` environment variable when it contains a path.
3. The platform default:
   - Windows: `%LOCALAPPDATA%\Wellio\venv`
   - macOS: `~/Library/Application Support/Wellio/venv`
   - Linux: `${XDG_DATA_HOME}/wellio/venv`, falling back to `~/.local/share/wellio/venv`.

Do not ask the user for a location when the safe default is available. If the user naturally says “put the environment on `D:\Tools\Wellio`,” pass that path with `--env-dir`; the user does not need to know about environment variables.

Never install into system Python, Conda `base`, `VIRTUAL_ENV`, or `CONDA_PREFIX`. Never create the environment beside the user's log file. If the chosen directory is nonempty and is not a recognized virtual environment, stop rather than overwrite it.

## Environment manager

Use `--manager auto` unless the user requests `uv`, `venv`, or Conda. Automatic selection prefers an already installed `uv`, then a compatible Python 3.12+ interpreter and `venv`, then Conda with a dedicated prefix.

If none is available, explain that a Python runtime manager is missing and ask before installing one. Do not fall back to a base or system installation.

## Bundled package requirements

The bundled package requires Python 3.12+ and declares these third-party dependencies in `runtime/pyproject.toml`:

- `defusedxml >=0.7.1,<0.8`
- `dlisio >=1.0.4,<2`
- `lasio >=0.32,<0.33`
- `pandas >=3.0,<4`
- `pyarrow >=18,<26`
- `typer >=0.12`

Install the local runtime package and let its package metadata resolve these dependencies. Do not install them into the interpreter used only to launch `run_wellio.py`.
