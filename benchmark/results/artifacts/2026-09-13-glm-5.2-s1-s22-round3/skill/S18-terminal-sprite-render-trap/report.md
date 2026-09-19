# S18 · The Terminal Sprite Render Trap — Analysis Report

Task: explain, from the shipped renderer code and evidence pack only, the four failure
modes (phantom pixels, ghost frames, frame-data drift, CI hang) and roll them into a
renderer contract + rollout audit. Mode A (read-only inspection) per the plugin-upgrade
skill; the fixture was not modified.

Evidence: `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`,
`ci-hang-evidence.txt` (all under the read-only fixture directory).

---

## 1. Phantom pixels at the sprite's right edges (SGR state persistence)

### Mechanism

The renderer packs two vertical pixels per cell and only emits an escape sequence when
the desired SGR state *changes* (`if (seq !== current)`). SGR (Select Graphic
Rendition) attributes — once set — apply to every subsequent cell until reset. The bug
lives in the two **half-filled** branches:

```ts
} else if (up !== undefined) {
  seq = fg(up)          // sets foreground only — background stays whatever it was
  ch = '▀'
} else if (lo !== undefined) {
  seq = fg(lo)          // foreground = lower pixel — background stays whatever it was
  ch = '▄'
}
```

- **Upper-only cell (`▀`)**: the glyph's *lower* half is painted with the cell's
  **background**. Since the branch never sets a background, the background from the
  previous cell persists → the EMPTY lower half of this cell is painted with the
  previous cell's lower-pixel color.
- **Lower-only cell (`▄`)**: the glyph's *upper* half is painted with the cell's
  background — again inherited from the previous cell → the EMPTY upper half shows the
  stale background color.

The `current` tracker only compares the string the renderer *would* emit, so it
believes "no change needed" exactly when a stale background is still active.

### Which cells expose it

Cells where exactly one of (upper, lower) is transparent (`.`), immediately following
a cell whose sequence set a background (a full `fg+bg` cell or any lower-pixel cell).
At the sprite's right edges this is precisely the neighborhood of:

- the **dark outline** (outline cells carry a lower dark pixel → bg set),
- the **sleep-Z symbols** and the **heart** (isolated glyphs with one opaque and one
  transparent half next to colored neighbors).

The result is a 1-cell-wide column of dim colored noise *right of* those features —
colored by the *previous* cell's palette, not by any frame data (frame rows end in
`.` there, as the symptom log confirms). It "moves with the animation" because each
frame shifts which neighbor last set a background.

### Precise escape fix

Half-filled branches must explicitly restore the background to default instead of
letting it leak. Emit SGR `49` (default background) alongside the foreground:

```ts
} else if (up !== undefined) {
  seq = fg(up) + '\x1b[49m'   // ▀ : upper pixel in fg, lower half = default bg
  ch = '▀'
} else if (lo !== undefined) {
  seq = fg(lo) + '\x1b[49m'   // ▄ : lower pixel in fg, upper half = default bg
  ch = '▄'
}
```

(`\x1b[49m` = default background; if the terminal paints a non-default canvas color,
substitute `bg(canvasColor)`.) Both branches must set *both* halves' colors every
time — the invariant is: **every emitted cell carries an explicit fg and bg**, so no
attribute can bleed across cell boundaries.

---

## 2. Ghost frames surviving a switch to a narrower frame

### What the renderer drops

```ts
let row = out.replace(/[ ]+$/, '')   // strips trailing transparent cells
```

Every row is trimmed of its trailing spaces — the transparent cells at the right end of
each row are never written to the terminal.

### What the text pipeline does

Trailing whitespace is invisible/unstable through the pipeline (editors strip it,
terminals don't retain trailing blanks, and many line-writer APIs trim it), so a wider
previous frame's pixels in those columns are **never overwritten** — nothing erases
them. When the wide pose (tail swung out) switches to the narrow pose:

- the narrow rows are shorter (and then trimmed even shorter),
- the surplus columns keep showing the previous frame's tail.

The row-final `RESET` (`\x1b[0m`) only resets SGR attributes; it does **not** erase
cells. Erasing requires writing a blank cell or an Erase-in-Line escape.

### Two-part fix

1. **Overwrite the full cell area every frame**: do not trim; pad each row with real
   space cells out to the full sprite width (40 columns), so every cell the sprite can
   ever occupy is written (spaces in both halves = transparent) on every frame.
2. **Erase to end of line after the last content cell**: append `\x1b[K` (EL 0) to
   each rendered row, so any columns to the right of the current row — including a
   previous wider frame's leftovers — are erased by the terminal itself.

Part 1 guarantees the sprite's own cell area is always repainted; part 2 guarantees
anything beyond it (from any earlier, wider frame) is cleared. Together a frame switch
can never leave stale pixels. (Equivalent alternative for part 2: track the previous
frame's bounding width and blank the max(old, new) extent before drawing.)

---

## 3. Frame data drift (hand-ported frames)

### What the digest report says

- 25 of 26 frames match the source art; **`tail2` MISMATCHes**: 23 differing cells,
  all in the upper-right spout/tail-tip area — a 1-column left shift of the
  upper-right cluster (rows 2–6), a stray `D` at row 3 col 25, extra `DD` at
  cols 36–37. I.e. the misplaced 6-pixel tail-tip cluster the user saw.
- Cause: `tail2` was **hand-copied** during conversion.

### Why the per-excerpt regression missed it

The regression compares only an *excerpt* of a frame, and it was added for **a different
frame** — `tail2` was never in its coverage. An excerpt check verifies the bytes it
pins, not the frames it doesn't; hand-porting drift outside the excerpt is invisible to
it.

### The gate that prevents recurrence

A **full-corpus frame-digest gate**: sha256 (or equivalent canonical digest) of every
frame's complete 25 rows, compared against the source-art frames, run in CI on every
change to frame data (exactly the check that produced this report — promoted from a
one-off audit to a committed test). Any cell-level drift in any frame, ported or
regenerated, fails the build. Keep the digests keyed by frame id and regenerate them
only from the source art, never from the shipped (possibly-drifted) copies.

---

## 4. The CI hang ("finished but never exits")

### Mechanism

The animation feature's planner drives the sprite with a self-re-arming
`setTimeout`: each tick schedules the next. A pending `Timeout` is a live event-loop
handle, so the Node process cannot exit while the chain continues. Per the kill-time
process state: no running test, no pending assertion — just one live `Timeout` per
planner tick, each re-arming the next. The scene checks all PASS; the job then sits idle
until the runner timeout kills it (~3 min historically; 19 min observed once).

### Which hosts, and why interactive is unaffected

The affected hosts (channel-ui CI) **mount the header component containing the sprite
and finish without unmounting it** — the planner's timer chain never stops because
nothing calls its teardown. The interactive terminal product is unaffected only
because its process is held alive anyway by TTY/stdin handles, so the extra timer chain
changes nothing observable there — which is why the bug shipped quietly and surfaced
exactly when the feature flipped **default-on** in CI.

### One-line fix

Mark the timer non-ref-counted so it never keeps the loop alive:

```ts
this.timer.unref()          // (Node) after each setTimeout(...) re-arm
```

(The complementary hygiene fix — actually unmounting/clearing the planner in host
teardown — is correct too, but `unref()` is the one-liner that guarantees exit.)

---

## 5. Prevention

### Renderer contract checklist (ship with any half-block terminal sprite renderer)

1. **Explicit full SGR per cell**: every emitted cell sets both foreground and
   background (half-filled cells use SGR 49 / canvas bg). No attribute may depend on
   the previous cell's state.
2. **Full-area repaint**: each frame writes every cell of the sprite's bounding box
   (width = max frame width), spaces for transparent — no trailing-whitespace trimming.
3. **Erase semantics on row end**: `\x1b[K` (or explicit blanking of the previous
   frame's extent) after the last content cell of every row.
4. **State hygiene between frames**: begin each frame from a reset (`\x1b[0m`) and
   end each row reset; never rely on cursor position or SGR carried across frames.
5. **Frame data integrity**: full-corpus digest gate against source art (§3) — every
   frame, every row, every cell; hand-ported frames are not "done" until digested.
6. **Timer lifecycle**: any animation timer must be cancellable on unmount and/or
   `.unref()`-ed; a render component must not assume its host process will outlive it.
7. **Deterministic output**: given a frame + palette, the escape byte stream is
   deterministic and snapshot-testable (golden byte-level snapshots of rendered rows).

### Audit to run BEFORE flipping an animation feature default-on

1. **Inventory every host that mounts the animated component** — including test
   harnesses, CI scene checks, and headless hosts — and verify each has an unmount /
   teardown path that actually runs (or that timers are unreffed).
2. **Event-loop audit**: run each affected host's suite and confirm the process exits
   on its own (e.g. `why-is-node-running` / `--trace-event-loop`-style handle dump at
   end-of-suite); zero live `Timeout`/interval handles after tests pass.
3. **Frame-switch sweep**: render every ordered pair of adjacent (and widest→narrowest)
   frame transitions into a fresh and a dirty buffer; assert no stale cells remain.
4. **SGR leak sweep**: render frames with half-transparent columns adjacent to opaque
   neighbors; assert the byte stream contains no cell lacking an explicit bg (grep for
   `fg`-only sequences preceding `▀`/`▄`).
5. **Digest gate green** on the full frame corpus.
6. Only then flip the default, and keep a one-line kill switch (env/config) to revert
   the default without a code rollback.

---

## Skill-mode notes

- Mode A (read-only inspection); no files inside the fixture or benchmark repository
  were modified, no installs or migrations executed.
- The seven touchpoint classes of the skill's pre-flight do not apply directly (this is
  an application-renderer diagnosis, not a DSH version-corridor migration); the
  skill's discipline of read-only evidence, explicit mechanism-before-fix, and
  validation layers was applied as the working methodology.
