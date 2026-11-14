"""``elisium`` command line: add, stdin, elisium:// links, exit codes (no window opens)."""

from __future__ import annotations

import io
from urllib.parse import quote

import pytest

from elisium_downloader import __version__, cli


class Env:
    def __init__(self, running: bool = True, reply=None) -> None:
        self.running = running
        self.sent: list[list[str]] = []
        self.launched: list[list[str]] = []
        self.reply = reply
        self.out = io.StringIO()
        self.err = io.StringIO()

    def sender(self, urls):
        if not self.running:
            return None
        self.sent.append(list(urls))
        return self.reply or {"ok": True, "added": len(urls), "known": 0, "ignored": 0}

    def launcher(self, urls, on_ready):
        self.launched.append(list(urls))
        if on_ready is not None:
            on_ready({"added": len(urls), "known": 0, "ignored": 0}, True)
        return 0

    def run(self, argv, stdin=""):
        code = cli.main(argv, launcher=self.launcher, sender=self.sender,
                        stdin=io.StringIO(stdin), stdout=self.out, stderr=self.err)
        return code


def test_no_arguments_launches_the_gui() -> None:
    env = Env(running=True)
    assert env.run([]) == 0
    assert env.launched == [[]] and env.sent == []  # run() itself handles "already running"


def test_add_sends_to_running_instance() -> None:
    env = Env()
    assert env.run(["add", "https://a.com/1", "https://b.com/2"]) == 0
    assert env.sent == [["https://a.com/1", "https://b.com/2"]] and env.launched == []
    assert env.out.getvalue() == "Sent 2 links to Elisium\n"


def test_add_single_link_wording() -> None:
    env = Env()
    env.run(["add", "https://a.com/1"])
    assert env.out.getvalue() == "Sent 1 link to Elisium\n"


def test_add_without_running_instance_starts_gui() -> None:
    env = Env(running=False)
    assert env.run(["add", "https://a.com/1"]) == 0
    assert env.launched == [["https://a.com/1"]]
    assert env.out.getvalue() == "Started Elisium and added 1 link\n"


def test_add_from_stdin_many_per_line() -> None:
    env = Env()
    text = "https://a.com/1 https://b.com/2\n\nhttps://c.com/3\nnope\n"
    assert env.run(["add", "-"], stdin=text) == 0
    assert env.sent == [["https://a.com/1", "https://b.com/2", "https://c.com/3"]]
    assert env.out.getvalue() == "Sent 3 links to Elisium (1 ignored)\n"


def test_duplicate_links_are_sent_once() -> None:
    env = Env()
    env.run(["add", "https://a.com/1", "https://a.com/1"])
    assert env.sent == [["https://a.com/1"]]


def test_many_links_are_chunked_to_the_message_limit() -> None:
    env = Env()
    links = [f"https://a.com/{i}" for i in range(120)]
    assert env.run(["add", *links]) == 0
    assert [len(s) for s in env.sent] == [50, 50, 20]
    assert env.out.getvalue() == "Sent 120 links to Elisium\n"


def test_no_valid_link_exits_1() -> None:
    env = Env()
    assert env.run(["add", "file:///etc/passwd", "javascript:1"]) == 1
    assert env.sent == [] and env.launched == [] and env.out.getvalue() == ""
    assert "No valid link" in env.err.getvalue()
    assert env.run(["add", "-"], stdin="   \n") == 1


def test_usage_errors_exit_2() -> None:
    for argv in (["add"], ["frobnicate"], ["--nope"], ["https://a.com/1"]):
        env = Env()
        assert env.run(argv) == 2, argv
        assert env.sent == [] and env.launched == []


def test_version_and_help(capsys) -> None:
    env = Env()
    assert env.run(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"elisium {__version__}"
    assert env.run(["--help"]) == 0
    assert "elisium://add" in capsys.readouterr().out


def test_elisium_uri_same_as_add() -> None:
    env = Env()
    uri = "elisium://add?url=" + quote("https://example.com/b", safe="")
    assert env.run([uri]) == 0
    assert env.sent == [["https://example.com/b"]]
    assert env.out.getvalue() == "Sent 1 link to Elisium\n"


def test_elisium_uri_repeated_and_urls_parameter() -> None:
    env = Env()
    uri = ("elisium://add?url=https%3A%2F%2Fa.com%2F1&url=https%3A%2F%2Fb.com%2F2&urls="
           + quote("https://c.com/3 https://d.com/4", safe=""))
    assert env.run([uri]) == 0
    assert env.sent == [["https://a.com/1", "https://b.com/2", "https://c.com/3", "https://d.com/4"]]


def test_elisium_uri_with_bad_content_exits_1_and_never_sends() -> None:
    env = Env()
    for uri in ("elisium://add?url=file%3A%2F%2F%2Fetc%2Fpasswd", "elisium://add",
                "elisium://settings?url=https%3A%2F%2Fa.com", "elisium://add?format=x"):
        assert env.run([uri]) == 1, uri
    assert env.sent == [] and env.launched == []


def test_elisium_uri_without_instance_starts_gui_with_default_preset_only() -> None:
    env = Env(running=False)
    uri = "elisium://add?url=https%3A%2F%2Fa.com%2F1&format=bestaudio&output=%2Ftmp"
    assert env.run([uri]) == 0
    assert env.launched == [["https://a.com/1"]]  # nothing but links reaches the launcher


def test_mixed_uri_and_other_arguments_is_a_usage_error() -> None:
    env = Env()
    assert env.run(["elisium://add?url=https%3A%2F%2Fa.com%2F1", "add", "https://b.com"]) == 2


def test_refusal_from_running_instance_exits_1() -> None:
    env = Env(reply={"ok": False, "error": "too many urls"})
    assert env.run(["add", "https://a.com/1"]) == 1
    assert "too many urls" in env.err.getvalue()


def test_start_race_loser_reports_sent() -> None:
    env = Env(running=False)

    def loser(urls, on_ready):
        on_ready({"added": 1}, False)
        return 0

    code = cli.main(["add", "https://a.com/1"], launcher=loser, sender=env.sender,
                    stdout=env.out, stderr=env.err)
    assert code == 0 and env.out.getvalue() == "Sent 1 link to Elisium\n"
