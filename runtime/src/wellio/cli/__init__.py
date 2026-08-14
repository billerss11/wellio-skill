"""Command-line interface for Wellio."""

import sys

from wellio.cli.app import app


def _configure_utf8_output() -> None:
    """Make console and piped command output deterministic."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="strict")


def main() -> None:
    """Run the CLI with strict UTF-8 standard streams."""

    _configure_utf8_output()
    app()


__all__ = ["app", "main"]
