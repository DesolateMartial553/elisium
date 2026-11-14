"""Check Afterglow token pairs against WCAG 2.2 contrast. Usage: python3 design/contrast_check.py"""

import json
import sys
from pathlib import Path


def lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (foreground, background, minimum): 4.5 for text, 3.0 for UI parts and large text
PAIRS = [
    ("text", "bg", 4.5), ("text", "surface", 4.5), ("text", "raised", 4.5),
    ("muted", "bg", 4.5), ("muted", "surface", 4.5), ("muted", "raised", 4.5),
    ("accent", "bg", 4.5), ("accent", "surface", 4.5), ("accent", "raised", 4.5),
    ("onAccent", "accent", 4.5),
    ("success", "surface", 4.5), ("error", "surface", 4.5), ("warning", "surface", 4.5),
    ("outlineStrong", "bg", 3.0), ("outlineStrong", "surface", 3.0), ("outlineStrong", "raised", 3.0),
    ("glowA", "bg", 3.0), ("glowB", "bg", 3.0), ("glowC", "bg", 3.0),
]

tokens = json.loads((Path(__file__).parent / "tokens.json").read_text())
failed = 0
for mode in ("dark", "light"):
    t = tokens[mode]
    for fg, bg, need in PAIRS:
        got = ratio(t[fg], t[bg])
        ok = got >= need
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {mode:5} {fg:8} on {bg:8} {got:5.2f} (need {need})")
print("FAILED" if failed else "ALL PASS", failed)
sys.exit(1 if failed else 0)
