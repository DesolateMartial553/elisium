"""yt-dlp runner: probe a URL, build the command line, stream progress.

Progress comes only from ``--progress-template`` JSON lines, never from scraped
text (``core-spec/SPEC.md``). Each output line is scanned for a JSON object; a
line without one is kept in the raw log so
:func:`elisium_downloader.engine.errors.explain` can turn the failure into a
plain-language message later.

Stages map onto the queue states from the spec::

    download progress        -> downloading
    postprocessor "Merger"   -> merging
    MoveFiles/Metadata/...   -> downloading (no state change)
    any other postprocessor  -> converting

Every yt-dlp flag that matters for queueing lives in :func:`build_command`, so
the dedupe layers (archive, output template, no-overwrites) are set in exactly
one place.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qsl, urlsplit

from .errors import ErrorInfo, explain

__all__ = [
    "DEFAULT_FORMAT",
    "OUTPUT_TEMPLATE",
    "PROGRESS_TEMPLATE",
    "POSTPROCESS_TEMPLATE",
    "STAGES",
    "DownloadOptions",
    "ProbeError",
    "DownloadProcess",
    "build_command",
    "probe",
    "run",
    "parse_progress_line",
    "progress_event",
    "stage_for_postprocessor",
]

# "Best video" preset from the spec.
DEFAULT_FORMAT = "bestvideo*+bestaudio/best"
# Dedupe layer 2: fixed name, so the id is always in the filename.
OUTPUT_TEMPLATE = "%(title).150B [%(id)s].%(ext)s"
# The whole progress dict as JSON, prefixed so download and post-processing
# lines can be told apart.
PROGRESS_TEMPLATE = "download:%(progress)j"
POSTPROCESS_TEMPLATE = "postprocess:%(progress)j"

STAGES: tuple[str, ...] = ("downloading", "merging", "converting")

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")

_MISSING_YTDLP = ErrorInfo(
    "yt-dlp is missing.", "Install yt-dlp", "ytdlp_missing"
)


def _path(value: str | Path) -> str:
    """Absolute-ish string for a path option (``~`` expanded)."""
    return str(Path(value).expanduser())


def _cookie_args(
    browser: str | None, file: str | Path | None
) -> list[str]:
    """The yt-dlp cookie flags for *browser* / *file* (browser wins).

    Only the browser name or the file path goes on the command line; the app
    never reads the file and never logs what is in it.
    """
    if browser:
        return ["--cookies-from-browser", str(browser)]
    if file:
        return ["--cookies", _path(file)]
    return []


@dataclass(frozen=True)
class DownloadOptions:
    """Everything one yt-dlp download run needs.

    The paths are explicit (never read from ``paths.py`` here) so tests and the
    queue can point them at a temporary directory.
    """

    url: str
    output_dir: str | Path
    temp_dir: str | Path
    archive_path: str | Path
    format_selector: str = DEFAULT_FORMAT
    limit_rate: str | None = None
    ytdlp: str = "yt-dlp"
    retries: int = 3
    fragment_retries: int = 3
    extra_args: Sequence[str] = ()
    path_file: str | Path | None = None
    # Instagram stories/private posts need a signed-in session. Only the browser
    # name or the cookies.txt path is kept: the app never reads, copies or logs
    # the cookie contents (the browser wins when both are set).
    cookies_browser: str | None = None
    cookies_file: str | Path | None = None
    # The probe's ``-J`` info dict, already written to a file. When set, yt-dlp
    # downloads with ``--load-info-json`` instead of extracting the page again
    # (brief 12B); ``url`` is then not passed at all.
    info_json: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.url, str) or not self.url.strip():
            raise ValueError("url must be a non-empty string")
        if not isinstance(self.format_selector, str) or not self.format_selector:
            raise ValueError("format_selector must be a non-empty string")
        if int(self.retries) < 0 or int(self.fragment_retries) < 0:
            raise ValueError("retries must not be negative")

    def command(self) -> list[str]:
        """The argv for this download."""
        return build_command(self)


def build_command(opts: DownloadOptions) -> list[str]:
    """Return the yt-dlp argv for *opts*.

    Covers the four spec requirements that live on the command line: the
    archive (dedupe layer 1), ``--no-overwrites`` plus the fixed output
    template (layer 2), the home/temp split so the output folder never holds a
    ``.part`` file, and ``--continue`` so a paused item resumes.

    When ``opts.path_file`` is set, yt-dlp writes the final moved file path
    to that file via ``--print-to-file after_move:filepath <file>``. This is
    the only reliable way to know the real output path for non-YouTube sites
    (the ``[<id>]`` scan in :func:`DownloadQueue._find_output` only works for
    YouTube ids). The flag does not imply ``--quiet`` or ``--simulate``.

    When ``opts.info_json`` is set, ``--load-info-json <file>`` replaces the
    URL: yt-dlp downloads from the probe's info dict instead of extracting the
    page a second time (brief 12B). Every other flag is unchanged.
    """
    argv = [
        str(opts.ytdlp),
        "-P",
        f"home:{_path(opts.output_dir)}",
        "-P",
        f"temp:{_path(opts.temp_dir)}",
        "--download-archive",
        _path(opts.archive_path),
        "--no-overwrites",
        "-o",
        OUTPUT_TEMPLATE,
        "--continue",
        "--newline",
        "--progress-template",
        PROGRESS_TEMPLATE,
        "--progress-template",
        POSTPROCESS_TEMPLATE,
        "--retries",
        str(int(opts.retries)),
        "--fragment-retries",
        str(int(opts.fragment_retries)),
        "-f",
        opts.format_selector,
        # The queue only ever downloads single videos (playlist picks are queued
        # one URL each); without this a ``watch?v=ID&list=...`` link would pull
        # the whole playlist or mix into one item.
        "--no-playlist",
    ]
    if opts.info_json is not None:
        # Brief 12B: reuse the probe instead of extracting the page again.
        argv.extend(["--load-info-json", _path(opts.info_json)])
    if opts.path_file is not None:
        argv.extend(
            [
                "--print-to-file",
                "after_move:filepath",
                _path(opts.path_file),
            ]
        )
    if opts.limit_rate:
        argv.extend(["--limit-rate", str(opts.limit_rate)])
    argv.extend(_cookie_args(opts.cookies_browser, opts.cookies_file))
    argv.extend(str(arg) for arg in opts.extra_args)
    if opts.info_json is None:
        argv.append(opts.url)
    return argv


class ProbeError(Exception):
    """A failed ``probe``: plain-language info plus the raw yt-dlp output."""

    def __init__(self, info: ErrorInfo, raw: str) -> None:
        super().__init__(f"{info.message} [{info.code}]")
        self.info = info
        self.raw = raw


_INSTAGRAM_HOSTS = frozenset({"instagram.com"})


def _bare_host(url: str) -> str:
    """The lower-case host of *url* without ``www.`` / ``m.``, else ``""``."""
    try:
        host = (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    return host


def _is_instagram_story_tray(url: str) -> bool:
    """True for ``instagram.com/stories/<user>/`` and ``/stories/highlights/<id>``.

    A story URL that carries its own numeric id (``/stories/<user>/<id>``) is
    one story, not a tray.
    """
    if _bare_host(url) not in _INSTAGRAM_HOSTS:
        return False
    try:
        segments = [s for s in urlsplit(url).path.split("/") if s]
    except ValueError:
        return False
    if not segments or segments[0] != "stories":
        return False
    if len(segments) == 2 and segments[1] != "highlights":
        return True  # /stories/<user>/: the whole tray
    return len(segments) == 3 and segments[1] == "highlights"


def _looks_like_playlist(url: str) -> bool:
    """True when *url* addresses a playlist rather than one video."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    segments = [segment for segment in parts.path.split("/") if segment]
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("list") and not query.get("v"):
        return True
    if _is_instagram_story_tray(url):
        return True
    return bool(segments) and segments[0] == "playlist"


def _json_object(text: str) -> dict[str, Any] | None:
    """The first complete JSON object in *text*, else ``None``."""
    start = text.find("{")
    while start != -1:
        end = text.rfind("}")
        while end > start:
            try:
                value = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                end = text.rfind("}", start, end)
                continue
            if isinstance(value, dict):
                return value
            break
        start = text.find("{", start + 1)
    return None


def probe(
    url: str,
    ytdlp: str = "yt-dlp",
    *,
    cookies_browser: str | None = None,
    cookies_file: str | Path | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Return yt-dlp's ``-J`` info dict for *url*.

    Single videos use ``--no-playlist``; playlist links and Instagram story
    trays use ``--flat-playlist`` so probing stays cheap. The cookie options
    are passed through unchanged so a story tray can be probed when the site
    needs a signed-in session. Raises :class:`ProbeError` carrying an
    :class:`ErrorInfo` and the raw output.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")
    argv = [str(ytdlp), "-J", "--no-download"]
    argv.append("--flat-playlist" if _looks_like_playlist(url) else "--no-playlist")
    argv.extend(_cookie_args(cookies_browser, cookies_file))
    argv.append(url)

    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except OSError as exc:
        raise ProbeError(_MISSING_YTDLP, str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raw = _text(exc.stdout) + _text(exc.stderr)
        raise ProbeError(explain("timed out"), raw or str(exc)) from exc

    raw = f"{result.stdout or ''}{result.stderr or ''}"
    if result.returncode != 0:
        raise ProbeError(explain(raw), raw)
    try:
        data = json.loads(result.stdout or "")
    except json.JSONDecodeError:
        data = _json_object(result.stdout or "")
    if not isinstance(data, dict):
        raise ProbeError(explain(raw), raw)
    return data


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


_HOUSEKEEPING_POSTPROCESSORS: frozenset[str] = frozenset(
    {
        "movefiles",
        "metadata",
        "ffmpegmetadata",
        "sponsorblock",
    }
)



def stage_for_postprocessor(name: str) -> str:
    """Map a yt-dlp postprocessor name onto a queue stage.

    Housekeeping postprocessors (MoveFiles, Metadata, FFmpegMetadata,
    SponsorBlock) return ``"downloading"``; the queue treats a postprocessor
    event with that stage as "no state change". Everything else (ExtractAudio,
    VideoConvertor, VideoRemuxer, EmbedSubtitle, EmbedThumbnail,
    ModifyChapters, Fixup*) is real work and maps to ``"converting"``;
    mergers map to ``"merging"``.
    """
    lowered = (name or "").lower()
    if "merg" in lowered:  # Merger, FFmpegMerger
        return "merging"
    if lowered in _HOUSEKEEPING_POSTPROCESSORS:
        return "downloading"
    return "converting"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def progress_event(data: Mapping[str, Any]) -> dict[str, Any] | None:
    """Turn one decoded progress dict into an event, or ``None``.

    ``None`` means "this JSON object is not a progress report" (yt-dlp prints
    other JSON shapes on some code paths).
    """
    if not isinstance(data, Mapping):
        return None
    status = data.get("status")
    status_text = status if isinstance(status, str) else ""
    known = {
        "downloaded_bytes",
        "total_bytes",
        "total_bytes_estimate",
        "speed",
        "eta",
        "fragment_index",
        "postprocessor",
        "elapsed",
    }
    if not known.intersection(data) and status_text not in (
        "downloading",
        "finished",
        "started",
        "processing",
        "error",
    ):
        return None

    downloaded = _number(data.get("downloaded_bytes"))
    total = _number(data.get("total_bytes"))
    if total is None:
        total = _number(data.get("total_bytes_estimate"))
    percent: float | None = None
    if downloaded is not None and total:
        percent = round(min(downloaded / total, 1.0) * 100.0, 1)
    elif status_text == "finished" and "postprocessor" not in data:
        percent = 100.0

    if "postprocessor" in data:
        postprocessor = data.get("postprocessor")
        name = postprocessor if isinstance(postprocessor, str) else ""
        return {
            "type": "progress",
            "stage": stage_for_postprocessor(name),
            "status": status_text,
            "postprocessor": name or None,
            "downloaded_bytes": None,
            "total_bytes": None,
            "speed": None,
            "eta": None,
            "percent": percent,
        }

    return {
        "type": "progress",
        "stage": "downloading",
        "status": status_text,
        "postprocessor": None,
        "downloaded_bytes": None if downloaded is None else int(downloaded),
        "total_bytes": None if total is None else int(total),
        "speed": _number(data.get("speed")),
        "eta": _number(data.get("eta")),
        "percent": percent,
    }


def parse_progress_line(line: str) -> dict[str, Any] | None:
    """Parse one output line into a progress event, or ``None``.

    yt-dlp prefixes template output with ``[download]``/``[postprocess]`` and
    may colour it, so only the JSON object inside the line is used.
    """
    text = _ANSI_RE.sub("", line).strip()
    if "{" not in text or "}" not in text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return progress_event(data)


class DownloadProcess:
    """A running (or finished) yt-dlp download.

    stdout and stderr are merged so the raw log keeps yt-dlp's own ordering;
    progress parsing only ever looks at JSON lines, so noise is harmless. The
    reader thread emits ``{"type": "progress", ...}`` for each parsed progress
    line and one final ``{"type": "exit", "returncode": ..., "raw": ...}``.
    """

    def __init__(
        self,
        argv: Sequence[str],
        on_event: Callable[[dict[str, Any]], None] | None = None,
        *,
        cwd: str | Path | None = None,
    ) -> None:
        self.argv = [str(arg) for arg in argv]
        self._on_event = on_event
        self._lock = threading.Lock()
        self._raw: list[str] = []
        self._terminated = False
        self.returncode: int | None = None
        self._proc = subprocess.Popen(
            self.argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            cwd=None if cwd is None else str(cwd),
        )
        self._thread = threading.Thread(
            target=self._pump, name="yt-dlp-reader", daemon=True
        )
        self._thread.start()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"DownloadProcess(pid={self._proc.pid}, returncode={self.returncode!r})"

    # -- reading ---------------------------------------------------------
    @property
    def raw_log(self) -> str:
        """Everything yt-dlp printed, newline separated."""
        with self._lock:
            return "\n".join(self._raw)

    @property
    def terminated(self) -> bool:
        """True when :meth:`terminate` ended the process."""
        with self._lock:
            return self._terminated

    @property
    def done(self) -> bool:
        return self.returncode is not None

    def _pump(self) -> None:
        stream = self._proc.stdout
        try:
            if stream is not None:
                for line in stream:
                    self._handle_line(line)
        finally:
            if stream is not None:
                try:
                    stream.close()
                except OSError:
                    pass
            code = self._proc.wait()
            with self._lock:
                self.returncode = code
                terminated = self._terminated
            self._emit(
                {
                    "type": "exit",
                    "returncode": code,
                    "terminated": terminated,
                    "raw": self.raw_log,
                }
            )

    def _handle_line(self, line: str) -> None:
        text = line.rstrip("\r\n")
        if text.strip():
            with self._lock:
                self._raw.append(text)
        event = parse_progress_line(text)
        if event is not None:
            self._emit(event)

    def _emit(self, event: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event)
        except Exception:  # a broken listener must not kill the reader thread
            pass

    # -- control ---------------------------------------------------------
    def terminate(self) -> None:
        """Stop the download (SIGTERM). ``.part`` files are left in place."""
        with self._lock:
            if self.returncode is not None:
                return
            self._terminated = True
        try:
            self._proc.terminate()
        except OSError:
            pass

    def kill(self) -> None:
        """Stop the download immediately (SIGKILL); ``.part`` files stay."""
        with self._lock:
            if self.returncode is not None:
                return
            self._terminated = True
        try:
            self._proc.kill()
        except OSError:
            pass

    def wait(self, timeout: float | None = None) -> int | None:
        """Block until the process has exited; returns the return code."""
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout)
        return self.returncode


def run(
    opts: DownloadOptions,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> DownloadProcess:
    """Start the download for *opts* and return the process handle."""
    return DownloadProcess(build_command(opts), on_event)
