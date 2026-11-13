"""yt-dlp compatible download archive (dedupe layer 1) plus reconciliation.

The file is yt-dlp's own ``--download-archive`` format: one
``<extractor> <id>`` pair per line, extractor lowercased, newline separated.
yt-dlp appends to this file too, so every operation re-reads it instead of
trusting an in-memory copy, and writes go through a temp file + ``os.replace``
so a crash can never leave a half-written archive behind.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

__all__ = ["Archive", "reconcile"]


class Archive:
    """A ``<extractor> <id>`` archive file at *path*."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Archive({str(self.path)!r})"

    # -- file access -----------------------------------------------------
    def _read(self) -> list[tuple[str, str]]:
        """Return the archive entries in file order (missing file -> ``[]``).

        Blank lines, comment-looking lines and anything that is not exactly two
        whitespace-separated fields are ignored, matching yt-dlp's tolerance.
        Duplicates are dropped (first occurrence wins).
        """
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return []
        entries: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for line in text.splitlines():
            fields = line.split()
            if len(fields) != 2:
                continue
            entry = (fields[0].lower(), fields[1])
            if entry in seen:
                continue
            seen.add(entry)
            entries.append(entry)
        return entries

    def _write(self, entries: list[tuple[str, str]]) -> None:
        """Replace the file atomically with *entries*."""
        payload = "".join(
            f"{extractor} {video_id}\n" for extractor, video_id in entries
        )
        parent = self.path.parent
        parent.mkdir(parents=True, exist_ok=True)
        handle = tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="\n",
            dir=parent,
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            delete=False,
        )
        tmp_name = handle.name
        try:
            with handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    @staticmethod
    def _clean(extractor: str, video_id: str) -> tuple[str, str]:
        if not isinstance(extractor, str) or not isinstance(video_id, str):
            raise TypeError("extractor and id must be strings")
        key = extractor.strip().lower()
        value = video_id.strip()
        if not key or not value:
            raise ValueError("extractor and id must not be empty")
        if any(ch.isspace() for ch in key) or any(ch.isspace() for ch in value):
            raise ValueError("extractor and id must not contain whitespace")
        return key, value

    # -- public API ------------------------------------------------------
    def has(self, extractor: str, video_id: str) -> bool:
        """True when ``(<extractor>, <id>)`` is archived."""
        key = extractor.strip().lower()
        return (key, video_id.strip()) in set(self._read())

    def add(self, extractor: str, video_id: str) -> bool:
        """Archive one entry. Returns ``False`` if it was already there."""
        entry = self._clean(extractor, video_id)
        entries = self._read()
        if entry in entries:
            return False
        entries.append(entry)
        self._write(entries)
        return True

    def remove(self, extractor: str, video_id: str) -> bool:
        """Drop one entry. Returns ``False`` if it was not archived."""
        entry = self._clean(extractor, video_id)
        entries = self._read()
        if entry not in entries:
            return False
        entries = [item for item in entries if item != entry]
        self._write(entries)
        return True


def _split_key(key: str) -> tuple[str, str] | None:
    """Turn ``"youtube:ID"`` into ``("youtube", "ID")``; ``None`` if malformed."""
    if not isinstance(key, str):
        return None
    head, sep, tail = key.strip().partition(":")
    head = head.strip().lower()
    tail = tail.strip()
    if not sep or not head or not tail:
        return None
    return head, tail


def _file_exists(output_dir: Path, video_id: str) -> bool:
    """True when a finished file named ``... [<id>] ...`` sits in *output_dir*.

    Unfinished yt-dlp side files (``.part``, ``.ytdl``, ``.temp``) never count:
    staging belongs in the cache temp dir, and a stray leftover must not make
    the app think the video is already downloaded.
    """
    needle = f"[{video_id}]"
    try:
        with os.scandir(output_dir) as entries:
            for entry in entries:
                if needle not in entry.name:
                    continue
                if entry.name.endswith((".part", ".ytdl", ".temp")):
                    continue
                try:
                    if entry.is_file():
                        return True
                except OSError:
                    continue
    except (FileNotFoundError, NotADirectoryError):
        return False
    return False


def reconcile(
    archive: Archive,
    key: str,
    output_dir: str | os.PathLike[str],
) -> bool:
    """Check a ``video_key`` against the archive *and* the output folder.

    Returns ``True`` only when the id is archived and a file whose name
    contains ``[<id>]`` exists in *output_dir*. If the id is archived but the
    file is gone (deleted by the user), the id is removed from the archive so
    the video downloads again, and ``False`` is returned.
    """
    parts = _split_key(key)
    if parts is None:
        return False
    extractor, video_id = parts
    if not archive.has(extractor, video_id):
        return False
    if _file_exists(Path(output_dir).expanduser(), video_id):
        return True
    archive.remove(extractor, video_id)
    return False
