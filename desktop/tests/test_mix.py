"""Brief 10B-2: song snippet + photo/song video (offline; fake ffmpeg / ffprobe on disk)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from elisium_downloader.engine import media, mix
from elisium_downloader.engine.archive import Archive
from elisium_downloader.engine.history import History
from elisium_downloader.engine.mix import Slide, StreamInfo
from elisium_downloader.engine.queue import DownloadQueue
from test_media import IG, read_log, write_fake_gallery
from test_queue import write_fake

POST = f"{IG}/p/CMus789rst/"
NO_VIDEO = "ERROR: [Instagram] CMus789rst: There is no video in this post"


# -- fake ffmpeg / ffprobe ----------------------------------------------------
def write_fake_ffmpeg(
    folder: Path,
    *,
    log: Path,
    fail_copy: bool = False,
    fail_all: bool = False,
    fail_mix: bool = False,
    name: str = "fake-ffmpeg",
) -> Path:
    """Logs argv, writes the output file (the last argument) like ffmpeg would."""
    cfg = {"fail_copy": fail_copy, "fail_all": fail_all, "fail_mix": fail_mix}
    lines = [
        "#!/usr/bin/env python3",
        "import json, sys",
        "argv = sys.argv[1:]",
        f"with open({str(log)!r}, 'a', encoding='utf-8') as fh:",
        "    fh.write(json.dumps(argv) + '\\n')",
        f"cfg = {cfg!r}",
        "mixing = '-filter_complex' in argv",
        "copying = '-c' in argv and argv[argv.index('-c') + 1] == 'copy'",
        "if cfg['fail_all'] or (mixing and cfg['fail_mix']) or (copying and cfg['fail_copy']):",
        "    sys.stderr.write('boom'); sys.exit(1)",
        "open(argv[-1], 'w').write('mix' if mixing else 'snippet')",
    ]
    script = folder / name
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


def write_fake_ffprobe(
    folder: Path, *, files: dict[str, dict[str, Any]] | None = None, name: str = "fake-ffprobe"
) -> Path:
    """Answers ffprobe's JSON by extension; *files* overrides per file name."""
    lines = [
        "#!/usr/bin/env python3",
        "import json, os, sys",
        "path = sys.argv[-1]",
        "base = os.path.basename(path)",
        "ext = base.rsplit('.', 1)[-1].lower()",
        f"over = {(files or {})!r}",
        "if ext in ('m4a', 'mp3', 'aac'):",
        "    spec = {'audio': True, 'video': False, 'duration': 6.0}",
        "elif ext in ('mp4', 'mov'):",
        "    spec = {'audio': True, 'video': True, 'duration': 4.0, 'width': 1080, 'height': 1920}",
        "else:",
        "    spec = {'audio': False, 'video': True, 'width': 1080, 'height': 1920}",
        "spec.update(over.get(base, {}))",
        "if spec.get('missing'):",
        "    sys.exit(1)",
        "streams = []",
        "if spec['video']:",
        "    streams.append({'codec_type': 'video', 'width': spec['width'], 'height': spec['height']})",
        "if spec['audio']:",
        "    streams.append({'codec_type': 'audio'})",
        "out = {'streams': streams, 'format': {}}",
        "if 'duration' in spec:",
        "    out['format']['duration'] = str(spec['duration'])",
        "print(json.dumps(out))",
    ]
    script = folder / name
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(0o755)
    return script


# -- snippet_from_metadata ----------------------------------------------------
@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        # Instagram's own music_consumption_info names, in ms
        (
            {"music_consumption_info": {"audio_asset_start_time_in_ms": 12500, "overlap_duration_in_ms": 15000}},
            (12.5, 15.0),
        ),
        # nested deeper, mixed with other fields
        (
            {"post": {"clips": [{"music": {"audio_asset_start_time_in_ms": 0, "overlap_duration_in_ms": 8000}}]}},
            (0.0, 8.0),
        ),
        # generic ms fields
        ({"audio": {"start_ms": 30000, "duration_ms": 20000}}, (30.0, 20.0)),
        # seconds
        ({"audio": {"start": 4, "duration": 10.5}}, (4.0, 10.5)),
        ({"music": {"start_time": 1.5, "length": 9}}, (1.5, 9.0)),
        # a start and an end
        ({"audio": {"start_time_ms": 5000, "end_time_ms": 20000}}, (5.0, 15.0)),
        ({"audio": {"start": 2, "end": 12}}, (2.0, 10.0)),
        # audio_timestamps-style lists
        ({"audio_timestamps": [3, 13]}, (3.0, 10.0)),
        ({"audio_timestamps_ms": [3000, 13000]}, (3.0, 10.0)),
        ({"audio_timestamps": [{"start_ms": 1000, "duration_ms": 5000}]}, (1.0, 5.0)),
        ({"audio_timestamps": {"start": 7, "end": 17}}, (7.0, 10.0)),
        # numeric strings
        ({"audio": {"start_ms": "2000", "duration_ms": "3000"}}, (2.0, 3.0)),
    ],
)
def test_snippet_from_metadata_shapes(meta: dict, expected: tuple[float, float]) -> None:
    assert mix.snippet_from_metadata(meta) == expected


@pytest.mark.parametrize(
    "meta",
    [
        None,
        {},
        [],
        "text",
        42,
        {"description": "no song data here", "count": 2},
        {"duration": 12.0},  # a bare duration is a video length, not the snippet
        {"audio": {"start_ms": 5000}},  # a start with no length
        {"audio": {"duration_ms": 5000}},  # a length with no start
        {"audio": {"start_ms": 5000, "duration_ms": 0}},
        {"audio": {"start_ms": 5000, "duration_ms": -3}},
        {"audio": {"start_ms": -1, "duration_ms": 3000}},
        {"audio": {"start_ms": "soon", "duration_ms": "long"}},
        {"audio": {"start_ms": True, "duration_ms": True}},
        {"audio": {"start": 9, "end": 4}},
        {"audio_timestamps": [3]},
        {"audio_timestamps": [3, "x"]},
        {"audio_timestamps": [10, 4]},
        {"audio": {"start_ms": float("nan"), "duration_ms": 5000}},
    ],
)
def test_snippet_from_metadata_missing_or_unusable(meta: Any) -> None:
    assert mix.snippet_from_metadata(meta) is None


def test_snippet_from_metadata_survives_deep_and_cyclic_looking_input() -> None:
    deep: dict[str, Any] = {}
    node = deep
    for _ in range(50):
        node["x"] = {}
        node = node["x"]
    node["audio"] = {"start": 1, "duration": 2}
    assert mix.snippet_from_metadata(deep) is None  # deeper than the walker goes


# -- names ----------------------------------------------------------------------
def test_song_base_drops_the_media_id_and_number() -> None:
    assert (
        mix.song_base("dj_north 2026-11-03 CMus789rst [3302000000000000009] 2.m4a")
        == "dj_north 2026-11-03 CMus789rst"
    )
    assert mix.song_base("dancer 7300000000000000001 [7300000000000000001_5] 5.m4a") == (
        "dancer 7300000000000000001"
    )
    assert mix.song_base("plain.m4a") == "plain"
    assert mix.song_base("a b song.m4a") == "a b"
    assert mix.song_base("[only] 1.m4a") == "[only] 1"


def test_mix_marker_comes_from_the_mix_key() -> None:
    assert mix.mix_marker("instagram", "CMus789rst") == "CMus789rst_mix"
    assert media.mix_key("Instagram", "CMus789rst") == "instagram CMus789rst_mix"
    assert mix.mix_marker("tiktok", "73") == "73_mix"


def test_find_existing_mix(tmp_path: Path) -> None:
    assert mix.find_existing_mix(None, "X_mix") is None
    assert mix.find_existing_mix(tmp_path / "missing", "X_mix") is None
    (tmp_path / "a [OTHER_mix].mp4").write_text("x")
    assert mix.find_existing_mix(tmp_path, "X_mix") is None
    (tmp_path / "a [X_mix].mp4").write_text("x")
    assert mix.find_existing_mix(tmp_path, "X_mix") == tmp_path / "a [X_mix].mp4"


# -- photo seconds / canvas -----------------------------------------------------
@pytest.mark.parametrize(
    ("song", "count", "expected"),
    [
        (6.0, 1, [6.0]),
        (9.0, 3, [3.0, 3.0, 3.0]),
        (5.0, 2, [2.5, 2.5]),
        (3.0, 3, [2.0, 2.0, 2.0]),  # the 2 s minimum wins
        (1.0, 1, [2.0]),
        (10.0, 0, []),
    ],
)
def test_photo_seconds(song: float, count: int, expected: list[float]) -> None:
    assert mix.photo_seconds(song, count) == expected


def test_photo_seconds_last_photo_holds_until_the_song_ends() -> None:
    seconds = mix.photo_seconds(7.0, 3)
    assert seconds[0] == seconds[1] == pytest.approx(7 / 3, abs=1e-3)
    assert sum(seconds) >= 7.0 - 0.002  # rounding only
    assert all(s >= mix.MIN_PHOTO_SECONDS for s in seconds)


def test_choose_canvas_portrait_vs_landscape() -> None:
    tall, wide, square = StreamInfo(1080, 1350), StreamInfo(1600, 900), StreamInfo(1000, 1000)
    assert mix.choose_canvas([tall]) == (1080, 1920)
    assert mix.choose_canvas([wide]) == (1920, 1080)
    assert mix.choose_canvas([wide, wide, tall]) == (1920, 1080)
    assert mix.choose_canvas([tall, tall, wide]) == (1080, 1920)
    assert mix.choose_canvas([tall, wide]) == (1080, 1920)  # a tie is portrait
    assert mix.choose_canvas([square, wide]) == (1920, 1080)
    assert mix.choose_canvas([square]) == (1080, 1920)
    assert mix.choose_canvas([None, None]) == (1080, 1920)
    assert mix.choose_canvas([]) == (1080, 1920)


def test_parse_probe_json_reads_size_rotation_and_duration() -> None:
    text = json.dumps(
        {
            "streams": [
                {"codec_type": "video", "width": 1920, "height": 1080, "side_data_list": [{"rotation": -90}]},
                {"codec_type": "audio"},
            ],
            "format": {"duration": "4.5"},
        }
    )
    info = mix.parse_probe_json(text)
    assert info == StreamInfo(1080, 1920, 4.5, True, True)
    assert info is not None and info.portrait is True
    assert mix.parse_probe_json("not json") is None
    assert mix.parse_probe_json("[]") is None
    assert mix.parse_probe_json('{"streams": []}') == StreamInfo()


# -- argv builders (pure) ---------------------------------------------------------
def test_cut_command_copies_then_re_encodes() -> None:
    copy = mix.build_cut_command("ffmpeg", "in.m4a", "out.m4a", 12.5, 15)
    assert copy[0] == "ffmpeg"
    assert copy[copy.index("-ss") + 1] == "12.500"
    assert copy[copy.index("-t") + 1] == "15.000"
    assert copy.index("-ss") < copy.index("-t") < copy.index("-i")
    assert copy[copy.index("-i") + 1] == "in.m4a"
    assert copy[copy.index("-c") + 1] == "copy"
    assert copy[copy.index("-threads") + 1] == "2" and copy[-1] == "out.m4a"
    again = mix.build_cut_command("ffmpeg", "in.m4a", "out.m4a", 12.5, 15, reencode=True)
    assert "copy" not in again
    assert again[again.index("-c:a") + 1] == "aac" and again[again.index("-b:a") + 1] == "192k"
    assert "-vn" in again


def _inputs(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, a in enumerate(argv) if a == "-i"]


def test_mix_command_one_photo() -> None:
    argv = mix.build_mix_command(
        "ffmpeg", [Slide(Path("a.jpg"), "image", 6.0)], "song.m4a", "out.mp4", (1080, 1920)
    )
    assert _inputs(argv) == ["a.jpg", "song.m4a"]
    graph = argv[argv.index("-filter_complex") + 1]
    assert "scale=1080:1920:force_original_aspect_ratio=decrease" in graph
    assert "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black" in graph
    assert "concat=n=1:v=1:a=0[v]" in graph
    assert "[1:a]" in graph and "apad=whole_dur=6.000" in graph
    assert argv.count("-loop") == 1 and argv[argv.index("-t") + 1] == "6.000"
    assert argv[argv.index("-c:v") + 1] == "libx264"
    assert argv[argv.index("-pix_fmt") + 1] == "yuv420p"
    assert argv[argv.index("-r") + 1] == "30"
    assert argv[argv.index("-c:a") + 1] == "aac"
    assert argv[argv.index("-threads") + 1] == "2" and argv[-1] == "out.mp4"
    assert "-shortest" not in argv


def test_mix_command_three_photos_shows_each_for_its_share() -> None:
    slides = [Slide(Path(f"{n}.jpg"), "image", 3.0) for n in "abc"]
    argv = mix.build_mix_command("ffmpeg", slides, "s.m4a", "o.mp4", (1920, 1080))
    assert _inputs(argv) == ["a.jpg", "b.jpg", "c.jpg", "s.m4a"]
    assert argv.count("-loop") == 3
    graph = argv[argv.index("-filter_complex") + 1]
    assert "concat=n=3:v=1:a=0[v]" in graph and "[v0][v1][v2]concat" in graph
    assert "scale=1920:1080" in graph and "[3:a]" in graph
    durations = [argv[i + 1] for i, a in enumerate(argv) if a == "-t"]
    assert durations == ["3.000", "3.000", "3.000", "9.000"]  # each photo, then the whole video


def test_mix_command_mixed_carousel_keeps_slide_order_and_drops_clip_sound() -> None:
    slides = [
        Slide(Path("1.jpg"), "image", 2.0),
        Slide(Path("2.mp4"), "video", 4.5),
        Slide(Path("3.jpg"), "image", 2.0),
    ]
    argv = mix.build_mix_command("ffmpeg", slides, "s.m4a", "o.mp4")
    assert _inputs(argv) == ["1.jpg", "2.mp4", "3.jpg", "s.m4a"]
    assert argv.count("-loop") == 2  # the clip is not looped
    graph = argv[argv.index("-filter_complex") + 1]
    assert "[1:v]scale" in graph and "[1:a]" not in graph and "[2:a]" not in graph
    assert "[3:a]" in graph and "apad=whole_dur=8.500" in graph  # the song only, over everything
    assert argv[argv.index("-t", argv.index("-c:a")) + 1] == "8.500"  # output trimmed to the total
    maps = [argv[i + 1] for i, a in enumerate(argv) if a == "-map"]
    assert maps == ["[v]", "[a]"]


def test_mix_command_needs_slides() -> None:
    with pytest.raises(ValueError):
        mix.build_mix_command("ffmpeg", [], "s.m4a", "o.mp4")


# -- process_staging (direct, fake binaries) --------------------------------------
@dataclass
class Staging:
    root: Path
    staging: Path
    out: Path
    ffmpeg: str
    ffprobe: str
    log: Path

    def calls(self) -> list[list[str]]:
        return read_log(self.log)

    def names(self) -> list[str]:
        return sorted(p.name for p in self.staging.iterdir() if p.is_file())

    def run(self, **kw: Any) -> mix.MixResult:
        args: dict[str, Any] = dict(
            post_id="CMus789rst",
            site="instagram",
            existing_dir=self.out,
            ffmpeg=self.ffmpeg,
            ffprobe=self.ffprobe,
        )
        args.update(kw)
        return mix.process_staging(self.staging, **args)


@pytest.fixture
def stage(tmp_path: Path):
    def make(
        *,
        photos: int = 3,
        song: str | None = "dj 2026-11-03 CMus789rst [900] 4.m4a",
        times: bool = True,
        extra: tuple[str, ...] = (),
        probe_files: dict[str, dict[str, Any]] | None = None,
        **ffmpeg_kw: Any,
    ) -> Staging:
        root = tmp_path / f"s{len(list(tmp_path.iterdir()))}"
        staging, out = root / "staging", root / "out"
        for folder in (staging, out):
            folder.mkdir(parents=True)
        for n in range(1, photos + 1):
            (staging / f"dj 2026-11-03 CMus789rst [10{n}] {n}.jpg").write_text("img")
        if song:
            (staging / song).write_text("fullsong")
            meta: dict[str, Any] = {"category": "instagram", "num": 4}
            if times:
                meta["music_consumption_info"] = {
                    "audio_asset_start_time_in_ms": 12000,
                    "overlap_duration_in_ms": 6000,
                }
            (staging / (song + ".json")).write_text(json.dumps(meta))
        for name in extra:
            (staging / name).write_text("x")
        log = root / "ffmpeg.log"
        ffmpeg = write_fake_ffmpeg(root, log=log, **ffmpeg_kw)
        ffprobe = write_fake_ffprobe(root, files=probe_files)
        return Staging(root, staging, out, str(ffmpeg), str(ffprobe), log)

    return make


def test_cut_and_mix_three_photos(stage) -> None:
    s = stage()
    converted: list[int] = []
    result = s.run(on_convert=lambda: converted.append(1))
    names = s.names()
    assert "dj 2026-11-03 CMus789rst song.m4a" in names
    assert "dj 2026-11-03 CMus789rst [CMus789rst_mix].mp4" in names
    assert "dj 2026-11-03 CMus789rst [900] 4.m4a" not in names  # the full download is dropped
    assert not (s.staging / mix.WORK_FOLDER).exists()
    assert result.song == s.staging / "dj 2026-11-03 CMus789rst song.m4a"
    assert result.video == s.staging / "dj 2026-11-03 CMus789rst [CMus789rst_mix].mp4"
    assert result.note is None and result.attempted_video and not result.cancelled
    assert converted == [1]  # told the queue exactly once

    cut, build = s.calls()
    assert cut[cut.index("-ss") + 1] == "12.000" and cut[cut.index("-t") + 1] == "6.000"
    assert cut[cut.index("-c") + 1] == "copy"
    assert _inputs(build)[:3] == [str(s.staging / f"dj 2026-11-03 CMus789rst [10{n}] {n}.jpg") for n in (1, 2, 3)]
    assert _inputs(build)[3].endswith("dj 2026-11-03 CMus789rst song.m4a")
    graph = build[build.index("-filter_complex") + 1]
    assert "concat=n=3" in graph and "scale=1080:1920" in graph
    assert "apad=whole_dur=6.000" in graph  # ffprobe says the snippet is 6 s, 3 photos of 2 s


def test_cut_retries_with_aac_when_stream_copy_fails(stage) -> None:
    s = stage(fail_copy=True)
    result = s.run()
    cut_copy, cut_aac, build = s.calls()
    assert cut_copy[cut_copy.index("-c") + 1] == "copy"
    assert "copy" not in cut_aac and cut_aac[cut_aac.index("-c:a") + 1] == "aac"
    assert cut_aac[-1].endswith(".m4a")
    assert result.video is not None and result.note is None
    assert "dj 2026-11-03 CMus789rst [900] 4.m4a" not in s.names()


def test_no_snippet_times_keeps_the_full_song_with_a_note(stage) -> None:
    s = stage(times=False)
    result = s.run()
    assert "dj 2026-11-03 CMus789rst [900] 4.m4a" in s.names()  # the full song is the result
    assert not any(n.endswith(" song.m4a") for n in s.names())
    assert result.note == "Kept the full song: the post doesn't say which part it plays."
    assert result.video is not None
    calls = s.calls()
    assert len(calls) == 1 and "-filter_complex" in calls[0]  # no cut, only the mix


def test_cut_failure_keeps_the_full_song(stage) -> None:
    s = stage(fail_all=True)
    result = s.run()
    assert "dj 2026-11-03 CMus789rst [900] 4.m4a" in s.names()
    assert result.video is None
    assert result.note == (
        "Kept the full song: it couldn't be trimmed. "
        "Saved the photos and the song; the video couldn't be made."
    )


def test_no_song_means_no_video_and_no_ffmpeg_call(stage) -> None:
    s = stage(song=None)
    result = s.run()
    assert s.calls() == [] and result.video is None and result.song is None
    assert result.note is None and not result.attempted_video
    assert len(s.names()) == 3


def test_several_songs_is_a_tray_and_is_left_alone(stage) -> None:
    s = stage(extra=("other 2.m4a",))
    result = s.run()
    assert s.calls() == [] and result.video is None and result.note is None


def test_missing_ffmpeg_still_keeps_photos_and_song_with_a_note(stage) -> None:
    s = stage()
    result = s.run(ffmpeg="/nonexistent/ffmpeg")  # a path that cannot run
    assert result.video is None
    assert "Saved the photos and the song; the video couldn't be made." in (result.note or "")
    assert "dj 2026-11-03 CMus789rst [900] 4.m4a" in s.names() and len([n for n in s.names() if not n.endswith(".json")]) == 4
    # and with no ffmpeg found at all (the test guard makes find_ffmpeg() None)
    s2 = stage()
    result2 = mix.process_staging(s2.staging, post_id="CMus789rst", site="instagram")
    assert result2.video is None
    assert result2.note is not None and "the video couldn't be made" in result2.note
    assert s2.calls() == []


def test_failed_mix_is_a_note_not_an_error(stage) -> None:
    s = stage(fail_mix=True)
    result = s.run()
    assert result.video is None
    assert result.note == "Saved the photos and the song; the video couldn't be made."
    names = s.names()
    assert "dj 2026-11-03 CMus789rst song.m4a" in names  # the snippet still stands
    assert not any("_mix" in n for n in names)
    assert not (s.staging / mix.WORK_FOLDER).exists()


def test_existing_mix_in_the_output_folder_is_not_built_again(stage) -> None:
    s = stage()
    (s.out / "old name [CMus789rst_mix].mp4").write_text("old")
    result = s.run()
    assert result.video is None and result.note is None and not result.attempted_video
    calls = s.calls()
    assert len(calls) == 1 and "-filter_complex" not in calls[0]  # only the cut
    assert not any("_mix" in n for n in s.names())


def test_existing_mix_in_staging_is_kept(stage) -> None:
    s = stage(extra=("x [CMus789rst_mix].mp4",))
    result = s.run()
    assert result.video is None and not result.attempted_video
    assert all("-filter_complex" not in c for c in s.calls())
    assert "x [CMus789rst_mix].mp4" in s.names()


def test_already_cut_song_is_not_cut_again(stage) -> None:
    s = stage(song="dj 2026-11-03 CMus789rst song.m4a", times=True)
    result = s.run()
    calls = s.calls()
    assert len(calls) == 1 and "-filter_complex" in calls[0]  # a retry after a pause
    assert result.video is not None and result.note is None


def test_mixed_carousel_orders_slides_probes_videos_and_picks_canvas(stage) -> None:
    s = stage(
        photos=2,
        extra=("dj 2026-11-03 CMus789rst [55] 3.mp4",),
        probe_files={
            "dj 2026-11-03 CMus789rst [55] 3.mp4": {"duration": 4.5, "width": 1920, "height": 1080},
            "dj 2026-11-03 CMus789rst [101] 1.jpg": {"width": 1600, "height": 900},
            "dj 2026-11-03 CMus789rst [102] 2.jpg": {"width": 1600, "height": 900},
        },
    )
    # the song is num 4 here: slide order is 1, 2, 3
    result = s.run()
    assert result.video is not None
    build = s.calls()[-1]
    inputs = _inputs(build)
    assert [Path(p).name for p in inputs[:3]] == [
        "dj 2026-11-03 CMus789rst [101] 1.jpg",
        "dj 2026-11-03 CMus789rst [102] 2.jpg",
        "dj 2026-11-03 CMus789rst [55] 3.mp4",
    ]
    assert build.count("-loop") == 2
    graph = build[build.index("-filter_complex") + 1]
    assert "scale=1920:1080" in graph  # landscape majority
    # 2 photos share the 6 s snippet (3 s each) + the 4.5 s clip, audio padded to 10.5 s
    assert "apad=whole_dur=10.500" in graph


def test_audio_saved_as_mp4_is_recognised_as_the_song(stage) -> None:
    s = stage(
        song="dj 2026-11-03 CMus789rst [900] 4.mp4",
        probe_files={"dj 2026-11-03 CMus789rst [900] 4.mp4": {"video": False, "audio": True, "duration": 6.0}},
    )
    result = s.run()
    assert result.video is not None
    cut = s.calls()[0]
    assert cut[cut.index("-i") + 1].endswith("[900] 4.mp4")


def test_unknown_clip_length_makes_the_mix_fail_gracefully(stage) -> None:
    s = stage(
        photos=1,
        extra=("clip 2.mp4",),
        probe_files={"clip 2.mp4": {"missing": True}},
    )
    result = s.run()
    assert result.video is None and "video couldn't be made" in (result.note or "")


def test_mix_job_cancelled_before_it_starts(stage) -> None:
    s = stage()
    job = mix.MixJob()
    job.terminate()
    result = s.run(job=job)
    assert result.cancelled and result.video is None
    assert s.calls() == []
    assert not (s.staging / mix.WORK_FOLDER).exists()


# -- through the queue -----------------------------------------------------------
def music_post(*, photos: int = 2, times: bool = True, shortcode: str = "CMus789rst") -> str:
    base = {
        "category": "instagram",
        "subcategory": "post",
        "username": "dj_northfield",
        "post_shortcode": shortcode,
        "post_id": "3302000000000000000",
        "date": "2026-11-03 18:45:00",
        "description": "New track",
    }
    messages: list[Any] = [[2, dict(base, count=photos + 1)]]
    for n in range(1, photos + 1):
        messages.append(
            [3, f"https://cdn.example.com/{n}.jpg", dict(base, media_id=f"33020000000000000{n:02d}", num=n, extension="jpg")]
        )
    song = dict(base, media_id="3302000000000000099", num=photos + 1, extension="m4a")
    if times:
        song["music_consumption_info"] = {
            "audio_asset_start_time_in_ms": 12000,
            "overlap_duration_in_ms": 6000,
        }
    messages.append([3, "https://cdn.example.com/s.m4a", song])
    return json.dumps(messages)


@dataclass
class MixHarness:
    queue: DownloadQueue
    history: History
    out: Path
    root: Path
    ffmpeg_log: Path
    events: list[dict[str, Any]] = field(default_factory=list)

    def ffmpeg_calls(self) -> list[list[str]]:
        return read_log(self.ffmpeg_log)

    def run_one(self, url: str = POST) -> dict[str, Any]:
        item = self.queue.add(url)
        self.queue.start()
        assert self.queue.wait_until_idle(20)
        found = self.queue.item(item["id"])
        assert found is not None
        return found

    def states(self) -> list[str]:
        return [e["state"] for e in self.events if e.get("type") == "state"]

    def owner_files(self) -> list[str]:
        return sorted(p.name for p in (self.out / "dj_northfield").iterdir())


@pytest.fixture
def mix_harness(tmp_path: Path):
    built: list[MixHarness] = []

    def factory(
        *,
        probe_stdout: str | None = None,
        with_ffmpeg: bool = True,
        pre_existing: str | None = None,
        **ffmpeg_kw: Any,
    ) -> MixHarness:
        root = tmp_path / f"q{len(built)}"
        data, out, tmp = root / "data", root / "out", root / "cache" / "tmp"
        for folder in (data, out, tmp):
            folder.mkdir(parents=True, exist_ok=True)
        ytdlp = write_fake(root, log=root / "ytdlp.log", probe_info=None)
        ytdlp.write_text(
            "#!/usr/bin/env python3\nimport sys\n"
            f"print({NO_VIDEO!r}, file=sys.stderr)\nsys.exit(1)\n"
        )
        gallery = write_fake_gallery(
            root, log=root / "gdl.log", probe_stdout=probe_stdout or music_post()
        )
        ffmpeg_log = root / "ffmpeg.log"
        ffmpeg = ffprobe = None
        if with_ffmpeg:
            ffmpeg = str(write_fake_ffmpeg(root, log=ffmpeg_log, **ffmpeg_kw))
            ffprobe = str(write_fake_ffprobe(root))
        if pre_existing:
            folder = out / "dj_northfield"
            folder.mkdir(parents=True)
            (folder / pre_existing).write_text("old")
        history = History(data / "history.sqlite")
        queue = DownloadQueue(
            history,
            Archive(data / "archive.txt"),
            out,
            tmp,
            ytdlp=str(ytdlp),
            sleep=lambda _s: None,
            gallery_dl=str(gallery),
            ffmpeg=ffmpeg,
            ffprobe=ffprobe,
        )
        harness = MixHarness(queue, history, out, root, ffmpeg_log)
        queue.add_listener(harness.events.append)
        built.append(harness)
        return harness

    yield factory
    for h in built:
        h.queue.stop(1.0)
        h.history.close()


def test_queue_mixes_after_the_download_and_moves_everything(mix_harness) -> None:
    h = mix_harness()
    item = h.run_one()
    assert item["state"] == "done" and item["note"] is None
    names = h.owner_files()
    assert len(names) == 4  # 2 photos + the snippet + the video (the full song is gone)
    assert any(n.endswith(" song.m4a") for n in names)
    assert any(n.endswith("[CMus789rst_mix].mp4") for n in names)
    assert not any(n.endswith("99 3.m4a") for n in names)
    assert not any(n.endswith(".json") for n in names)
    assert item["progress"]["files_total"] == 4  # 3 downloads + the mix
    assert item["progress"]["files_done"] == 4 and item["progress"]["percent"] == 100.0
    assert h.states().count("converting") == 1
    assert h.states().index("converting") > h.states().index("downloading")
    assert h.states()[-1] == "done"
    assert len(h.ffmpeg_calls()) == 2  # cut + mix
    # the staging folder keeps only the metadata
    staging = media.item_directory(h.queue.temp_dir, item["identity"])
    assert all(p.suffix == ".json" for p in staging.iterdir())


def test_queue_progress_counts_the_mix_as_a_file(mix_harness) -> None:
    h = mix_harness()
    item = h.run_one()
    progress = [e["item"]["progress"] for e in h.events if e.get("type") == "progress"]
    assert progress and all(p["files_total"] == 4 for p in progress)
    assert max(p["files_done"] for p in progress) == 3  # the downloads; the mix completes it
    assert item["progress"]["files_done"] == 4


def test_queue_no_song_no_video(mix_harness) -> None:
    messages = json.loads(music_post())[:-1]  # drop the song
    h = mix_harness(probe_stdout=json.dumps(messages))
    item = h.run_one()
    assert item["state"] == "done" and item["note"] is None
    assert h.ffmpeg_calls() == []
    assert len(h.owner_files()) == 2
    assert item["progress"]["files_total"] == 2
    assert "converting" not in h.states()


def test_queue_ffmpeg_missing_is_done_with_a_note(mix_harness) -> None:
    h = mix_harness(with_ffmpeg=False)
    item = h.run_one()
    assert item["state"] == "done"
    assert "Saved the photos and the song; the video couldn't be made." in item["note"]
    assert len(h.owner_files()) == 3  # the photos and the full song
    assert item["progress"]["files_total"] == 3  # no mp4 was expected
    assert item["error"] is None


def test_queue_failed_mix_is_done_with_a_note(mix_harness) -> None:
    h = mix_harness(fail_mix=True)
    item = h.run_one()
    assert item["state"] == "done"
    assert item["note"] == "Saved the photos and the song; the video couldn't be made."
    names = h.owner_files()
    assert len(names) == 3 and any(n.endswith(" song.m4a") for n in names)
    assert item["progress"]["files_total"] == 3 and item["progress"]["files_done"] == 3
    assert item["error"] is None and item["file_path"]


def test_queue_no_times_keeps_the_full_song_with_a_note(mix_harness) -> None:
    h = mix_harness(probe_stdout=music_post(times=False))
    item = h.run_one()
    assert item["state"] == "done"
    assert item["note"] == "Kept the full song: the post doesn't say which part it plays."
    names = h.owner_files()
    assert any(n.endswith("99 3.m4a") for n in names)  # the full song
    assert any(n.endswith("[CMus789rst_mix].mp4") for n in names)
    assert len(h.ffmpeg_calls()) == 1  # only the mix


def test_queue_existing_mix_in_output_is_skipped(mix_harness) -> None:
    h = mix_harness(pre_existing="earlier [CMus789rst_mix].mp4")
    item = h.run_one()
    assert item["state"] == "done"
    names = h.owner_files()
    assert names.count("earlier [CMus789rst_mix].mp4") == 1
    assert sum(1 for n in names if "_mix" in n) == 1  # no second copy
    assert all("-filter_complex" not in " ".join(c) for c in h.ffmpeg_calls())
    assert item["progress"]["files_total"] == 3  # the mp4 is not counted: it was not made


def test_queue_pause_while_converting_stops_the_mix(tmp_path: Path, mix_harness) -> None:
    h = mix_harness()
    # a slow ffmpeg so the item is still "converting" when it is paused
    slow = Path(h.queue._ffmpeg)  # type: ignore[arg-type]
    slow.write_text(slow.read_text().replace("open(argv[-1]", "import time; time.sleep(5); open(argv[-1]"))
    item = h.queue.add(POST)
    h.queue.start()
    from test_queue import wait_for

    assert wait_for(lambda: (h.queue.item(item["id"]) or {}).get("state") == "converting")
    assert h.queue.pause(item["id"])
    assert h.queue.wait_until_idle(10)
    assert h.queue.item(item["id"])["state"] == "paused"
    assert not (h.out / "dj_northfield").exists()  # nothing was moved on a pause
