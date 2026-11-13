"""Filesystem locations, per ``core-spec/SPEC.md``.

Every function accepts optional ``env`` and ``home`` overrides so tests never
touch the real home directory, and only creates the directory when called
with ``create=True``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Mapping

__all__ = [
    "APP_DIR_NAME",
    "OUTPUT_DIR_NAME",
    "output_dir",
    "temp_dir",
    "config_dir",
    "data_dir",
    "cache_dir",
]

APP_DIR_NAME = "elisium-downloader"
OUTPUT_DIR_NAME = "Elisium Downloader"


def _environment(env: Mapping[str, str] | None) -> dict[str, str]:
    if env is None:
        return dict(os.environ)
    return {str(key): str(value) for key, value in env.items()}


def _home(env: Mapping[str, str], home: str | os.PathLike[str] | None) -> Path:
    if home is not None:
        return Path(home).expanduser()
    value = env.get("HOME")
    if value:
        return Path(value).expanduser()
    return Path.home()


def _xdg_path(env: Mapping[str, str], key: str, fallback: Path, home: Path) -> Path:
    value = env.get(key)
    if not value:
        return fallback
    return _expand(value, home)


def _expand(value: str, home: Path) -> Path:
    if value == "$HOME" or value.startswith("$HOME/"):
        value = str(home) + value[len("$HOME") :]
    return Path(value).expanduser()


def _xdg_user_dir_download() -> Path | None:
    """Ask ``xdg-user-dir`` for the download folder; ``None`` if unavailable."""
    try:
        result = subprocess.run(
            ["xdg-user-dir", "DOWNLOAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    path = result.stdout.strip()
    if result.returncode != 0 or not path:
        return None
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        return None
    return candidate


def _finish(path: Path, create: bool) -> Path:
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def output_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
    create: bool = False,
) -> Path:
    """``<download folder>/Elisium Downloader``."""
    environment = _environment(env)
    home_path = _home(environment, home)
    # When the caller supplies an env, it is a test override: never probe the
    # real machine, and only honour an explicit XDG_DOWNLOAD_DIR.
    configured = environment.get("XDG_DOWNLOAD_DIR")
    if env is None:
        root = _xdg_user_dir_download()
        if root is None:
            root = (
                _expand(configured, home_path)
                if configured
                else home_path / "Downloads"
            )
    elif configured:
        root = _expand(configured, home_path)
    else:
        root = home_path / "Downloads"
    return _finish(root / OUTPUT_DIR_NAME, create)


def temp_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
    create: bool = False,
) -> Path:
    """Staging area for ``-P temp:`` so the output folder holds no ``.part``."""
    return _finish(cache_dir(env=env, home=home) / "tmp", create)


def config_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
    create: bool = False,
) -> Path:
    """``~/.config/elisium-downloader`` (or ``$XDG_CONFIG_HOME``)."""
    environment = _environment(env)
    home_path = _home(environment, home)
    base = _xdg_path(environment, "XDG_CONFIG_HOME", home_path / ".config", home_path)
    return _finish(base / APP_DIR_NAME, create)


def data_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
    create: bool = False,
) -> Path:
    """``~/.local/share/elisium-downloader`` (history.sqlite, archive.txt)."""
    environment = _environment(env)
    home_path = _home(environment, home)
    base = _xdg_path(
        environment, "XDG_DATA_HOME", home_path / ".local" / "share", home_path
    )
    return _finish(base / APP_DIR_NAME, create)


def cache_dir(
    *,
    env: Mapping[str, str] | None = None,
    home: str | os.PathLike[str] | None = None,
    create: bool = False,
) -> Path:
    """``~/.cache/elisium-downloader`` (or ``$XDG_CACHE_HOME``)."""
    environment = _environment(env)
    home_path = _home(environment, home)
    base = _xdg_path(environment, "XDG_CACHE_HOME", home_path / ".cache", home_path)
    return _finish(base / APP_DIR_NAME, create)
