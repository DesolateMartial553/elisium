"""Command line entry point: start the GUI, or hand links to the running one."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from typing import Any, TextIO

from . import __version__

__all__ = ["main"]

CHUNK = 50  # links per message (the running instance accepts at most 50)

Launcher = Callable[[list[str], Callable[[dict[str, int], bool], None] | None], int]
Sender = Callable[[list[str]], "dict[str, Any] | None"]


def _links(count: int) -> str:
    return f"{count} link" if count == 1 else f"{count} links"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elisium",
        description="Elisium video downloader. With no arguments it opens the window.",
        epilog='Also accepts a link such as "elisium://add?url=<percent-encoded link>".',
    )
    parser.add_argument("--version", action="version", version=f"elisium {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="{add}")
    add = sub.add_parser("add", help="queue links in the running Elisium (starts it if needed)")
    add.add_argument("urls", nargs="+", metavar="URL",
                     help="http(s) links, or - to read them from standard input")
    return parser


def _default_launcher(urls: list[str], on_ready: Any) -> int:
    from .ui.app import run

    return run(["elisium"], initial_urls=urls, on_ready=on_ready)


def _default_sender(urls: list[str]) -> dict[str, Any] | None:
    from .ui.ipc import send_add

    return send_add(urls)


def _collect(args: Sequence[str], stdin: TextIO) -> tuple[list[str], int]:
    """Valid links (and ignored count) from add-arguments or elisium:// links."""
    from .ui.ipc import links_from_elisium_uri, split_links

    links: list[str] = []
    ignored = 0
    for arg in args:
        if arg == "-":
            text = stdin.read()
        elif arg[:9].lower() == "elisium:/":
            found, bad = links_from_elisium_uri(arg)
            links += found
            ignored += bad
            continue
        else:
            text = arg
        found, bad = split_links(text)
        links += found
        ignored += bad
    seen: set[str] = set()
    unique = [u for u in links if not (u in seen or seen.add(u))]
    return unique, ignored


def main(
    argv: Sequence[str] | None = None,
    *,
    launcher: Launcher | None = None,
    sender: Sender | None = None,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    launch = launcher or _default_launcher
    send = sender or _default_sender

    if not args:
        return launch([], None)

    if args[0][:9].lower() == "elisium:/":
        # The desktop environment calls the handler with the link(s) only.
        if not all(a[:9].lower() == "elisium:/" for a in args):
            _parser().print_usage(err)
            return 2
        urls_args = args
    else:
        try:
            ns = _parser().parse_args(args)
        except SystemExit as exit_:
            code = exit_.code
            return code if isinstance(code, int) else 2
        urls_args = ns.urls
    links, ignored = _collect(urls_args, stdin or sys.stdin)
    if not links:
        print("No valid link found (only http and https links are accepted)", file=err)
        return 1

    sent_ignored = 0
    reply: dict[str, Any] | None = None
    for start in range(0, len(links), CHUNK):
        reply = send(links[start:start + CHUNK])
        if reply is None:
            break
        if not reply.get("ok"):
            print(f"Elisium did not accept the links: {reply.get('error', 'no reply')}", file=err)
            return 1
        sent_ignored += int(reply.get("ignored", 0))
    suffix = f" ({ignored + sent_ignored} ignored)" if ignored + sent_ignored else ""
    if reply is not None:
        print(f"Sent {_links(len(links))} to Elisium{suffix}", file=out)
        return 0

    # Nothing is running: start the GUI and add everything once it is up.
    def report(counts: dict[str, int], started: bool) -> None:
        if started:
            n = counts.get("added", 0)
            print(f"Started Elisium and added {_links(n)}{suffix}", file=out, flush=True)
        else:  # another instance won the start-up race
            print(f"Sent {_links(len(links))} to Elisium{suffix}", file=out, flush=True)

    return launch(links, report)
