"""Command line entry point."""

from __future__ import annotations

from collections.abc import Sequence

__all__ = ["main"]


def main(argv: Sequence[str] | None = None) -> int:
    """No arguments launches the GUI. (Subcommands come later.)"""
    from .ui.app import run

    return run(argv)
