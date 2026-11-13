from __future__ import annotations

from pathlib import Path

from elisium_downloader.engine import paths


def _env(home: Path, **extra: str) -> dict[str, str]:
    return {"HOME": str(home), **extra}


def test_default_locations_use_home_override(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _env(home)

    assert paths.config_dir(env=env) == home / ".config" / "elisium"
    assert paths.data_dir(env=env) == home / ".local" / "share" / "elisium"
    assert paths.cache_dir(env=env) == home / ".cache" / "elisium"
    assert paths.temp_dir(env=env) == home / ".cache" / "elisium" / "tmp"
    assert paths.output_dir(env=env) == home / "Downloads" / "Elisium"


def test_xdg_overrides_are_honoured(tmp_path: Path) -> None:
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    env = _env(
        home,
        XDG_CONFIG_HOME=str(xdg / "config"),
        XDG_DATA_HOME=str(xdg / "data"),
        XDG_CACHE_HOME=str(xdg / "cache"),
        XDG_DOWNLOAD_DIR=str(xdg / "downloads"),
    )

    assert paths.config_dir(env=env) == xdg / "config" / "elisium"
    assert paths.data_dir(env=env) == xdg / "data" / "elisium"
    assert paths.cache_dir(env=env) == xdg / "cache" / "elisium"
    assert paths.temp_dir(env=env) == xdg / "cache" / "elisium" / "tmp"
    assert paths.output_dir(env=env) == xdg / "downloads" / "Elisium"


def test_xdg_download_dir_expands_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _env(home, XDG_DOWNLOAD_DIR="$HOME/My Downloads")
    assert paths.output_dir(env=env) == home / "My Downloads" / "Elisium"


def test_directories_are_only_created_with_create_true(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = _env(home)

    for func in (
        paths.output_dir,
        paths.temp_dir,
        paths.config_dir,
        paths.data_dir,
        paths.cache_dir,
    ):
        path = func(env=env)
        assert not path.exists(), f"{func.__name__} created {path} without create=True"

    created = paths.data_dir(env=env, create=True)
    assert created.is_dir()

    output = paths.output_dir(env=env, create=True)
    assert output.is_dir()


def test_explicit_home_argument_wins_over_env(tmp_path: Path) -> None:
    env = {"HOME": str(tmp_path / "ignored")}
    home = tmp_path / "actual"
    assert paths.config_dir(env=env, home=home) == home / ".config" / "elisium"


def test_real_home_is_not_touched_when_overrides_are_given(
    tmp_path: Path, monkeypatch
) -> None:
    def _boom(*args, **kwargs):  # pragma: no cover - should never run
        raise AssertionError("real home was consulted")

    monkeypatch.setattr(Path, "home", classmethod(_boom))
    monkeypatch.setattr(paths.subprocess, "run", _boom)

    home = tmp_path / "home"
    env = _env(home)
    assert paths.output_dir(env=env).is_relative_to(tmp_path)
    assert paths.temp_dir(env=env).is_relative_to(tmp_path)
    assert paths.config_dir(env=env).is_relative_to(tmp_path)
    assert paths.data_dir(env=env).is_relative_to(tmp_path)
    assert paths.cache_dir(env=env).is_relative_to(tmp_path)
