# Elisium design: "Afterglow"

One look for both apps. Source of truth for colour and sizes: `design/tokens.json` (checked by `python3 design/contrast_check.py`, which must stay ALL PASS). Never invent new colours; use tokens.

## Idea
Elisium means a place of calm and light. The app is a quiet ink-violet night with one luminous accent: a horizon **glow** that runs violet -> rose -> amber (`glowA` -> `glowB` -> `glowC`). Everything else is soft, rounded and low-contrast-in-decoration, high-contrast-in-text. Beauty comes from restraint plus ONE glowing signature, not from many effects.

## Themes
- **Nightfall** (`dark`) is the identity and the default.
- **Daybreak** (`light`) is the same layout on a pale lilac-white ground.
- Follow the system light/dark setting; fall back to Nightfall. The user may force one in Settings (System / Night / Day).
- Android: do NOT use Material You dynamic colour by default (it would erase the identity).

## Signature elements (these make it "uniquely Elisium")
1. **Glow progress**: download progress is a thick rounded bar filled with the glow gradient, with a soft glowing leading edge (a blurred brighter cap). Paused = muted gradient (no glow). Done = solid `success`. Failed = `error`. Never rely on colour alone: state text always shown.
2. **Horizon header**: the top of each main screen carries a faint glow band (the gradient at ~12-18% opacity fading to the background) behind the wordmark. The wordmark "Elisium" is set large with a gradient fill (use solid `text` colour as fallback where gradient text is not supported).
3. **Raised cards**: queue and history rows are rounded cards (`raised` on `surface`, radius `medium`) with a 1px `outline` border and generous padding, instead of dense table gridlines. One selected/active card gets a 1px glow-gradient border.
4. **State chips**: small rounded pills with an icon + word (Queued, Downloading, Merging, Done, Failed, Paused), tinted from the semantic tokens.
5. **Empty state**: a large soft glowing glyph (the app icon's arrow) with one warm sentence; no clip-art.
6. **Icon**: arrow-into-tray glyph, but drawn with the glow gradient on an ink-violet rounded square with a faint horizon line. Update both launcher icons to match.

## Type
- Sans: Inter (bundled on Android; on desktop use "Inter" if installed, else the system UI font). Wordmark and screen titles: weight 700-800, slightly tight tracking. Body 400-500. Numbers (speed, size, ETA) use tabular figures where available.
- Sizes: title 28, section 18, body 15-16, caption 13. Never below 13. Must stay usable at 200% font scale.

## Shape and space
Radii small 10 / medium 16 / large 24. 4-point spacing scale from tokens. Min touch/click target 44-48. Focus ring: 2px `accent` outline with 2px offset, always visible for keyboard users (never removed).

## Motion
`fast` 120 / `base` 220 / `slow` 420 ms, ease-out. Used for: card enter (fade + 8px rise), progress fill easing, tab/page cross-fade, chip colour change, a slow breathing of the glow edge while downloading. **Respect reduced motion** (Android `Settings.Global.ANIMATOR_DURATION_SCALE == 0` / "remove animations"; desktop: a Settings switch "Reduce motion" plus honour `QT` no-animation env if present): then no breathing, no rises, instant changes. Motion never carries meaning on its own.

## Accessibility (non-negotiable)
Contrast per `contrast_check.py`. Keep every existing accessible name, role, live region and keyboard shortcut from the current apps; the redesign changes looks, not semantics. Do not hide information in hover-only states. Screen-reader text for the glow progress stays "N percent".

## Copy voice
Warm, short, plain. "Paste a link to begin" not "No items". Errors keep the existing plain-language messages.
