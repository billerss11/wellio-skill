#!/usr/bin/env python3
"""Create an isolated runtime when needed and run the bundled Wellio CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

MINIMUM_PYTHON = (3, 12)
RUNTIME_DIR = Path(__file__).resolve().parents[1] / "runtime"
MARKER_NAME = ".wellio-skill-runtime.sha256"
OWNER_MARKER_NAME = ".wellio-skill-environment"
CONDA_ENV_NAME = "wellio-skill"
DEFAULT_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
DEFAULT_FALLBACK_INDEX_URL = "https://pypi.org/simple"


def _status(message: str) -> None:
    print(f"Wellio skill: {message}", file=sys.stderr)


def _default_environment_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Local"
        return root / "Wellio" / "venv"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Wellio" / "venv"
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "wellio" / "venv"


def _requested_environment_dir(requested):
    raw_path = requested or os.environ.get("WELLIO_ENV_DIR")
    return Path(raw_path).expanduser().resolve() if raw_path else None


def _looks_like_environment(path: Path) -> bool:
    return (path / "pyvenv.cfg").is_file() or (path / "conda-meta").is_dir()


def _is_managed_environment(path: Path) -> bool:
    return (path / OWNER_MARKER_NAME).is_file() or (path / MARKER_NAME).is_file()


def _claim_environment(path: Path) -> None:
    (path / OWNER_MARKER_NAME).write_text(
        "Managed by the Wellio Codex skill.\n",
        encoding="utf-8",
    )


def _prepare_environment_target(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise RuntimeError(f"Environment path is not a directory: {path}")
        if any(path.iterdir()) and not _looks_like_environment(path):
            raise RuntimeError(
                "Environment directory exists but is not a recognized virtual "
                f"environment: {path}"
            )
        if _looks_like_environment(path) and not _is_managed_environment(path):
            raise RuntimeError(
                "Refusing to modify an existing environment not created by this "
                f"skill: {path}"
            )
    else:
        path.parent.mkdir(parents=True, exist_ok=True)


def _environment_python(path: Path):
    candidates = (
        path / "Scripts" / "python.exe",
        path / "python.exe",
        path / "bin" / "python",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _environment_wellio(path: Path):
    candidates = (
        path / "Scripts" / "wellio.exe",
        path / "Scripts" / "wellio",
        path / "bin" / "wellio",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _run_checked(command, **kwargs):
    if "stdout" not in kwargs and not kwargs.get("capture_output"):
        kwargs["stdout"] = sys.stderr
    return subprocess.run([str(part) for part in command], check=True, **kwargs)


def _python_is_compatible(command) -> bool:
    probe = (
        "import sys; "
        f"raise SystemExit(0 if sys.version_info >= {MINIMUM_PYTHON!r} else 1)"
    )
    result = subprocess.run(
        [*command, "-c", probe],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _venv_python_command():
    candidates = []
    if sys.version_info >= MINIMUM_PYTHON:
        candidates.append([sys.executable])
    if sys.platform == "win32" and shutil.which("py"):
        candidates.append(["py", "-3.12"])
    for name in ("python3.12", "python3", "python"):
        executable = shutil.which(name)
        if executable:
            candidates.append([executable])

    seen = set()
    for command in candidates:
        key = tuple(command)
        if key not in seen and _python_is_compatible(command):
            return command
        seen.add(key)
    return None


def _create_environment(path: Path, manager: str) -> str:
    conda = shutil.which("conda")
    if manager in ("auto", "conda") and conda:
        _status(f"creating isolated Conda environment at {path}")
        _run_checked(
            [conda, "create", "--prefix", path, "python=3.12", "pip", "-y"]
        )
        _claim_environment(path)
        return "conda"
    if manager == "conda":
        raise RuntimeError("Conda was requested but is not installed")

    uv = shutil.which("uv")
    if manager in ("auto", "uv") and uv:
        _status(f"creating isolated environment at {path} with uv")
        _run_checked([uv, "venv", path, "--python", "3.12"])
        _claim_environment(path)
        return "uv"
    if manager == "uv":
        raise RuntimeError("uv was requested but is not installed")

    python_command = _venv_python_command()
    if manager in ("auto", "venv") and python_command:
        _status(f"creating isolated environment at {path} with venv")
        _run_checked([*python_command, "-m", "venv", path])
        _claim_environment(path)
        return "venv"
    if manager == "venv":
        raise RuntimeError("venv was requested but Python 3.12+ is unavailable")

    raise RuntimeError(
        "No safe environment manager is available. Install Conda, uv, or "
        "Python 3.12+, or provide a new environment location with --env-dir."
    )


def _conda_environment_path(conda: str, name: str):
    result = _run_checked(
        [conda, "env", "list", "--json"],
        capture_output=True,
        text=True,
    )
    try:
        environments = json.loads(result.stdout).get("envs", [])
    except json.JSONDecodeError as exc:
        raise RuntimeError("Conda returned invalid environment information") from exc

    matches = [
        Path(environment).resolve()
        for environment in environments
        if Path(environment).name.casefold() == name.casefold()
    ]
    if len(matches) > 1:
        choices = ", ".join(str(path) for path in matches)
        raise RuntimeError(f"Multiple Conda environments are named {name!r}: {choices}")
    return matches[0] if matches else None


def _resolve_named_conda_environment(conda: str) -> Path:
    path = _conda_environment_path(conda, CONDA_ENV_NAME)
    if path is not None:
        if not _is_managed_environment(path):
            raise RuntimeError(
                f"Conda environment {CONDA_ENV_NAME!r} already exists at {path} "
                "but is not managed by this skill. Ask the user for another "
                "location and pass it with --env-dir."
            )
        _status(f"using Conda environment at {path}")
        return path

    _status(
        f"creating dedicated Conda environment {CONDA_ENV_NAME!r}; "
        "Conda will use its configured environment directory"
    )
    _run_checked(
        [
            conda,
            "create",
            "--name",
            CONDA_ENV_NAME,
            "python=3.12",
            "pip",
            "-y",
        ]
    )
    path = _conda_environment_path(conda, CONDA_ENV_NAME)
    if path is None:
        raise RuntimeError(
            f"Conda created {CONDA_ENV_NAME!r} but its location could not be resolved"
        )
    _claim_environment(path)
    _status(f"Conda environment created at {path}")
    return path


def _existing_environment_manager(path: Path) -> str:
    return "conda" if (path / "conda-meta").is_dir() else "venv"


def _runtime_fingerprint() -> str:
    digest = hashlib.sha256()
    files = sorted(
        path
        for path in RUNTIME_DIR.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and path.suffix not in {".pyc", ".pyo"}
    )
    for path in files:
        digest.update(path.relative_to(RUNTIME_DIR).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _install_from_index(
    python: Path,
    manager: str,
    index_url: str,
) -> None:
    uv = shutil.which("uv")
    if uv and manager in ("auto", "uv"):
        _run_checked(
            [
                uv,
                "pip",
                "install",
                "--python",
                python,
                "--index-url",
                index_url,
                RUNTIME_DIR,
            ]
        )
    else:
        _run_checked(
            [
                python,
                "-m",
                "pip",
                "install",
                "--index-url",
                index_url,
                RUNTIME_DIR,
            ]
        )


def _install_runtime(
    path: Path,
    manager: str,
    index_url: str,
    fallback_index_url: str,
) -> Path:
    if not (RUNTIME_DIR / "pyproject.toml").is_file():
        raise RuntimeError(f"Bundled runtime is missing: {RUNTIME_DIR}")

    python = _environment_python(path)
    if python is None:
        raise RuntimeError(f"Environment Python was not created correctly: {path}")

    fingerprint = _runtime_fingerprint()
    marker = path / MARKER_NAME
    wellio = _environment_wellio(path)
    if (
        wellio
        and marker.is_file()
        and marker.read_text(encoding="utf-8").strip() == fingerprint
    ):
        return wellio

    _status(
        "installing the bundled runtime and third-party dependencies from "
        f"{index_url}"
    )
    try:
        _install_from_index(python, manager, index_url)
    except subprocess.CalledProcessError:
        if not fallback_index_url or fallback_index_url == index_url:
            raise
        _status(
            f"the primary package index failed; retrying {fallback_index_url}"
        )
        _install_from_index(python, manager, fallback_index_url)

    wellio = _environment_wellio(path)
    if wellio is None:
        raise RuntimeError(f"Wellio executable was not installed in {path}")
    subprocess.run(
        [str(wellio), "--help"],
        stdout=subprocess.DEVNULL,
        check=True,
    )
    marker.write_text(fingerprint + "\n", encoding="utf-8")
    _status(f"runtime ready at {path}")
    return wellio


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Wellio CLI from this skill's isolated runtime."
    )
    parser.add_argument(
        "--env-dir",
        help="Override the managed environment directory.",
    )
    parser.add_argument(
        "--manager",
        choices=("auto", "uv", "venv", "conda"),
        default=os.environ.get("WELLIO_ENV_MANAGER", "auto"),
        help="Choose the environment manager (default: auto).",
    )
    parser.add_argument(
        "--index-url",
        default=os.environ.get("WELLIO_PYPI_INDEX_URL", DEFAULT_INDEX_URL),
        help="Primary Python package index.",
    )
    parser.add_argument(
        "--fallback-index-url",
        default=os.environ.get(
            "WELLIO_PYPI_FALLBACK_INDEX_URL",
            DEFAULT_FALLBACK_INDEX_URL,
        ),
        help="Package index retried if the primary index fails.",
    )
    parser.add_argument(
        "wellio_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to Wellio after --.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    wellio_args = list(args.wellio_args)
    if wellio_args[:1] == ["--"]:
        wellio_args.pop(0)
    if not wellio_args:
        wellio_args = ["--help"]

    try:
        requested_dir = _requested_environment_dir(args.env_dir)
        conda = shutil.which("conda")
        if requested_dir is None and args.manager in ("auto", "conda") and conda:
            environment_dir = _resolve_named_conda_environment(conda)
            manager = "conda"
        else:
            environment_dir = requested_dir or _default_environment_dir().resolve()
            _prepare_environment_target(environment_dir)
            if _looks_like_environment(environment_dir):
                manager = _existing_environment_manager(environment_dir)
                if args.manager == "conda" and manager != "conda":
                    raise RuntimeError(
                        f"Requested Conda, but {environment_dir} is not a "
                        "Conda environment"
                    )
                if args.manager in ("uv", "venv") and manager == "conda":
                    raise RuntimeError(
                        f"Requested {args.manager}, but {environment_dir} is a "
                        "Conda environment"
                    )
            else:
                manager = _create_environment(environment_dir, args.manager)
        wellio = _install_runtime(
            environment_dir,
            manager,
            args.index_url,
            args.fallback_index_url,
        )
        completed = subprocess.run([str(wellio), *wellio_args], check=False)
        return completed.returncode
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Wellio skill setup failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
