"""Phase 12A download-speed benchmark (desktop). Needs the network; NOT part of pytest.

Runs the app's real flow (runner.probe, then runner.build_command) per URL under several
configs, each run in a fresh temp folder with a fresh archive, so nothing is skipped or
resumed and the real ~/Downloads/Elisium and archive are never touched. Configs are
alternated round by round so CDN caching does not favour one of them.

Usage:
  python3 tools/bench.py [--rounds 2] [--configs base,once,n4,once_n4] [--format 720p] URL [URL ...]

Prints one markdown table: per URL and config, the median of
  start  = Add -> first progress line (includes the probe),
  xfer   = first progress line -> transfer finished,
  post   = transfer finished -> process exit (merge/convert/move),
  total, MB downloaded, MB/s over the transfer, failures.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from elisium_downloader.engine import presets, runner  # noqa: E402

CONFIGS = {
    # today's app: probe, then a download that extracts the page again
    "base": {"once": False, "extra": []},
    # extract once: reuse the probe's info JSON
    "once": {"once": True, "extra": []},
    # parallel fragments (only matters for DASH/HLS formats)
    "n4": {"once": False, "extra": ["-N", "4"]},
    "once_n4": {"once": True, "extra": ["-N", "4"]},
}


def fmt_selector(preset_id: str) -> tuple[str, tuple[str, ...]]:
    if preset_id not in presets.PRESETS:
        raise SystemExit(f"unknown preset {preset_id}; choose from {', '.join(presets.PRESETS)}")
    p = presets.PRESETS[preset_id]
    return p.format_selector, tuple(p.extra_args)


def one_run(url: str, cfg: dict, fmt: str, fmt_extra: tuple[str, ...]) -> dict:
    with tempfile.TemporaryDirectory(prefix="elisium-bench-") as tmp:
        t = Path(tmp)
        (t / "out").mkdir()
        (t / "tmp").mkdir()
        t0 = time.monotonic()
        try:
            info = runner.probe(url, timeout=120)
        except runner.ProbeError as exc:
            return {"fail": f"probe: {exc}"}
        t_probe = time.monotonic()
        extra = list(fmt_extra) + list(cfg["extra"])
        opts = runner.DownloadOptions(
            url=url, output_dir=t / "out", temp_dir=t / "tmp", archive_path=t / "archive.txt",
            format_selector=fmt, extra_args=extra,
        )
        argv = runner.build_command(opts)
        if cfg["once"]:
            info_path = t / "info.json"
            info_path.write_text(json.dumps(info))
            argv = argv[:-1] + ["--load-info-json", str(info_path)]  # drop the URL
        first = done = None
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        tail: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            now = time.monotonic()
            ev = runner.parse_progress_line(line.rstrip("\n"))
            if ev is not None and first is None:
                first = now
            if line.startswith("postprocess:") or "[Merger]" in line or "[ExtractAudio]" in line:
                done = done or now
            tail = (tail + [line.rstrip()])[-5:]
        rc = proc.wait()
        end = time.monotonic()
        files = [p for p in (t / "out").rglob("*") if p.is_file()]
        if rc != 0 or not files:
            return {"fail": f"rc={rc}: {' | '.join(tail)[-300:]}"}
        size_mb = sum(p.stat().st_size for p in files) / 1e6
        first = first or t_probe
        done = done or end
        xfer = max(done - first, 1e-3)
        return {
            "probe": t_probe - t0, "start": first - t0, "xfer": done - first, "post": end - done,
            "total": end - t0, "mb": size_mb, "mbps": size_mb / xfer,
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--configs", default="base,once,n4,once_n4")
    ap.add_argument("--format", default="720p", help="preset id from presets.py")
    a = ap.parse_args()
    fmt, fmt_extra = fmt_selector(a.format)
    names = a.configs.split(",")
    results: dict[tuple[str, str], list[dict]] = {}
    for r in range(a.rounds):
        order = names if r % 2 == 0 else list(reversed(names))
        for url in a.urls:
            for name in order:
                res = one_run(url, CONFIGS[name], fmt, fmt_extra)
                results.setdefault((url, name), []).append(res)
                print(f"round {r + 1} {name:8} {url[:60]} -> "
                      + (res["fail"] if "fail" in res else f"{res['total']:.1f}s {res['mb']:.1f}MB"),
                      file=sys.stderr, flush=True)
    med = lambda rs, k: statistics.median(x[k] for x in rs) if rs else float("nan")  # noqa: E731
    print(f"\nFormat preset: {a.format}; rounds: {a.rounds}; medians.\n")
    print("| URL | config | start s | (probe s) | transfer s | post s | total s | MB | MB/s | failures |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for (url, name), rs in results.items():
        ok = [x for x in rs if "fail" not in x]
        fails = len(rs) - len(ok)
        if not ok:
            print(f"| {url} | {name} | - | - | - | - | - | - | - | {fails} |")
            continue
        print(f"| {url} | {name} | {med(ok,'start'):.1f} | {med(ok,'probe'):.1f} | {med(ok,'xfer'):.1f} | "
              f"{med(ok,'post'):.1f} | {med(ok,'total'):.1f} | {med(ok,'mb'):.1f} | {med(ok,'mbps'):.2f} | {fails} |")


if __name__ == "__main__":
    main()
