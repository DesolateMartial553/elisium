"""Render the Night shelf screenshots (offscreen, temp XDG dirs, sample data, no network).

Usage (from the repository root or from ``desktop/``; no wrapper needed):
    nice python3 desktop/tools/render_screenshots.py [OUT_DIR]

Writes queue/empty/history/settings/choose-quality/playlist in Night and Day, at the
normal text size and at a larger one (``-large``), to ``docs/screenshots/`` by default.
Nothing of the real home folder is read or written: every XDG folder is a temp folder.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="elisium-shots-")
os.environ["QT_QPA_PLATFORM"] = "offscreen"  # always headless, whatever the desktop session exports
for _name in ("CONFIG", "DATA", "CACHE", "STATE"):
    os.environ[f"XDG_{_name}_HOME"] = str(Path(_TMP) / _name.lower())
    Path(os.environ[f"XDG_{_name}_HOME"]).mkdir(parents=True, exist_ok=True)
os.environ["XDG_RUNTIME_DIR"] = _TMP
os.environ["ELISIUM_REDUCE_MOTION"] = "1"  # still frames: no easing, no busy bar
os.environ["QT_QPA_PLATFORMTHEME"] = ""  # never let qt6ct/Kvantum restyle the shots

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from elisium_downloader.engine.archive import Archive  # noqa: E402
from elisium_downloader.engine.history import History  # noqa: E402
from elisium_downloader.engine.queue import DownloadQueue  # noqa: E402
from elisium_downloader.ui import theme  # noqa: E402
from elisium_downloader.ui.main_window import MainWindow  # noqa: E402
from elisium_downloader.ui.playlist_dialog import PlaylistDialog  # noqa: E402
from elisium_downloader.ui.quality_dialog import QualityDialog  # noqa: E402
from elisium_downloader.ui.settings import Settings  # noqa: E402
from elisium_downloader.ui.widgets import app_icon  # noqa: E402

_POS = [a for a in sys.argv[1:] if not a.startswith("--") and not a.replace(".", "").isdigit()]
OUT = Path(_POS[0]) if _POS else ROOT.parent / "docs" / "screenshots"

INFO = {
    "title": "Northfield after dark: a walk through the city",
    "uploader": "Quiet Streets",
    "duration": 1325,
    "thumbnail": "https://img.example/t.jpg",
    "formats": [
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 128,
         "tbr": 128, "filesize": 21_000_000},
        {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 160,
         "tbr": 160, "filesize": 26_000_000},
        {"format_id": "137", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "width": 1920,
         "height": 1080, "fps": 30, "tbr": 4000, "filesize": 680_000_000},
        {"format_id": "136", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "width": 1280,
         "height": 720, "fps": 30, "tbr": 2200, "filesize": 380_000_000},
        {"format_id": "18", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "width": 640,
         "height": 360, "fps": 30, "tbr": 500, "filesize": 90_000_000},
    ],
}
PLAYLIST = {
    "title": "Slow evenings: ambient mixes",
    "entries": [
        {"id": f"v{n:02d}", "title": title, "url": f"https://www.youtube.com/watch?v=v{n:02d}",
         "duration": 60 * (n + 20)}
        for n, title in enumerate(
            ("Low tide", "Window light", "Paper lanterns", "The long way home",
             "Sleeping city", "Last light"), start=1)
    ][:4] + [None] + [
        {"id": "v09", "title": "Last train", "url": "https://www.youtube.com/watch?v=v09",
         "duration": 1800},
    ],
}


def pump(ms: int = 60) -> None:
    end = time.monotonic() + ms / 1000
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.004)


# Flat stand-ins for the media's own pictures: a solid block and one lighter shape, no gradient.
_PICTURES = (
    ("#3a2a22", "#c8602a"), ("#2c3a44", "#8fb0c8"), ("#2a2a2a", "#9a9a9a"),
    ("#26331c", "#6a8a3a"), ("#2a1a30", "#c01850"), ("#3a3020", "#caa44a"),
)


def thumb_bytes(kind: int = 0) -> bytes:
    ground, accent = _PICTURES[kind % len(_PICTURES)]
    image = QImage(480, 270, QImage.Format.Format_RGB32)
    image.fill(QColor(ground))
    painter = QPainter(image)
    painter.fillRect(60 + 40 * (kind % 3), 130, 120, 140, QColor(accent))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def fetch_thumbnail(url: str, callback) -> None:
    """Rows carry ``thumbnail="t3"``: the number picks the picture; any other link gets picture 0."""
    callback(thumb_bytes(int(url[1:]) if url[:1] == "t" and url[1:].isdigit() else 0))


def snap(item_id: int, state: str, title: str, **extra):
    row = {
        "id": item_id, "record_id": item_id, "url": f"https://example.com/watch?v={item_id}",
        "identity": f"id{item_id}", "video_key": None, "state": state, "title": title,
        "file_path": None, "attempts": 0, "error": None,
        "progress": {"stage": None, "downloaded_bytes": None, "total_bytes": None,
                     "speed": None, "eta": None, "percent": None},
    }
    progress = extra.pop("progress", {})
    row.update(extra)
    row["progress"].update(progress)
    return row


SAMPLE = [
    snap(1, "downloading", "Birmingham after dark: Selfridges to Moor Street",
         url="https://www.youtube.com/watch?v=a1", thumbnail="t0",
         progress={"percent": 37.0, "speed": 4_404_019.0, "eta": 97, "total_bytes": 680_000_000}),
    snap(2, "downloading", "Monument Hill at dawn", url="https://www.instagram.com/p/b2/",
         thumbnail="t1",
         progress={"percent": 43.0, "speed": 1_990_000.0, "eta": 7, "files_done": 3, "files_total": 7}),
    snap(3, "failed", "Street final, Tokyo 2023", url="https://www.instagram.com/reel/c3/",
         thumbnail="t2",
         error={"code": "session_expired", "message": "Instagram sign-in has expired", "fix": "Sign in"}),
    snap(4, "paused", "How a 1940s radio repair shop worked", url="https://www.youtube.com/watch?v=d4",
         thumbnail="t3",
         progress={"percent": 54.0, "total_bytes": 310_000_000, "downloaded_bytes": 167_400_000}),
    snap(5, "queued", "Cat in the catmint", url="https://www.tiktok.com/@x/video/5", thumbnail="t4"),
    snap(6, "queued", "Live in Montreal, full show", url="https://www.youtube.com/watch?v=f6",
         thumbnail="t5", progress={"total_bytes": 1_331_439_861}),
    snap(7, "done", "Ramen kitchen: the 5 a.m. broth", url="https://www.tiktok.com/@y/video/7",
         thumbnail="t3", note="Kept the full song: the video would have been cut short",
         progress={"percent": 100.0, "total_bytes": 14_900_000}),
]


def build_window(tmp: Path, setting: str, rows) -> tuple[MainWindow, DownloadQueue]:
    for sub in ("data", "out", "tmp"):
        (tmp / sub).mkdir(exist_ok=True)
    history = History(tmp / "data" / "history.sqlite")
    queue = DownloadQueue(
        history, Archive(tmp / "data" / "archive.txt"), tmp / "out", tmp / "tmp",
        sleep=lambda _s: None, probe_url=lambda *a, **k: INFO,
        run_download=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no downloads")),
    )
    seed_history(history, tmp)
    window = MainWindow(queue, settings=Settings(appearance=setting), version_fn=lambda: "2026.11.04",
                        detect_fn=lambda: ["firefox"],  # never read the real browser profiles
                        tray_factory=lambda w: None,
                        probe_fn=lambda url: PLAYLIST if "playlist" in url else INFO,
                        thumbnail_fetcher=fetch_thumbnail)
    window.model.load(rows)
    window._refresh_ui()
    return window, queue


def seed_history(history: History, tmp: Path) -> None:
    """Seven entries over three days (today, yesterday, four days ago); files are sparse."""
    if history.recent(1):
        return
    now = datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def at(days_back: int, hour: int, minute: int) -> str:
        when = min(midnight - timedelta(days=days_back) + timedelta(hours=hour, minutes=minute),
                   now - timedelta(minutes=1))
        return when.isoformat(timespec="seconds")

    def entry(url: str, title: str, when: str, size: int | None = None, **kw) -> None:
        path = None
        if size:
            file = tmp / "out" / f"{title[:40]}.mp4"
            with file.open("wb") as handle:
                handle.seek(size - 1)  # a sparse file: the size is real, the disk use is not
                handle.write(b"\0")
            path = str(file)
        row_id = history.add(url, title=title, created_at=when, file_path=path, **kw)
        history._write("UPDATE downloads SET finished_at = ? WHERE id = ?", (when, row_id))

    entry("https://www.tiktok.com/@y/video/7", "Ramen kitchen: the 5 a.m. broth", at(0, 10, 41),
          14_200_000, state="done")
    entry("https://www.instagram.com/p/b2/", "Monument Hill at dawn", at(0, 10, 38),
          22_400_000, state="done")
    entry("https://www.instagram.com/reel/c3/", "Street final, Tokyo 2023", at(0, 10, 36),
          state="failed", error_code="session_expired", error_message="Instagram sign-in has expired")
    entry("https://www.youtube.com/watch?v=a1", "Birmingham after dark: Selfridges to Moor Street",
          at(1, 21, 4), 648_500_000, state="done")
    entry("https://www.tiktok.com/@x/video/5", "Cat in the catmint", at(1, 18, 12), 9_800_000,
          state="done")
    entry("https://www.youtube.com/watch?v=d4", "How a 1940s radio repair shop worked", at(4, 16, 50),
          295_600_000, state="done")
    entry("https://www.youtube.com/watch?v=f6", "Live in Montreal, full show", at(4, 9, 15),
          state="done")  # no file: shows "File missing"


def save(widget, name: str) -> None:
    pump(80)
    image = widget.grab()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    image.save(str(path))
    print("wrote", path.name, f"{image.width()}x{image.height()}")


def unfocus(window) -> None:
    """Still frames show the page, not a focus ring on whichever field Qt focused first."""
    focused = QApplication.focusWidget()
    if focused is not None:
        focused.clearFocus()
    pump(40)


def wait_state(dialog, state: str) -> None:
    end = time.monotonic() + 5
    while dialog.state != state and time.monotonic() < end:
        pump(20)


def render(app: QApplication, setting: str, suffix: str, tmp: Path, big: bool) -> None:
    theme.apply(app, setting)
    theme.set_reduce_motion(True)
    size_name = f"-{suffix}" if suffix else ""
    window, queue = build_window(tmp, setting, SAMPLE)
    width, height = (1180, 860) if big else (980, 660)
    window.resize(width, height)
    window.show()
    pump(150)
    window.table.selectRow(0)
    window.table.setFocus()
    save(window, f"queue-{setting}{size_name}")
    # empty state
    window.model.load([])
    window._refresh_ui()
    save(window, f"empty-{setting}{size_name}")
    window.model.load(SAMPLE)
    window._refresh_ui()
    window.show_section(1)
    window.history_page.table.selectRow(0)
    unfocus(window)
    save(window, f"history-{setting}{size_name}")
    window.show_section(2)
    unfocus(window)
    save(window, f"settings-{setting}{size_name}")
    window.show_section(0)
    quality = QualityDialog("https://example.com/watch?v=1", queue, window._probe_fn,
                            thumbnail_fetcher=fetch_thumbnail, parent=window)
    quality.show()
    wait_state(quality, "ready")
    quality.advanced_button.setChecked(True)
    pump(120)
    save(quality, f"choose-quality-{setting}{size_name}")
    quality.close()
    playlist = PlaylistDialog("https://www.youtube.com/playlist?list=PL1", queue, window._probe_fn,
                              parent=window)
    playlist.show()
    wait_state(playlist, "ready")
    playlist.list.setCurrentRow(1)
    pump(120)
    save(playlist, f"playlist-{setting}{size_name}")
    playlist.close()
    window.bridge.close()
    window.deleteLater()
    queue.stop(1.0)
    queue.history.close()
    pump(50)


def main() -> int:
    """No arguments: render both text sizes, each in a fresh process (a clean Qt font table).

    ``--scale F`` renders one text size (F times the base size) in this process.
    """
    args = [a for a in sys.argv[1:] if not a.startswith("--scale")]
    scale = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--scale":
            scale = float(sys.argv[i + 1])
            args = [a for a in args if a != sys.argv[i + 1]]
        elif arg.startswith("--scale="):
            scale = float(arg.split("=", 1)[1])
    if scale is None:
        import subprocess

        code = 0
        for factor in (1.0, 1.5):
            cmd = [sys.executable, str(Path(__file__).resolve()), "--scale", str(factor), *args]
            code |= subprocess.call(cmd)
        return code
    app = QApplication.instance() or QApplication(["elisium-shots"])
    app.setWindowIcon(app_icon())
    font = app.font()
    font.setPointSizeF(max(font.pointSizeF(), 12.0) * scale)
    app.setFont(font)  # theme.apply takes this as the base text size
    theme.apply(app, "night")
    for setting in ("night", "day"):
        tmp = Path(tempfile.mkdtemp(prefix="run-", dir=_TMP))
        render(app, setting, "large" if scale > 1 else "", tmp, scale > 1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
