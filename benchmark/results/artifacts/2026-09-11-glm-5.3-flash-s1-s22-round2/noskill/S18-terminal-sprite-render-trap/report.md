# S18 · The Terminal Sprite Render Trap — Diagnostic Report

Evidence pack: `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`, `ci-hang-evidence.txt` (read-only fixture).

## 1. Phantom pixels: stale SGR background leaking into the EMPTY half of a half-filled cell

**Mechanism (from `renderer-excerpt.ts`).** Each terminal cell packs two vertical pixels into one half-block glyph (`▀`: foreground = upper pixel, background = lower pixel). The emitter deduplicates SGR state with a `current` tracker:

```ts
if (up !== undefined && lo !== undefined) { seq = fg(up) + bg(lo); ch = '▀' }
else if (up !== undefined)               { seq = fg(up);        ch = '▀' }
else if (lo !== undefined)               { seq = fg(lo);        ch = '▄' }
else                                     { seq = '';            ch = ' ' }
```

SGR colors persist until changed or reset. A **fully populated** cell emits `fg(up) + bg(lo)`; the **partial** branches emit only a foreground sequence (`fg(up)` or `fg(lo)`) and never touch the background. So the background set by the last fully-populated cell remains active, and the empty half of the half-filled glyph is painted with that stale background color:

- Cell where upper is opaque but lower is transparent (`up` set, `lo === undefined`): emits `fg(up)` + `▀`. The glyph's **lower half** is drawn in the background color left over from the previous cell → a phantom pixel hanging below the sprite edge.
- Symmetrically, `▄` cells (`lo` set, `up === undefined`) expose a stale background in the **upper** half.

**Which cells expose it.** Exactly the cells at the sprite's right boundaries where one of the two vertical pixels is `'.'` (transparent) and the other is opaque — matching `symptom-log.txt` item 1: "a 1-cell-wide column of dim colored noise directly to the right of the dark outline cells, next to the sleep-Z symbols, and to the right of the heart glyph". The log confirms the frame data is clean there ("frame rows end in `.` at those columns"), so the noise can only come from render-time SGR state, not data. Interior cells are unaffected because both halves are set every time.

Why "dim" and why it "moves with the animation": the leaked color is whatever palette background the previous opaque cell happened to set, which changes per row and per frame — so the artifact tracks the outline/Z/heart edges as the frames cycle.

**Precise escape fix.** In both partial branches, reset (or explicitly default) the background so no prior `bg()` survives into the glyph:

```ts
else if (up !== undefined) { seq = fg(up) + '\x1b[49m'; ch = '▀' }  // default bg
else if (lo !== undefined) { seq = fg(lo) + '\x1b[49m'; ch = '▄' }
```

(`\x1b[49m` = default background; `\x1b[0m` would also work but forces re-emitting fg on the next cell.) The fully-empty branch is already correct because it emits `RESET`. Patching the two partial branches is sufficient and minimal.

## 2. Ghost frames: trimmed rows + no erase-to-end-of-line

**What the renderer drops from each row.** After emitting a row it strips trailing blank cells:

```ts
let row = out.replace(/[ ]+$/, '')
```

This is a deliberate optimization (don't emit dozens of "transparent" spaces), but it means each emitted line covers only the sprite's left-most opaque extent. Columns to the right of the trim point are **never written** on the narrower frame.

**What the text pipeline does with trailing whitespace.** Writing a shorter line to the terminal does not clear the rest of the row; the cursor simply advances and the previously drawn cells stay on screen. So when the animation switches from a wide pose back to a narrower one, the surplus columns — exactly where the wide tail used to be — still show the **previous frame's** pixels. This is `symptom-log.txt` item 2 verbatim: "the narrow frame renders fine, but the surplus columns keep showing the previous frame's tail". (The renderer appends `RESET` if the row doesn't end with it, but `RESET` only clears *attributes*, never *cells*.)

**Two-part fix guaranteeing a clean frame switch.**

1. **Erase to end of line after each row, with attributes reset first:** emit `RESET + '\x1b[0K'` (EL) at the end of every row, after the trailing-space trim. Order matters: EL erases using the *current* SGR background, so if the row ends mid-`bg()` state the "erased" area would be repainted as a colored bar — the same stale-SGR mechanism as symptom 1. `RESET` then `\x1b[0K` guarantees the trimmed columns become true default-background blanks.
2. **Clear once per frame switch** (home cursor and emit one bounded area erase, or at minimum an EL on every row including previously-wide rows). Per-row EL covers horizontal shrink; the frame-level erase covers cases where the new frame also occupies fewer rows or the writer repositions, so no cell of the old frame can survive any switch.

Together: the trim stays, but every row ends `...RESET\x1b[0K` and the frame boundary does a bounded clear — old pixels are physically erased, not merely overwritten.

## 3. Frame data drift: the hand-ported `tail2` and the missed gate

**What the digest report says.** `frames-digest-report.txt` compares sha256 of each ported frame's 25 rows against the source-art frames. All frames are `OK` except **`tail2`: MISMATCH**. Detail: 23 differing cells, all in the upper-right spout/tail-tip area — row 2 has `D` at col 26 instead of col 27 (1-column left shift), row 3 has an extra `D` at col 25, `DBD` shifted left 1 at cols 26–28, and extra `DD` at cols 36–37; rows 4–6 have the whole upper-right cluster shifted 1 column left. The report states the cause plainly: "The ported `tail2` was hand-copied during conversion." This is symptom 3's misplaced tail-tip cluster.

**Why the existing regression missed it.** Per the report, the excerpt-based regression "was added later for a different frame" — it pins hand-picked row excerpts of one frame only; `tail2` predates it and was never added to its coverage. Excerpt tests are frame-selective and position-partial by construction, so a whole-frame transcription error in an uncovered frame passes CI.

**The gate that prevents recurrence.** Make the digest comparison itself the regression: for **every** frame, compute sha256 of its 25 rows against committed source-art digests and fail the build on any mismatch — exactly what `frames-digest-report.txt` does, moved from a one-off report into CI as a golden-digest fixture. New or re-ported frames must add their digest in the same PR; a 1-column shift anywhere in any frame can no longer ship. Keep the excerpt test only as a failure *diagnostic* (diffing which cells differ), never as the gate.

## 4. The hang: a self-rescheduling timer pinning the event loop after the work is done

**Mechanism (from `ci-hang-evidence.txt`).** The `channel-ui` job shows PASS for all scene checks, then idles forever (historically ~3 minutes to finish; killed at the runner timeout; one local observation idled 19 minutes before manual kill). At kill: "no running test, no pending assertion; the event loop has live handles of kind Timeout — one per tick of the sprite animation planner, each re-arming the next." The planner reschedules a `setTimeout` for the next animation tick **as long as its component stays mounted**. The flip to default-on made every CI host mount that header component, and "these particular hosts mount the header component and finish WITHOUT unmounting it" — the timer chain never stops re-arming, so the event loop always has a live handle and the process never exits. Before the flip the component never mounted in CI, so the job exited normally.

**Why the interactive terminal is unaffected.** Per the evidence: "its process is kept alive by the TTY/stdin handles regardless of the timer chain" — a long-lived interactive process wants a live event loop, so the extra timer is invisible there. The symptom appears only in short-lived CI processes whose correct end state is "zero live handles."

**One-line fix.** Dispose the planner on teardown so the chain cannot outlive the host — in the component's unmount/cleanup path, clear the pending timer (e.g., `clearTimeout(next)` in the disposer); equivalently `.unref()` the animation timer so it cannot hold the loop open in CI. The clean one-liner is: unmount the header component (or clear its animation timer) when the host finishes.

## 5. Prevention

**Renderer contract checklist** a terminal sprite implementation should ship with:

- **SGR completeness per glyph:** every emitted glyph fully specifies the attributes its two half-pixels need — a half-filled cell (`▀`/`▄`) sets its foreground **and** resets/defaults its background; attribute state never leaks across cells by assumption. SGR deduplication must be state-complete, not prefix-complete.
- **Erase semantics:** every row ends with `RESET` + EL (`\x1b[0K`) after trailing-space trimming; a frame switch performs a bounded clear (per-row EL plus a frame-level erase) so narrower frames cannot leave prior-frame pixels. Erase always runs with default attributes.
- **Frame-data integrity:** every frame is pinned by a whole-frame digest against source art, compared in CI; hand transcription is verified by the digest, never by spot excerpts.
- **Lifecycle:** every animation timer is owned by the component and disposed on unmount; hosts that mount-and-finish cannot keep the process alive (timers cleaned up or unref'd).
- **Fixture parity:** golden fixtures capture the exact byte output of rendered rows (including escape sequences) so SGR/erase regressions are byte-visible.

**Pre-flip rollout audit** (before flipping an animation feature default-on):

1. **Run the "mount and finish" host profile**: every CI/headless host that mounts the component must exit with zero live handles after completion (check active handles, or gate on the job's own exit) — this is precisely the check that would have caught the Timeout-chain hang.
2. **Enable the feature in CI for a full run with a hard exit assertion**, not just scene PASS — "all checks PASS but the process didn't exit" is the failure signature to gate on.
3. **Diff rendered output with the feature on and off** across frame *switches* (wide → narrow included) using whole-frame digests, confirming erase semantics hold and no stale SGR appears at transparent boundaries.
4. Confirm fix scope: interactive TTY behavior unchanged (its lifetime is owned by TTY/stdin handles), non-interactive/CI hosts exit cleanly.
