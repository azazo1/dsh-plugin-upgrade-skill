# S18 · The Terminal Sprite Render Trap — Analysis Report

Fixture: `S18-terminal-sprite-render-trap/environment/fixture` (read-only; renderer excerpt, symptom log, frame digest report, CI hang evidence). Sprite: 25 pixel rows × 40 columns, packed two vertical pixels per terminal cell via half-block glyphs (fg = upper pixel, bg = lower pixel).

---

## 1. Phantom pixels at the sprite's right edges

### Mechanism: SGR background persistence into the EMPTY half of a half-filled cell

The renderer emits SGR sequences as *deltas* — it only emits a sequence when the composed `seq` string differs from the `current` one, and the sequences it composes are **incomplete for half-filled cells**:

- Both pixels present: `seq = fg(up) + bg(lo)`, glyph `▀` — sets both fg and bg; both halves of the cell are intentionally painted.
- **Upper only**: `seq = fg(up)`, glyph `▀` — sets fg only. The glyph's upper half is the pixel; the cell's **lower half (the EMPTY pixel) is painted with whatever background color is currently active**.
- **Lower only**: `seq = fg(lo)`, glyph `▄` — sets fg only. The glyph's lower half is the pixel; the cell's **upper half (EMPTY pixel) shows the currently active background**.
- Both transparent: emits `RESET`, glyph ` ` — safe.

SGR state is cell-global and persists across cells until changed. When a full cell (`fg+bg`, e.g. the dark outline `D`, the sleep-Z pixels, the heart pixels) is followed by a **half-filled** cell — exactly the geometry at the sprite's right edges, where one pixel row of the pair extends one column further than the other (frame rows end in `.` there) — the half-filled cell inherits the **previous cell's `bg` color**. The EMPTY half of that half-block glyph is therefore filled with the stale background color: a phantom pixel in a color that belongs to no frame data.

Which cells expose it: any upper-only or lower-only cell whose *preceding* cell had a defined background — i.e. right-edge cells adjacent to the dark outline, the sleep-Z symbols, and the heart. It is a 1-cell-wide band, it "appears and move with the animation" because the stale bg color varies frame to frame, and it is absent from frame data (those columns are `.`) — matching the symptom log exactly.

### Precise escape fix

Make every emitted `seq` **fully specify the background**, so no stale bg can persist into a half-filled cell. For the two half-filled branches, set the background to the terminal default using `\x1b[49m` (SGR 49 = default background):

```ts
} else if (up !== undefined) {
  seq = fg(up) + '\x1b[49m'   // was: fg(up)
  ch = '▀'
} else if (lo !== undefined) {
  seq = fg(lo) + '\x1b[49m'   // was: fg(lo)
  ch = '▄'
}
```

(Equivalently `bg(terminalBg)` if the canvas has a known background color; `\x1b[49m` is the exact escape for "default background".) With each `seq` now self-contained for fg and bg, the existing `seq !== current` delta logic remains correct and the EMPTY half renders transparently. The full-cell and transparent branches already define (or RESET) the background.

---

## 2. Ghost pixels surviving a switch to a narrower frame

### Why the previous frame's tail persists

Two facts combine:

1. **The renderer drops trailing cells from each row**: `let row = out.replace(/[ ]+$/, '')` trims trailing transparent cells. A narrower frame produces rows that are *shorter* than the previous wide frame's rows. Only columns up to the last non-space pixel are written; **the surplus columns of the wide frame (the swung-out tail) are simply never overwritten** — the old glyphs stay on screen at their old positions. This is purely a renderer-side row-trimming decision: the code chooses not to emit the trailing blank cells it has already computed.
2. **The text pipeline strips trailing whitespace**: even if the renderer *did* emit trailing spaces to overwrite old pixels, PTY/line-oriented text pipelines commonly discard trailing whitespace per line (and a consumer reading the stream cannot rely on trailing blanks arriving). So "just write 40 spaces" is not a robust overwrite mechanism across pipelines.

### The two-part fix that guarantees a clean frame switch

1. **Renderer side — draw each row at full sprite width (don't trim):** emit all 40 columns per row, including trailing transparent cells (blank, after the SGR fix above), so a narrower frame physically overwrites every column the wider frame touched. Keep rows a fixed known width (the sprite's declared column count) so the overwrite envelope never shrinks.
2. **Terminal side — explicitly erase the rest of each line:** after writing each row, emit **EL (Erase to Line End, `\x1b[K`)** — e.g. `row += '\x1b[K'` before pushing (applied after the trailing RESET). This erases anything beyond the written cells regardless of row length and regardless of whether the pipeline stripped trailing blanks. Belt and braces: the fixed-width write handles the columns the sprite owns; `\x1b[K` guarantees nothing from any previous, wider frame can survive to the right.

---

## 3. Frame data drift (tail2)

### What the digest report says

The sha256-per-frame comparison against the source art found one mismatch: **tail2**, hand-copied during conversion. 23 differing cells, all in the upper-right spout/tail-tip area: the upper-right cluster (including `DBD` at rows 2–3 and rows 4–6) is shifted **1 column left** throughout, plus stray extra pixels (`D` at row 2 col 26 vs source col 27; extra `D` at row 3 col 25; extra `DD` at cols 36–37). This is the "misplaced 6-pixel tail tip cluster" from symptom 3. All other 20 frames match.

### Why the existing regression missed it

The regression that existed was **excerpt-based and was added for a *different* frame** — it asserted only on a hand-picked slice of one frame's rows. tail2 was not in the excerpt, and even for covered frames only the excerpted cells were asserted, so a uniform 1-column shift outside the excerpt is invisible. Excerpt tests verify the pixels someone thought to look at, not the data.

### The gate that prevents recurrence

Pin **every frame in full** with a content digest: canonicalize each frame (exact 25 rows × 40 cols, no trailing trims) and record `sha256(frame)` (and/or per-row digests plus dimensions) in a checked-in golden file; CI recomputes and fails on any mismatch or dimension change. Golden regeneration is a deliberate, reviewed act (regenerate from the *source art*, never from the shipped port). This turns "the port matches the art" from a spot check into an all-frames invariant — exactly the check the digest report performed manually.

---

## 4. The CI hang: "finished but never exits"

### Mechanism

The animation feature (flipped default-on) added a **sprite animation planner that reschedules a `setTimeout` for the next tick for as long as its component stays mounted**. The CI hosts for the channel-ui group **mount the header component and finish their scene checks without ever unmounting it**, so the planner keeps re-arming timers forever — the process-state capture shows live `Timeout` handles, one per tick, each re-arming the next. In Node, a live ref'd timer keeps the event loop alive: all tests PASS, there is no running test or pending assertion, but the process cannot exit because the timer chain never ends. It sits idle until the runner kills it (observed 19 min vs the historical ~3 min).

### Why the interactive terminal is unaffected

The interactive terminal product is a long-lived process by design: its **TTY/stdin handles** keep the event loop open regardless of the timer chain, and it runs until the user quits — so a never-ending timer chain changes nothing observable there. The CI job, by contrast, expects the loop to drain once tests finish; the timer chain is the only thing holding it open.

### The one-line fix

Mark the rescheduled timer as not keeping the loop alive:

```ts
scheduleTimer.unref()   // on each setTimeout handle the planner arms
```

(`setTimeout(...).unref()` — Node; the `Deno.unrefTimer` equivalent on other runtimes.) The animation still ticks while the process lives, but the timer no longer holds the event loop open, so finished jobs exit. (Complementary hygiene: hosts should unmount mounted components in teardown — but `unref()` alone fixes the hang.)

---

## 5. Prevention

### Renderer contract checklist (ship with any half-block sprite renderer)

1. **Per-cell complete SGR state**: every emitted style segment fully specifies fg *and* bg (use `\x1b[49m`/default bg for half-filled cells); never rely on SGR state persisting across cells except as a pure byte-count optimization over fully-specified sequences.
2. **Constant row envelope**: every frame renders at the sprite's declared width (and declared row count) — never trim rows; the draw envelope of frame N+1 must cover frame N.
3. **Explicit erase on redraw**: each redrawn line ends with `\x1b[K` (EL); a full-canvas clear (`\x1b[2J` or region clear) on frame-size changes. Never rely on trailing spaces surviving the text pipeline (they are commonly stripped).
4. **Cursor addressing, not streaming**: position with CUP (`\x1b[<r>;<c>H`) per row rather than assuming scroll state; leave cursor parked/hidden (`\x1b[?25l\x1b[?25h` around the run).
5. **Frame data invariants**: frames are fixed-size (rows × cols) with a closed palette; unknown palette chars fail loud at load, not render as noise.
6. **Digest gate**: golden sha256 per frame (full content + dimensions) checked in CI; regeneration is a reviewed, source-art-driven act.
7. **Timer discipline**: all animation timers are `unref()`'d (or owned by a component lifecycle that provably disposes them on unmount); no timer may outlive its mount.
8. **Determinism**: identical frame + palette ⇒ identical byte output (snapshot-test the exact escape strings).

### Pre-flip audit before turning an animation feature default-on

1. **Inventory every host that mounts the animated component** — for each, verify the component is unmounted (or its scheduler disposed) at end-of-life, including test/CI/scene-check hosts and non-interactive embedders, not just the interactive terminal.
2. **Event-loop audit**: run each affected CI job and confirm the process exits promptly with zero live handles at completion (timer chains, intervals, watchers — all `unref()`'d or cancelled).
3. **Render-envelope diff**: render every adjacent frame pair (wide→narrow especially) and diff the byte output — confirm each frame's draw covers the union of all frames' extents and erases beyond it.
4. **SGR audit**: assert no output segment paints a cell half without defining that half's color (grep/AST for half-filled `seq` construction; snapshot full-row byte strings for edge rows).
5. **Golden-digest run**: all frames' digests green against source art *before* the flip, and the digest gate wired into the same CI group.
6. **Canary timing**: compare job wall-clock before/after the flip on the default-on configuration; a timeout/kill in this canary blocks the flip.

---

## Summary of fixes

| Symptom | Root cause | Fix |
|---|---|---|
| Phantom pixels at right edges | SGR `bg` persists from full cells into half-filled cells' EMPTY half | Emit `\x1b[49m` (default bg) with every half-filled `seq` |
| Ghost pixels on narrow switch | Rows trimmed of trailing blanks; pipeline strips trailing whitespace | Render full-width rows **and** end each row with `\x1b[K` |
| tail2 drift | Hand-ported frame; excerpt regression covered a different frame | Full-frame sha256 digest gate in CI over all frames |
| CI hang | Planner reschedules ref'd `setTimeout` forever; hosts mount without unmounting | `timer.unref()` (one line) |
