# S18 · The Terminal Sprite Render Trap — Analysis Report

Scope: read-only analysis of the shipped half-block sprite renderer (`renderer-excerpt.ts`),
the symptom log, the frame digest report, and the CI hang evidence. No fixture files were
modified.

The renderer packs two vertical sprite pixels into one terminal cell: `▀` with
foreground = upper pixel and background = lower pixel (`▄` covers the lower-only case).
The sprite is 25 pixel rows × 40 columns, so each frame renders as 13 terminal rows.
Three of the four findings are consequences of that packing; the fourth is a lifecycle bug
unleashed by the feature flip.

---

## 1. Phantom pixels at the right edges (SGR state persistence)

**Mechanism.** The renderer emits SGR (color) escapes only when the desired color state
*changes* (`if (seq !== current)`), which is correct compression — but it relies on the
terminal's SGR state persisting across cells, and SGR persistence applies to **both**
foreground and background independently. Look at the half-filled branches:

- `up !== undefined && lo === undefined`: emits `fg(up)` only, glyph `▀`. The *upper*
  half is painted with `up` — fine — but the *lower* half of that cell is painted with the
  **current background**, which is whatever `bg(...)` was last set to, i.e. the lower-pixel
  color of the nearest earlier fully-opaque cell on that row.
- `lo !== undefined && up === undefined`: emits `fg(lo)` only, glyph `▄`. Here the
  background (painting the *upper* half of the cell) is again the stale inherited color.

So every half-filled cell paints a phantom pixel **in the EMPTY half of the cell**, using a
color leaked from an earlier cell's background state. Fully transparent cells are safe —
they emit `RESET` (`seq === ''` branch) — and fully opaque cells are safe because they set
both fg and bg.

**Which cells expose it.** Exactly the right-edge geometry the symptom log describes:
the dark outline, the sleep-Z symbols, and the heart glyph all sit where the sprite's
pixel data ends in `.` (transparent) on one vertical half — e.g. the bottom pixel of an
outline column is transparent while the top pixel is dark. At the *left* of the sprite the
preceding cells are transparent (already RESET), so the inherited background is the
default; at the *right edges* the immediately preceding cells are opaque sprite pixels,
so the inherited background is a real sprite color — producing the observed 1-cell-wide
column of dim colored noise that "appears and moves with the animation" (each frame has
different half-transparent edge cells, and the last opaque cell — hence the leaked bg —
differs per frame/row). The artifacts are strictly inside the sprite's cell area because
the leak only ever reuses colors already set within the same row.

**Precise escape fix.** The empty half must be explicitly painted with the default
background instead of inheriting: in both half-filled branches, emit the default-bg escape
together with the fg:

- up-only: `seq = fg(up) + '\x1b[49m'` (SGR 49 = default background), glyph `▀`;
- lo-only: `seq = fg(lo) + '\x1b[49m'`, glyph `▄`.

(If the terminal surface has a known background color, `bg(thatColor)` is the equivalent
fix and also survives screenshots with non-default palettes.) With SGR 49 in the sequence,
the transparent half renders as terminal background and no state can leak into it. Note
the dedup logic (`seq !== current`) continues to work; only the contents of `seq` change.

## 2. Ghost pixels surviving a switch to a narrower frame

**What the renderer drops.** The final line of the loop:

```ts
let row = out.replace(/[ ]+$/, '')
```

Trailing transparent cells were emitted as plain spaces (after a RESET), and then the
regex **trims all trailing spaces off the row** before appending `RESET`. So the rendered
row string only extends as far as the rightmost opaque glyph of *this* frame.

**What the text pipeline does.** When the frame's rows are written to the terminal (or
through any line-oriented pipeline), writing a shorter line simply leaves everything to the
right of its last glyph untouched — trailing whitespace is not "painted", and the trim also
means any padding that *would* have overwritten the old pixels is gone. Switching from a
WIDE pose (tail swung out, rows extending further right) to a NARROWER pose therefore
redraws only up to the narrow frame's extent; the surplus columns still hold the previous
frame's tail glyphs — exactly the reported "pixels of the wide tail REMAIN on screen at
their old positions".

**Two-part fix that guarantees a clean frame switch:**

1. **Never trim; erase instead.** Replace the trailing-space strip with an explicit
   end-of-line erase: keep the row at full sprite width, or trim *then* append
   `\x1b[K` (EL, erase to end of line) after the last glyph (before/with the final
   `RESET`). `\x1b[K` blanks every column to the right of the cursor, so surplus columns
   from any previous wider frame are cleared by construction, regardless of what the
   downstream pipeline does with spaces.
2. **Clear the previous frame's extents before drawing.** On each frame switch, erase the
   union bounding box of the previous and next frame (or simply the full 40×13 cell area,
   e.g. position at each row and `\x1b[K`, or `\x1b[2J`-style region clear for a
   full-canvas redraw) before writing the new rows. This covers the vertical dimension
   too (a shorter frame would otherwise leave ghost rows below) and makes frame switching
   idempotent rather than dependent on the new frame happening to be at least as wide/tall
   as the old one.

Part 1 fixes the horizontal surplus on rows that are still drawn; part 2 guarantees
correctness for any shape change (width *and* height) independent of draw order.

## 3. Frame data drift (hand-ported frames)

**What the digest says.** Of the 24 ported frames, only `tail2` mismatches the source
art: 23 differing cells, all in the upper-right spout/tail-tip area — a consistent
1-column left shift of the upper-right cluster (row 2: `D` at col 26 vs source col 27;
row 3: an extra `D` at col 25, the `DBD` run shifted left 1, plus stray `DD` at cols
36–37; rows 4–6 shifted throughout). This matches symptom 3, the misplaced 6-pixel tail-tip
cluster. The report states the frame was **hand-copied during conversion**.

**Why the regression missed it.** The existing regression is **excerpt-based**: it was
added later, for a *different* frame, and asserts only on a selected excerpt of selected
frames. `tail2` was never in its coverage, so a wholesale 1-column shift inside it was
invisible to the suite — per-excerpt goldens verify the excerpts they contain, not the
frames they don't.

**Gate that prevents recurrence.** Pin **every** frame's full content with a digest: a CI
golden test that computes sha256 over each frame's complete 25 rows (as the digest report
does) for all frames — `standard, blink, fin1-2, spout1-6, tail1-4, heart1-3, sleep1-5` —
and compares against digests generated from the source art (ideally generated, not
hand-transcribed, from the same conversion path). Any hand edit, partial re-port, or
column shift in any frame then fails CI with a named frame and diff, closing the
"excerpt happened to not cover it" hole. (Stronger variant: check the frames in with the
source art and derive them mechanically, so there is no hand-copy step to drift at all.)

## 4. The CI hang (timer-pinned event loop)

**Mechanism.** After the animation feature flipped default-on, the sprite animation
planner started running inside the `channel-ui` job. The planner drives each animation
tick with a `setTimeout` and **re-arms a new timeout for the next tick for as long as its
component stays mounted**. All scene checks PASS — the tests genuinely finish — but Node's
event loop cannot exit while live handles remain, and the kill-time process snapshot shows
exactly that: live handles of kind `Timeout`, one per tick, each scheduling the next. The
job therefore sits idle after "PASS" until the runner timeout kills it (~3 min historically;
one local observation ran 19 idle minutes). Nothing is deadlocked and no assertion is
pending: the process is *finished* but *pinned* by a self-perpetuating timer chain.

**Which hosts.** The hosts that mount the header component (which owns the animated
sprite) and **finish without unmounting it** — the CI test hosts. They complete their
assertions and drop references, but "dropping a reference" is not "unmounting": the
planner's mounted flag is still true, so it keeps rescheduling forever.

**Why the interactive terminal is unaffected.** Its process is intentionally long-lived:
the TTY/stdin handles keep the event loop alive by design, so the extra timer chain
changes nothing observable. That's why the bug shipped silently and only surfaced in CI,
where a job's exit depends on the event loop draining.

**One-line fix.** Stop the re-armed timer from pinning the loop:

```ts
this.timer.unref() // on every setTimeout the planner arms
```

`.unref()` on each armed timeout lets the process exit despite the pending timer. (The
complementary hygiene fix — calling `component.unmount()` in the mounting hosts' teardown,
so the planner stops instead of merely becoming harmless — is the right durable follow-up,
but `unref()` alone is the one-liner that un-hangs CI.)

## 5. Prevention

### Renderer contract checklist (ship with any half-block sprite implementation)

1. **No SGR state may cross a cell unintentionally.** Every glyph cell must define both
   the half it paints *and* the half it leaves empty: half-filled cells emit an explicit
   default/known background (`\x1b[49m` or the surface bg) alongside the fg. Rule: after
   processing any cell, the terminal's fg AND bg must both be correct for that cell.
2. **Rows are never shortened by trimming.** Trailing transparent cells must be cleared
   explicitly (`\x1b[K` / full-width padding), never dropped, so a shorter line always
   erases what a longer previous line painted.
3. **Frame switch = clear union extents, then draw.** Erase the bounding region covering
   previous *and* next frames (width and height) before rendering; switching must not
   depend on monotonic frame size.
4. **Every frame is digest-pinned in CI.** Full-content sha256 of all rows of all frames
   against source art (or mechanical derivation with no hand-copy step).
5. **Render output is byte-golden-tested.** Snapshot the exact escape sequences for
   representative frames, including right-edge half-transparent cells and a wide→narrow
   switch, so regressions in SGR emission or row termination fail loudly.
6. **Animation timers are lifecycle-owned.** Every re-armed timer belongs to the
   component's mount scope: cleared/disposed on unmount and `.unref()`-ed (or the host
   unmounts what it mounts). A component must not keep an event loop alive after its host
   is done with it.

### Pre-flip audit (run BEFORE turning an animation feature default-on)

1. **Identify every host that mounts the animated component** (CI test hosts, preview
   shells, the interactive product) and verify each one either unmounts it on finish or
   is intentionally long-lived. Check for timer/interval handles at teardown.
2. **Dry-run the default-on configuration in a process that must exit** (a CI-like job):
   confirm it exits cleanly after tests pass; inspect live handles at exit, not just test
   results.
3. **Re-run the full-frame digest gate and the render byte-goldens under animation**
   (multiple ticks, frame switches in both directions) — per-frame correctness under
   static display does not cover switch/erase behavior.
4. **Audit visual edges**: cells where pixel data ends mid-cell (right/bottom edges,
   overlaid glyphs like the Zs and heart) — confirm no phantom pixels in the empty halves
   and no ghost pixels after narrowing switches.
5. **Confirm symptom surface isolation**: artifacts must be reproducible/pinnable to the
   sprite's cell area only, so any leak beyond it fails a scene check.

---

### Summary of root causes and fixes

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | Phantom pixels at right edges | SGR background persists across cells; half-filled cells (`fg`-only `▀`/`▄`) paint their empty half with a leaked earlier bg | Emit explicit default bg (`\x1b[49m`) in both half-filled branches |
| 2 | Ghost pixels after wide→narrow switch | `replace(/[ ]+$/, '')` drops trailing transparent cells; shorter rows never overwrite surplus columns | Append `\x1b[K` instead of trimming + erase union extents of old/new frames before drawing |
| 3 | tail2 tail-tip drift | Hand-copied frame drifted 1 column (23 cells); excerpt regression didn't cover it | Full-content per-frame sha256 golden gate over all frames vs source art (or mechanical derivation) |
| 4 | CI hang after default-on flip | Planner re-arms a `setTimeout` while mounted; CI hosts mount and never unmount → timer-pinned event loop; interactive terminal kept alive by TTY anyway | `.unref()` each armed timer (one line); unmount in hosts' teardown as follow-up |
