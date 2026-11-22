"""Check Night shelf token pairs against WCAG 2.2. Usage: python3 design/contrast_check.py"""
import json
import sys
from pathlib import Path


def lum(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a: str, b: str) -> float:
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# (foreground, background, minimum): 4.5 for text, 3.0 for marks and focus rings.
PAIRS = [
    ("text", "ground", 4.5), ("text", "surface", 4.5), ("text", "raised", 4.5),
    ("muted", "ground", 4.5), ("muted", "surface", 4.5), ("muted", "raised", 4.5),
    ("faint", "ground", 4.5), ("faint", "surface", 4.5),
    ("negative", "surface", 4.5), ("positive", "surface", 4.5), ("warning", "surface", 4.5),
    ("onPrimary", "primary", 4.5),
    ("hue", "surface", 3.0), ("hue", "track", 3.0), ("focus", "ground", 3.0), ("focus", "surface", 3.0),
]

tokens = json.loads((Path(__file__).parent / "tokens.json").read_text())
failed = False
for theme in ("dark", "light"):
    t = tokens[theme]
    for fg, bg, need in PAIRS:
        r = ratio(t[fg], t[bg])
        ok = r >= need
        failed |= not ok
        print(f"{theme:5} {fg:>9} on {bg:<8} {r:5.2f} (need {need}) {'PASS' if ok else 'FAIL'}")
print("ALL PASS" if not failed else "SOME FAIL")
sys.exit(1 if failed else 0)
