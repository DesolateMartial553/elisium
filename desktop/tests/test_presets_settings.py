from __future__ import annotations

import json
import os

import pytest

from elisium_downloader.engine import presets
from elisium_downloader.ui import settings as st


def test_presets_table() -> None:
    assert list(presets.PRESETS) == [
        "best", "1080p", "720p", "audio-mp3", "audio-m4a", "audio-opus", "audio-flac", "smallest",
    ]
    assert presets.PRESETS["best"].format_selector == "bestvideo*+bestaudio/best"
    assert presets.PRESETS["1080p"].format_selector == "bestvideo*[height<=1080]+bestaudio/best[height<=1080]"
    assert presets.PRESETS["720p"].format_selector.count("720") == 2
    mp3 = presets.PRESETS["audio-mp3"]
    assert mp3.label == "Audio only (MP3)" and mp3.format_selector == "bestaudio/best"
    assert mp3.extra_args == ("-x", "--audio-format", "mp3")
    for fmt in ("m4a", "opus", "flac"):
        assert presets.PRESETS[f"audio-{fmt}"].extra_args == ("-x", "--audio-format", fmt)
    assert presets.PRESETS["smallest"].format_selector == "wv*+wa/w"
    assert presets.PRESETS["smallest"].label == "Smallest file"
    assert presets.DEFAULT_ID == "best"


def test_m4a_and_opus_presets_prefer_a_stream_that_needs_no_re_encoding() -> None:
    m4a, opus = presets.PRESETS["audio-m4a"], presets.PRESETS["audio-opus"]
    assert m4a.format_selector == "bestaudio[ext=m4a]/bestaudio/best"
    assert opus.format_selector == "bestaudio[acodec=opus]/bestaudio/best"
    assert m4a.extra_args == ("-x", "--audio-format", "m4a")
    assert opus.extra_args == ("-x", "--audio-format", "opus")
    # MP3 and FLAC must encode, so they keep the plain selector.
    for fmt in ("mp3", "flac"):
        assert presets.PRESETS[f"audio-{fmt}"].format_selector == "bestaudio/best"


def test_unknown_preset_falls_back_to_best() -> None:
    assert presets.get("nope") is presets.PRESETS["best"]
    assert presets.get(None) is presets.PRESETS["best"]
    assert presets.get("720p").id == "720p"


def test_settings_defaults_and_validation() -> None:
    s = st.Settings()
    assert (s.concurrency, s.speed_limit, s.preset_id, s.notify_on_done, s.close_to_tray) == (
        2, None, "best", True, False)
    assert st.Settings(concurrency=0).concurrency == 2
    assert st.Settings(concurrency=6).concurrency == 2
    assert st.Settings(concurrency=5).concurrency == 5
    assert st.Settings(concurrency=True).concurrency == 2
    for good in ("2M", "500K", "1.5G", "100"):
        assert st.Settings(speed_limit=good).speed_limit == good
    for bad in ("fast", "2MB", "-1M", "", "1.M", 5):
        assert st.Settings(speed_limit=bad).speed_limit is None
    assert st.Settings(preset_id="zzz").preset_id == "best"
    assert st.Settings(notify_on_done="yes").notify_on_done is True


def test_round_trip_and_atomic_write(tmp_path) -> None:
    path = tmp_path / "cfg" / "settings.json"
    original = st.Settings(concurrency=4, speed_limit="2M", preset_id="audio-mp3",
                           notify_on_done=False, close_to_tray=True)
    st.save(original, path)
    assert st.load(path) == original
    assert os.listdir(path.parent) == ["settings.json"]  # no temp file left


def test_atomic_write_keeps_old_file_on_failure(tmp_path, monkeypatch) -> None:
    path = tmp_path / "settings.json"
    st.save(st.Settings(concurrency=3), path)

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(st.os, "replace", boom)
    with pytest.raises(OSError):
        st.save(st.Settings(concurrency=5), path)
    monkeypatch.undo()
    assert st.load(path).concurrency == 3
    assert os.listdir(tmp_path) == ["settings.json"]


def test_missing_and_corrupt_files_give_defaults(tmp_path) -> None:
    assert st.load(tmp_path / "none.json") == st.Settings()
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert st.load(bad) == st.Settings()
    bad.write_text("[1, 2]", encoding="utf-8")
    assert st.load(bad) == st.Settings()
    bad.write_bytes(b"\xff\xfe\x00")
    assert st.load(bad) == st.Settings()


def test_unknown_keys_ignored_and_bad_values_defaulted(tmp_path) -> None:
    path = tmp_path / "s.json"
    path.write_text(json.dumps({"concurrency": 3, "future": 1, "preset_id": "x"}))
    s = st.load(path)
    assert s.concurrency == 3 and s.preset_id == "best"
    # A settings file written before the cookie fields existed still loads.
    assert s.cookies_browser is None and s.cookies_file is None


def test_cookie_settings_round_trip(tmp_path) -> None:
    path = tmp_path / "settings.json"
    original = st.Settings(cookies_browser="firefox", cookies_file="/tmp/cookies.txt")
    st.save(original, path)
    assert st.load(path) == original
    assert json.loads(path.read_text())["cookies_browser"] == "firefox"


def test_cookie_settings_validation() -> None:
    assert st.Settings().cookies_browser is None
    assert st.Settings(cookies_browser=" Chrome ").cookies_browser == "chrome"
    assert st.Settings(cookies_browser="safari").cookies_browser is None
    assert st.Settings(cookies_browser=5).cookies_browser is None  # type: ignore[arg-type]
    assert st.Settings(cookies_file=" /tmp/c.txt ").cookies_file == "/tmp/c.txt"
    assert st.Settings(cookies_file="   ").cookies_file is None
    assert st.Settings(cookies_file=7).cookies_file is None  # type: ignore[arg-type]
    assert set(st.COOKIE_BROWSERS) == {
        "firefox", "chrome", "chromium", "brave", "edge", "vivaldi", "opera",
    }


def test_apply_pushes_the_cookie_choice() -> None:
    calls: list = []

    class FakeQueue:
        def set_concurrency(self, v): pass
        def set_limit_rate(self, v): pass
        def set_format_selector(self, v): pass
        def set_extra_args(self, v): pass
        def set_cookies(self, browser, file): calls.append((browser, file))
        def set_photo_mode(self, v): pass
        def set_song_length(self, v): pass
        def set_reuse_probe(self, v): pass

    st.apply(st.Settings(cookies_browser="brave", cookies_file=None), FakeQueue())
    st.apply(st.Settings(), FakeQueue())
    assert calls == [("brave", None), (None, None)]


def test_apply_calls_queue_setters() -> None:
    calls: list = []

    class FakeQueue:
        def set_concurrency(self, v): calls.append(("c", v))
        def set_limit_rate(self, v): calls.append(("l", v))
        def set_format_selector(self, v): calls.append(("f", v))
        def set_extra_args(self, v): calls.append(("e", tuple(v)))
        def set_cookies(self, browser, file): calls.append(("ck", browser, file))
        def set_photo_mode(self, v): calls.append(("pm", v))
        def set_song_length(self, v): calls.append(("sl", v))
        def set_reuse_probe(self, v): calls.append(("rp", v))

    st.apply(st.Settings(concurrency=4, speed_limit="1M", preset_id="audio-flac"), FakeQueue())
    assert calls == [("c", 4), ("l", "1M"), ("f", "bestaudio/best"),
                     ("e", ("-x", "--audio-format", "flac")),
                     ("ck", None, None), ("pm", "video"), ("sl", "snippet"), ("rp", True)]
