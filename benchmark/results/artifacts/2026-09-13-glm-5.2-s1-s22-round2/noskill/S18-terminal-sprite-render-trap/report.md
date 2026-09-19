# S18 · The Terminal Sprite Render Trap — Analysis Report

Scope: read-only analysis of the fixture evidence pack (`renderer-excerpt.ts`,
`symptom-log.txt`, `frames-digest-report.txt`, `ci-hang-evidence.txt`). No fixture
files were modified; nothing outside the designated output directory was written.

## 1. Phantom pixels at the sprite's right edges

**Mechanism — SGR state persistence into the EMPTY half of a half-filled cell.**

The renderer emits an SGR sequence only when the desired color state *changes*, and for
half-filled cells it emits **only the foreground color**:

```ts
} else if (up !== undefined) {
  seq = fg(up)      // no background parameter!
  ch = '▀'
} else if (lo !== undefined) {
  seq = fg(lo)      // no background parameter!
  ch = '▄'
}
```

ANSI SGR parameters are *cell-spanning and sticky*: `38;2;r;g;b` (foreground) and
`48;2;r;g;b` (background) are independent, and neither is implicitly cleared when the
other is set. A terminal cell painted with a half-block glyph shows **two** pixels —
the upper half in the current foreground, the lower half in the current background.

So when the renderer walks rightward and reaches the sprite edge:

1. The last *fully-covered* cell emits `fg(upper) + bg(lower)` — both halves colored.
2. The next cell has `up` defined but `lo === undefined` (the frame row ends in `.`
   = transparent at that column in the lower pixel row). The renderer emits only
   `fg(up)`; `seq !== current` so it is written, but **the background SGR from the
   previous cell is still active**.
3. That cell renders `▀` with the *previous cell's lower-pixel color* bleeding into
   its lower half — a phantom pixel in the EMPTY half of a half-filled cell.

**Which cells expose it:** exactly the edge columns where one pixel row is opaque and
the paired row is transparent (`.`) at the same column — the right edge of the dark
outline, beside the sleep-Zs, and beside the heart glyph, matching the symptom log
("frame rows end in `.` at those columns"). Because the inherited bg changes as the
animation moves the neighboring colored cells, the phantom column appears as "dim
colored noise" that moves with the animation. The symmetric `▄` case (only `lo`
defined) has the same defect in the *upper* half via a stale foreground.

**Precise escape fix:** never leave the empty half's color implicit. For half-filled
cells, explicitly set the unused parameter to the terminal default:

- `▀` with only `up`: emit `fg(up) + '\x1b[49m'` (`SGR 49` = default background);
- `▄` with only `lo`: emit `fg(lo) + '\x1b[49m'` as well (the glyph paints only the
  lower half, but pinning bg also keeps the `current`-tracking optimization sound),
  or equivalently emit `RESET + fg(lo)`.

With both SGR parameters always explicit, no state can leak across cell boundaries and
the phantom column disappears.

## 2. Ghost pixels surviving a switch to a narrower frame

**What the renderer drops:** each finished row is right-trimmed —

```ts
let row = out.replace(/[ ]+$/, '')
```

Fully-transparent trailing cells (rendered as plain spaces) are stripped from the row
string. Those spaces were the only thing that would *overwrite and erase* whatever the
previous (wider) frame had painted in those columns.

**What the text pipeline does:** the surrounding text pipeline additionally collapses /
strips trailing whitespace (the trimming in the renderer exists to cooperate with it),
so even untrimmed trailing spaces cannot be relied on to reach the terminal.

**Combined effect:** switching from the wide pose (tail swung out, rows extending
further right) to a narrower pose writes a *shorter* row per line. The narrow frame
overwrites only its own columns; the surplus columns to its right are never written,
never erased, and keep showing the previous frame's tail — the "ghost frame".

**Two-part fix that guarantees a clean frame switch:**

1. **Erase semantics instead of space padding.** After the last glyph of each row (and
   only there — the glyph cells must not be disturbed), emit `ESC[K` (EL — Erase to
   End of Line, optionally `ESC[0K`). Erase clears from the cursor to the end of the
   line *including* columns the current row never reached, and an escape sequence is
   not whitespace, so trailing-whitespace trimming in the text pipeline cannot strip
   it. The renderer should stop trimming meaningful content and append `\x1b[K`
   before the final `RESET`.
2. **Full-frame clear on frame switch (or cursor-addressed repaint).** On switching
   frames, repaint the full sprite cell rectangle from a home cursor position (or emit
   `ESC[2K` per occupied line / `ESC[J` for the region) so every cell previously
   owned by the sprite is rewritten or erased in the same output batch. Together with
   (1) this makes each frame self-contained: a frame's render does not depend on what
   the previous frame happened to leave in any column.

## 3. Frame data drift (tail2)

**What the digest report says:** the sha256 digest of each frame's 25 rows was compared
against the source-art frames. Every frame matches **except `tail2`**: 23 differing
cells, all in the upper-right spout/tail-tip area — the upper-right cluster shifted
**1 column left** throughout rows 4–6, with row-level symptoms (row 2: `D` at col 26
instead of 27; row 3: an extra `D` at col 25, a shifted `DBD` at cols 26–28, and
stray `DD` at cols 36–37). This matches the user-visible "misplaced tail tip: a
6-pixel cluster drawn at the wrong position". `tail2` was hand-copied during the
conversion from the source art.

**Why the existing regression missed it:** the regression added after porting was
*excerpt-based* — it asserted on a hand-picked excerpt of a **different** frame, not an
exhaustive check of every ported frame. A hand-copied frame that nobody pinned has no
test failure mode; excerpt tests verify the frames you already looked at, not the ones
you copied wrong.

**Gate that prevents recurrence:** check in an **exhaustive per-frame digest test** —
for *every* frame in the sprite data, compute a stable content digest (e.g., sha256 of
the frame's 25 canonical rows) and compare it against digests generated *from the
source-art files* at build/test time (single source of truth). Any ported frame that
drifts — shifted columns, extra cells, missing cells — fails CI with the frame name and
a diff, as the digest report itself demonstrates is possible. Re-porting or editing a
frame requires regenerating the digest *from source*, never hand-editing the expected
value.

## 4. The CI hang ("finished but not exiting")

**Mechanism — a timer-pinned event loop.** The animation feature (flipped default-on in
the offending push) runs a sprite animation planner that schedules each tick with
`setTimeout` and **re-arms the next timeout as long as its component stays mounted**
(it has no terminal condition of its own). Node exits when the event loop drains; a
live `Timeout` handle is a ref'd handle that keeps the loop alive forever. The
channel-ui CI hosts **mount the header component and finish the scene checks without
ever unmounting it**, so the planner's timer chain never ends: every tick re-arms the
next. Process state at kill confirms it — no running test, no pending assertion, only
live `Timeout` handles, one per tick, each re-arming the next. The job therefore shows
PASS and then sits idle until the runner timeout kills it (~3 min historically vs. a
recorded 19 min of idle).

**Why the interactive terminal is unaffected:** its process is *already* kept alive by
its TTY/stdin handles for its entire lifetime, so the animation's ref'd timer chain
adds no observable behavior — the latent leak exists there too, it just cannot change
when that process exits. The CI job is a finite-work process with no other keep-alive
handles, so the timer chain is the only thing pinning the loop and the hang becomes
visible.

**One-line fix:** mark the planner's timer unref'd so it can never pin the event loop:

```ts
setTimeout(tick, interval).unref()
```

(The root-cause hygiene fix is for hosts to unmount/dispose the header component —
which must clear the pending timeout — when they finish; the harness should provide
that teardown in `afterEach`/`afterAll`. But `unref()` alone restores the
"finished job exits" behavior.)

## 5. Prevention

### Renderer contract checklist (ship with any terminal half-block sprite renderer)

1. **Every SGR parameter explicit per cell.** Both foreground and background are set
   (or explicitly defaulted, `ESC[49m` / `ESC[39m`) for every glyph cell; no cell
   relies on SGR state inherited from a previous cell. Half-filled cells are the trap.
2. **Color-state tracking is compared against the *full* intended state** (fg and bg
   together), not the last emitted string fragment.
3. **Erase, don't pad.** Row tails end with `ESC[K` (EL) rather than relying on
   space characters, which text pipelines strip and which cannot clear columns a
   narrower previous frame wrote.
4. **Frames are self-contained.** A frame switch rewrites or erases the entire sprite
   rectangle (cursor-home repaint or `ESC[2K` per row); correctness never depends on
   the previous frame's residual cell contents or width.
5. **Transparent is a decision, not an absence.** `.` cells must render as an
   explicitly defaulted (or erased) cell, never as "whatever was there before".
6. **Frame data is digest-pinned to source art.** Every frame, not excerpts; digests
   generated from the source files, never hand-maintained.
7. **Animation timers never pin the event loop.** Tickers are cleared on unmount and
   `unref()`'d so an unmounted-or-leaked component cannot keep a finite process
   alive; component mount in tests is paired with teardown.
8. **Cursor discipline.** All writes are cursor-addressed (CUP) or preceded by an
   explicit home; no implicit cursor assumptions after trimmed rows.

### Audit BEFORE flipping an animation feature default-on

1. **Inventory every host that mounts the animated component** (product surfaces,
   tests, CI scene checks) and confirm each one has an unmount/teardown path — plus a
   belt-and-braces `unref()` on the tick timer.
2. **Run the finite-work consumers** (CI jobs, scripts) with the feature on and verify
   the process *exits* after PASS — watch event-loop handle counts, not just test
   results; a job that passes then idles is a failed audit.
3. **Re-verify visual invariants under frame switching:** exercise wide→narrow (and
   every adjacent) frame transition and assert no residual pixels outside the current
   frame's bounds (erase-semantics test).
4. **Re-verify edge cells under animation:** assert no cell's rendered colors depend
   on the previous cell's state (SGR isolation test), especially along right edges of
   every opaque cluster in every frame.
5. **Confirm the digest gate covers all frames** and is green against source art with
   the feature on (animation must not select frames the digest never pinned).
6. **Check default-flip blast radius:** the flip changes behavior for every existing
   consumer, including ones that never opted in — each must be re-run, not just the
   feature's own tests.
