from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from elisium_downloader.engine.runner import (
    OUTPUT_TEMPLATE,
    DownloadOptions,
    ProbeError,
    build_command,
    parse_progress_line,
    probe,
    run,
    stage_for_postprocessor,
)

VIDEO_ID = "dQw4w9WgXcQ"


# -- fake yt-dlp ---------------------------------------------------------
def write_fake(
    tmp_path: Path,
    *,
    log: Path,
    probe_info: dict | None = None,
    body: str = "",
    code: int = 0,
    name: str = "fake-yt-dlp",
) -> Path:
    """Write a shell-free fake yt-dlp that logs its argv, then exits *code*."""
    lines = [
        "#!/usr/bin/env python3",
        "import json, pathlib, sys, time",
        "argv = sys.argv[1:]",
        f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:",
        "    fh.write(json.dumps(argv) + '\\n')",
        "if '-J' in argv:",
    ]
    if probe_info is None:
        lines += [
            "    print('ERROR: Video unavailable', file=sys.stderr)",
            "    sys.exit(1)",
        ]
    else:
        lines += [f"    print(json.dumps({probe_info!r}))", "    sys.exit(0)"]
    if body:
        lines += body.splitlines()
    lines.append(f"sys.exit({code})")
    script = tmp_path / name
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def progress(obj: dict) -> str:
    return "print('[download] ' + json.dumps(" + repr(obj) + "), flush=True)"


def make_options(tmp_path: Path, ytdlp: Path, **kwargs) -> DownloadOptions:
    out = tmp_path / "out"
    tmp = tmp_path / "tmp"
    out.mkdir(exist_ok=True)
    tmp.mkdir(exist_ok=True)
    return DownloadOptions(
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        output_dir=out,
        temp_dir=tmp,
        archive_path=tmp_path / "archive.txt",
        ytdlp=str(ytdlp),
        **kwargs,
    )


def read_log(log: Path) -> list[list[str]]:
    if not log.exists():
        return []
    return [
        json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
    ]


# -- build_command -------------------------------------------------------
def test_build_command_has_the_dedupe_and_path_flags(tmp_path: Path) -> None:
    opts = make_options(tmp_path, tmp_path / "yt-dlp")
    argv = build_command(opts)

    assert argv[0] == str(tmp_path / "yt-dlp")
    assert ["-P", f"home:{opts.output_dir}"] == argv[argv.index("-P") :][:2]
    assert f"temp:{opts.temp_dir}" in argv
    assert "--download-archive" in argv
    assert argv[argv.index("--download-archive") + 1] == str(opts.archive_path)
    assert "--no-overwrites" in argv
    assert argv[argv.index("--continue")] == "--continue"
    assert argv[argv.index("--newline")] == "--newline"


def test_output_template_keeps_the_id_and_limits_the_title() -> None:
    assert OUTPUT_TEMPLATE == "%(title).150B [%(id)s].%(ext)s"


def test_build_command_has_both_progress_templates(tmp_path: Path) -> None:
    argv = build_command(make_options(tmp_path, tmp_path / "yt-dlp"))
    templates = [
        argv[index + 1]
        for index, arg in enumerate(argv)
        if arg == "--progress-template"
    ]
    assert templates == ["download:%(progress)j", "postprocess:%(progress)j"]


def test_build_command_retries_and_format(tmp_path: Path) -> None:
    opts = make_options(tmp_path, tmp_path / "yt-dlp", format_selector="720p")
    argv = build_command(opts)
    assert argv[argv.index("--retries") + 1] == "3"
    assert argv[argv.index("--fragment-retries") + 1] == "3"
    assert argv[argv.index("-f") + 1] == "720p"
    assert "bestvideo*+bestaudio/best" not in argv


def test_build_command_home_before_temp(tmp_path: Path) -> None:
    argv = build_command(make_options(tmp_path, tmp_path / "yt-dlp"))
    home_index = argv.index(f"home:{(tmp_path / 'out')}")
    temp_index = argv.index(f"temp:{(tmp_path / 'tmp')}")
    assert home_index < temp_index


def test_limit_rate_only_when_set(tmp_path: Path) -> None:
    plain = build_command(make_options(tmp_path, tmp_path / "yt-dlp"))
    assert "--limit-rate" not in plain

    limited = build_command(
        make_options(tmp_path, tmp_path / "yt-dlp", limit_rate="2M")
    )
    assert limited[limited.index("--limit-rate") + 1] == "2M"


def test_url_is_last_and_extra_args_before_it(tmp_path: Path) -> None:
    opts = make_options(
        tmp_path, tmp_path / "yt-dlp", extra_args=["--no-playlist"]
    )
    argv = build_command(opts)
    assert argv[-1] == opts.url
    assert argv[-2] == "--no-playlist"


def test_downloads_always_pass_no_playlist(tmp_path: Path) -> None:
    opts = make_options(tmp_path, tmp_path / "yt-dlp")
    argv = build_command(opts)
    assert argv.count("--no-playlist") == 1
    assert argv.index("--no-playlist") < len(argv) - 1  # before the URL


def test_info_json_replaces_the_url_and_changes_nothing_else(tmp_path: Path) -> None:
    plain = build_command(
        make_options(tmp_path, tmp_path / "yt-dlp", path_file=tmp_path / "p", limit_rate="1M")
    )
    info = tmp_path / "tmp" / "7.info.json"
    reused_opts = make_options(
        tmp_path, tmp_path / "yt-dlp", path_file=tmp_path / "p", limit_rate="1M", info_json=info
    )
    reused = build_command(reused_opts)
    assert reused[reused.index("--load-info-json") + 1] == str(info)
    assert reused_opts.url not in reused
    assert plain[-1] == reused_opts.url
    stripped = list(reused)
    at = stripped.index("--load-info-json")
    del stripped[at : at + 2]
    assert stripped == plain[:-1]


def test_no_info_json_means_no_load_flag(tmp_path: Path) -> None:
    argv = build_command(make_options(tmp_path, tmp_path / "yt-dlp"))
    assert "--load-info-json" not in argv
    assert argv[-1] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def test_options_reject_an_empty_url(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        DownloadOptions(
            url="  ",
            output_dir=tmp_path,
            temp_dir=tmp_path,
            archive_path=tmp_path / "a.txt",
        )


# -- progress parsing ----------------------------------------------------
def test_parse_download_progress_line() -> None:
    event = parse_progress_line(
        '[download] {"status": "downloading", "downloaded_bytes": 512,'
        ' "total_bytes": 1024, "speed": 256.5, "eta": 2}'
    )
    assert event is not None
    assert event["type"] == "progress"
    assert event["stage"] == "downloading"
    assert event["downloaded_bytes"] == 512
    assert event["total_bytes"] == 1024
    assert event["speed"] == 256.5
    assert event["eta"] == 2
    assert event["percent"] == 50.0


def test_parse_bare_json_line_without_prefix() -> None:
    event = parse_progress_line('{"status": "downloading", "downloaded_bytes": 1}')
    assert event is not None
    assert event["stage"] == "downloading"


def test_parse_ignores_plain_text_and_ansi() -> None:
    assert parse_progress_line("[download] Destination: a.mp4") is None
    assert parse_progress_line("") is None
    assert parse_progress_line("\x1b[0;94m[download]\x1b[0m nothing to see") is None
    assert parse_progress_line('{"status": "weird"}') is None


def test_parse_uses_total_bytes_estimate() -> None:
    event = parse_progress_line(
        '{"status": "downloading", "downloaded_bytes": 50,'
        ' "total_bytes_estimate": 200}'
    )
    assert event is not None
    assert event["percent"] == 25.0


def test_parse_finished_download_is_100_percent() -> None:
    event = parse_progress_line('{"status": "finished", "downloaded_bytes": 9}')
    assert event is not None
    assert event["percent"] == 100.0


def test_parse_merger_postprocess_maps_to_merging() -> None:
    event = parse_progress_line(
        '[postprocess] {"status": "started", "postprocessor": "Merger"}'
    )
    assert event is not None
    assert event["stage"] == "merging"
    assert event["postprocessor"] == "Merger"


def test_parse_audio_extract_maps_to_converting() -> None:
    event = parse_progress_line(
        '{"status": "processing", "postprocessor": "ExtractAudio"}'
    )
    assert event is not None
    assert event["stage"] == "converting"


def test_stage_for_postprocessor_names() -> None:
    assert stage_for_postprocessor("Merger") == "merging"
    assert stage_for_postprocessor("FFmpegMerger") == "merging"
    assert stage_for_postprocessor("VideoConvertor") == "converting"
    assert stage_for_postprocessor("FixupM4a") == "converting"
    assert stage_for_postprocessor("") == "converting"


# -- probe ---------------------------------------------------------------
def test_probe_runs_the_single_video_command(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    fake = write_fake(
        tmp_path,
        log=log,
        probe_info={"id": VIDEO_ID, "title": "Never Gonna Give You Up"},
    )
    info = probe("https://youtu.be/dQw4w9WgXcQ", str(fake))
    assert info["title"] == "Never Gonna Give You Up"

    argv = read_log(log)[0]
    assert "-J" in argv
    assert "--no-download" in argv
    assert "--no-playlist" in argv
    assert "--flat-playlist" not in argv
    assert argv[-1] == "https://youtu.be/dQw4w9WgXcQ"


def test_probe_playlist_uses_flat_playlist(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    fake = write_fake(tmp_path, log=log, probe_info={"id": "PL1", "title": "List"})
    probe("https://www.youtube.com/playlist?list=PL1", str(fake))
    argv = read_log(log)[0]
    assert "--flat-playlist" in argv
    assert "--no-playlist" not in argv


def test_probe_raises_probe_error_with_mapped_info(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    fake = write_fake(tmp_path, log=log, probe_info=None)
    with pytest.raises(ProbeError) as caught:
        probe("https://youtu.be/x", str(fake))
    assert caught.value.info.code == "video_unavailable"
    assert "Video unavailable" in caught.value.raw


def test_probe_maps_a_403(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    fake = write_fake(tmp_path, log=log, probe_info=None)
    fake.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "print('ERROR: unable to download video data: HTTP Error 403: Forbidden',"
        " file=sys.stderr)\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    with pytest.raises(ProbeError) as caught:
        probe("https://youtu.be/x", str(fake))
    assert caught.value.info.code == "http_403"


def test_probe_reports_a_missing_ytdlp() -> None:
    with pytest.raises(ProbeError) as caught:
        probe("https://youtu.be/x", "/nonexistent/yt-dlp-binary")
    assert caught.value.info.code == "ytdlp_missing"


def test_probe_rejects_an_empty_url() -> None:
    with pytest.raises(ValueError):
        probe("   ")


# -- run -----------------------------------------------------------------
def test_run_streams_progress_then_exit(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    body = "\n".join(
        [
            progress(
                {
                    "status": "downloading",
                    "downloaded_bytes": 10,
                    "total_bytes": 20,
                    "speed": 5.0,
                    "eta": 2,
                }
            ),
            progress(
                {
                    "status": "downloading",
                    "downloaded_bytes": 20,
                    "total_bytes": 20,
                    "speed": 5.0,
                    "eta": 0,
                }
            ),
        ]
    )
    fake = write_fake(tmp_path, log=log, probe_info={"id": VIDEO_ID}, body=body)
    events: list[dict] = []
    handle = run(make_options(tmp_path, fake), events.append)
    assert handle.wait(10) == 0

    kinds = [event["type"] for event in events]
    assert kinds.count("progress") == 2
    assert kinds[-1] == "exit"
    assert events[0]["downloaded_bytes"] == 10
    assert events[1]["percent"] == 100.0
    assert events[-1]["returncode"] == 0
    assert handle.raw_log.count("[download]") == 2


def test_run_keeps_the_raw_log_for_a_failure(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    body = "print('ERROR: Video unavailable', file=sys.stderr)\nprint('more detail')"
    fake = write_fake(tmp_path, log=log, probe_info={"id": VIDEO_ID}, body=body, code=10)
    handle = run(make_options(tmp_path, fake))
    assert handle.wait(10) == 10
    assert "ERROR: Video unavailable" in handle.raw_log
    assert "more detail" in handle.raw_log


def test_run_passes_the_built_command(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    fake = write_fake(tmp_path, log=log, probe_info={"id": VIDEO_ID})
    opts = make_options(tmp_path, fake)
    run(opts, None).wait(10)

    argv = read_log(log)[0]
    assert f"home:{opts.output_dir}" in argv
    assert f"temp:{opts.temp_dir}" in argv
    assert "--download-archive" in argv
    assert "--no-overwrites" in argv
    assert "--continue" in argv
    assert argv[-1] == opts.url


def test_run_slow_progress_arrives_in_order(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    body = "\n".join(
        [
            f"time.sleep(0.05)\nprint('[download] ' + json.dumps({{'status':"
            f" 'downloading', 'downloaded_bytes': {size}, 'total_bytes': 300}}),"
            " flush=True)"
            for size in (100, 200, 300)
        ]
    )
    fake = write_fake(tmp_path, log=log, probe_info={"id": VIDEO_ID}, body=body)
    sizes: list[int] = []
    handle = run(
        make_options(tmp_path, fake),
        lambda event: sizes.append(event["downloaded_bytes"])
        if event.get("stage") == "downloading"
        else None,
    )
    assert handle.wait(10) == 0
    assert sizes == [100, 200, 300]


def test_terminate_stops_the_process_and_keeps_the_part_file(
    tmp_path: Path,
) -> None:
    log = tmp_path / "argv.log"
    opts = make_options(tmp_path, tmp_path / "yt-dlp")
    part = Path(opts.temp_dir) / "Video [dQw4w9WgXcQ].f137.mp4.part"
    body = "\n".join(
        [
            f"pathlib.Path({str(part)!r}).write_text('partial')",
            "time.sleep(30)",
        ]
    )
    fake = write_fake(tmp_path, log=log, probe_info={"id": VIDEO_ID}, body=body)
    opts = make_options(tmp_path, fake)
    handle = run(opts, None)

    deadline = time.monotonic() + 10
    while not part.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert part.exists()

    handle.terminate()
    assert handle.wait(10) is not None
    assert handle.terminated
    assert handle.returncode != 0
    assert part.exists()


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("ELISIUM_LIVE_TESTS"),
    reason="live yt-dlp download; set ELISIUM_LIVE_TESTS=1",
)
def test_live_short_video_download(tmp_path: Path) -> None:
    """Optional: one short public video, real network, real yt-dlp."""
    url = "https://www.youtube.com/watch?v=BaW_jenozKc"
    out = tmp_path / "out"
    tmp = tmp_path / "tmp"
    out.mkdir()
    tmp.mkdir()
    info = probe(url)
    assert info["id"] == "BaW_jenozKc"

    handle = run(
        DownloadOptions(
            url=url,
            output_dir=out,
            temp_dir=tmp,
            archive_path=tmp_path / "archive.txt",
            format_selector="worst",
        ),
        None,
    )
    assert handle.wait(600) == 0
    assert list(out.iterdir())


# -- brief 1D ------------------------------------------------------------
def test_path_file_adds_print_to_file_after_move(tmp_path: Path) -> None:
    opts = make_options(tmp_path, tmp_path / "yt-dlp")
    assert "--print-to-file" not in build_command(opts)
    with_file = DownloadOptions(
        url=opts.url,
        output_dir=opts.output_dir,
        temp_dir=opts.temp_dir,
        archive_path=opts.archive_path,
        path_file=tmp_path / "x.path",
    )
    argv = build_command(with_file)
    at = argv.index("--print-to-file")
    assert argv[at + 1 : at + 3] == ["after_move:filepath", str(tmp_path / "x.path")]
    assert argv[-1] == opts.url


def test_housekeeping_postprocessors_are_not_converting() -> None:
    for name in ("MoveFiles", "Metadata", "FFmpegMetadata", "SponsorBlock"):
        assert stage_for_postprocessor(name) == "downloading"


def test_real_conversion_postprocessors_stay_converting() -> None:
    for name in (
        "ExtractAudio",
        "VideoConvertor",
        "VideoRemuxer",
        "EmbedSubtitle",
        "EmbedThumbnail",
        "ModifyChapters",
        "FixupM4a",
    ):
        assert stage_for_postprocessor(name) == "converting"


# -- brief 8A: cookies and Instagram story trays -------------------------
def test_no_cookie_flags_by_default(tmp_path: Path) -> None:
    argv = build_command(make_options(tmp_path, tmp_path / "yt-dlp"))
    assert "--cookies-from-browser" not in argv
    assert "--cookies" not in argv


def test_cookie_flags_for_a_browser(tmp_path: Path) -> None:
    opts = make_options(
        tmp_path, tmp_path / "yt-dlp", cookies_browser="firefox",
        cookies_file="/tmp/cookies.txt",
    )
    argv = build_command(opts)
    at = argv.index("--cookies-from-browser")
    assert argv[at + 1] == "firefox"
    assert "--cookies" not in argv  # the browser wins when both are set
    assert argv[-1] == opts.url


def test_cookie_flags_for_a_file(tmp_path: Path) -> None:
    opts = make_options(
        tmp_path, tmp_path / "yt-dlp", cookies_file="~/cookies.txt"
    )
    argv = build_command(opts)
    at = argv.index("--cookies")
    assert argv[at + 1] == str(Path("~/cookies.txt").expanduser())
    assert "--cookies-from-browser" not in argv


def test_instagram_story_trays_are_playlists() -> None:
    from elisium_downloader.engine.runner import _looks_like_playlist

    for url in (
        "https://www.instagram.com/stories/tiktok/",
        "https://instagram.com/stories/highlights/17912345678901234/",
    ):
        assert _looks_like_playlist(url) is True, url


def test_single_story_and_tiktok_video_are_not_playlists() -> None:
    from elisium_downloader.engine.runner import _looks_like_playlist

    for url in (
        "https://www.instagram.com/stories/tiktok/3211234567890123456/",
        "https://www.instagram.com/reel/CabcdEFghij/",
        "https://www.tiktok.com/@tiktok/video/7106594312292453675",
    ):
        assert _looks_like_playlist(url) is False, url


def test_probe_passes_the_cookie_choice(tmp_path: Path) -> None:
    log = tmp_path / "argv.log"
    fake = write_fake(tmp_path, log=log, probe_info={"id": "1", "title": "t"})
    probe(
        "https://www.instagram.com/stories/tiktok/",
        str(fake),
        cookies_browser="chrome",
    )
    filter_urls = probe(
        "https://www.instagram.com/stories/tiktok/",
        str(fake),
        cookies_file="~/cookies.txt",
    )
    assert filter_urls["title"] == "t"

    first, second = read_log(log)
    assert "--flat-playlist" in first and "--no-playlist" not in first
    assert first[first.index("--cookies-from-browser") + 1] == "chrome"
    assert second[second.index("--cookies") + 1] == str(
        Path("~/cookies.txt").expanduser()
    )
    assert "--cookies-from-browser" not in second


@pytest.mark.live
@pytest.mark.skipif(
    not os.environ.get("ELISIUM_LIVE_TESTS"),
    reason="live yt-dlp probe; set ELISIUM_LIVE_TESTS=1",
)
def test_live_tiktok_public_video_probe() -> None:
    """Public TikTok video, real network and real yt-dlp, no login."""
    url = "https://www.tiktok.com/@tiktok/video/7106594312292453675"
    info = probe(url, timeout=120)
    assert "7106594312292453675" in str(info.get("id", ""))
