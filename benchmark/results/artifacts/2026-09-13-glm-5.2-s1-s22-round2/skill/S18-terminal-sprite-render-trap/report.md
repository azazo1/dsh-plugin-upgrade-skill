# S18 · The Terminal Sprite Render Trap — Analysis Report

Task: read-only diagnosis of a half-block terminal sprite renderer with four defects
(phantom pixels, ghost frames, one drifted frame, a CI hang) plus prevention guidance.
Evidence: `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`,
`ci-hang-evidence.txt` under the read-only fixture. No fixture file was modified; no
migration, install, or execution was performed.

## 1. Phantom pixels at the sprite's right edges

**Mechanism — partial SGR sequences let color state persist across cells.**
The renderer builds each cell's escape prefix `seq` from only the halves that exist:

- both halves: `fg(up) + bg(lo)` — fully specified;
- upper only: `fg(up)` — **background parameter not emitted**;
- lower only: `fg(lo)` — **background parameter not emitted** (and for `'▄'` the *upper*
  half of the glyph is painted with the background color);
- both transparent: `''` → emits `RESET`.

SGR parameters (38;2 and 48;2) are *modal*: anything not explicitly set persists from
the previous cell on the row. The `seq !== current` change-tracking only avoids
re-sending an identical prefix; it does not clear parameters that the new prefix omits.
So whenever a half-filled cell follows any earlier cell that set a background (any
full `▀` body/outline cell), the half-filled glyph's **empty half is painted with the
stale background color** of that earlier cell.

**Which cells expose it.** Exactly the cells where exactly one of `up`/`lo` is defined
and a background was set earlier in the same row — at the sprite's right edges the data
ends in `'.'` on one half while a palette char occupies the other: the dark outline
cells (tail/spout boundary), the sleep-Z symbols, and the heart glyph. The stale
background changes as neighboring full cells change per animation frame, which is why
the noise "moves with the animation" while belonging to no frame's data. It renders at
half-cell resolution as a dim 1-cell-wide colored column hugging the edge.

**Precise escape fix.** Make every drawn cell's prefix fully specify both SGR
parameters, defaulting the empty half instead of omitting it:

```ts
if (up !== undefined && lo !== undefined) { seq = fg(up) + bg(lo); ch = '▀' }
else if (up !== undefined) { seq = fg(up) + '\x1b[49m'; ch = '▀' }   // bg = default
else if (lo !== undefined) { seq = '\x1b[39m' + fg(lo); ch = '▄' }   // fg(default) upper… 
```

For `'▄'` the upper half takes the *background*, so the empty half must be `\x1b[49m`
and the drawn half `fg(lo)`; equivalently `seq = fg(lo) + '\x1b[49m'` works because
`'▄'` paints its lower half in foreground and the upper half in background. Either
formulation: **the empty half always gets an explicit default (`49m` for bg, `39m` for
fg), so no SGR parameter ever leaks from a previous cell.** (Emitting `RESET` before
every partial cell also works but produces more escape traffic.)

## 2. Ghost pixels surviving a switch to a narrower frame

**What the renderer drops.** `let row = out.replace(/[ ]+$/, '')` trims all trailing
spaces from every row. Transparent canvas cells at the row's end are erased from the
output string entirely.

**What the pipeline does.** A row string that stops at the last drawn glyph rewrites
only those terminal cells; the text/terminal layer does not erase cells beyond the
written text (and typical text pipelines additionally strip or normalize trailing
whitespace, so even padding inside the string can be lost). When the animation goes
from a wide pose (tail swung out) to a narrower pose, the narrower frame's rows are
shorter: the surplus columns on the right are never overwritten, and the previous
frame's tail pixels stay on screen at their old positions.

**Two-part fix.**

1. **Never trim to content — render a fixed-size canvas.** Pad every row to the full
   sprite width (40 columns / 13 terminal rows) with spaces (each preceded by the
   appropriate fully-specified prefix per §1) so every frame rewrite covers every cell
   of the sprite's cell area; a narrower frame then writes blanks over the old tail.
2. **Erase the previous extent explicitly.** Before/while drawing a frame, clear the
   rows to end-of-line (`\x1b[K` after the row content, or a cursor-addressed clear of
   the previous frame's bounding box / full canvas clear), so correctness does not
   depend on the new frame being at least as wide as the old. Together: fixed-width
   writes + explicit EL guarantees a clean frame switch even wide→narrow.

## 3. Frame data drift (tail2)

**What the digest says.** `frames-digest-report.txt` compares sha256 digests of each
frame's 25 rows against the source art: every frame is OK except `tail2` — MISMATCH
with 23 differing cells, all in the upper-right spout/tail-tip area: the cluster
shifted 1 column left (e.g. row 2 `D` at col 26 vs source col 27; row 3 has an extra
`D` at col 25 and extra `DD` at cols 36-37; rows 4-6 shifted left throughout). This
matches symptom 3, the misplaced 6-pixel tail-tip cluster. `tail2` was hand-copied
during conversion.

**Why the regression missed it.** The existing regression is *per-excerpt*: it was
added later for a different frame and asserts only on selected excerpts, so `tail2`
(and the shifted cluster inside it) was never in its assertion set. Excerpt-based
checks verify the pieces someone thought to pin; a hand-porting error elsewhere is
invisible.

**Gate.** Pin **every** frame with a full-frame digest: commit golden sha256 values
per frame (exactly what `frames-digest-report.txt` computes over the complete 25 rows)
and make CI fail on any mismatch. Any hand edit, shift, or dropped pixel in any frame
then fails the gate; regenerating a golden requires an explicit, reviewable update.

## 4. The CI hang (finished but never exiting)

**Mechanism — a timer-pinned event loop.** The CI evidence shows the channel-ui job
PASSes all scene checks, then sits idle with no running test and no pending assertion,
but with live event-loop handles of kind `Timeout` — one per animation tick, each
re-arming the next. The sprite animation planner reschedules a `setTimeout` for as long
as its component stays **mounted**. The channel-ui hosts mount the header component
and finish **without unmounting it**, so the timer chain never stops, at least one
handle is always pending, and Node's event loop never drains — the process cannot
exit and is killed at the runner timeout (~3 min normally; one observed run idled 19
minutes). The hang appeared exactly in the push that flipped the animation feature
default from off to on.

**Why the interactive terminal is unaffected.** The interactive product is a
foreground app whose TTY/stdin handles keep the event loop alive by design; the extra
timer chain changes nothing observable there — the app exits when the user quits, not
when the loop drains. Only drain-to-exit processes (CI/test hosts) notice.

**One-line fix.** Make the timer not pin the loop / not outlive the component —
e.g. call `.unref()` on each rescheduled `setTimeout`, or (equivalently, at the
mount site) dispose the planner on unmount:

```ts
const t = setTimeout(tick, interval); t.unref(); return t   // one-line fix
```

The robust form is teardown (`clearTimeout` in the component's unmount disposer), with
`unref()` as the one-line safety net for hosts that forget to unmount.

## 5. Prevention

**Renderer contract checklist (ship with any half-block sprite renderer):**

1. **Fully specified SGR per cell**: every drawn cell emits both fg and bg (default
   `39m`/`49m` for an empty half); no SGR parameter may depend on the previous cell.
2. **Fixed-size canvas**: every frame writes the same cell rectangle; no
   trailing-space trimming of rendered rows.
3. **Explicit erase on switch**: EL (`\x1b[K`) or full-canvas clear so a narrower
   frame cannot leave the previous frame's pixels; never rely on the new frame
   overwriting the old extent.
4. **Cursor discipline**: address cells absolutely (CUP) or rewrite whole rows in
   order; don't assume the cursor position after trimmed rows.
5. **Frame data integrity**: golden full-frame digests (per frame, all rows) committed
   and enforced in CI; hand-ported frames must pass the digest before merge.
6. **Lifecycle**: every timer/animation loop is created with a disposer and is
   cancelled on unmount; rescheduled timers are `unref()`-ed so they cannot pin a
   drain-to-exit host.
7. **Determinism in tests**: scene checks must assert the *rendered escape output*
   (or a rendered-screen model), not just frame data, so SGR/erase regressions are
   caught.

**Audit before flipping an animation feature default-on:**

1. **Inventory every host** that mounts the animated component (interactive terminal,
   CI scene hosts, screenshot/preview generators, headless tests) and verify each one
   unmounts/disposes it — or that the timers are `unref()`-ed.
2. **Event-loop audit**: run each CI job with handle diagnostics; confirm the job
   exits by loop drain, not runner timeout, with the feature on.
3. **Wide→narrow frame transitions**: exercise the full frame cycle (widest pose →
   narrowest pose) and diff the rendered screen, not the frame data.
4. **Edge-cell review**: inspect right-edge, glyph-adjacent cells (outline, Z, heart)
   for stale-color artifacts against a reference renderer.
5. **Digest gate green** for all frames, and no test relies on trimming or on the
   previous frame's extent.
6. Only after 1-5 pass, flip the default and observe the exact CI jobs that changed
   behavior — the timeline in the evidence (hang appears in the same push as the flip)
   is the expected signature.

## Verdict summary

| Symptom | Root cause | Fix |
|---|---|---|
| Phantom right-edge pixels | partial SGR prefixes leak fg/bg state across cells into the empty half of half-filled cells | fully specify both SGR params per cell (`49m`/`39m` defaults) |
| Ghost pixels after wide→narrow switch | trailing-space trimming + no erase beyond written text | fixed-width canvas writes + explicit EL/clear |
| tail2 drift (23 cells) | hand-ported frame; excerpt regression didn't cover it | full-frame golden digests enforced in CI |
| CI hang | animation planner re-arms `setTimeout` while mounted; hosts never unmount → timer-pinned event loop | `unref()` / `clearTimeout` on unmount |

Completed from the read-only evidence pack; nothing outside the designated output
directory was written, and no migrations, installs, or fixture executions were performed.
