"""The post's song snippet and the photo + song video (brief 10B-2).

Runs on the staging folder of one media item, after gallery-dl finished and
before :func:`media.finalize` moves the files to the output folder:

1. find the post's song (one audio file) and the snippet times the post's
   ``--write-metadata`` JSON files hold (:func:`snippet_from_metadata`);
2. cut the snippet with ffmpeg (stream copy first, AAC 192k m4a if that fails)
   into ``<base> song.<ext>`` and drop the full download; without times the
   full song is kept and the item gets a note;
3. build ``<base> [<post id>_mix].mp4``: the photos (and, in a carousel, the
   videos) in slide order over the song, H.264 yuv420p, 30 fps, AAC.

ffmpeg and ffprobe run as separate processes, always under ``nice`` with two
threads. Nothing here ever fails the item: a missing ffmpeg or a failed mix
leaves the photos and the song as they are and returns a note.
"""

from __future__ import annotations

import glob
import json
import math
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import media

__all__ = [
    "FULL_SONG_NOTE",
    "MIX_FAILED_NOTE",
    "MIN_PHOTO_SECONDS",
    "MixJob",
    "MixResult",
    "Slide",
    "StreamInfo",
    "build_cut_command",
    "build_mix_command",
    "choose_canvas",
    "find_existing_mix",
    "find_ffmpeg",
    "find_ffprobe",
    "mix_marker",
    "photo_seconds",
    "probe_stream",
    "process_staging",
    "snippet_from_metadata",
    "song_base",
]

FULL_SONG_NOTE = "Kept the full song: the post doesn't say which part it plays."
TRIM_FAILED_NOTE = "Kept the full song: it couldn't be trimmed."
MIX_FAILED_NOTE = "Saved the photos and the song; the video couldn't be made."

MIN_PHOTO_SECONDS = 2.0
PORTRAIT = (1080, 1920)
LANDSCAPE = (1920, 1080)
FPS = 30
THREADS = "2"
WORK_FOLDER = ".mix-work"
_CUT_TIMEOUT = 300.0
_MIX_TIMEOUT = 3600.0
_PROBE_TIMEOUT = 60.0
_MAX_JSON_BYTES = 8 * 1024 * 1024


def find_ffmpeg() -> str | None:
    """The ``ffmpeg`` executable on ``PATH``, or ``None``."""
    return shutil.which("ffmpeg")


def find_ffprobe() -> str | None:
    """The ``ffprobe`` executable on ``PATH``, or ``None``."""
    return shutil.which("ffprobe")


# -- snippet times from the post metadata -----------------------------------
# Instagram's own names first (``music_consumption_info`` and friends), then
# generic start / length / end spellings. ``*_ms`` / ``*_in_ms`` are
# milliseconds; a bare ``start`` / ``duration`` is seconds.
_START_MS = (
    "audio_asset_start_time_in_ms",
    "audio_start_time_in_ms",
    "start_time_in_ms",
    "start_time_ms",
    "start_in_ms",
    "start_ms",
    "music_start_ms",
    "snippet_start_ms",
    "clip_start_ms",
    "audio_start_ms",
)
_START_S = ("start_time", "start", "start_s", "start_seconds", "audio_start", "snippet_start")
_LENGTH_MS = (
    "overlap_duration_in_ms",
    "duration_in_ms",
    "duration_ms",
    "length_ms",
    "snippet_duration_ms",
    "clip_duration_ms",
    "audio_duration_ms",
)
_LENGTH_S = (
    "duration",
    "length",
    "duration_s",
    "duration_seconds",
    "length_s",
    "snippet_length",
    "snippet_duration",
)
_END_MS = ("end_time_in_ms", "end_time_ms", "end_in_ms", "end_ms", "audio_end_time_in_ms")
_END_S = ("end_time", "end", "end_s", "end_seconds")
_MAX_DEPTH = 8


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        number = float(value)
        if math.isfinite(number) and number >= 0:
            return number
    return None


def _lookup(
    meta: Mapping[str, Any], ms_keys: Sequence[str], s_keys: Sequence[str]
) -> float | None:
    lowered = {str(k).lower(): v for k, v in meta.items()}
    for key in ms_keys:
        number = _number(lowered.get(key))
        if number is not None:
            return number / 1000.0
    for key in s_keys:
        number = _number(lowered.get(key))
        if number is not None:
            return number
    return None


def _pair(start: float | None, length: float | None, end: float | None) -> tuple[float, float] | None:
    if start is None:
        return None
    if length is None and end is not None and end > start:
        length = end - start
    if length is None or length <= 0:
        return None
    return round(start, 3), round(length, 3)


def _from_dict(meta: Mapping[str, Any]) -> tuple[float, float] | None:
    return _pair(
        _lookup(meta, _START_MS, _START_S),
        _lookup(meta, _LENGTH_MS, _LENGTH_S),
        _lookup(meta, _END_MS, _END_S),
    )


def _from_timestamp_list(key: str, value: Sequence[Any]) -> tuple[float, float] | None:
    """``audio_timestamps: [start, end]`` (seconds, or ms when the key says so)."""
    if len(value) != 2:
        return None
    start, end = _number(value[0]), _number(value[1])
    if start is None or end is None:
        return None
    if key.lower().endswith("ms") or "_ms" in key.lower():
        start, end = start / 1000.0, end / 1000.0
    return _pair(start, None, end)


def _walk(value: Any, key: str, depth: int) -> tuple[float, float] | None:
    if depth > _MAX_DEPTH:
        return None
    if isinstance(value, Mapping):
        found = _from_dict(value)
        if found is not None:
            return found
        for child_key, child in value.items():
            found = _walk(child, str(child_key), depth + 1)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        if "timestamp" in key.lower():
            found = _from_timestamp_list(key, value)
            if found is not None:
                return found
        for child in value:
            found = _walk(child, key, depth + 1)
            if found is not None:
                return found
    return None


def snippet_from_metadata(meta: Any) -> tuple[float, float] | None:
    """``(start_seconds, length_seconds)`` of the post's song, or ``None``.

    Reads tolerantly, anywhere in the (nested) metadata:

    * a dict holding a start and a length (``audio_asset_start_time_in_ms`` +
      ``overlap_duration_in_ms``, ``start_ms`` + ``duration_ms``, ``start`` +
      ``duration``, ...) or a start and an end;
    * an ``audio_timestamps``-style list ``[start, end]`` (seconds; ms when the
      key ends in ``ms``).

    A start without a length, a non-positive length or anything that is not
    a number gives ``None`` (the caller then keeps the full song). A bare
    ``duration`` without a start is deliberately ignored: it is usually the
    length of a video file, not of the song.
    """
    return _walk(meta, "", 0)


# -- naming ------------------------------------------------------------------
_TRAILER_RE = re.compile(r"\s*\[[^\]]*\]\s*\d*\s*$")
_NUM_RE = re.compile(r"(\d+)\.[^.]+$")


def song_base(song_name: str) -> str:
    """``<base>`` for ``<base> song.<ext>`` and the mix: the song file name
    without its extension and without the trailing ``[<media id>] <num>``."""
    stem = Path(song_name).stem
    if stem.endswith(" song"):
        stem = stem[: -len(" song")]
    trimmed = _TRAILER_RE.sub("", stem).strip()
    return trimmed or stem or "song"


def mix_marker(site: str | None, post_id: str) -> str:
    """The ``<post id>_mix`` part of the mix file name (from :func:`media.mix_key`)."""
    return media.mix_key(site or "media", post_id).split(" ", 1)[1]


def find_existing_mix(folder: str | os.PathLike[str] | None, marker: str) -> Path | None:
    """A ``* [<marker>].mp4`` already in *folder*, or ``None``."""
    if folder is None:
        return None
    pattern = os.path.join(glob.escape(str(Path(folder).expanduser())), f"*[[]{glob.escape(marker)}].mp4")
    hits = sorted(glob.glob(pattern))
    return Path(hits[0]) if hits else None


# -- ffprobe -----------------------------------------------------------------
@dataclass(frozen=True)
class StreamInfo:
    """What ffprobe says about one file."""

    width: int | None = None
    height: int | None = None
    duration: float | None = None
    has_video: bool = False
    has_audio: bool = False

    @property
    def portrait(self) -> bool | None:
        """``True`` / ``False`` for a tall / wide picture, ``None`` for a square or unknown one."""
        if not self.width or not self.height or self.width == self.height:
            return None
        return self.height > self.width


def _rotation(stream: Mapping[str, Any]) -> int:
    """Degrees (0-359) the player turns the picture: ``rotate`` tag or side data."""
    tags = stream.get("tags")
    candidates: list[Any] = [tags.get("rotate")] if isinstance(tags, Mapping) else []
    for side in stream.get("side_data_list") or ():
        if isinstance(side, Mapping):
            candidates.append(side.get("rotation"))
    for value in candidates:
        if isinstance(value, bool):
            continue
        try:
            return int(abs(float(value))) % 360
        except (TypeError, ValueError):
            continue
    return 0


def parse_probe_json(text: str) -> StreamInfo | None:
    """ffprobe ``-print_format json -show_format -show_streams`` -> :class:`StreamInfo`."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, Mapping):
        return None
    streams = [s for s in data.get("streams") or () if isinstance(s, Mapping)]
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    width = height = None
    if video is not None:
        w, h = _number(video.get("width")), _number(video.get("height"))
        if w and h:
            width, height = int(w), int(h)
            if _rotation(video) % 180 == 90:
                width, height = height, width
    duration = None
    fmt = data.get("format")
    if isinstance(fmt, Mapping):
        duration = _number(fmt.get("duration"))
    if duration is None:
        for stream in streams:
            duration = _number(stream.get("duration"))
            if duration is not None:
                break
    return StreamInfo(width, height, duration, video is not None, has_audio)


def probe_stream(
    ffprobe: str, path: str | os.PathLike[str], *, run: Callable[..., Any] = subprocess.run
) -> StreamInfo | None:
    """Run ffprobe on *path*; ``None`` when it fails or prints nothing usable."""
    argv = [
        str(ffprobe),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = run(argv, capture_output=True, text=True, timeout=_PROBE_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    return parse_probe_json(getattr(result, "stdout", "") or "")


# -- slides and command lines (pure) -----------------------------------------
@dataclass(frozen=True)
class Slide:
    """One picture or clip of the video; *seconds* is how long it is shown."""

    path: Path
    kind: str  # "image" | "video"
    seconds: float


def photo_seconds(song_seconds: float, photo_count: int) -> list[float]:
    """Seconds for each photo: ``song / count``, at least 2 s each.

    The last photo also holds until the song ends when the others fell short.
    """
    if photo_count <= 0:
        return []
    each = max(MIN_PHOTO_SECONDS, song_seconds / photo_count)
    seconds = [each] * photo_count
    seconds[-1] = max(each, song_seconds - each * (photo_count - 1))
    return [round(s, 3) for s in seconds]


def choose_canvas(infos: Sequence[StreamInfo | None]) -> tuple[int, int]:
    """1080x1920 for a portrait majority (ties and unknowns too), else 1920x1080.

    Square or unprobed pictures vote for neither.
    """
    tall = sum(1 for i in infos if i is not None and i.portrait is True)
    wide = sum(1 for i in infos if i is not None and i.portrait is False)
    return LANDSCAPE if wide > tall else PORTRAIT


def _nice(argv: list[str]) -> list[str]:
    nice = shutil.which("nice")
    return [nice, "-n", "10", *argv] if nice else argv


def _clock(value: float) -> str:
    return f"{value:.3f}"


def build_cut_command(
    ffmpeg: str,
    song: str | os.PathLike[str],
    output: str | os.PathLike[str],
    start: float,
    length: float,
    *,
    reencode: bool = False,
) -> list[str]:
    """``ffmpeg -ss <start> -t <length> -i <song> -c copy <output>``.

    *reencode* gives the retry: AAC 192k (for an ``.m4a`` output).
    """
    argv = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-ss",
        _clock(start),
        "-t",
        _clock(length),
        "-i",
        str(song),
    ]
    if reencode:
        argv += ["-vn", "-c:a", "aac", "-b:a", "192k"]
    else:
        argv += ["-c", "copy"]
    argv += ["-threads", THREADS, str(output)]
    return argv


def build_mix_command(
    ffmpeg: str,
    slides: Sequence[Slide],
    song: str | os.PathLike[str],
    output: str | os.PathLike[str],
    canvas: tuple[int, int] = PORTRAIT,
) -> list[str]:
    """The ffmpeg argv that turns *slides* + *song* into the mp4 (nothing is run).

    Every picture is scaled to fit *canvas* and padded with black bars, then
    all are concatenated; the song is the only audio (the clips' own sound is
    never mapped) and is padded with silence / cut to the total length, so
    the video is exactly as long as its slides.
    """
    if not slides:
        raise ValueError("a mix needs at least one slide")
    width, height = canvas
    total = sum(s.seconds for s in slides)
    argv = [
        str(ffmpeg),
        "-hide_banner",
        "-nostdin",
        "-y",
        "-v",
        "error",
        "-filter_complex_threads",
        THREADS,
    ]
    chains: list[str] = []
    for index, slide in enumerate(slides):
        if slide.kind == "image":
            argv += ["-loop", "1", "-framerate", str(FPS), "-t", _clock(slide.seconds)]
        argv += ["-i", str(slide.path)]
        chains.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=decrease:out_range=tv,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS},"
            f"format=yuv420p[v{index}]"
        )
    song_index = len(slides)
    argv += ["-i", str(song)]
    inputs = "".join(f"[v{i}]" for i in range(len(slides)))
    chains.append(f"{inputs}concat=n={len(slides)}:v=1:a=0[v]")
    chains.append(f"[{song_index}:a]aresample=44100,apad=whole_dur={_clock(total)}[a]")
    argv += [
        "-filter_complex",
        ";".join(chains),
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-t",
        _clock(total),
        "-movflags",
        "+faststart",
        "-threads",
        THREADS,
        "-f",
        "mp4",
        str(output),
    ]
    return argv


# -- running ------------------------------------------------------------------
class MixJob:
    """Runs the ffmpeg steps; :meth:`terminate` stops the current one.

    The queue keeps it as the item's handle while converting, so pause and
    cancel work like they do for a download.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[str] | None = None
        self.cancelled = False

    def terminate(self) -> None:
        with self._lock:
            self.cancelled = True
            proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    def run(self, argv: list[str], timeout: float) -> bool:
        """Run *argv* under ``nice``; ``True`` on exit code 0."""
        with self._lock:
            if self.cancelled:
                return False
            try:
                proc = subprocess.Popen(
                    _nice(argv),
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                return False
            self._proc = proc
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            return False
        finally:
            with self._lock:
                self._proc = None
        return proc.returncode == 0 and not self.cancelled


@dataclass
class MixResult:
    """What :func:`process_staging` did (all paths are in the staging folder)."""

    song: Path | None = None
    video: Path | None = None
    note: str | None = None
    attempted_video: bool = False  # a mix was wanted (so files_total counted it)
    cancelled: bool = False
    removed_songs: int = 0  # songs deleted because the setting is "Photos only"
    notes: list[str] = field(default_factory=list)


def _list_files(directory: Path) -> list[Path]:
    try:
        entries = [e for e in os.scandir(directory) if e.is_file(follow_symlinks=False)]
    except OSError:
        return []
    return sorted(
        (Path(e.path) for e in entries if not e.name.startswith(".")),
        key=lambda p: p.name,
    )


def _ext(path: Path) -> str:
    return path.suffix.lower().lstrip(".")


def _slide_order(path: Path) -> tuple[int, str]:
    match = _NUM_RE.search(path.name)
    return (int(match.group(1)) if match else 10**9, path.name)


def _read_json(path: Path) -> Any:
    try:
        if path.stat().st_size > _MAX_JSON_BYTES:
            return None
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None


def _snippet_in_staging(directory: Path, song: Path) -> tuple[float, float] | None:
    """The song's own metadata file first, then every other ``.json`` there."""
    own = directory / (song.name + ".json")
    others = [p for p in sorted(directory.glob("*.json")) if p != own]
    for path in ([own] if own.exists() else []) + others:
        found = snippet_from_metadata(_read_json(path))
        if found is not None:
            return found
    return None


def _remove(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def process_staging(
    directory: str | os.PathLike[str],
    *,
    post_id: str,
    site: str | None = None,
    existing_dir: str | os.PathLike[str] | None = None,
    ffmpeg: str | None = None,
    ffprobe: str | None = None,
    job: MixJob | None = None,
    on_convert: Callable[[], None] | None = None,
    make_video: bool = True,
    keep_song: bool = True,
    cut_song: bool = True,
) -> MixResult:
    """Cut the song snippet and build the video in the staging *directory*.

    * no song (or several: a story tray) -> nothing happens;
    * no ffmpeg -> the photos and the full song stay, note
      :data:`MIX_FAILED_NOTE` when there were pictures;
    * *on_convert* is called once, just before the first ffmpeg run (the queue
      moves the item to ``converting`` there);
    * *existing_dir* is the output folder: a mix of this post already there is
      never built again.

    The photo/song settings (brief 10C): ``make_video=False`` builds no mp4,
    ``keep_song=False`` deletes the song (photos only), ``cut_song=False``
    keeps the full song without a note (the user asked for it).

    Never raises for an ffmpeg problem; check :attr:`MixResult.cancelled`.
    """
    staging = Path(directory).expanduser()
    result = MixResult()
    marker = mix_marker(site, post_id)
    files = _list_files(staging)
    skip_names = [f for f in files if f"[{marker}]" in f.name]
    files = [f for f in files if f not in skip_names]
    ffmpeg = ffmpeg or find_ffmpeg()
    ffprobe = ffprobe or find_ffprobe()
    job = job or MixJob()

    pictures = [f for f in files if _ext(f) in media.IMAGE_EXTENSIONS]
    videos = [f for f in files if _ext(f) in media.VIDEO_EXTENSIONS]
    songs = [f for f in files if _ext(f) in media.AUDIO_EXTENSIONS]
    infos: dict[Path, StreamInfo | None] = {}
    if not songs and ffprobe and videos:
        # gallery-dl may save the audio as .mp4: an audio-only "video" is the song.
        for clip in videos:
            infos[clip] = probe_stream(ffprobe, clip)
        songs = [
            c
            for c in videos
            if (found := infos[c]) is not None and found.has_audio and not found.has_video
        ]
        videos = [v for v in videos if v not in songs]
    if not keep_song:
        for extra in songs:
            _remove(extra)
        result.removed_songs = len(songs)
        return result
    if len(songs) != 1:
        return result  # no song, or a tray of several: nothing to cut or mix
    song = songs[0]
    visuals = sorted(pictures + videos, key=_slide_order)
    result.song = song

    already_cut = song.stem.endswith(" song")
    times = None if already_cut or not cut_song else _snippet_in_staging(staging, song)
    base = song_base(song.name)
    existing_mix = (
        skip_names[0]
        if skip_names
        else find_existing_mix(existing_dir, marker)
    )
    wants_video = make_video and bool(visuals) and existing_mix is None
    result.attempted_video = wants_video

    if not ffmpeg:
        if not cut_song:
            pass
        elif times is None and not already_cut:
            result.notes.append(FULL_SONG_NOTE)
        elif times is not None:
            result.notes.append(TRIM_FAILED_NOTE)
        if wants_video:
            result.notes.append(MIX_FAILED_NOTE)
        result.note = " ".join(result.notes) or None
        return result

    work = staging / WORK_FOLDER
    try:
        work.mkdir(parents=True, exist_ok=True)
    except OSError:
        if wants_video:
            result.notes.append(MIX_FAILED_NOTE)
        result.note = " ".join(result.notes) or None
        return result
    converting = False

    def convert() -> None:
        nonlocal converting
        if not converting:
            converting = True
            if on_convert is not None:
                on_convert()

    try:
        # -- 1. the snippet ------------------------------------------------
        if already_cut:
            pass
        elif not cut_song:
            pass  # "Full song": nothing to cut, nothing to explain
        elif times is None:
            result.notes.append(FULL_SONG_NOTE)
        else:
            convert()
            snippet = _cut(ffmpeg, job, song, work, staging, base, times)
            if job.cancelled:
                result.cancelled = True
                return result
            if snippet is None:
                result.notes.append(TRIM_FAILED_NOTE)
            else:
                _remove(song)
                song = snippet
                result.song = snippet

        # -- 2. the video ---------------------------------------------------
        if wants_video:
            convert()
            video = _mix(
                ffmpeg, ffprobe, job, song, visuals, infos, work, staging, base, marker, times
            )
            if job.cancelled:
                result.cancelled = True
                return result
            if video is None:
                result.notes.append(MIX_FAILED_NOTE)
            else:
                result.video = video
    finally:
        for leftover in _list_files_all(work):
            _remove(leftover)
        try:
            work.rmdir()
        except OSError:
            pass
    result.note = " ".join(result.notes) or None
    return result


def _list_files_all(folder: Path) -> list[Path]:
    try:
        return [Path(e.path) for e in os.scandir(folder) if e.is_file(follow_symlinks=False)]
    except OSError:
        return []


def _cut(
    ffmpeg: str,
    job: MixJob,
    song: Path,
    work: Path,
    staging: Path,
    base: str,
    times: tuple[float, float],
) -> Path | None:
    """The snippet as ``<base> song.<ext>`` in *staging*, or ``None``."""
    start, length = times
    ext = _ext(song) or "m4a"
    attempts = [(ext, False), ("m4a", True)]
    for out_ext, reencode in attempts:
        scratch = work / f"snippet.{out_ext}"
        _remove(scratch)
        argv = build_cut_command(ffmpeg, song, scratch, start, length, reencode=reencode)
        ok = job.run(argv, _CUT_TIMEOUT)
        if job.cancelled:
            return None
        if ok and scratch.exists() and scratch.stat().st_size > 0:
            final = staging / f"{base} song.{out_ext}"
            try:
                os.replace(scratch, final)
            except OSError:
                return None
            return final
        _remove(scratch)
    return None


def _mix(
    ffmpeg: str,
    ffprobe: str | None,
    job: MixJob,
    song: Path,
    visuals: Sequence[Path],
    infos: dict[Path, StreamInfo | None],
    work: Path,
    staging: Path,
    base: str,
    marker: str,
    times: tuple[float, float] | None,
) -> Path | None:
    """Build ``<base> [<marker>].mp4`` in *staging*, or ``None`` on any failure."""
    if not ffprobe:
        return None
    song_info = probe_stream(ffprobe, song)
    song_seconds = song_info.duration if song_info and song_info.duration else None
    if song_seconds is None and times is not None:
        song_seconds = times[1]
    if not song_seconds or song_seconds <= 0:
        return None
    for path in visuals:
        if path not in infos:
            infos[path] = probe_stream(ffprobe, path)
    photos = [p for p in visuals if _ext(p) in media.IMAGE_EXTENSIONS]
    photo_times = iter(photo_seconds(song_seconds, len(photos)))
    slides: list[Slide] = []
    for path in visuals:
        if path in photos:
            slides.append(Slide(path, "image", next(photo_times)))
            continue
        info = infos.get(path)
        if info is None or not info.duration or info.duration <= 0:
            return None
        slides.append(Slide(path, "video", info.duration))
    canvas = choose_canvas([infos.get(p) for p in visuals])
    scratch = work / "mix.mp4"
    _remove(scratch)
    argv = build_mix_command(ffmpeg, slides, song, scratch, canvas)
    ok = job.run(argv, _MIX_TIMEOUT)
    if not ok or not scratch.exists() or scratch.stat().st_size == 0:
        _remove(scratch)
        return None
    final = staging / f"{base} [{marker}].mp4"
    try:
        os.replace(scratch, final)
    except OSError:
        return None
    return final
