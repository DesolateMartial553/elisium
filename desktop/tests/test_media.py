"""Brief 10B-1: the gallery-dl media engine (offline, fake binary, hand-made fixtures)."""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from elisium_downloader.engine import media
from elisium_downloader.engine.media import MediaUrlKind

FIXTURES = Path(__file__).parent / "fixtures" / "media"
REPO = Path(__file__).resolve().parents[2]

IG = "https://www.instagram.com"
TRAY = f"{IG}/stories/bakery_north/"
POST = f"{IG}/p/CAbc123xyz/"
TIKTOK = "https://www.tiktok.com/@dancer/photo/7300000000000000001"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# -- fake gallery-dl -----------------------------------------------------
def write_fake_gallery(
    tmp_path: Path,
    *,
    log: Path,
    fixture: str | None = "instagram_single_image.json",
    probe_stdout: str | None = None,
    probe_stderr: str = "",
    probe_code: int = 0,
    download_stderr: str = "",
    download_code: int = 0,
    sleep_after_first: float = 0.0,
    name: str = "fake-gallery-dl",
) -> Path:
    """A fake gallery-dl: logs argv, answers ``-j`` from a fixture, "downloads" files.

    The download half creates one file (plus ``.json`` metadata) per ``[3, ...]``
    message in ``-D``, prints its path (``# path`` when the fake archive already
    holds it) and appends to the file given as ``--download-archive``.
    """
    text = probe_stdout if probe_stdout is not None else (
        fixture_text(fixture) if fixture else ""
    )
    lines = [
        "#!/usr/bin/env python3",
        "import json, os, sys, time",
        "argv = sys.argv[1:]",
        f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:",
        "    fh.write(json.dumps(argv) + '\\n')",
        f"TEXT = {text!r}",
        "if '-j' in argv:",
        f"    sys.stderr.write({probe_stderr!r})",
        "    sys.stdout.write(TEXT)",
        f"    sys.exit({probe_code})",
        "directory = argv[argv.index('-D') + 1]",
        "archive = argv[argv.index('--download-archive') + 1]",
        "seen = set(open(archive).read().split()) if os.path.exists(archive) else set()",
        "messages = json.loads(TEXT) if TEXT.strip() else []",
        "count = 0",
        "for message in messages:",
        "    if message[0] != 3:",
        "        continue",
        "    meta = message[2]",
        "    who = meta.get('username') or meta['author']['uniqueId']",
        "    ident = str(meta.get('media_id') or meta['id'])",
        "    key = meta['category'] + ':' + ident + ':' + str(meta['num'])",
        "    path = os.path.join(directory, f\"{who} {ident} {meta['num']}.{meta['extension']}\")",
        "    if key in seen:",
        "        print('# ' + path, flush=True)",
        "        continue",
        "    os.makedirs(directory, exist_ok=True)",
        "    open(path, 'w').write('data ' + key)",
        "    open(path + '.json', 'w').write(json.dumps(meta))",
        "    with open(archive, 'a') as fh:",
        "        fh.write(key + '\\n')",
        "    print(path, flush=True)",
        "    count += 1",
        f"    if {sleep_after_first!r} and count == 1:",
        f"        time.sleep({sleep_after_first!r})",
        f"sys.stderr.write({download_stderr!r})",
        f"sys.exit({download_code})",
    ]
    script = tmp_path / name
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def read_log(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]


def value_after(argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


# -- URL classification and routing --------------------------------------
@pytest.mark.parametrize(
    ("url", "kind"),
    [
        (f"{IG}/p/CAbc123xyz/", MediaUrlKind.POST),
        (f"{IG}/tv/CAbc123xyz/", MediaUrlKind.POST),
        ("https://m.instagram.com/p/CAbc123xyz/?igsh=abc&utm_source=x", MediaUrlKind.POST),
        (f"{IG}/reel/CAbc123xyz/", MediaUrlKind.REEL),
        (f"{IG}/stories/bakery_north/", MediaUrlKind.STORIES_USER),
        (f"{IG}/stories/bakery_north", MediaUrlKind.STORIES_USER),
        (f"{IG}/stories/bakery_north/3303000000000000001/", MediaUrlKind.STORY_ITEM),
        (f"{IG}/stories/highlights/17912345678901234/", MediaUrlKind.HIGHLIGHT),
        (f"{IG}/stories/highlights/", MediaUrlKind.UNKNOWN),
        (f"{IG}/stories/highlights/abc/", MediaUrlKind.UNKNOWN),
        (f"{IG}/bakery_north/", MediaUrlKind.UNKNOWN),
        (f"{IG}/reels/bakery_north/", MediaUrlKind.UNKNOWN),
        (f"{IG}/", MediaUrlKind.UNKNOWN),
        (TIKTOK, MediaUrlKind.TIKTOK_PHOTO),
        ("https://www.tiktok.com/@dancer/video/7300000000000000001", MediaUrlKind.UNKNOWN),
        ("https://vm.tiktok.com/ZMabc123/", MediaUrlKind.UNKNOWN),
        ("https://www.tiktok.com/@dancer", MediaUrlKind.UNKNOWN),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", MediaUrlKind.UNKNOWN),
        ("not a url", MediaUrlKind.UNKNOWN),
        ("", MediaUrlKind.UNKNOWN),
    ],
)
def test_classify_media_url(url: str, kind: MediaUrlKind) -> None:
    assert media.classify_media_url(url).kind is kind


def test_classify_media_url_fields() -> None:
    tray = media.classify_media_url(TRAY)
    assert (tray.site, tray.username) == ("instagram", "bakery_north")
    item = media.classify_media_url(f"{IG}/stories/bakery_north/3303000000000000001/")
    assert (item.username, item.story_id) == ("bakery_north", "3303000000000000001")
    assert media.classify_media_url(f"{IG}/stories/highlights/77/").highlight_id == "77"
    post = media.classify_media_url(POST)
    assert post.shortcode == "CAbc123xyz"
    tt = media.classify_media_url(TIKTOK)
    assert (tt.site, tt.username, tt.tiktok_id) == ("tiktok", "dancer", "7300000000000000001")
    assert media.classify_media_url(None).kind is MediaUrlKind.UNKNOWN


@pytest.mark.parametrize(
    ("url", "route"),
    [
        (TRAY, "media"),
        (f"{IG}/stories/highlights/17912345678901234/", "media"),
        (TIKTOK, "media"),
        (POST, "ytdlp_then_media"),
        (f"{IG}/tv/CAbc123xyz/", "ytdlp_then_media"),
        (f"{IG}/stories/bakery_north/3303000000000000001/", "ytdlp_then_media"),
        (f"{IG}/reel/CAbc123xyz/", "ytdlp"),
        ("https://www.tiktok.com/@dancer/video/7300000000000000001", "ytdlp"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "ytdlp"),
        ("https://vimeo.com/1", "ytdlp"),
    ],
)
def test_route_for(url: str, route: str) -> None:
    assert media.route_for(url) == route


def test_find_gallery_dl_uses_path(monkeypatch) -> None:
    monkeypatch.undo()  # drop conftest's "no real gallery-dl" stub for this test
    monkeypatch.setattr(media.shutil, "which", lambda name: f"/x/{name}")
    assert media.find_gallery_dl() == "/x/gallery-dl"
    monkeypatch.setattr(media.shutil, "which", lambda name: None)
    assert media.find_gallery_dl() is None


# -- config --------------------------------------------------------------
def test_write_config_is_private_and_turns_audio_on(tmp_path: Path) -> None:
    path = media.write_config(tmp_path / "cache" / "gallery-dl.json")
    assert path == tmp_path / "cache" / "gallery-dl.json"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    data = json.loads(path.read_text())
    assert data["extractor"]["instagram"]["audio"] is True
    assert data["extractor"]["instagram"]["videos"] is True
    assert data["extractor"]["tiktok"]["audio"] is True
    assert data["extractor"]["tiktok"]["photos"] is True
    # The stdout format the file counter relies on is pinned, not auto-detected.
    assert data["output"]["mode"] == "pipe"
    assert data["output"]["skip"] is True
    assert data["output"]["shorten"] is False
    assert data["output"]["progress"] is False


def test_write_config_replaces_a_loose_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "gallery-dl.json"
    path.write_text("{}")
    path.chmod(0o644)
    media.write_config(path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert "extractor" in json.loads(path.read_text())
    assert [p.name for p in tmp_path.iterdir()] == ["gallery-dl.json"]  # no scratch left


# -- argv ----------------------------------------------------------------
def make_opts(tmp_path: Path, url: str = POST, **over: Any) -> media.MediaOptions:
    return media.MediaOptions(
        url=url,
        directory=tmp_path / "stage",
        config_path=tmp_path / "gallery-dl.json",
        archive_path=tmp_path / "gallery-archive.sqlite3",
        gallery_dl="gallery-dl",
        **over,
    )


def test_download_argv(tmp_path: Path) -> None:
    argv = media.build_command(make_opts(tmp_path))
    assert argv[0] == "gallery-dl"
    assert "--config-ignore" in argv
    assert value_after(argv, "--config-json") == str(tmp_path / "gallery-dl.json")
    assert argv.index("--config-ignore") < argv.index("--config-json")
    assert value_after(argv, "-D") == str(tmp_path / "stage")
    assert value_after(argv, "--download-archive") == str(tmp_path / "gallery-archive.sqlite3")
    assert "--write-metadata" in argv
    assert "--no-input" in argv
    assert argv[-1] == POST
    # Never a probe flag on a download.
    assert "-s" not in argv and "-j" not in argv
    # No cookies, no rate limit unless asked.
    assert "--cookies" not in argv and "--cookies-from-browser" not in argv
    assert "--limit-rate" not in argv


def test_filename_formats_always_carry_the_media_id(tmp_path: Path) -> None:
    ig = value_after(media.build_command(make_opts(tmp_path, POST)), "-f")
    assert "{username}" in ig and "{date:%Y-%m-%d}" in ig and "{num}" in ig
    assert "[{media_id" in ig and ig.endswith(".{extension}")
    tt = value_after(media.build_command(make_opts(tmp_path, TIKTOK)), "-f")
    assert tt == "{author[uniqueId]} {id} [{id}_{num}] {num}.{extension}"
    # An explicit format wins.
    explicit = media.build_command(make_opts(tmp_path, POST, filename_format="{id}.{extension}"))
    assert value_after(explicit, "-f") == "{id}.{extension}"


def test_cookie_variants(tmp_path: Path) -> None:
    browser = media.build_command(make_opts(tmp_path, cookies_browser="firefox", cookies_file="/c.txt"))
    assert value_after(browser, "--cookies-from-browser") == "firefox"
    assert "--cookies" not in browser  # the browser wins
    only_file = media.build_command(make_opts(tmp_path, cookies_file="/c.txt"))
    assert value_after(only_file, "--cookies") == "/c.txt"
    assert "--cookies-from-browser" not in only_file
    limited = media.build_command(make_opts(tmp_path, limit_rate="2M"))
    assert value_after(limited, "--limit-rate") == "2M"


def test_probe_argv(tmp_path: Path) -> None:
    argv = media.build_probe_command(
        TRAY, "gallery-dl", config_path=tmp_path / "c.json", cookies_browser="firefox"
    )
    assert argv[0] == "gallery-dl"
    assert "--config-ignore" in argv
    assert value_after(argv, "--config-json") == str(tmp_path / "c.json")
    assert "-s" in argv and "-j" in argv
    assert value_after(argv, "--cookies-from-browser") == "firefox"
    assert argv[-1] == TRAY
    assert "-D" not in argv and "--download-archive" not in argv


def test_options_reject_an_empty_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        make_opts(tmp_path, url="  ")


# -- probe parsing -------------------------------------------------------
def test_parse_single_image() -> None:
    plan = media.parse_probe(fixture_text("instagram_single_image.json"), POST)
    assert plan.site == "instagram"
    assert plan.total == 1
    only = plan.files[0]
    assert (only.kind, only.media_id, only.num, only.ext) == (
        "image",
        "3300000000000000001",
        1,
        "jpg",
    )
    assert plan.owner == "cafe_northfield"
    assert plan.shortcode == "CAbc123xyz"
    assert plan.post_id == "3300000000000000001"
    assert plan.date == "2026-11-01 10:30:00"
    assert plan.title == "Fresh bread today"  # first caption line only
    assert plan.display_title == "Fresh bread today"


def test_parse_carousel_mixed_keeps_order_and_kinds() -> None:
    plan = media.parse_probe(fixture_text("instagram_carousel_mixed.json"), POST)
    assert [(f.num, f.kind, f.ext) for f in plan.files] == [
        (1, "image", "jpg"),
        (2, "video", "mp4"),
        (3, "image", "jpg"),
    ]
    assert [f.media_id for f in plan.files] == [
        "3301000000000000001",
        "3301000000000000002",
        "3301000000000000003",
    ]


def test_parse_image_with_music() -> None:
    plan = media.parse_probe(fixture_text("instagram_image_with_music.json"), POST)
    assert [f.kind for f in plan.files] == ["image", "audio"]
    assert plan.files[1].ext == "m4a"
    assert plan.files[1].is_audio


def test_parse_story_tray_without_a_shortcode() -> None:
    plan = media.parse_probe(fixture_text("instagram_story_tray.json"), TRAY)
    assert plan.total == 3
    assert plan.owner == "bakery_north"
    assert plan.shortcode is None
    assert plan.title is None
    assert plan.display_title == "bakery_north 3303000000000000000"


def test_parse_tiktok_slideshow() -> None:
    plan = media.parse_probe(fixture_text("tiktok_photo_slideshow.json"), TIKTOK)
    assert plan.site == "tiktok"
    assert plan.owner == "dancer"  # author.uniqueId
    assert plan.title == "Three slides #fyp"
    assert [f.kind for f in plan.files] == ["image", "image", "image", "audio"]
    assert [f.media_id for f in plan.files] == [
        "7300000000000000001_1",
        "7300000000000000001_2",
        "7300000000000000001_3",
        "7300000000000000001_4",
    ]


def test_parse_accepts_json_lines_and_one_message() -> None:
    plan = media.parse_probe(fixture_text("instagram_single_image.jsonl"), POST)
    assert plan.total == 1 and plan.owner == "cafe_northfield"
    one = media.parse_probe(
        '[3, "https://cdn.example.com/a.png", {"num": 1, "id": "9"}]', IG + "/p/x/"
    )
    assert [(f.kind, f.ext, f.media_id) for f in one.files] == [("image", "png", "9")]


@pytest.mark.parametrize("text", ["", "[]", "  \n", "not json at all", "{}", "[[]]", "null"])
def test_parse_empty_or_garbage_has_no_files(text: str) -> None:
    plan = media.parse_probe(text, POST)
    assert plan.total == 0 and plan.display_title is None


def test_parse_skips_noise_and_unknown_messages() -> None:
    text = (
        "[instagram][info] hello\n"
        '[[1, {"version": "1.32.20"}], [6, "https://x.example/child", {}], '
        '[3, "https://cdn.example.com/a.jpg", {"num": 1, "media_id": "5"}]]\n'
    )
    assert media.parse_probe(text, POST).total == 1


def test_parse_tolerates_missing_fields() -> None:
    plan = media.parse_probe('[[3, "https://cdn.example.com/clip", {}]]', POST)
    assert plan.total == 1
    only = plan.files[0]
    assert (only.kind, only.media_id, only.num, only.ext) == ("image", "", 1, "")


def test_kind_follows_the_extension_first() -> None:
    text = json.dumps(
        [
            [3, "u1", {"extension": "MP4", "type": "image", "num": 1}],
            [3, "u2", {"extension": "opus", "num": 2}],
            [3, "u3", {"extension": "bin", "type": "video", "num": 3}],
        ]
    )
    assert [f.kind for f in media.parse_probe(text, POST).files] == ["video", "audio", "video"]


def test_archive_keys_mirror_android() -> None:
    assert media.archive_key("Instagram", "3300000000000000001") == "instagram 3300000000000000001"
    assert media.archive_key("tiktok", "7300000000000000001_2") == "tiktok 7300000000000000001_2"
    assert media.mix_key("instagram", "CAbc123xyz") == "instagram CAbc123xyz_mix"
    assert media.mix_key("tiktok", "73") == "tiktok 73_mix"


# -- probe() with a fake binary ------------------------------------------
def probe_with(tmp_path: Path, url: str = POST, **fake: Any):
    log = tmp_path / "gdl.log"
    script = write_fake_gallery(tmp_path, log=log, **fake)
    cfg = media.write_config(tmp_path / "gallery-dl.json")

    def call(**kwargs: Any):
        return media.probe(url, str(script), config_path=cfg, **kwargs)

    return call, log


def test_probe_returns_the_plan(tmp_path: Path) -> None:
    call, log = probe_with(tmp_path, fixture="instagram_carousel_mixed.json")
    plan = call()
    assert plan.total == 3
    (argv,) = read_log(log)
    assert "-s" in argv and "-j" in argv and "--config-ignore" in argv


def test_probe_passes_cookies_through(tmp_path: Path) -> None:
    call, log = probe_with(tmp_path)
    call(cookies_browser="firefox", cookies_file="/c.txt")
    (argv,) = read_log(log)
    assert value_after(argv, "--cookies-from-browser") == "firefox"
    assert "--cookies" not in argv


def test_probe_login_required(tmp_path: Path) -> None:
    call, _ = probe_with(
        tmp_path,
        probe_stdout="[]",
        probe_stderr=fixture_text("login_required.txt"),
        probe_code=4,
    )
    with pytest.raises(media.MediaProbeError) as caught:
        call()
    assert caught.value.info.code == "login_required"
    assert "Instagram" in caught.value.info.message
    assert "authenticated cookies" in caught.value.raw


def test_probe_login_required_with_cookies_is_an_expired_session(tmp_path: Path) -> None:
    call, _ = probe_with(
        tmp_path,
        probe_stdout="[]",
        probe_stderr=fixture_text("login_required.txt"),
        probe_code=4,
    )
    with pytest.raises(media.MediaProbeError) as caught:
        call(cookies_browser="firefox")
    assert caught.value.info.code == "session_expired"


def test_probe_empty_story_tray_is_expired(tmp_path: Path) -> None:
    call, _ = probe_with(tmp_path, url=TRAY, fixture="empty.json")
    with pytest.raises(media.MediaProbeError) as caught:
        call()
    assert caught.value.info.code == "story_expired"


def test_probe_empty_post_has_no_media(tmp_path: Path) -> None:
    call, _ = probe_with(tmp_path, url=POST, fixture="empty.json")
    with pytest.raises(media.MediaProbeError) as caught:
        call()
    assert caught.value.info.code == "no_media"


def test_probe_empty_highlight_has_no_media(tmp_path: Path) -> None:
    call, _ = probe_with(tmp_path, url=f"{IG}/stories/highlights/12345/", fixture="empty.json")
    with pytest.raises(media.MediaProbeError) as caught:
        call()
    assert caught.value.info.code == "no_media"


@pytest.mark.parametrize(
    ("stderr", "code"),
    [
        ("[instagram][error] HttpError: '429 Too Many Requests'", "rate_limited"),
        ("[instagram][error] This account is private", "private_account"),
        ("[instagram][error] HttpError: '404 Not Found'", "video_unavailable"),
        ("[instagram][error] Connection reset by peer", "network"),
    ],
)
def test_probe_error_mapping(tmp_path: Path, stderr: str, code: str) -> None:
    call, _ = probe_with(tmp_path, probe_stdout="", probe_stderr=stderr, probe_code=1)
    with pytest.raises(media.MediaProbeError) as caught:
        call()
    assert caught.value.info.code == code


def test_probe_unknown_failure_is_the_generic_message(tmp_path: Path) -> None:
    call, _ = probe_with(tmp_path, probe_stdout="", probe_stderr="boom", probe_code=1)
    with pytest.raises(media.MediaProbeError) as caught:
        call()
    assert caught.value.info.code == "unknown"


def test_probe_caption_text_is_not_read_as_an_error(tmp_path: Path) -> None:
    text = json.dumps(
        [[3, "u", {"category": "instagram", "num": 1, "media_id": "1", "extension": "jpg",
                   "description": "this account is private, 429 too many requests"}]]
    )
    call, _ = probe_with(tmp_path, probe_stdout=text, probe_code=1)
    assert call().total == 1  # files were listed: the plan is returned


def test_probe_missing_binary(tmp_path: Path) -> None:
    cfg = media.write_config(tmp_path / "c.json")
    with pytest.raises(media.MediaProbeError) as caught:
        media.probe(POST, str(tmp_path / "nope"), config_path=cfg)
    assert caught.value.info.code == "gallery_dl_missing"
    assert "sudo pacman -S gallery-dl" in caught.value.info.message


# -- run(): counting files ------------------------------------------------
def test_run_counts_finished_and_skipped_files(tmp_path: Path) -> None:
    log = tmp_path / "gdl.log"
    script = write_fake_gallery(tmp_path, log=log, fixture="instagram_carousel_mixed.json")
    archive = tmp_path / "gallery-archive.sqlite3"
    archive.write_text("instagram:3301000000000000001:1\n")  # slide 1 already archived
    stage = tmp_path / "stage"
    cfg = media.write_config(tmp_path / "c.json")
    events: list[dict[str, Any]] = []
    opts = media.MediaOptions(
        url=POST, directory=stage, config_path=cfg, archive_path=archive, gallery_dl=str(script)
    )
    proc = media.run(opts, events.append, files_total=3)
    proc.wait(10)
    assert proc.returncode == 0
    assert len(proc.finished) == 2 and len(proc.skipped) == 1
    assert proc.files_done == 3
    progress = [e for e in events if e["type"] == "progress"]
    assert [e["files_done"] for e in progress] == [1, 2, 3]
    assert {e["files_total"] for e in progress} == {3}
    assert [e["percent"] for e in progress] == [33.3, 66.7, 100.0]
    assert all(e["stage"] == "downloading" for e in progress)
    assert events[-1]["type"] == "exit" and events[-1]["returncode"] == 0
    # The metadata JSON is left in the staging folder.
    assert sorted(p.suffix for p in stage.iterdir()).count(".json") == 2


def test_run_without_a_total_has_no_percent(tmp_path: Path) -> None:
    log = tmp_path / "gdl.log"
    script = write_fake_gallery(tmp_path, log=log)
    events: list[dict[str, Any]] = []
    opts = media.MediaOptions(
        url=POST,
        directory=tmp_path / "stage",
        config_path=media.write_config(tmp_path / "c.json"),
        archive_path=tmp_path / "a.sqlite3",
        gallery_dl=str(script),
    )
    media.run(opts, events.append).wait(10)
    progress = [e for e in events if e["type"] == "progress"]
    assert progress[0]["percent"] is None and progress[0]["files_total"] is None


def test_run_ignores_lines_outside_the_staging_folder(tmp_path: Path) -> None:
    script = tmp_path / "noisy"
    script.write_text(
        "#!/bin/sh\n"
        "echo '[instagram][warning] something'\n"
        "echo '/elsewhere/file.jpg'\n"
        f"echo '{tmp_path}/stage/a.jpg'\n"
        f"echo '{tmp_path}/stage/a.jpg'\n"  # a repeat is not counted twice
        f"echo '# {tmp_path}/stage/b.jpg'\n"
    )
    script.chmod(0o755)
    proc = media.MediaProcess([str(script)], directory=tmp_path / "stage", files_total=2)
    proc.wait(10)
    assert proc.files_done == 2
    assert len(proc.finished) == 1 and len(proc.skipped) == 1
    assert "[instagram][warning] something" in proc.raw_log


def test_run_a_missing_binary_raises_oserror(tmp_path: Path) -> None:
    opts = media.MediaOptions(
        url=POST,
        directory=tmp_path / "stage",
        config_path=tmp_path / "c.json",
        archive_path=tmp_path / "a",
        gallery_dl=str(tmp_path / "nope"),
    )
    with pytest.raises(OSError):
        media.run(opts)


# -- finalize: the move into the output folder ---------------------------
def stage_files(stage: Path, names: list[str]) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    for name in names:
        (stage / name).write_text(f"staged {name}")


def test_finalize_moves_media_and_keeps_metadata(tmp_path: Path) -> None:
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage_files(stage, ["a 1.jpg", "a 1.jpg.json", "a 2.mp4", "a 3.jpg.part"])
    result = media.finalize(stage, out, "cafe_northfield")
    assert [p.name for p in result.moved] == ["a 1.jpg", "a 2.mp4"]
    assert (out / "cafe_northfield" / "a 1.jpg").read_text() == "staged a 1.jpg"
    assert sorted(p.name for p in stage.iterdir()) == ["a 1.jpg.json", "a 3.jpg.part"]
    assert sorted(p.name for p in (out / "cafe_northfield").iterdir()) == ["a 1.jpg", "a 2.mp4"]
    assert result.first == out / "cafe_northfield" / "a 1.jpg"


def test_finalize_never_overwrites_or_renames(tmp_path: Path) -> None:
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage_files(stage, ["a 1.jpg", "a 2.jpg"])
    folder = out / "cafe_northfield"
    folder.mkdir(parents=True)
    (folder / "a 1.jpg").write_text("the original")
    result = media.finalize(stage, out, "cafe_northfield")
    assert (folder / "a 1.jpg").read_text() == "the original"
    assert sorted(p.name for p in folder.iterdir()) == ["a 1.jpg", "a 2.jpg"]  # no "(1)"
    assert [p.name for p in result.moved] == ["a 2.jpg"]
    assert [p.name for p in result.existing] == ["a 1.jpg"]
    assert list(stage.iterdir()) == []  # the duplicate staged copy is dropped


def test_finalize_only_existing_files(tmp_path: Path) -> None:
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage_files(stage, ["a 1.jpg"])
    (out / "u").mkdir(parents=True)
    (out / "u" / "a 1.jpg").write_text("x")
    result = media.finalize(stage, out, "u")
    assert not result.moved and result.first == out / "u" / "a 1.jpg"


def test_finalize_falls_back_to_a_copy_across_filesystems(tmp_path: Path, monkeypatch) -> None:
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage_files(stage, ["a 1.jpg"])

    def cross_device(src, dst, **kw):
        raise OSError(errno.EXDEV, "cross-device")

    monkeypatch.setattr(os, "link", cross_device)
    result = media.finalize(stage, out, "u")
    assert (out / "u" / "a 1.jpg").read_text() == "staged a 1.jpg"
    assert [p.name for p in result.moved] == ["a 1.jpg"]
    assert not (stage / "a 1.jpg").exists()


def test_finalize_copy_fallback_does_not_overwrite(tmp_path: Path, monkeypatch) -> None:
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage_files(stage, ["a 1.jpg"])
    (out / "u").mkdir(parents=True)
    (out / "u" / "a 1.jpg").write_text("the original")
    monkeypatch.setattr(os, "link", lambda *a, **k: (_ for _ in ()).throw(OSError(errno.EXDEV, "x")))
    result = media.finalize(stage, out, "u")
    assert (out / "u" / "a 1.jpg").read_text() == "the original"
    assert not result.moved and result.existing


@pytest.mark.parametrize(
    ("owner", "folder"),
    [
        ("cafe_northfield", "cafe_northfield"),
        ("../evil", "_evil"),
        ("a/b\\c", "a_b_c"),
        ("..", None),
        (".hidden", "hidden"),
        ("  spaced name  ", "spaced name"),
        ("line\nbreak", "line_break"),
        ("", None),
        (None, None),
    ],
)
def test_safe_folder_name(owner, folder) -> None:
    assert media.safe_folder_name(owner) == folder


def test_finalize_cannot_escape_the_output_folder(tmp_path: Path) -> None:
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage_files(stage, ["a 1.jpg"])
    result = media.finalize(stage, out, "../../escape")
    (moved,) = result.moved
    assert out in moved.parents
    assert not (tmp_path / "escape").exists()


def test_finalize_without_an_owner_uses_the_output_root(tmp_path: Path) -> None:
    stage, out = tmp_path / "stage", tmp_path / "out"
    stage_files(stage, ["a 1.jpg"])
    result = media.finalize(stage, out, None)
    assert result.first == out / "a 1.jpg"


def test_finalize_missing_or_empty_stage(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert media.finalize(tmp_path / "nope", out, "u").first is None
    stage_files(tmp_path / "stage", ["only.json"])
    assert media.finalize(tmp_path / "stage", out, "u").first is None
    assert not out.exists()  # nothing to move: no empty owner folder


def test_item_directory_is_stable_per_link(tmp_path: Path) -> None:
    a = media.item_directory(tmp_path, "https://www.instagram.com/stories/a/")
    assert a == media.item_directory(tmp_path, "https://www.instagram.com/stories/a/")
    assert a != media.item_directory(tmp_path, "https://www.instagram.com/stories/b/")
    assert a.parent == tmp_path / "media"


# -- packaging -----------------------------------------------------------
def test_pkgbuild_depends_on_gallery_dl() -> None:
    text = (REPO / "packaging" / "arch" / "PKGBUILD").read_text()
    depends = next(l for l in text.splitlines() if l.startswith("depends="))
    assert "'gallery-dl'" in depends


def test_install_script_only_hints_about_gallery_dl() -> None:
    text = (REPO / "install-desktop.sh").read_text()
    assert "command -v gallery-dl" in text
    missing_lines = [l for l in text.splitlines() if 'missing="$missing' in l]
    assert not any("gallery-dl" in l for l in missing_lines)  # optional: never blocks
    assert not any(l.strip().startswith("sudo pacman") for l in text.splitlines())


def test_nothing_imports_gallery_dl() -> None:
    root = REPO / "desktop" / "elisium_downloader"
    for path in root.rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            assert not stripped.startswith(("import gallery_dl", "from gallery_dl")), path
