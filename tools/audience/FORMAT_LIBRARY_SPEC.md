# Audience Format Library — Spec

**Status:** SPEC ONLY (Brian's order, 2026-11-18: "spec all of this"). Nothing in this
document is built yet. The build starts on Brian's go.
**Home when built:** `successbrian-os/tools/audience/` on alpha, beside `meme_template.py`.
**Source of the machinery:** the AI Crossover build of 2026-11-18 — the rail format master
(`render_ai_theme_v13.py`) and the graph driver (`render_crossover_graph.py`), currently
living only in the Muse-side working folder
`~/workspace/builds/ai-meme-gemini-muse-theme/`. This spec is the migration path that moves
that machinery into Brian's ecosystem, per his ruling that builds belong in SuccessBrian OS,
with Muse-side storage interim only.

## The problem this solves

The canonical `tools/audience/meme_template.py` on alpha (42,765 bytes) still renders the
PRE-RAIL layout: `render_meme(content)`, `headline_3d`, `holo_pill`, `kicker_ai`, `footer`,
`spencer_badge`, `photo_card`, backdrop and icon helpers. The format Brian approved on
2026-11-18 — full-height left rail + chart card — exists only in one-off drivers on the
Muse side. Every future template (AI, health, crypto, political) would either re-derive
that machinery by hand or go without it. Brian's ruling governs: NEVER CREATE NEW — USE MY
THEMES. The library is where the theme machinery lives; this spec moves the new machinery
into it, once, for all themes.

## Governing principles

1. **Content stays a dict; machinery moves to the library.** A driver script per post is
   fine (Brian's standing pattern). A driver that re-implements drawing machinery is not —
   that machinery belongs in the library after its first proven use.
2. **No theme's approved look changes.** The crossover render of 2026-11-18 (1080×1080,
   approved by Brian 08:55 CST) is the reference output. Library extraction must reproduce
   it, not redesign it.
3. **Delivery is 1080 native, never upscaled** (Brian's delivery ruling, 2026-11-18: the
   2160 exports glitched his client; native 1080 ~500 KB loads clean). The library enforces
   this at save time (Module 4).
4. **Graph/chart text is black** (Brian, 2026-11-18); lines, bands and legend swatches keep
   their colors. Era/annotation blocks may use a dark slate.

---

## Module 1 — `audience_chart.py`: the chart module

**What exists today:** `graph(y)`, a ~130-line closure inside the crossover driver's
`main()`. It is already data-shaped: series are fraction lists smoothed by `_smooth()`
(Catmull-Rom, 20 subdivisions), mapped by `_yf(fr)`; the snapshot is a hand-looped dashed
line; the band, era tint, star, legend (`_legend(off, swatch, l1, l2, dashed)`) and the
under-axis strip are all computed from a handful of constants.

**API:**

```python
draw_chart(img, box, spec) -> int   # returns y below the card
```

`box = (x0, y, x1, height)` — the crossover reference is `(RAIL_W+34, y, W-30, 310)`.

**The spec dict:**

| Key | Meaning | Crossover reference value |
|---|---|---|
| `x_labels` | Axis labels, evenly spaced | `["2026"…"2033"]` |
| `series` | List of series dicts (below) | 3 lines + snapshot |
| `band` | `{from: 2/7, to: 3/7, color, alpha, label}` — highlighted span | gold, "RANGE OF CONVERGENCE" |
| `era` | `{from: 5/7, color, alpha}` — faint tint span inside the plot | slate, 2031–2033 |
| `star` | `{series: 0, index: 2}` — gold star on that data point | teal × snapshot crossing, 2028 |
| `strip` | Under-axis timeline (below) | arrow + era panel |
| `legend` | `{position: "left", entries: "auto"}` from series | 4 entries, offsets 16/62/108/154 |

**Series dict:** `{name, color, values, scale, dashed: bool, width, labels}` where

- `values` are REAL numbers, not fractions — the module maps them through `scale`.
- `scale = {min, max}` per series, so one plot can carry two measures the way the crossover
  does (intelligence 55–95 and cost $0–20K share pixels, each with its own mapping).
- `labels` = per-point optional `{index, text, place: above|below|left|right}` — the
  placement field exists because of the 2026-11-18 collision fix (the "77" label had to move
  under its dot when the line struck through it).
- A series with a single repeated value + `dashed: true` renders the frozen snapshot line.

**Strip spec:** `{arrow: {from, to, color, label_lines: [..]}, era_panel: {from, to,
heading, lines: [..]}}` — one continuous baseline; the arrow ends exactly where the shaded
era panel begins (crossover: arrow 2028→2031, panel 2031→2033, heading and body in matched
fonts, dark slate `#3d5a78`).

**Fixed behaviors (not options):** Catmull-Rom smoothing (20 subdivisions); year gridlines
faint `(226,231,241)`; baseline axis `mt.FAINT`; card = white rounded rect, outline
`(205,214,228)`, holo strip across the top (reuses `mt.holo_pill`); all text INK/black
except era-panel slate.

**Acceptance:** (a) the crossover chart reproduced from a spec dict alone, visually
matching the approved 2026-11-18 render; (b) a second chart rendered from a different spec
in the crypto theme (e.g. adoption vs. price) with no new drawing code.

---

## Module 2 — the rail, extracted into the library

**What exists today:** the rail lives in `render_ai_theme_v13.py` (the format master) and
the crossover drivers: `cx_text()`, `draw_rack(base, x, y, w, units)` (drawn supersampled,
factor `S`), plus inline code for the photo/nameplate, brand header, AMD badge, and the
Spencer block at the rail's foot.

**API (new file `audience_rail.py`, or a section of `meme_template.py` — builder's choice,
one file preferred):**

```python
draw_rail(img, spec) -> dict   # returns the content zone geometry
```

**Rail spec:** `{photo, name, brand_line, rack: {units: [(label, sub)], nameplate},
badge: "amd", cta: {badge_photo, line1, line2}}`.

**Fixed geometry and content (Brian's rulings, 2026-11-18):**

- `RAIL_W = 252`; content zone starts at `RAIL_W`; the function returns
  `{content_x0, content_x1, center}` so every theme lays out against the same zone.
- Brand header default: **"Run Your AI Locally"** (Brian's branding, ruled 2026-11-18
  07:52 CST) — a spec field, because whether it propagates beyond the AI theme is Brian's
  call (Open Decision D1).
- Rack rows show the JOB, not the tech, one box per work, green light on every row
  (Brian, 2026-11-18 06:51/07:08). Reference unit list (AI theme): LAN · AI INFERENCE
  (Alpha/Bravo shelf, two K11 mini-PCs) · SUCCESSBRIAN OS · BLOG WRITER · VIDEO AND IMAGE ·
  WEB HOSTING · SAAS HOSTING · BLOG SERVING · SOCIAL MEDIA · DATABASE · AI TRAINING.
  Nameplate: "SUCCESSBRIAN ECOSYSTEM", auto-fit (Module 3 helper).
  **Gamma never appears on the rack** (rented/shared — standing rule).
- Spencer + CTA pinned to the rail foot: "ASK BRIAN FOR YOUR FREE MUSE AI AGENT".

**Acceptance:** (a) crossover rail reproduced from spec; (b) one sibling theme (crypto)
rendered with the identical rail and only its content column changed.

---

## Module 3 — auto-fit text helpers (into `meme_template.py`)

Three fit loops were hand-rolled during the crossover build. They become library helpers:

1. `fit_font(text, font_name, start, floor, max_width, tracking=0)` — step down from
   `start` until `textlength ≤ max_width`. (Generalizes the rack nameplate loop:
   `while size > floor and textlength("SUCCESSBRIAN ECOSYSTEM") > plate_w − 16*S`.)
2. `fit_headline(text, colors, max_width, start=96, floor=28)` — for `headline_3d`. MUST
   measure the **true rendered layer width**, not `textlength`: the 3D extrusion and padding
   under-measure by plain textlength, which is why the crossover headline loop renders the
   layer and measures the image. Returns the fitted font; the driver pastes at the fitted
   size. Reference outcome: "YOUR OWN AI WILL OUTSMART THEIRS" at the largest size whose
   layer fits `W − RAIL_W − 14`.
3. `fit_pill(lines, max_width, start=20, floor=16, padding=90)` — wrap-aware fit for the
   holo pill: shrink until the widest line + padding fits. Reference: the crossover pill,
   two lines, landing in the 20→16 search.

**Acceptance:** crossover headline and pill reproduced at identical fitted sizes by the
helpers; one deliberate-overflow test string fitted without clipping in each helper.

---

## Module 4 — render machinery (into `meme_template.py`)

1. `supersampled(w, h, scale=4)` — a context manager yielding a draw surface at `scale`×,
   downscaling on exit. Generalizes `draw_rack`'s internal `S` factor so any detailed inset
   (rack, device, diagram) gets the same crispness in one line.
2. `save_native(img, path)` — the ONLY sanctioned save path for finished memes: asserts
   1080×1080, saves at native size, never upscales (Brian's delivery ruling, 2026-11-18).
3. `preview_crop(img, box, zoom=3, out=...)` — writes an enlarged crop of a region for QA.
   This morning's collision fixes (line through the "77" label, label/strikethrough checks)
   were all found through hand-made crops in /tmp; the helper makes that inspection a
   one-call step of every render.

**Acceptance:** rack rendered through `supersampled` matches the current output;
`save_native` refuses a non-1080 canvas; `preview_crop` reproduces a graph-zone zoom.

---

## Build order (when Brian gives the go)

1. Module 3 (helpers) — smallest, unblocks the rest.
2. Module 4 (machinery) — save/preview discipline lands before new rendering code.
3. Module 1 (chart) — extract `graph()` against the helpers; crossover-from-spec test.
4. Module 2 (rail) — extract from v13; sibling-theme test.
5. QA: a selftest script rendering the four acceptance cases; PM project
   `audience-format-library` with one QA check per module, in the coverage-watch pattern.

**Non-goals:** no theme's content or approved look changes; the crossover driver stays as
the reference implementation until its library twin passes acceptance; no posting or
publishing machinery is touched.

## Open decisions (Brian's, not the builder's)

- **D1 — Rail brand line per theme or global?** "Run Your AI Locally" is AI-theme branding.
  Do health/crypto/political rails carry their own brand lines (spec field, per-theme
  values Brian supplies) or the one line everywhere? Spec default until ruled: per-theme
  field, AI value as above.
- **D2 — The punchline audit item is separate.** "QLORA TODAY • FROM SCRATCH TOMORROW •
  YOURS WINS" is content, not machinery; this spec neither changes nor endorses it. It
  stays on Brian's plate independently of this build.

## Staging (Brian, 2026-11-18 09:13 CST: "staged to be coded into successbrian os over time")

Registered in the SBOS PM queue as a dependency chain — each step unlocks only when the
previous one is done, so the library is coded in order, over time:

| Step | PM id | Key | Depends on |
|---|---|---|---|
| 1 — auto-fit text helpers (Module 3) | 8689 | audience-format-library-s1-textfit | — |
| 2 — render machinery (Module 4) | 8690 | audience-format-library-s2-machinery | s1 |
| 3 — chart module (Module 1) | 8691 | audience-format-library-s3-chart | s2 |
| 4 — rail extraction (Module 2) | 8692 | audience-format-library-s4-rail | s3 |
| 5 — selftest + QA checks | 8693 | audience-format-library-s5-qa | s4 |

The umbrella registration step (id 8682) is marked done: spec filed + staging complete.
