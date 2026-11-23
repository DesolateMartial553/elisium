"""Brief 10G: bulk saves (whole profile, tabs, Saved, TikTok profile) in slow mode.

Everything runs against a fake gallery-dl script on disk (it is passed to the queue
explicitly; the autouse guard in conftest keeps the real binary out of reach). No
network, no real account, offscreen Qt only.
"""

from __future__ import annotations

import json
import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QFontInfo
from PySide6.QtWidgets import QAbstractButton, QLabel, QWidget

from elisium_downloader.engine import errors, media
from elisium_downloader.engine.archive import Archive
from elisium_downloader.engine.history import History
from elisium_downloader.engine.media import BulkKind
from elisium_downloader.engine.queue import (
    BULK_DEFAULT_MAX_POSTS,
    BULK_MAX_POSTS_LIMIT,
    DownloadQueue,
    clamp_bulk_max,
)
from elisium_downloader.engine.runner import ProbeError
from elisium_downloader.ui import settings as st
from elisium_downloader.ui import theme
from elisium_downloader.ui.main_window import MainWindow, _needs_picker
from elisium_downloader.ui.model import describe_row
from elisium_downloader.ui.playlist_dialog import (
    BULK_WARNING_TEXT,
    BulkWarningDialog,
    PlaylistDialog,
)
from elisium_downloader.ui.settings_page import SettingsPage

from test_media import read_log, value_after

IG = "https://www.instagram.com"
PROFILE = f"{IG}/bakery_north/"
TT_PROFILE = "https://www.tiktok.com/@dancer"


# -- a fake gallery-dl for bulk runs ------------------------------------------
def post_codes(count: int) -> list[str]:
    return [f"CODE{n:03d}" for n in range(1, count + 1)]


def write_fake_bulk(
    root: Path,
    *,
    log: Path,
    posts: int,
    owner: str = "bakery_north",
    limit_file: Path | None = None,
    ignore_range: bool = False,
    limit_text: str = "HTTP Error 429: Too Many Requests",
) -> Path:
    """Answers ``-j`` with *posts* posts (newest first) and honours ``--post-range``.

    A download run ("-D <dir> ... <post url>") writes ``<owner> <code> [<mid>] 1.jpg``
    and prints its path. When *limit_file* exists and names the post code, that run
    prints a 429 on stderr and exits 1 before writing anything.
    """
    lines = [
        "#!/usr/bin/env python3",
        "import json, os, re, sys",
        "argv = sys.argv[1:]",
        f"open({str(log)!r}, 'a').write(json.dumps(argv) + '\\n')",
        f"CODES = {post_codes(posts)!r}",
        f"OWNER = {owner!r}",
        f"LIMIT = {str(limit_file) if limit_file else None!r}",
        "def messages(codes):",
        "    out = []",
        "    for n, code in enumerate(codes):",
        "        meta = {'category': 'instagram', 'username': OWNER, 'post_shortcode': code,",
        "                'shortcode': code, 'media_id': '9' + code[-3:], 'num': 1, 'count': 1,",
        "                'extension': 'jpg', 'date': '2026-11-%02d 10:00:00' % (28 - n % 27),",
        "                'description': 'Post ' + code}",
        "        out.append([2, {'username': OWNER, 'post_shortcode': code}])",
        "        out.append([3, 'https://cdn.example.invalid/' + code + '.jpg', meta])",
        "    return out",
        "if '-j' in argv:",
        "    codes = CODES",
        f"    if not {ignore_range!r} and '--post-range' in argv:",
        "        hi = int(argv[argv.index('--post-range') + 1].split('-')[1])",
        "        codes = CODES[:hi]",
        "    sys.stdout.write(json.dumps(messages(codes)))",
        "    sys.exit(0)",
        "url = argv[-1]",
        "code = re.search(r'/p/([^/]+)/', url).group(1)",
        "if LIMIT and os.path.exists(LIMIT) and open(LIMIT).read().strip() == code:",
        f"    sys.stderr.write({limit_text!r} + '\\n')",
        "    sys.exit(1)",
        "directory = argv[argv.index('-D') + 1]",
        "os.makedirs(directory, exist_ok=True)",
        "path = os.path.join(directory, f'{OWNER} {code} [9{code[-3:]}] 1.jpg')",
        "open(path, 'w').write('data ' + code)",
        "print(path, flush=True)",
        "sys.exit(0)",
    ]
    script = root / "fake-bulk-gallery-dl"
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@dataclass
class BulkHarness:
    queue: DownloadQueue
    history: History
    out: Path
    data: Path
    tmp: Path
    log: Path
    limit_file: Path

    def calls(self) -> list[list[str]]:
        return read_log(self.log)

    def probes(self) -> list[list[str]]:
        return [a for a in self.calls() if "-j" in a]

    def downloads(self) -> list[list[str]]:
        return [a for a in self.calls() if "-j" not in a]

    def downloaded_codes(self) -> list[str]:
        return [a[-1].rstrip("/").rsplit("/", 1)[-1] for a in self.downloads()]

    def run(self, item_id: int, timeout: float = 20.0) -> dict[str, Any]:
        self.queue.start()
        assert self.queue.wait_until_idle(timeout)
        found = self.queue.item(item_id)
        assert found is not None
        return found


@pytest.fixture
def bulk_harness(tmp_path: Path):
    built: list[BulkHarness] = []

    def factory(*, posts: int = 6, cap: int = 50, **fake: Any) -> BulkHarness:
        root = tmp_path / f"b{len(built)}"
        data, out, tmp = root / "data", root / "out", root / "cache" / "tmp"
        for folder in (data, out, tmp):
            folder.mkdir(parents=True, exist_ok=True)
        log, limit_file = root / "gdl.log", root / "limit.txt"
        script = write_fake_bulk(root, log=log, posts=posts, limit_file=limit_file, **fake)
        history = History(data / "history.sqlite")
        queue = DownloadQueue(
            history,
            Archive(data / "archive.txt"),
            out,
            tmp,
            concurrency=2,
            sleep=lambda _s: None,
            gallery_dl=str(script),
            bulk_delay=lambda: 0.0,
            bulk_max_posts=cap,
        )
        harness = BulkHarness(queue, history, out, data, tmp, log, limit_file)
        built.append(harness)
        return harness

    yield factory
    for h in built:
        h.queue.stop(1.0)
        h.history.close()


# -- URL classification ---------------------------------------------------------
@pytest.mark.parametrize(
    ("url", "kind", "user"),
    [
        (f"{IG}/bakery_north/", BulkKind.PROFILE, "bakery_north"),
        (f"{IG}/bakery_north", BulkKind.PROFILE, "bakery_north"),
        (f"{IG}/bakery_north/?hl=en&igsh=abc", BulkKind.PROFILE, "bakery_north"),
        ("https://instagram.com/Bakery.North_1/", BulkKind.PROFILE, "Bakery.North_1"),
        ("https://m.instagram.com/bakery_north/", BulkKind.PROFILE, "bakery_north"),
        (f"{IG}/bakery_north/reels/", BulkKind.REELS, "bakery_north"),
        (f"{IG}/bakery_north/reels", BulkKind.REELS, "bakery_north"),
        (f"{IG}/bakery_north/tagged/", BulkKind.TAGGED, "bakery_north"),
        (f"{IG}/bakery_north/saved/", BulkKind.SAVED, "bakery_north"),
        (f"{IG}/bakery_north/saved/?x=1", BulkKind.SAVED, "bakery_north"),
        (f"{IG}/bakery_north/saved/Food/1789000/", BulkKind.SAVED_COLLECTION, "bakery_north"),
        (f"{IG}/bakery_north/saved/Food", BulkKind.SAVED_COLLECTION, "bakery_north"),
        ("https://www.tiktok.com/@dancer", BulkKind.TIKTOK_PROFILE, "dancer"),
        ("https://www.tiktok.com/@dancer/", BulkKind.TIKTOK_PROFILE, "dancer"),
        ("https://www.tiktok.com/@dancer?lang=en", BulkKind.TIKTOK_PROFILE, "dancer"),
    ],
)
def test_bulk_links_are_classified(url: str, kind: BulkKind, user: str) -> None:
    found = media.classify_bulk_url(url)
    assert found is not None and (found.kind, found.username) == (kind, user)
    assert media.route_for(url) == "bulk"
    assert _needs_picker(url)


@pytest.mark.parametrize(
    "url",
    [
        # single posts stay single posts
        f"{IG}/p/CAbc123xyz/",
        f"{IG}/p/CAbc123xyz",
        f"{IG}/tv/CAbc123xyz/",
        f"{IG}/reel/CAbc123xyz/",
        f"{IG}/bakery_north/p/CAbc123xyz/",
        f"{IG}/bakery_north/reel/CAbc123xyz/",
        f"{IG}/stories/bakery_north/",
        f"{IG}/stories/bakery_north/3303000000000000001/",
        f"{IG}/stories/highlights/17912345678901234/",
        "https://www.tiktok.com/@dancer/photo/7300000000000000001",
        "https://www.tiktok.com/@dancer/video/7300000000000000001",
        "https://vm.tiktok.com/ZMabc123/",
        # reserved paths are never a username
        f"{IG}/explore/",
        f"{IG}/explore/tags/bread/",
        f"{IG}/accounts/login/",
        f"{IG}/accounts/",
        f"{IG}/reels/",
        f"{IG}/reels/bakery_north/",
        f"{IG}/direct/inbox/",
        f"{IG}/p/",
        f"{IG}/",
        # tabs and pages that are not lists
        f"{IG}/bakery_north/followers/",
        f"{IG}/bakery_north/saved/Food/1/extra/",
        f"{IG}/bakery_north/saved/Food/1/extra/more/",
        "https://www.tiktok.com/",
        "https://www.tiktok.com/@",
        "https://www.tiktok.com/@dancer/likes",
        "https://www.tiktok.com/foryou",
        # not these sites / not links
        "https://www.youtube.com/@somechannel",
        "https://example.com/bakery_north/",
        "not a url",
        "",
    ],
)
def test_single_posts_reserved_paths_and_other_sites_are_not_bulk(url: str) -> None:
    assert media.classify_bulk_url(url) is None
    assert media.route_for(url) != "bulk"


def test_none_is_not_bulk() -> None:
    assert media.classify_bulk_url(None) is None


def test_one_identity_whatever_the_spelling() -> None:
    a = media.classify_bulk_url(f"{IG}/Bakery_North/?hl=en")
    b = media.classify_bulk_url("https://instagram.com/bakery_north")
    assert a is not None and b is not None and a.identity == b.identity
    saved = media.classify_bulk_url(f"{IG}/bakery_north/saved/")
    assert saved is not None and saved.identity != a.identity
    assert a.url == f"{IG}/Bakery_North/" and saved.url == f"{IG}/bakery_north/saved/"
    assert media.classify_bulk_url(TT_PROFILE).url == TT_PROFILE  # type: ignore[union-attr]


# -- slow mode config -------------------------------------------------------------
def _walk(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)


def test_bulk_config_has_the_4_to_10_second_request_sleep(tmp_path: Path) -> None:
    config = media.config_dict(bulk=True)
    assert config["extractor"]["instagram"]["sleep-request"] == [4.0, 10.0]
    assert config["extractor"]["tiktok"]["sleep-request"] == [4.0, 10.0]
    assert config["extractor"]["sleep-request"] == [4.0, 10.0]
    # nothing that raises concurrency
    banned = ("concurr", "thread", "parallel", "worker", "jobs", "connections")
    for key, _ in _walk(config):
        assert not any(word in str(key).lower() for word in banned), key
    # the plain config is unchanged: no sleep
    assert not any(key == "sleep-request" for key, _ in _walk(media.config_dict()))
    path = media.write_config(tmp_path / "bulk.json", bulk=True)
    assert json.loads(path.read_text())["extractor"]["instagram"]["sleep-request"] == [4.0, 10.0]
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_bulk_runs_use_the_bulk_config_only(bulk_harness) -> None:
    h = bulk_harness(posts=2)
    item = h.queue.add(PROFILE)
    h.run(item["id"])
    configs = {value_after(a, "--config-json") for a in h.calls()}
    assert configs == {str(h.queue._gallery_bulk_config)}
    saved = json.loads(h.queue._gallery_bulk_config.read_text())
    assert saved["extractor"]["instagram"]["sleep-request"] == [4.0, 10.0]
    # the ordinary media config is never the one a bulk run uses
    assert not h.queue._gallery_config.exists() or not any(
        value_after(a, "--config-json") == str(h.queue._gallery_config) for a in h.calls()
    )


# -- count probe -------------------------------------------------------------------
def test_count_probe_lists_without_downloading_and_respects_the_cap(bulk_harness) -> None:
    h = bulk_harness(posts=12, cap=5)
    info = h.queue.probe(PROFILE)
    assert len(h.probes()) == 1 and h.downloads() == []
    argv = h.probes()[0]
    assert "-s" in argv and "-j" in argv and "-D" not in argv
    assert value_after(argv, "--post-range") == "1-6"  # the run cap + 1
    assert argv[-1] == PROFILE
    assert info["bulk"] is True and info["cap"] == 5
    assert len(info["entries"]) == 6  # cap + 1: enough to say "there are more"
    assert info["entries"][0]["url"] == f"{IG}/p/CODE001/"
    assert info["entries"][0]["owner"] == "bakery_north"
    assert info["title"] == "Posts from @bakery_north"


def test_probe_never_returns_more_than_the_limit_even_if_gallery_dl_ignores_the_range(
    bulk_harness,
) -> None:
    h = bulk_harness(posts=12, ignore_range=True)
    listing = media.probe_bulk(
        PROFILE, str(h.queue._gallery_dl), config_path=h.data / "c.json", limit=4
    )
    assert len(listing.posts) == 4


def test_probe_failure_is_a_probe_error_with_plain_wording(bulk_harness) -> None:
    h = bulk_harness(posts=0)
    with pytest.raises(ProbeError) as caught:
        h.queue.probe(PROFILE)
    assert caught.value.info.code == "no_media"


def test_missing_gallery_dl_is_said_plainly(tmp_path: Path) -> None:
    history = History(tmp_path / "h.sqlite")
    queue = DownloadQueue(history, Archive(tmp_path / "a.txt"), tmp_path / "o", tmp_path / "t")
    try:
        with pytest.raises(ProbeError) as caught:
            queue.probe(PROFILE)
        assert caught.value.info.code == "gallery_dl_missing"
    finally:
        history.close()


# -- parsing --------------------------------------------------------------------------
def test_parse_bulk_groups_files_by_post_and_builds_links() -> None:
    def post(code: str, count: int) -> list:
        out: list = [[2, {"username": "u", "post_shortcode": code}]]
        for n in range(1, count + 1):
            out.append([3, f"https://cdn.example.invalid/{code}_{n}.jpg",
                        {"category": "instagram", "username": "u", "post_shortcode": code,
                         "media_id": f"{code}{n}", "num": n, "extension": "jpg",
                         "date": "2026-11-02 09:00:00", "description": "Fresh loaves\nmore"}])
        return out

    posts = media.parse_bulk(json.dumps(post("AAA", 3) + post("BBB", 1)), f"{IG}/u/")
    assert [p.id for p in posts] == ["AAA", "BBB"]
    assert posts[0].url == f"{IG}/p/AAA/" and len(posts[0].files) == 3
    assert posts[0].label == "2026-11-02 · Fresh loaves · 3 photos"
    again = media.BulkPost.from_entry(posts[0].to_entry())
    assert again == posts[0]


def test_parse_bulk_tiktok_posts() -> None:
    text = json.dumps([[3, "https://cdn.example.invalid/a.jpeg",
                        {"category": "tiktok", "id": "7300000000000000001", "num": 1,
                         "extension": "jpeg", "author": {"uniqueId": "dancer"}, "desc": "hi"}]])
    (post,) = media.parse_bulk(text, TT_PROFILE)
    assert post.url == "https://www.tiktok.com/@dancer/video/7300000000000000001"
    assert media.bulk_key(post.site, post.id) == "tiktok 7300000000000000001"


# -- queue: a whole run ------------------------------------------------------------------
def test_picked_posts_are_saved_one_at_a_time_per_owner(bulk_harness) -> None:
    h = bulk_harness(posts=8)
    info = h.queue.probe(PROFILE)
    chosen = info["entries"][2:5]  # the picker returned posts 3-5
    snap = h.queue.add_bulk(PROFILE, chosen)
    assert snap["bulk"] == {"kind": "profile", "site": "instagram", "label": "@bakery_north"}
    done = h.run(snap["id"])
    assert done["state"] == "done"
    assert h.downloaded_codes() == ["CODE003", "CODE004", "CODE005"]  # one process per post, in order
    assert sorted(p.name for p in (h.out / "bakery_north").iterdir()) == [
        "bakery_north CODE003 [9003] 1.jpg",
        "bakery_north CODE004 [9004] 1.jpg",
        "bakery_north CODE005 [9005] 1.jpg",
    ]
    assert (done["progress"]["files_done"], done["progress"]["files_total"]) == (3, 3)
    assert done["progress"]["percent"] == 100.0
    assert done["title"] == "Posts from @bakery_north"
    # nothing else was asked of gallery-dl beyond the single posts
    for argv in h.downloads():
        assert argv[-1].startswith(f"{IG}/p/")
        assert "--download-archive" in argv


def test_items_headline_counts_posts_not_files(bulk_harness) -> None:
    h = bulk_harness(posts=4)
    events: list[dict] = []
    h.queue.add_listener(events.append)
    snap = h.queue.add(PROFILE)
    h.run(snap["id"])
    counts = [
        (e["item"]["progress"]["files_done"], e["item"]["progress"]["files_total"])
        for e in events
        if e["type"] == "progress"
    ]
    assert counts and counts[-1] == (4, 4)
    assert all(total == 4 for _done, total in counts)  # never the per-file count of one post
    assert [c[0] for c in counts] == sorted(c[0] for c in counts)


def test_without_a_picker_the_run_lists_and_saves_the_newest_up_to_the_cap(bulk_harness) -> None:
    h = bulk_harness(posts=9, cap=3)
    snap = h.queue.add(PROFILE)
    done = h.run(snap["id"])
    assert done["state"] == "done"
    assert value_after(h.probes()[0], "--post-range") == "1-4"
    assert h.downloaded_codes() == ["CODE001", "CODE002", "CODE003"]
    assert done["progress"]["files_total"] == 3


def test_a_picked_list_longer_than_the_cap_is_cut_to_the_cap(bulk_harness) -> None:
    h = bulk_harness(posts=10, cap=50)
    info = h.queue.probe(PROFILE)
    h.queue.set_bulk_max_posts(4)
    snap = h.queue.add_bulk(PROFILE, info["entries"])
    done = h.run(snap["id"])
    assert done["progress"]["files_total"] == 4
    assert len(h.downloads()) == 4


def test_bulk_item_takes_one_slot_and_is_one_item(bulk_harness) -> None:
    h = bulk_harness(posts=5)
    first = h.queue.add(PROFILE)
    again = h.queue.add(f"{IG}/bakery_north?hl=en")
    assert again["id"] == first["id"] and len(h.queue.items()) == 1


def test_the_pause_between_posts_is_the_randomised_delay(tmp_path: Path, bulk_harness) -> None:
    h = bulk_harness(posts=3)
    asked: list[int] = []
    h.queue._bulk_delay = lambda: asked.append(1) or 0.0
    snap = h.queue.add(PROFILE)
    h.run(snap["id"])
    # listing first, then a pause before every post (the listing was a request too)
    assert len(asked) == 3


# -- a rate limit stops the run cleanly ----------------------------------------------------
@pytest.mark.parametrize(
    "limit_text",
    [
        "HTTP Error 429: Too Many Requests",
        "[instagram][error] Please wait a few minutes before you try again.",
        "ERROR: challenge_required",
    ],
)
def test_a_rate_limit_stops_the_run_keeps_posts_and_resume_skips_them(
    bulk_harness, limit_text: str
) -> None:
    h = bulk_harness(posts=7, limit_text=limit_text)
    h.limit_file.write_text("CODE004")
    snap = h.queue.add(PROFILE)
    stopped = h.run(snap["id"])
    assert stopped["state"] == "paused"
    assert stopped["note"] == "Instagram asked us to slow down. Saved 3 posts. Try again later."
    assert stopped["error"] is None
    assert (stopped["progress"]["files_done"], stopped["progress"]["files_total"]) == (3, 7)
    saved = sorted(p.name for p in (h.out / "bakery_north").iterdir())
    assert [n.split()[1] for n in saved] == ["CODE001", "CODE002", "CODE003"]
    assert h.downloaded_codes() == ["CODE001", "CODE002", "CODE003", "CODE004"]  # stopped at the first
    row = describe_row(stopped)
    assert row.note == stopped["note"] and row.meta.endswith("3 of 7 posts")
    # the history keeps the note too
    assert h.history.get(stopped["record_id"]).get("note") == stopped["note"]

    # later: the limit is gone; adding the same link again resumes it
    h.limit_file.unlink()
    again = h.queue.add(PROFILE)
    assert again["id"] == snap["id"]
    done = h.run(snap["id"])
    assert done["state"] == "done"
    assert h.downloaded_codes() == [
        "CODE001", "CODE002", "CODE003", "CODE004",  # first run
        "CODE004", "CODE005", "CODE006", "CODE007",  # saved posts were not requested again
    ]
    assert len(list((h.out / "bakery_north").iterdir())) == 7
    assert done["note"] is None


def test_the_resume_button_also_continues_after_a_stop(bulk_harness) -> None:
    h = bulk_harness(posts=4)
    h.limit_file.write_text("CODE003")
    snap = h.queue.add(PROFILE)
    assert h.run(snap["id"])["state"] == "paused"
    h.limit_file.unlink()
    assert h.queue.resume(snap["id"])
    done = h.run(snap["id"])
    assert done["state"] == "done" and h.downloaded_codes().count("CODE001") == 1


def test_a_rate_limit_while_listing_pauses_with_nothing_saved(tmp_path: Path) -> None:
    root = tmp_path / "rl"
    root.mkdir()
    script = root / "gdl"
    script.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "sys.stderr.write('HTTP Error 429: Too Many Requests\\n')\nsys.exit(1)\n"
    )
    script.chmod(0o755)
    history = History(root / "h.sqlite")
    queue = DownloadQueue(history, Archive(root / "a.txt"), root / "o", root / "t",
                          gallery_dl=str(script), bulk_delay=lambda: 0.0, sleep=lambda _s: None)
    try:
        snap = queue.add(PROFILE)
        queue.start()
        assert queue.wait_until_idle(15)
        found = queue.item(snap["id"])
        assert found["state"] == "paused"
        assert found["note"] == "Instagram asked us to slow down. Saved 0 posts. Try again later."
    finally:
        queue.stop(1.0)
        history.close()


def test_a_login_wall_before_anything_is_saved_is_a_plain_sign_in_error(tmp_path: Path) -> None:
    root = tmp_path / "lw"
    root.mkdir()
    script = root / "gdl"
    script.write_text(
        "#!/usr/bin/env python3\nimport sys\n"
        "sys.stderr.write('Redirected to login page\\n')\nsys.exit(1)\n"
    )
    script.chmod(0o755)
    history = History(root / "h.sqlite")
    queue = DownloadQueue(history, Archive(root / "a.txt"), root / "o", root / "t",
                          gallery_dl=str(script), bulk_delay=lambda: 0.0, sleep=lambda _s: None)
    try:
        snap = queue.add(f"{IG}/bakery_north/saved/")
        queue.start()
        assert queue.wait_until_idle(15)
        found = queue.item(snap["id"])
        assert found["state"] == "failed" and found["error"]["code"] == "login_required"
    finally:
        queue.stop(1.0)
        history.close()


def test_slow_down_text_table() -> None:
    for text in ("HTTP Error 429: Too Many Requests", "429 Too Many Requests",
                 "please wait a few minutes", "rate limit exceeded", "challenge_required"):
        assert errors.is_slow_down(text)
    for text in ("", None, "HTTP Error 404: Not Found", "saved /tmp/x/p429 1.jpg", "network is down"):
        assert not errors.is_slow_down(text)
    assert errors.bulk_stop_note("instagram", 12) == (
        "Instagram asked us to slow down. Saved 12 posts. Try again later.")
    assert errors.bulk_stop_note("tiktok", 1) == (
        "TikTok asked us to slow down. Saved 1 post. Try again later.")


def test_pause_and_cancel_keep_the_finished_posts(bulk_harness) -> None:
    h = bulk_harness(posts=6)
    seen: list[int] = []

    def slow_delay() -> float:
        seen.append(1)
        return 0.0 if len(seen) < 3 else 5.0  # the third post waits long enough to cancel

    h.queue._bulk_delay = slow_delay
    snap = h.queue.add(PROFILE)
    h.queue.start()
    deadline = time.monotonic() + 10
    while len(seen) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.2)
    assert h.queue.cancel(snap["id"])
    assert h.queue.wait_until_idle(10)
    found = h.queue.item(snap["id"])
    assert found["state"] == "cancelled"
    kept = sorted((h.out / "bakery_north").iterdir())
    assert len(kept) == 2  # the two posts finished before the cancel are still there
    assert all(p.read_text().startswith("data ") for p in kept)


def test_existing_files_are_never_overwritten(bulk_harness) -> None:
    h = bulk_harness(posts=2)
    owner = h.out / "bakery_north"
    owner.mkdir()
    mine = owner / "bakery_north CODE001 [9001] 1.jpg"
    mine.write_text("mine")
    snap = h.queue.add(PROFILE)
    h.run(snap["id"])
    assert mine.read_text() == "mine"


def test_signed_in_items_never_run_beside_a_bulk_save(bulk_harness) -> None:
    h = bulk_harness(posts=2)
    q = h.queue
    q.set_cookies("firefox", None)
    bulk = q.add(PROFILE)
    single = q.add(f"{IG}/p/CAbc123xyz/")
    with q._cond:
        q._items[single["id"]].owned = True
        assert q._next_queued() is None  # the bulk save waits for the running Instagram item
        q._items[single["id"]].owned = False
        q._items[bulk["id"]].owned = True
        q._items[bulk["id"]].state = "downloading"
        q._items[single["id"]].state = "queued"
        assert q._next_queued() is None  # and nothing signed-in starts beside the bulk save
        other = q.add("https://example.com/v/1")
        assert q._next_queued() is not None and q._next_queued().id == other["id"]


# -- settings -----------------------------------------------------------------------------
def test_cap_setting_clamps_to_1_200(tmp_path: Path) -> None:
    assert (BULK_DEFAULT_MAX_POSTS, BULK_MAX_POSTS_LIMIT) == (50, 200)
    for raw, expected in ((0, 1), (-5, 1), (1, 1), (75, 75), (200, 200), (201, 200),
                          (100000, 200), (12.9, 12), ("x", 50), (None, 50), (True, 50)):
        assert clamp_bulk_max(raw) == expected, raw
        assert st.Settings(bulk_max_posts=raw).bulk_max_posts == expected, raw  # type: ignore[arg-type]
    assert st.Settings().bulk_max_posts == 50 and st.Settings().bulk_warning_seen is False
    path = tmp_path / "s.json"
    st.save(st.Settings(bulk_max_posts=120, bulk_warning_seen=True), path)
    loaded = st.load(path)
    assert (loaded.bulk_max_posts, loaded.bulk_warning_seen) == (120, True)
    path.write_text(json.dumps({"bulk_max_posts": 9999, "bulk_warning_seen": "yes"}))
    loaded = st.load(path)
    assert (loaded.bulk_max_posts, loaded.bulk_warning_seen) == (200, False)


def test_settings_reach_the_queue(ui_queue) -> None:
    st.apply(st.Settings(bulk_max_posts=77), ui_queue)
    assert ui_queue.bulk_max_posts == 77
    ui_queue.set_bulk_max_posts(5000)
    assert ui_queue.bulk_max_posts == 200
    ui_queue.set_bulk_max_posts(0)
    assert ui_queue.bulk_max_posts == 1


def test_settings_page_has_the_cap_box_and_keeps_the_warning_flag(qapp, ui_queue, tmp_path) -> None:
    path = tmp_path / "s.json"
    page = SettingsPage(st.Settings(bulk_warning_seen=True), ui_queue, path,
                        version_fn=lambda: "1", detect_fn=lambda: [])
    try:
        assert page.bulk_spin.minimum() == 1 and page.bulk_spin.maximum() == 200
        assert page.bulk_spin.value() == 50
        assert page.bulk_spin.accessibleName() == "Most posts per bulk save"
        page.bulk_spin.setValue(80)
        assert ui_queue.bulk_max_posts == 80
        loaded = st.load(path)
        assert (loaded.bulk_max_posts, loaded.bulk_warning_seen) == (80, True)
    finally:
        page.deleteLater()


# -- the warning -----------------------------------------------------------------------------
@pytest.fixture
def window(qapp, ui_queue, tmp_path):
    win = MainWindow(ui_queue, settings_path=tmp_path / "s.json", version_fn=lambda: "1",
                     tray_factory=lambda w: None)
    yield win
    win.bridge.close()
    win.deleteLater()


def test_warning_is_shown_once_then_never_again(window, tmp_path, monkeypatch) -> None:
    shown: list[BulkWarningDialog] = []

    def run_warning(dialog) -> bool:
        shown.append(dialog)
        return True

    monkeypatch.setattr(window, "_run_warning", run_warning)
    assert window.settings.bulk_warning_seen is False
    assert window._confirm_bulk_start() is True
    assert len(shown) == 1 and shown[0].text_label.text() == BULK_WARNING_TEXT
    assert window.settings.bulk_warning_seen is True
    assert st.load(tmp_path / "s.json").bulk_warning_seen is True  # remembered on disk
    assert window._confirm_bulk_start() is True
    assert len(shown) == 1  # not again
    window.settings_page.bulk_spin.setValue(60)  # a later settings change keeps the flag
    assert st.load(tmp_path / "s.json").bulk_warning_seen is True


def test_cancelling_the_warning_queues_nothing_and_asks_again(window, monkeypatch) -> None:
    asked: list[int] = []
    monkeypatch.setattr(window, "_run_warning", lambda dialog: asked.append(1) or False)
    assert window._confirm_bulk_start() is False
    assert window.settings.bulk_warning_seen is False
    assert window._confirm_bulk_start() is False
    assert len(asked) == 2


def test_warning_text_and_buttons(qapp) -> None:
    assert BULK_WARNING_TEXT == (
        "Instagram may slow down or flag accounts that download a lot at once. "
        "Elisium saves one post at a time, slowly, and stops if Instagram asks it to slow down."
    )
    dialog = BulkWarningDialog()
    try:
        assert dialog.start_button.text() == "Start" and dialog.cancel_button.text() == "Cancel"
        assert dialog.start_button.isDefault()
        assert dialog.start_button.property("primary") is True
        assert dialog.cancel_button.property("quiet") is True
        for widget in (dialog, dialog.text_label, dialog.start_button, dialog.cancel_button):
            assert widget.accessibleName()
        assert dialog.text_label.accessibleDescription() == BULK_WARNING_TEXT
        dialog.start_button.click()
        assert dialog.result() == dialog.DialogCode.Accepted
    finally:
        dialog.deleteLater()


# -- the picker --------------------------------------------------------------------------------
def pump_until(predicate, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


@pytest.fixture
def picker(qapp, bulk_harness):
    made: list[PlaylistDialog] = []

    def open_picker(*, posts: int = 12, cap: int = 50, confirm=lambda: True):
        h = bulk_harness(posts=posts, cap=cap)
        dialog = PlaylistDialog(PROFILE, h.queue, h.queue.probe, confirm_start=confirm)
        made.append(dialog)
        dialog.show()
        assert pump_until(lambda: dialog.state in ("ready", "failed"))
        return h, dialog

    yield open_picker
    for dialog in made:
        dialog.reject()
        dialog.deleteLater()


def test_picker_preselects_the_newest_and_never_goes_past_the_cap(picker) -> None:
    h, dialog = picker(posts=12, cap=5)
    assert dialog.state == "ready" and dialog.bulk is not None
    assert dialog.list.count() == 5  # the 6th probed post only says "there are more"
    assert dialog.selected_count() == 5
    assert "more" in dialog.status_label.text()
    dialog.select_none()
    dialog.select_all()
    assert dialog.selected_count() == 5
    dialog.range_edit.setText("1-9")
    assert "past the end" in dialog.range_error.text() and "posts" in dialog.range_error.text()
    assert "video" not in dialog.range_error.text() and dialog.selected_count() == 5
    h.queue.set_bulk_max_posts(2)  # the setting was lowered while the picker was open
    dialog.range_edit.setText("1-4")
    assert "at a time" in dialog.range_error.text() and dialog.selected_count() == 5
    h.queue.set_bulk_max_posts(5)
    dialog.range_edit.clear()
    dialog.newest_spin.setValue(2)
    assert [e.index for e in dialog.selected_entries()] == [1, 2]
    assert dialog.newest_spin.maximum() == 5


def test_picker_preselects_50_by_default(picker) -> None:
    _h, dialog = picker(posts=60, cap=100)
    assert dialog.selected_count() == 50 and dialog.newest_spin.value() == 50


def test_picker_ranges_and_hand_ticking(picker) -> None:
    _h, dialog = picker(posts=12, cap=4)
    dialog.range_edit.setText("2-3")
    assert [e.index for e in dialog.selected_entries()] == [2, 3]
    dialog.select_none()
    for row in range(4):
        dialog.list.item(row).setCheckState(Qt_Checked())
    assert dialog.selected_count() == 4 and dialog.add_button.isEnabled()


def Qt_Checked():
    from PySide6.QtCore import Qt
    return Qt.CheckState.Checked


def test_picker_returns_the_chosen_posts_as_one_bulk_item(picker) -> None:
    h, dialog = picker(posts=8, cap=50)
    dialog.select_none()
    dialog.range_edit.setText("2,4-5")
    added: list = []
    dialog.itemsAdded.connect(added.append)
    dialog.add_button.click()
    (results,) = added
    (snapshot, is_new), = results
    assert is_new and snapshot["bulk"]["label"] == "@bakery_north"
    done = h.run(snapshot["id"])
    assert done["state"] == "done"
    assert h.downloaded_codes() == ["CODE002", "CODE004", "CODE005"]
    assert dialog.result() == dialog.DialogCode.Accepted


def test_cancelling_the_warning_keeps_the_picker_open_and_queues_nothing(picker) -> None:
    h, dialog = picker(posts=4, confirm=lambda: False)
    dialog.add_button.click()
    assert h.queue.items() == [] and dialog.result() != dialog.DialogCode.Accepted
    assert dialog.state == "ready"


def test_empty_account_says_so(qapp, bulk_harness) -> None:
    h = bulk_harness(posts=0)
    dialog = PlaylistDialog(PROFILE, h.queue, h.queue.probe)
    try:
        assert pump_until(lambda: dialog.state == "failed")
        assert dialog.retry_button.isVisibleTo(dialog)
    finally:
        dialog.reject()
        dialog.deleteLater()


def test_picker_accessible_names(picker) -> None:
    _h, dialog = picker(posts=3)
    assert dialog.accessibleName() == "Posts"
    for widget in (dialog.list, dialog.newest_spin, dialog.range_edit, dialog.add_button,
                   dialog.cancel_button, dialog.select_all_button, dialog.select_none_button,
                   dialog.count_label, dialog.title_label):
        assert widget.accessibleName(), widget
    assert dialog.list.accessibleName() == "Posts on the account"
    assert not dialog.quality_combo.isVisibleTo(dialog)  # posts have no quality choice
    # a plain playlist is untouched
    plain = PlaylistDialog("https://y.t/p", _h.queue,
                           lambda u: {"title": "T", "entries": [{"id": "a", "title": "One", "url": "https://y.t/a"}]})
    try:
        assert pump_until(lambda: plain.state == "ready")
        assert plain.bulk is None and plain.accessibleName() == "Playlist"
        assert not plain.newest_spin.isVisibleTo(plain) and plain.quality_combo.isVisibleTo(plain)
    finally:
        plain.reject()
        plain.deleteLater()


@pytest.mark.parametrize("scheme", ["night", "day"])
def test_bulk_dialogs_in_both_colour_schemes_nothing_below_12_px(qapp, picker, scheme: str) -> None:
    theme.apply(qapp, scheme)
    theme.set_base_size(qapp, 11.0)
    try:
        _h, dialog = picker(posts=4)
        warning = BulkWarningDialog()
        try:
            for root in (dialog, warning):
                for widget in [root, *root.findChildren(QWidget)]:
                    widget.ensurePolished()
                    if isinstance(widget, (QLabel, QAbstractButton)) and widget.text():
                        assert QFontInfo(widget.font()).pixelSize() >= 12, (
                            type(widget).__name__, widget.text())
                    sheet = widget.styleSheet().lower()
                    assert "gradient" not in sheet and "shadow" not in sheet and "glow" not in sheet
        finally:
            warning.deleteLater()
    finally:
        theme.apply(qapp, "night")


# -- the row ------------------------------------------------------------------------------------
def test_row_text_names_the_account_and_counts_posts() -> None:
    row = {
        "id": 1, "record_id": 1, "url": PROFILE, "identity": "x", "video_key": None,
        "state": "downloading", "title": "Posts from @bakery_north", "file_path": None,
        "note": None, "thumbnail": None, "format_label": None, "wait_hint": None,
        "attempts": 0, "error": None,
        "bulk": {"kind": "profile", "site": "instagram", "label": "@bakery_north"},
        "progress": {"stage": "downloading", "downloaded_bytes": None, "total_bytes": None,
                     "speed": None, "eta": None, "percent": 24.0, "files_done": 12,
                     "files_total": 50},
    }
    assert describe_row(row).meta == "Instagram · @bakery_north · 12 of 50 posts"
    row["state"] = "done"
    assert describe_row(row).meta == "Instagram · @bakery_north · 50 posts"
    row["state"], row["note"] = "paused", "Instagram asked us to slow down. Saved 12 posts. Try again later."
    assert describe_row(row).note.startswith("Instagram asked us to slow down")
    from elisium_downloader.ui.model import DownloadModel
    assert "12 of 50 posts" in DownloadModel.spoken(row)
    assert "slow down" in DownloadModel.spoken(row)


def test_existing_single_post_rules_still_hold(bulk_harness) -> None:
    h = bulk_harness(posts=1)
    for url, route in ((f"{IG}/p/CAbc123xyz/", "ytdlp_then_media"), (f"{IG}/reel/CAbc123xyz/", "ytdlp"),
                       (f"{IG}/stories/bakery_north/", "media"),
                       ("https://www.tiktok.com/@dancer/photo/7300000000000000001", "media")):
        assert media.route_for(url) == route
        snap = h.queue.add(url)
        assert snap["bulk"] is None
