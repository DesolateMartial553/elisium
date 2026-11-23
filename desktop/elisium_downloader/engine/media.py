"""Photo posts, carousels, stories and TikTok slideshows via gallery-dl (brief 10B-1).

yt-dlp cannot save images, so the queue hands those links to the system
``gallery-dl`` binary. Elisium (GPL-3.0) only ever runs it as a **separate
process**, exactly like yt-dlp: nothing from gallery-dl is imported or copied.

The module is shaped like :mod:`runner`:

* :func:`classify_media_url` / :func:`route_for` decide which engine a link
  needs (pure, no network; the URL kinds mirror the Android ``MediaUrls``);
* :func:`write_config` writes the per-run config JSON, so the user's own
  gallery-dl config never changes Elisium's behaviour;
* :func:`probe` runs ``gallery-dl -s -j`` and returns a :class:`MediaPlan`
  (the file list gives the progress total before anything downloads);
* :func:`build_command` / :func:`run` download into a per-item temp folder and
  count finished files from the lines gallery-dl prints;
* :func:`finalize` moves the finished files to ``<output>/<owner>/`` without
  ever overwriting or renaming (an existing name is skipped).

gallery-dl's own ``--download-archive`` (an SQLite file) keeps re-added
carousels from fetching what they already have. Cookies use the same settings
as yt-dlp (browser wins); only the browser name or the file path is passed on
the command line, never the cookie contents.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlsplit

from . import runner
from .errors import (
    GALLERY_DL_MISSING,
    NO_MEDIA_FILES,
    STORY_EXPIRED,
    ErrorInfo,
    explain_gallery,
)
from .urlnorm import normalize_url, site_kind

__all__ = [
    "FILENAME_FORMATS",
    "IMAGE_EXTENSIONS",
    "VIDEO_EXTENSIONS",
    "AUDIO_EXTENSIONS",
    "MediaOptions",
    "MediaPlan",
    "MediaProbeError",
    "MediaProcess",
    "MediaUrl",
    "MediaUrlKind",
    "BULK_SLEEP",
    "BulkKind",
    "BulkListing",
    "BulkPost",
    "BulkUrl",
    "MoveResult",
    "PlannedFile",
    "archive_key",
    "build_bulk_probe_command",
    "build_command",
    "build_probe_command",
    "bulk_key",
    "classify_bulk_url",
    "classify_media_url",
    "listing_info",
    "parse_bulk",
    "probe_bulk",
    "config_dict",
    "filename_format_for",
    "find_gallery_dl",
    "all_present",
    "finalize",
    "item_directory",
    "mix_key",
    "parse_probe",
    "probe",
    "route_for",
    "run",
    "safe_folder_name",
    "staged_files",
    "write_config",
]

IMAGE_EXTENSIONS = frozenset(
    {"jpg", "jpeg", "png", "webp", "heic", "heif", "gif", "avif", "bmp"}
)
VIDEO_EXTENSIONS = frozenset({"mp4", "mov", "webm", "m4v", "mkv"})
AUDIO_EXTENSIONS = frozenset({"m4a", "mp3", "aac", "opus", "ogg", "wav", "flac"})

# Every filename carries the media id, so each carousel slide is unique.
# Alternatives (``a|b``) mean a field gallery-dl does not provide falls through
# to the next one instead of printing "None".
FILENAME_FORMATS: dict[str, str] = {
    "instagram": (
        "{username} {date:%Y-%m-%d} {post_shortcode|shortcode|post_id} "
        "[{media_id|id}] {num}.{extension}"
    ),
    "tiktok": "{author[uniqueId]} {id} [{id}_{num}] {num}.{extension}",
}
_DEFAULT_FORMAT = "{category} {id} {num}.{extension}"

# Files gallery-dl leaves next to the media that are never finished downloads.
_NOT_MEDIA_SUFFIXES = (".json", ".part", ".tmp", ".temp")


# -- finding the binary ----------------------------------------------------
def find_gallery_dl() -> str | None:
    """The ``gallery-dl`` executable on ``PATH``, or ``None``."""
    return shutil.which("gallery-dl")


# -- URL classification ----------------------------------------------------
class MediaUrlKind(str, Enum):
    """What a link points at (same kinds as the Android ``MediaUrlKind``)."""

    POST = "post"  # /p/<code>, /tv/<code>
    REEL = "reel"  # /reel/<code>
    STORIES_USER = "stories_user"  # /stories/<user>/
    STORY_ITEM = "story_item"  # /stories/<user>/<id>/
    HIGHLIGHT = "highlight"  # /stories/highlights/<id>/
    TIKTOK_PHOTO = "tiktok_photo"  # /@user/photo/<id>
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MediaUrl:
    """A classified link; only the fields that belong to :attr:`kind` are set."""

    kind: MediaUrlKind
    site: str | None = None
    shortcode: str | None = None
    username: str | None = None
    story_id: str | None = None
    highlight_id: str | None = None
    tiktok_id: str | None = None


_UNKNOWN_URL = MediaUrl(MediaUrlKind.UNKNOWN)
_SHORTCODE_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def classify_media_url(url: str | None) -> MediaUrl:
    """Classify *url* without any network call.

    Normalisation is :func:`~elisium_downloader.engine.urlnorm.normalize_url`,
    so ``www.`` / ``m.`` hosts and share-link junk behave exactly as they do
    for queue dedupe. Profiles, ``/reels/<user>/``, video links and TikTok
    short links (which would need a redirect) are ``UNKNOWN``.
    """
    if not isinstance(url, str) or not url.strip():
        return _UNKNOWN_URL
    try:
        normalised = normalize_url(url)
    except ValueError:
        return _UNKNOWN_URL
    site = site_kind(normalised)
    if site is None:
        return _UNKNOWN_URL
    try:
        segments = [s for s in urlsplit(normalised).path.split("/") if s]
    except ValueError:
        return _UNKNOWN_URL
    if site == "instagram":
        return _classify_instagram(segments)
    return _classify_tiktok(segments)


def _classify_instagram(segments: list[str]) -> MediaUrl:
    if not segments:
        return _UNKNOWN_URL
    first = segments[0]
    if len(segments) >= 2 and first in ("p", "tv", "reel"):
        code = segments[1]
        if not _SHORTCODE_RE.match(code):
            return _UNKNOWN_URL
        kind = MediaUrlKind.REEL if first == "reel" else MediaUrlKind.POST
        return MediaUrl(kind, "instagram", shortcode=code)
    if first != "stories":
        return _UNKNOWN_URL
    if len(segments) == 3 and segments[1] == "highlights":
        if not segments[2].isdigit():
            return _UNKNOWN_URL
        return MediaUrl(MediaUrlKind.HIGHLIGHT, "instagram", highlight_id=segments[2])
    if len(segments) == 2 and segments[1] != "highlights":
        return MediaUrl(MediaUrlKind.STORIES_USER, "instagram", username=segments[1])
    if len(segments) >= 3 and segments[1] != "highlights":
        if not segments[2].isdigit():
            return _UNKNOWN_URL
        return MediaUrl(
            MediaUrlKind.STORY_ITEM,
            "instagram",
            username=segments[1],
            story_id=segments[2],
        )
    return _UNKNOWN_URL


def _classify_tiktok(segments: list[str]) -> MediaUrl:
    if len(segments) < 3:
        return _UNKNOWN_URL
    user = segments[0]
    if not user.startswith("@") or len(user) == 1:
        return _UNKNOWN_URL
    if segments[1] != "photo" or not segments[2].isdigit():
        return _UNKNOWN_URL
    return MediaUrl(
        MediaUrlKind.TIKTOK_PHOTO,
        "tiktok",
        username=user[1:],
        tiktok_id=segments[2],
    )


def route_for(url: str | None) -> str:
    """Which engine a link needs.

    * ``"media"`` - story trays, highlights and TikTok photos: gallery-dl only;
    * ``"ytdlp_then_media"`` - Instagram posts and single stories: yt-dlp first
      (a video works today), gallery-dl when yt-dlp says "no video in this
      post";
    * ``"bulk"`` - a whole profile, ``/reels/``, ``/tagged/``, Saved or a TikTok
      profile (brief 10G): many posts, always in slow mode;
    * ``"ytdlp"`` - everything else, reels and video links included.
    """
    if classify_bulk_url(url) is not None:
        return "bulk"
    kind = classify_media_url(url).kind
    if kind in (
        MediaUrlKind.STORIES_USER,
        MediaUrlKind.HIGHLIGHT,
        MediaUrlKind.TIKTOK_PHOTO,
    ):
        return "media"
    if kind in (MediaUrlKind.POST, MediaUrlKind.STORY_ITEM):
        return "ytdlp_then_media"
    return "ytdlp"


# -- bulk links: profiles, tabs, Saved (brief 10G) -------------------------
class BulkKind(str, Enum):
    """What a bulk link lists."""

    PROFILE = "profile"  # instagram.com/<user>/
    REELS = "reels"  # instagram.com/<user>/reels/
    TAGGED = "tagged"  # instagram.com/<user>/tagged/
    SAVED = "saved"  # instagram.com/<user>/saved/
    SAVED_COLLECTION = "saved_collection"  # instagram.com/<user>/saved/<name>/<id>/
    TIKTOK_PROFILE = "tiktok_profile"  # tiktok.com/@<user>


# First path segments on instagram.com that are never a username.
_INSTAGRAM_RESERVED = frozenset(
    {
        "about", "accounts", "ads", "api", "ar", "business", "challenge", "developers",
        "direct", "directory", "download", "emails", "explore", "fxcal", "graphql",
        "help", "legal", "lite", "locations", "login", "logout", "nametag",
        "notifications", "oauth", "p", "press", "privacy", "reel", "reels", "session",
        "settings", "shop", "static", "stories", "tags", "terms", "threads", "topics",
        "tv", "web", "_u",
    }
)
_IG_USER_RE = re.compile(r"^(?=.*[A-Za-z0-9])[A-Za-z0-9._]{1,30}$")
_TT_USER_RE = re.compile(r"^(?=.*[A-Za-z0-9])[A-Za-z0-9._]{1,48}$")
_COLLECTION_SEGMENT_RE = re.compile(r"^[^/\\\s]{1,100}$")


@dataclass(frozen=True)
class BulkUrl:
    """A classified bulk link (a profile, a profile tab, Saved)."""

    kind: BulkKind
    site: str
    username: str
    collection: str | None = None  # "name/id" of a Saved collection

    @property
    def url(self) -> str:
        """The canonical link gallery-dl is given."""
        if self.site == "tiktok":
            return f"https://www.tiktok.com/@{self.username}"
        base = f"https://www.instagram.com/{self.username}/"
        if self.kind is BulkKind.PROFILE:
            return base
        if self.kind is BulkKind.SAVED_COLLECTION:
            return f"{base}saved/{self.collection}/"
        return f"{base}{self.kind.value}/"

    @property
    def identity(self) -> str:
        """One queue identity per list, whatever the spelling of the link."""
        parts = ["bulk", self.site, self.username.lower(), self.kind.value]
        if self.collection:
            parts.append(self.collection.lower())
        return ":".join(parts)

    @property
    def label(self) -> str:
        return f"@{self.username}"

    @property
    def title(self) -> str:
        who = self.label
        return {
            BulkKind.PROFILE: f"Posts from {who}",
            BulkKind.REELS: f"Reels from {who}",
            BulkKind.TAGGED: f"Posts tagging {who}",
            BulkKind.SAVED: f"Saved posts of {who}",
            BulkKind.SAVED_COLLECTION: f"Saved collection of {who}",
            BulkKind.TIKTOK_PROFILE: f"Posts from {who}",
        }[self.kind]


def classify_bulk_url(url: str | None) -> BulkUrl | None:
    """The bulk kind of *url*, or ``None`` when it is not a whole-list link.

    A profile is never a post and a post is never a profile: ``/p/<code>``,
    ``/reel/<code>``, ``/stories/...``, ``/explore/`` and the other reserved
    paths are not bulk, and neither is ``/@user/video/<id>``. Trailing slashes,
    query strings and ``www.`` / ``m.`` hosts do not matter. No network.
    """
    if not isinstance(url, str) or not url.strip():
        return None
    try:
        normalised = normalize_url(url)
    except ValueError:
        return None
    site = site_kind(normalised)
    if site is None:
        return None
    try:
        parts = urlsplit(normalised)
        segments = [s for s in parts.path.split("/") if s]
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if site == "tiktok":
        if host != "tiktok.com" or len(segments) != 1:
            return None
        user = segments[0]
        if not user.startswith("@") or not _TT_USER_RE.match(user[1:]):
            return None
        return BulkUrl(BulkKind.TIKTOK_PROFILE, "tiktok", user[1:])
    if not segments or segments[0].lower() in _INSTAGRAM_RESERVED:
        return None
    user = segments[0]
    if not _IG_USER_RE.match(user):
        return None
    if len(segments) == 1:
        return BulkUrl(BulkKind.PROFILE, "instagram", user)
    tab = segments[1].lower()
    if len(segments) == 2 and tab in ("reels", "tagged", "saved"):
        return BulkUrl(BulkKind(tab), "instagram", user)
    if tab == "saved" and 3 <= len(segments) <= 4:
        rest = segments[2:]
        if all(_COLLECTION_SEGMENT_RE.match(seg) for seg in rest):
            return BulkUrl(
                BulkKind.SAVED_COLLECTION, "instagram", user, "/".join(rest)
            )
    return None


def bulk_key(site: str | None, post_id: str) -> str:
    """The key of a post saved by a bulk run: ``"instagram <shortcode>"``."""
    return f"{(site or '').lower()} {post_id}"


def filename_format_for(url: str | None) -> str:
    """The gallery-dl ``-f`` filename format for the site of *url*."""
    site = site_kind(url) if isinstance(url, str) else None
    return FILENAME_FORMATS.get(site or "", _DEFAULT_FORMAT)


# -- archive keys (mirror of the Android MediaKeys) ------------------------
def archive_key(site: str, media_id: str) -> str:
    """``"instagram <mediaId>"`` / ``"tiktok <id>_<n>"``: one key per file."""
    return f"{site.lower()} {media_id}"


def mix_key(site: str, post_id: str) -> str:
    """``"instagram <shortcode>_mix"``: the mp4 built later (brief 10B-2)."""
    return f"{site.lower()} {post_id}_mix"


# -- per-run config --------------------------------------------------------
# Brief 10G: bulk runs ask for one request every 4-10 s (randomised by gallery-dl).
BULK_SLEEP: tuple[float, float] = (4.0, 10.0)


def config_dict(bulk: bool = False) -> dict[str, Any]:
    """The gallery-dl config Elisium runs with.

    *bulk* (brief 10G) adds ``sleep-request`` as a 4-10 s range, so requests are
    randomised and spaced out. Nothing here ever raises concurrency: gallery-dl
    fetches one file at a time and Elisium runs one post at a time.

    Instagram audio is off in gallery-dl by default; it is what carries the
    song of a photo post and story music stickers. TikTok photos and audio are
    on by default and are stated anyway. The ``output`` block pins the stdout
    format Elisium counts files from (one finished path per line, a skipped
    file with a leading ``# ``, full paths, no progress indicator).
    """
    config: dict[str, Any] = {
        "extractor": {
            "instagram": {"audio": True, "videos": True},
            "tiktok": {"audio": True, "photos": True, "videos": True},
        },
        "output": {
            "mode": "pipe",
            "shorten": False,
            "skip": True,
            "progress": False,
        },
    }
    if bulk:
        sleep = list(BULK_SLEEP)
        extractor = config["extractor"]
        extractor["sleep-request"] = sleep
        extractor["instagram"]["sleep-request"] = list(sleep)
        extractor["tiktok"]["sleep-request"] = list(sleep)
    return config


def write_config(path: str | os.PathLike[str], *, bulk: bool = False) -> Path:
    """Write :func:`config_dict` to *path* (mode 0600) and return the path.

    Written to a fresh sibling file and renamed into place, so two runs
    starting together never see a half-written config. The parent folder is
    created when needed.
    """
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    scratch = target.with_name(
        f".{target.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        scratch.unlink(missing_ok=True)
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(scratch, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(config_dict(bulk), stream, indent=2)
        os.replace(scratch, target)
    except BaseException:
        try:
            scratch.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return target


# -- command lines ---------------------------------------------------------
@dataclass(frozen=True)
class MediaOptions:
    """Everything one gallery-dl download run needs (paths are explicit)."""

    url: str
    directory: str | os.PathLike[str]
    config_path: str | os.PathLike[str]
    archive_path: str | os.PathLike[str]
    gallery_dl: str = "gallery-dl"
    filename_format: str | None = None
    limit_rate: str | None = None
    # Only the browser name or the cookies.txt path; the browser wins.
    cookies_browser: str | None = None
    cookies_file: str | os.PathLike[str] | None = None
    extra_args: Sequence[str] = ()
    # False for "Download again anyway": gallery-dl's SQLite archive remembers a
    # post even after its files were deleted, so that run leaves it out.
    use_archive: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.url, str) or not self.url.strip():
            raise ValueError("url must be a non-empty string")

    def command(self) -> list[str]:
        return build_command(self)


def _base(gallery_dl: str, config_path: str | os.PathLike[str]) -> list[str]:
    return [
        str(gallery_dl),
        "--config-ignore",
        "--config-json",
        str(Path(config_path).expanduser()),
        "--no-input",
    ]


def build_probe_command(
    url: str,
    gallery_dl: str = "gallery-dl",
    *,
    config_path: str | os.PathLike[str],
    cookies_browser: str | None = None,
    cookies_file: str | os.PathLike[str] | None = None,
) -> list[str]:
    """``gallery-dl --config-ignore --config-json <cfg> -s -j <url>``."""
    argv = _base(gallery_dl, config_path)
    argv.extend(["-s", "-j"])
    argv.extend(runner._cookie_args(cookies_browser, cookies_file))
    argv.append(url)
    return argv


def build_command(opts: MediaOptions) -> list[str]:
    """The download argv: exact folder, fixed filename format, archive, metadata.

    ``--write-metadata`` leaves one ``.json`` per file next to it in the temp
    folder (brief 10B-2 reads them); :func:`finalize` never moves them.
    """
    argv = _base(opts.gallery_dl, opts.config_path)
    argv.extend(
        [
            "-D",
            str(Path(opts.directory).expanduser()),
            "-f",
            opts.filename_format or filename_format_for(opts.url),
        ]
    )
    if opts.use_archive:
        argv.extend(["--download-archive", str(Path(opts.archive_path).expanduser())])
    argv.append("--write-metadata")
    if opts.limit_rate:
        argv.extend(["--limit-rate", str(opts.limit_rate)])
    argv.extend(runner._cookie_args(opts.cookies_browser, opts.cookies_file))
    argv.extend(str(arg) for arg in opts.extra_args)
    argv.append(opts.url)
    return argv


# -- probe: ``-j`` output -> plan ------------------------------------------
@dataclass(frozen=True)
class PlannedFile:
    """One file gallery-dl will save."""

    kind: str  # "image" | "video" | "audio"
    media_id: str
    num: int
    ext: str

    @property
    def is_audio(self) -> bool:
        return self.kind == "audio"


@dataclass(frozen=True)
class MediaPlan:
    """The files and post details a probe found."""

    site: str | None
    files: tuple[PlannedFile, ...]
    owner: str | None = None
    post_id: str | None = None
    shortcode: str | None = None
    date: str | None = None
    title: str | None = None
    # The first picture's link (or the post's cover): shown on the row, display only.
    thumbnail: str | None = None

    @property
    def total(self) -> int:
        return len(self.files)

    @property
    def format_label(self) -> str | None:
        """What the post holds, in plain words: ``6 photos + song``, ``2 videos``."""
        photos = sum(1 for f in self.files if f.kind == "image")
        videos = sum(1 for f in self.files if f.kind == "video")
        songs = sum(1 for f in self.files if f.is_audio)
        parts = []
        if photos:
            parts.append(f"{photos} photo{'s' if photos != 1 else ''}")
        if videos:
            parts.append(f"{videos} video{'s' if videos != 1 else ''}")
        if songs:
            parts.append("song" if songs == 1 else f"{songs} songs")
        return " + ".join(parts) or None

    @property
    def display_title(self) -> str | None:
        """A card title: the caption's first line, else ``owner shortcode``."""
        if self.title:
            return self.title
        parts = [p for p in (self.owner, self.shortcode or self.post_id) if p]
        return " ".join(parts) or None


class MediaProbeError(Exception):
    """A failed probe: plain-language info plus the raw gallery-dl output."""

    def __init__(self, info: ErrorInfo, raw: str) -> None:
        super().__init__(f"{info.message} [{info.code}]")
        self.info = info
        self.raw = raw


def _messages(text: str) -> list[list[Any]]:
    """Every gallery-dl message (``[type, ...]``) found in *text*.

    Accepts one JSON array of messages, JSON Lines (one message per line) or
    any run of JSON values; characters that are not JSON are skipped.
    """
    decoder = json.JSONDecoder()
    out: list[list[Any]] = []
    index = 0
    length = len(text)
    while index < length:
        if text[index] not in "[{":
            index += 1
            continue
        try:
            value, end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index += 1
            continue
        index = end
        if not isinstance(value, list):
            continue
        if value and isinstance(value[0], int) and not isinstance(value[0], bool):
            out.append(value)  # a single message
        else:
            out.extend(
                m
                for m in value
                if isinstance(m, list)
                and m
                and isinstance(m[0], int)
                and not isinstance(m[0], bool)
            )
    return out


def _string(value: Any) -> str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int)) and str(value).strip():
        return str(value).strip()
    return None


def _first(meta_list: Sequence[Mapping[str, Any]], *keys: str) -> str | None:
    for meta in meta_list:
        for key in keys:
            found = _string(meta.get(key))
            if found is not None:
                return found
    return None


def _owner(meta_list: Sequence[Mapping[str, Any]]) -> str | None:
    found = _first(meta_list, "username", "owner_username", "author_username")
    if found is not None:
        return found
    for meta in meta_list:
        for key in ("author", "owner", "user"):
            value = meta.get(key)
            if isinstance(value, Mapping):
                name = _first([value], "uniqueId", "username", "name")
                if name is not None:
                    return name
            else:
                name = _string(value)
                if name is not None:
                    return name
    return None


def _caption_title(meta_list: Sequence[Mapping[str, Any]]) -> str | None:
    for meta in meta_list:
        for key in ("description", "desc", "caption", "title"):
            value = meta.get(key)
            if isinstance(value, Mapping):
                value = value.get("text")
            if not isinstance(value, str):
                continue
            for line in value.splitlines():
                line = line.strip()
                if line:
                    return line[:150]
    return None


def _extension(meta: Mapping[str, Any], url: Any) -> str:
    ext = _string(meta.get("extension"))
    if ext is None and isinstance(url, str):
        try:
            name = urlsplit(url).path.rsplit("/", 1)[-1]
        except ValueError:
            name = ""
        if "." in name:
            ext = name.rsplit(".", 1)[-1]
    return (ext or "").lower().lstrip(".")


def _kind(ext: str, meta: Mapping[str, Any]) -> str:
    if ext in AUDIO_EXTENSIONS:
        return "audio"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    if ext in IMAGE_EXTENSIONS:
        return "image"
    declared = _string(meta.get("type"))
    if declared in ("image", "video", "audio"):
        return declared
    return "image"


def parse_probe(text: str, url: str | None = None) -> MediaPlan:
    """Turn ``gallery-dl -j`` output into a :class:`MediaPlan`.

    Message type ``3`` is a file (``[3, url, metadata]``), ``2`` is directory
    metadata (the post). Unknown messages are ignored; missing fields never
    raise. An empty or error-only output gives a plan with no files.
    """
    dir_meta: list[Mapping[str, Any]] = []
    file_meta: list[Mapping[str, Any]] = []
    files: list[PlannedFile] = []
    thumbnail: str | None = None
    for message in _messages(text or ""):
        kind = message[0]
        if kind == 2 and len(message) >= 2 and isinstance(message[1], Mapping):
            dir_meta.append(message[1])
        elif kind == 3:
            file_url = message[1] if len(message) >= 2 else None
            meta = message[2] if len(message) >= 3 else {}
            if not isinstance(meta, Mapping):
                meta = {}
            file_meta.append(meta)
            ext = _extension(meta, file_url)
            num_raw = meta.get("num")
            num = (
                num_raw
                if isinstance(num_raw, int) and not isinstance(num_raw, bool)
                else len(files) + 1
            )
            category = _string(meta.get("category")) or (
                site_kind(url) if isinstance(url, str) else None
            )
            ident = _string(meta.get("media_id")) or _string(meta.get("id")) or ""
            if category == "tiktok":
                ident = f"{ident}_{num}" if ident else ""
            planned = PlannedFile(_kind(ext, meta), ident, num, ext)
            files.append(planned)
            if (
                thumbnail is None
                and planned.kind == "image"
                and isinstance(file_url, str)
                and file_url.lower().startswith(("http://", "https://"))
            ):
                thumbnail = file_url
    both = list(dir_meta) + list(file_meta)
    site = _first(both, "category") or (site_kind(url) if isinstance(url, str) else None)
    return MediaPlan(
        site=site.lower() if site else None,
        files=tuple(files),
        owner=_owner(both),
        post_id=_first(both, "post_id", "id"),
        shortcode=_first(both, "post_shortcode", "shortcode"),
        date=_first(both, "post_date", "date"),
        title=_caption_title(both),
        thumbnail=thumbnail or _cover(both),
    )


def _cover(meta_list: Sequence[Mapping[str, Any]]) -> str | None:
    """A post's own cover picture, when no file is a picture (a video-only post)."""
    found = _first(meta_list, "thumbnail", "display_url", "cover")
    if found and found.lower().startswith(("http://", "https://")):
        return found
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


def probe(
    url: str,
    gallery_dl: str = "gallery-dl",
    *,
    config_path: str | os.PathLike[str],
    cookies_browser: str | None = None,
    cookies_file: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
) -> MediaPlan:
    """Run ``gallery-dl -s -j <url>`` and return the planned files.

    Raises :class:`MediaProbeError` (plain-language info plus the raw output)
    when gallery-dl is missing, times out, or finds nothing it can save. A run
    that exits non-zero but still listed files returns the plan: the
    download surfaces the error for the files that failed.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")
    has_cookies = bool(cookies_browser or cookies_file)
    argv = build_probe_command(
        url,
        gallery_dl,
        config_path=config_path,
        cookies_browser=cookies_browser,
        cookies_file=cookies_file,
    )
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except OSError as exc:
        raise MediaProbeError(GALLERY_DL_MISSING, str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raw = _text(exc.stdout) + _text(exc.stderr)
        raise MediaProbeError(
            explain_gallery("timed out", url, has_cookies), raw or str(exc)
        ) from exc

    stdout, stderr = result.stdout or "", result.stderr or ""
    plan = parse_probe(stdout, url)
    if plan.files:
        return plan
    # Captions inside JSON must never be read as error wording: only look at
    # the text around the JSON when there are no files.
    raw = f"{stdout}{stderr}"
    info = explain_gallery(raw, url, has_cookies)
    if info.code == "unknown":
        kind = classify_media_url(url).kind
        if kind in (MediaUrlKind.STORIES_USER, MediaUrlKind.STORY_ITEM):
            info = STORY_EXPIRED  # an empty tray / a missing story: gone after 24 h
        elif result.returncode == 0:
            info = NO_MEDIA_FILES
    raise MediaProbeError(info, raw)


# -- bulk probe: list a profile's posts without downloading (brief 10G) -----
@dataclass(frozen=True)
class BulkPost:
    """One post of a bulk listing: where to fetch it and what it holds."""

    id: str
    url: str
    site: str | None = None
    owner: str | None = None
    date: str | None = None
    title: str | None = None
    files: tuple[PlannedFile, ...] = ()
    thumbnail: str | None = None

    @property
    def plan(self) -> MediaPlan:
        return MediaPlan(
            site=self.site,
            files=self.files,
            owner=self.owner,
            post_id=self.id,
            shortcode=self.id,
            date=self.date,
            title=self.title,
            thumbnail=self.thumbnail,
        )

    @property
    def label(self) -> str:
        """A picker line: ``2026-11-02 · Fresh loaves · 3 photos``."""
        day = (self.date or "")[:10]
        parts = [day, self.title or self.id, self.plan.format_label or ""]
        return " · ".join(p for p in parts if p)

    def to_entry(self) -> dict[str, Any]:
        """The playlist-shaped dict the picker shows (round-trips with :meth:`from_entry`)."""
        return {
            "id": self.id,
            "title": self.label,
            "url": self.url,
            "duration": None,
            "site": self.site,
            "owner": self.owner,
            "date": self.date,
            "caption": self.title,
            "thumbnail": self.thumbnail,
            "files": [[f.kind, f.media_id, f.num, f.ext] for f in self.files],
        }

    @staticmethod
    def from_entry(entry: Mapping[str, Any]) -> "BulkPost | None":
        """Rebuild a post from a picker entry; ``None`` when it has no id or link."""
        ident = _string(entry.get("id"))
        link = entry.get("url")
        if ident is None or not isinstance(link, str) or not link.startswith(("http://", "https://")):
            return None
        files: list[PlannedFile] = []
        for row in entry.get("files") or ():
            try:
                kind, media_id, num, ext = row
                files.append(PlannedFile(str(kind), str(media_id), int(num), str(ext)))
            except (TypeError, ValueError):
                continue
        site = entry.get("site")
        return BulkPost(
            id=ident,
            url=link,
            site=site if isinstance(site, str) else None,
            owner=_string(entry.get("owner")),
            date=_string(entry.get("date")),
            title=_string(entry.get("caption")),
            files=tuple(files),
            thumbnail=_string(entry.get("thumbnail")),
        )


@dataclass(frozen=True)
class BulkListing:
    """The posts a bulk probe found, newest first (never more than the probe's limit)."""

    posts: tuple[BulkPost, ...]


def build_bulk_probe_command(
    url: str,
    gallery_dl: str = "gallery-dl",
    *,
    config_path: str | os.PathLike[str],
    limit: int,
    cookies_browser: str | None = None,
    cookies_file: str | os.PathLike[str] | None = None,
) -> list[str]:
    """``gallery-dl ... -s -j --post-range 1-<limit> <url>``: list, never download."""
    argv = _base(gallery_dl, config_path)
    argv.extend(["-s", "-j", "--post-range", f"1-{max(int(limit), 1)}"])
    argv.extend(runner._cookie_args(cookies_browser, cookies_file))
    argv.append(url)
    return argv


def _post_link(site: str | None, plan: MediaPlan, owner: str | None) -> tuple[str | None, str | None]:
    """``(post id, link)`` for one planned post, or ``(None, None)``."""
    if site == "tiktok":
        ident = plan.post_id
        if ident and owner:
            return ident, f"https://www.tiktok.com/@{owner}/video/{ident}"
        return None, None
    code = plan.shortcode
    if code and _SHORTCODE_RE.match(code):
        return code, f"https://www.instagram.com/p/{code}/"
    return None, None


def parse_bulk(text: str, url: str | None = None) -> tuple[BulkPost, ...]:
    """Group ``gallery-dl -j`` output into posts, in the order gallery-dl listed them.

    A file belongs to the post named by its ``post_shortcode`` / ``shortcode``
    (Instagram) or ``id`` (TikTok). Files without one are left out: Elisium
    could not fetch that post on its own.
    """
    site_hint = site_kind(url) if isinstance(url, str) else None
    groups: dict[str, list[Any]] = {}
    directory: Any = None
    for message in _messages(text or ""):
        kind = message[0]
        if kind == 2 and len(message) >= 2 and isinstance(message[1], Mapping):
            directory = message
            continue
        if kind != 3 or len(message) < 3 or not isinstance(message[2], Mapping):
            continue
        meta = message[2]
        dir_meta = directory[1] if directory is not None else {}
        category = _string(meta.get("category")) or site_hint
        if category == "tiktok":
            ident = _string(meta.get("id"))
        else:
            ident = _first([meta, dir_meta], "post_shortcode", "shortcode")
        if ident is None:
            continue
        group = groups.get(ident)
        if group is None:
            group = groups[ident] = [directory] if directory is not None else []
        group.append(message)
    posts: list[BulkPost] = []
    for group in groups.values():
        plan = parse_probe(json.dumps(group), url)
        site = plan.site or site_hint
        owner = plan.owner
        ident, link = _post_link(site, plan, owner)
        if ident is None or link is None:
            continue
        posts.append(
            BulkPost(
                id=ident,
                url=link,
                site=site,
                owner=owner,
                date=plan.date,
                title=plan.title,
                files=plan.files,
                thumbnail=plan.thumbnail,
            )
        )
    return tuple(posts)


def probe_bulk(
    url: str,
    gallery_dl: str = "gallery-dl",
    *,
    config_path: str | os.PathLike[str],
    limit: int,
    cookies_browser: str | None = None,
    cookies_file: str | os.PathLike[str] | None = None,
    timeout: float | None = 900.0,
) -> BulkListing:
    """List up to *limit* posts of a bulk link (``-s -j --post-range 1-<limit>``).

    Callers pass the run cap + 1, so they can tell "there are more" without
    reading a whole account. The slow mode config (4-10 s between requests)
    applies to the listing too. The result is cut to *limit* even when
    gallery-dl returned more. Raises :class:`MediaProbeError` like :func:`probe`.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("url must be a non-empty string")
    has_cookies = bool(cookies_browser or cookies_file)
    argv = build_bulk_probe_command(
        url,
        gallery_dl,
        config_path=config_path,
        limit=limit,
        cookies_browser=cookies_browser,
        cookies_file=cookies_file,
    )
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, check=False
        )
    except OSError as exc:
        raise MediaProbeError(GALLERY_DL_MISSING, str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raw = _text(exc.stdout) + _text(exc.stderr)
        raise MediaProbeError(
            explain_gallery("timed out", url, has_cookies), raw or str(exc)
        ) from exc
    stdout, stderr = result.stdout or "", result.stderr or ""
    posts = parse_bulk(stdout, url)[: max(int(limit), 1)]
    if posts:
        return BulkListing(posts)
    raw = f"{stdout}{stderr}"
    info = explain_gallery(raw, url, has_cookies)
    if info.code == "unknown" and result.returncode == 0:
        info = NO_MEDIA_FILES
    raise MediaProbeError(info, raw)


def listing_info(
    listing: BulkListing, bulk: BulkUrl | None, cap: int
) -> dict[str, Any]:
    """A yt-dlp-shaped playlist dict (``title`` + ``entries``) for the picker."""
    return {
        "title": bulk.title if bulk is not None else "Posts",
        "bulk": True,
        "cap": cap,
        "entries": [post.to_entry() for post in listing.posts],
    }


# -- what is already saved ----------------------------------------------------
def _is_meta(name: str) -> bool:
    return name.lower().endswith(_NOT_MEDIA_SUFFIXES)


def staged_files(directory: str | os.PathLike[str]) -> list[Path]:
    """Finished media files waiting in a staging folder (metadata and ``.part`` left out)."""
    try:
        return [
            Path(e.path)
            for e in os.scandir(Path(directory).expanduser())
            if e.is_file(follow_symlinks=False) and not _is_meta(e.name)
        ]
    except OSError:
        return []


def all_present(
    output_root: str | os.PathLike[str], owner: str | None, plan: MediaPlan
) -> bool:
    """True when every picture and clip of *plan* is already in ``<output>/<owner>/``.

    Files carry ``[<media id>]`` in their name. The song is left out of the
    check: once cut, its name no longer holds the id. A plan with nothing to
    look for, or a file without an id, counts as not present.
    """
    wanted = [f for f in plan.files if not f.is_audio]
    if not wanted or any(not f.media_id for f in wanted):
        return False
    folder = safe_folder_name(owner)
    root = Path(output_root).expanduser()
    try:
        names = [e.name for e in os.scandir(root / folder if folder else root) if e.is_file()]
    except OSError:
        return False
    return all(any(f"[{f.media_id}]" in name for name in names) for f in wanted)


# -- running ---------------------------------------------------------------
class MediaProcess(runner.DownloadProcess):
    """A running gallery-dl download that counts files as they finish.

    gallery-dl prints no percentages: each finished file's path is printed on
    stdout, a skipped one (already in the archive or on disk) with a leading
    ``# ``. Both count as done. Every new file emits the same progress event
    shape the yt-dlp runner uses, plus ``files_done`` and ``files_total``
    (``percent`` is ``files_done / files_total * 100``).
    """

    def __init__(
        self,
        argv: Sequence[str],
        on_event: Callable[[dict[str, Any]], None] | None = None,
        *,
        directory: str | os.PathLike[str],
        files_total: int | None = None,
    ) -> None:
        # The reader thread starts inside the base constructor, so everything
        # it touches is set first.
        self._directory = str(Path(directory).expanduser()).rstrip(os.sep)
        self.files_total = files_total if files_total and files_total > 0 else None
        self._seen: set[str] = set()
        self.finished: list[str] = []
        self.skipped: list[str] = []
        super().__init__(argv, on_event)

    @property
    def files_done(self) -> int:
        with self._lock:
            return len(self._seen)

    def _handle_line(self, line: str) -> None:
        text = line.rstrip("\r\n")
        if text.strip():
            with self._lock:
                self._raw.append(text)
        stripped = runner._ANSI_RE.sub("", text).strip()
        was_skipped = stripped.startswith("# ")
        path = stripped[2:].strip() if was_skipped else stripped
        if not path.startswith(self._directory + os.sep):
            return
        with self._lock:
            if path in self._seen:
                return
            self._seen.add(path)
            (self.skipped if was_skipped else self.finished).append(path)
            done = len(self._seen)
        self._emit(self._event(done))

    def _event(self, done: int) -> dict[str, Any]:
        total = self.files_total
        percent = None if not total else round(min(done / total, 1.0) * 100.0, 1)
        return {
            "type": "progress",
            "stage": "downloading",
            "status": "downloading",
            "postprocessor": None,
            "downloaded_bytes": None,
            "total_bytes": None,
            "speed": None,
            "eta": None,
            "percent": percent,
            "files_done": done,
            "files_total": total,
        }


def run(
    opts: MediaOptions,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    *,
    files_total: int | None = None,
) -> MediaProcess:
    """Start the gallery-dl download for *opts*; raises ``OSError`` if it is missing."""
    return MediaProcess(
        build_command(opts),
        on_event,
        directory=opts.directory,
        files_total=files_total,
    )


# -- output ----------------------------------------------------------------
def item_directory(temp_dir: str | os.PathLike[str], identity: str) -> Path:
    """The per-item staging folder: stable for one link, so a restart resumes in it."""
    digest = hashlib.sha1(identity.encode("utf-8", "replace")).hexdigest()[:16]
    return Path(temp_dir).expanduser() / "media" / digest


def safe_folder_name(name: str | None) -> str | None:
    """A single safe folder name from remote text, or ``None`` when nothing is left.

    The owner name comes from remote JSON, so path separators, control
    characters, leading dots and ``..`` are all removed.
    """
    if not isinstance(name, str):
        return None
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\]", "_", name)
    cleaned = cleaned.strip().strip(".").strip()
    cleaned = cleaned[:100].rstrip(". ")
    return cleaned or None


@dataclass
class MoveResult:
    """What :func:`finalize` did."""

    moved: list[Path] = field(default_factory=list)
    existing: list[Path] = field(default_factory=list)  # already in the output folder

    @property
    def first(self) -> Path | None:
        if self.moved:
            return self.moved[0]
        return self.existing[0] if self.existing else None


def _move_without_overwrite(src: Path, dst: Path) -> bool:
    """Move *src* to *dst*; ``False`` (and *src* untouched) when *dst* exists."""
    try:
        os.link(src, dst)
    except FileExistsError:
        return False
    except OSError as exc:
        if exc.errno not in (errno.EXDEV, errno.EPERM, errno.ENOTSUP, errno.EMLINK):
            raise
        # Another filesystem (or one without hard links): copy, never replace.
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(dst, flags, 0o644)
        except FileExistsError:
            return False
        try:
            with os.fdopen(fd, "wb") as out, open(src, "rb") as source:
                shutil.copyfileobj(source, out)
        except BaseException:
            try:
                dst.unlink(missing_ok=True)
            except OSError:
                pass
            raise
    src.unlink(missing_ok=True)
    return True


def finalize(
    directory: str | os.PathLike[str],
    output_root: str | os.PathLike[str],
    owner: str | None,
) -> MoveResult:
    """Move the finished files in *directory* to ``<output_root>/<owner>/``.

    The staging folder is scanned (not stdout), so files that finished before a
    pause or a restart are picked up too. ``.json`` metadata (kept for brief
    10B-2), ``.part`` and other leftovers stay where they are. An existing name
    in the output folder is never overwritten or renamed: that staged copy is
    dropped and counted in :attr:`MoveResult.existing`. A missing owner puts
    the files straight in *output_root*.
    """
    source = Path(directory).expanduser()
    root = Path(output_root).expanduser()
    folder = safe_folder_name(owner)
    target = root / folder if folder else root
    result = MoveResult()
    try:
        entries = sorted(
            (e for e in os.scandir(source) if e.is_file(follow_symlinks=False)),
            key=lambda e: e.name,
        )
    except OSError:
        return result
    media = [e for e in entries if not e.name.lower().endswith(_NOT_MEDIA_SUFFIXES)]
    if not media:
        return result
    target.mkdir(parents=True, exist_ok=True)
    for entry in media:
        src = Path(entry.path)
        dst = target / entry.name
        if _move_without_overwrite(src, dst):
            result.moved.append(dst)
        else:
            result.existing.append(dst)
            try:
                src.unlink(missing_ok=True)
            except OSError:
                pass
    return result
