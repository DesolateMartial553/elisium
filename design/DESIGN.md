# Elisium design: "Night shelf"

Owner's pick on 2026-11-22, for **both** the desktop and the phone. It is the only design: both apps are built on it.
Mockup: https://claude.ai/artifact/7Y3QxXNMDL9PiesAsqsZB1 (desktop) and https://claude.ai/artifact/As1YVj8NtnAJdqVkQFKR3Q (phone).
Colours and sizes come only from `design/tokens.json`. `python3 design/contrast_check.py` must stay ALL PASS.

## The idea
Elisium is a shelf of your media at night. Your thumbnails do the decorating. The interface is true black (or plain
light grey by day), with no borders, glows or shadows. Colour goes on one thing only: the progress of a download.

## The one move (keep it intact)
- Elevation by lightness alone: `ground` < `surface` < `raised`. No borders on cards, no shadows on anything at rest.
  The only shadow allowed is on something truly floating (a menu, a dialog).
- The one hue (`hue`, sky blue at night, deep blue by day) is used **only** for progress bars, the selected count card's
  outline, and the focus ring. Never on buttons, tabs, navigation, headings or icons.
- The primary action is made primary by **inversion**: a white pill with black text at night, a black pill with white text by day.
- The active navigation item is shown only by its label going from `faint` to `text`, with no pill, bar or tint behind it.

## Banned (the reasons a media app reads as generated)
Gradients of any kind, including text and progress. Glows and blurred edges. Violet or indigo. A coloured pill behind the
active nav item. Icons in tinted squares. Emoji. Tiny uppercase letter-spaced labels. Monospace outside code.
Anything not listed in the tokens.

## Type
- Hanken Grotesk (SIL Open Font License, Google Fonts), bundled in both apps with its OFL text next to the font files:
  desktop `desktop/elisium_downloader/ui/fonts/`, Android `android/app/src/main/res/font/`. Static weights 400, 600, 700.
- Sizes: screen title 20, row title 15/600, big figure (percent) 24/600, body 14, meta 13, small 12. Nothing smaller than 12.
- Every number that updates (percent, MB/s, size, time left, counts) uses tabular figures.
- Sentence case everywhere. Must stay usable at 200% font scale.

## Screens and components
- **Top bar (desktop, no sidebar):** 48 px, on the ground colour, no border. Left: the mark and "Elisium" (18/700),
  then the text links Downloads, History, Settings (14/600, `faint`; active `text`). Right: the link field (pill, 36 px,
  `surface` fill) and the Download pill (inverted). A 1 px `raised` rule appears under it only once content scrolls under it.
- **Phone top bar:** 56 px with the mark, "Elisium" and a menu button (History, Settings live in the menu sheet).
  Below it: the link field and the Download pill, 44 px tall.
- **Count cards = filters:** All, Downloading, Waiting (queued + paused), Failed, Done. Desktop: 5 equal cards, 61 px,
  `surface`, 13 px label over a 16/600 count; the selected one has a 1.5 px `hue` outline. Phone: a row of 36 px chips you
  swipe sideways. Zero prints as 0. These are the filters for the list below.
- **Download row:** 80 px, `surface`, radius 16, 8 px apart. Thumbnail 112 x 63 (phone 104 x 59), radius 10, the item's
  real thumbnail (placeholder: a `raised` block with the site name, never an icon in a box). Title 15/600 one line
  (phone: two lines). Meta line 13 `faint`: "Site · format · size", or for multi-file posts "Instagram · 6 photos + song · 3 of 7 files".
  A 4 px progress bar in `hue` on a `track`. Right column: percent 24/600 over "4.2 MB/s · 1 min 37 s left" 12 `muted`.
- **Row states (text always says the state; colour never carries it alone):**
  Downloading: hue bar + percent + speed/time left. Paused: bar in `faint`, "Paused · 136.0 MB to go".
  Waiting: "Waiting" in `faint` + size or "Starts next". Failed: the plain reason in `negative` and one inverted pill for the
  fix ("Sign in", "Retry"). Done: "Done" in `positive` + "Open · Show in folder".
- **History and Settings:** same ground/surface/raised steps and the same row anatomy; settings are grouped lists on `surface`
  with one setting per row. Approved by the owner 2026-11-22: https://claude.ai/artifact/KpTfdZAD13xd6qPYApJM8F (History: grouped by day, search, site filter, Open / Show in folder / Download again; Settings: Downloads, Photos and music, Accounts, Appearance, About).
- **Mark:** three stacked rounded bars getting shorter (a queue), the last one in `hue`. Launcher icon: the same mark on a black square.

## Motion
120-200 ms, ease-out. Progress fills ease; a new row fades in with a 6 px rise; count changes cross-fade. No breathing, pulsing
or looping. Respect reduced motion (desktop "Reduce motion" setting, Android remove-animations): instant changes.

## Accessibility (unchanged, non-negotiable)
Keep every accessible name, role, live region, keyboard shortcut and TalkBack/Orca text ("N percent"). The focus ring is a
2 px `focus` outline with 2 px offset and is never removed. 44 px minimum touch target on the phone.

## Copy voice
Short, plain, specific. "Paste a link from YouTube, Instagram, TikTok…", "Instagram sign-in has expired" + "Sign in".
Error wording stays exactly as in `core-spec/SPEC.md`.
