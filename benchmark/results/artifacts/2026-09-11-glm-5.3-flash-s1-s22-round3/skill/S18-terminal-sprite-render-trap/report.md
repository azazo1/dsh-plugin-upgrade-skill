# S18 · The Terminal Sprite Render Trap — Diagnostic Report

Evidence pack (read-only): `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`, `ci-hang-evidence.txt`, `README.md`.

## 1. Phantom pixels — SGR background state leaking into the EMPTY half of a half-block cell

**Mechanism (from `renderer-excerpt.ts`).** The renderer packs two vertical pixels into one terminal cell: foreground SGR (`\x1b[38;2;r;g;bm` via `fg()`) paints the upper half via `'▀'`, background SGR (`\x1b[48;2;r;g;bm` via `bg()`) paints the lower half. SGR state is sticky: once emitted, it persists across all subsequent cells until explicitly changed or reset.

The bug is in the mixed/transparency branch of the cell loop:

```ts
} else if (up !== undefined) {
  seq = fg(up)          // <-- sets foreground ONLY; no background escape
  ch = '▀'
}
```

When the upper pixel is opaque and the lower pixel is transparent (`lower[x]` is `'.'`, so `lo === undefined`), the renderer emits **only a foreground sequence**. The terminal therefore fills the lower (EMPTY) half of that cell with whatever background SGR is currently in effect — i.e. the `bg(lo)` color emitted by the **previous** opaque cell (`seq = fg(up) + bg(lo)`). The upper half is a correct sprite pixel; the lower half shows a stale palette color that belongs to no frame data. That is the "dim colored noise" column.

**Which cells expose it.** Exactly the cells where the sprite's odd row (lower pixel row) is transparent while the even row above is opaque — precisely the 1-cell-wide strip hugging the right edges of solid features. The symptom log confirms the locations: "directly to the right of the dark outline cells, next to the sleep-Z symbols, and to the right of the heart glyph", and "NOT part of any frame's data (frame rows end in '.' at those columns)". They "appear and move with the animation" because the neighbors whose background gets inherited change every frame.

**Precise escape fix.** Every half-filled cell must pin BOTH halves explicitly. In the up-only branch, reset or default the background alongside the foreground:

```ts
seq = fg(up) + '\x1b[49m'   // default background; the lower half can no longer inherit a neighbor's color
```

Symmetrically, the lo-only branch (`seq = fg(lo); ch = '▄'`) should pin the foreground (`'\x1b[39m'`) so the empty upper half cannot inherit a stale foreground. (Alternatively, map transparent to a concrete palette color and emit `fg+bg` for every cell.) The diff-suppression check `if (seq !== current)` then works correctly, because the sequence differs whenever either half changes.

## 2. Ghost frames — trailing-whitespace trimming meets no erase on frame switch

**What the renderer drops from each row.** After building each output row, the renderer strips the tail of transparent cells:

```ts
let row = out.replace(/[ ]+$/, '')
```

Every fully transparent cell is emitted as `' '` (plain space with `seq = ''`), so the wide pose's rightmost columns — beyond the narrower frame's extent — exist only as trailing spaces, and this regex deletes them. The narrow frame's rows are therefore physically shorter than the wide frame's rows.

**What the text pipeline does to trailing whitespace.** A terminal advances the cursor over trailing spaces but paints nothing persistent where nothing is written; stripped columns are simply never re-written on the next frame. Nothing in the excerpt emits any erase (`\x1b[K` / `\x1b[2K`) or pads rows to a fixed width, so the cells occupied by the previous wide tail keep their old glyphs.

**Result.** Exactly symptom 2: after switching from a wide pose (tail swung out) back to a narrower pose, "the pixels of the wide tail REMAIN on screen at their old positions — the narrow frame renders fine, but the surplus columns keep showing the previous frame's tail."

**Two-part fix that guarantees a clean frame switch.**
1. **Emit full-width rows with explicit blanks:** drop the `replace(/[ ]+$/,"")` trim (or pad each row back to the sprite's fixed width, 40 cols), and make the blank cells attribute-safe — the transparency case already emits `RESET` (`seq === '' ? RESET : seq`), so the filler spaces carry default colors and overwrite rather than blend. Then every frame paints the same cell rectangle and the surplus columns are explicitly cleared by the frame itself.
2. **Erase the frame region on switch:** before/while writing each frame, clear the previously occupied area — e.g. append `\x1b[0K` (erase to end of line) after each sprite row, or `\x1b[2K` per line / a rectangle clear before redrawing. With (1) this is belt-and-braces; without fixed-width rows it is mandatory. Together they guarantee no cell of the previous frame survives.

## 3. Frame data drift — the hand-ported tail2 and the digest gate

**What the digest report says.** Per-frame sha256 digests of each frame's 25 rows, compared against the source-art frames, show every frame OK except **tail2: MISMATCH**. The tail2 detail: in the upper-right spout/tail-tip area, row 2 has the ported `D` at col 26 vs source col 27 (1-column left shift); row 3 has an extra `D` at col 25, `DBD` at cols 26–28 shifted left 1, and extra `DD` at cols 36–37; rows 4–6 have the whole upper-right cluster shifted 1 column left. **23 differing cells total** — this is symptom 3's misplaced tail-tip cluster (plus its neighbors).

**Why the existing regression missed it.** The report states it directly: "The ported tail2 was hand-copied during conversion; an excerpt-based regression (added later for a different frame) did not cover it." The regression asserted only an excerpt of one frame, so a mis-copied *different* frame never entered its comparison — per-excerpt coverage cannot see drift in frames it does not pin.

**The gate that prevents recurrence.** Make the digest comparison itself the regression: for **every** frame (all 25 rows × 40 cols), compute the row-content digest against the source art and fail the suite on any mismatch — pin tail2 (and all frames) with whole-frame sha256 digests generated from the source art rather than from the ported data, so any future hand-port or edit that shifts even one cell breaks CI with a frame-named failure.

## 4. The hang — a rescheduling timer pinning the event loop after the job finished

**Mechanism (from `ci-hang-evidence.txt`).** The job shows PASS for all scene checks, then sits idle: no running test, no pending assertion, but the event loop holds **live handles of kind Timeout — one per tick of the sprite animation planner, each re-arming the next**. "The planner reschedules a setTimeout for as long as its component stays mounted." A Node process exits only when its event loop has no live handles; the self-rescheduling timer chain is exactly such a handle, so the process never exits and is killed at the runner timeout (previously ~3 minutes; one local observation idled 19 minutes before a manual kill).

**Which hosts mount without unmounting.** The evidence names them: "these particular hosts mount the header component and finish WITHOUT unmounting it" — the channel-ui group's CI hosts. The interactive terminal product is unaffected because "its process is kept alive by the TTY/stdin handles regardless of the timer chain" — its lifetime never depended on the event loop draining, so the extra timer handle changes nothing there. The hang "first appeared in the same push that flipped the animation feature's default from off to on", because that is when the CI hosts began mounting the planner at all.

**One-line fix.** Stop the planner timer from holding the loop open — either unmount/dispose the header component (clearing the timer) when the host finishes, or, minimally, mark the animation tick timer non-keeping: `timer.unref()` on the rescheduled `setTimeout` handle (the planner still animates interactive hosts but cannot keep a finished CI process alive).

## 5. Prevention — renderer contract checklist and pre-rollout audit

**Renderer contract checklist for a terminal sprite implementation:**

1. Every half-filled cell emits escapes for BOTH halves: up-only ⇒ `fg(up)` + `\x1b[49m`; lo-only ⇒ `\x1b[39m` + `bg(lo)`. No cell may leave either half dependent on inherited SGR state.
2. Every cell is written with a fully-specified sequence; the transparency case emits an explicit reset/default pair, not an empty sequence with only `current`-tracking bookkeeping.
3. Rows are emitted at fixed width (full sprite columns) with attribute-safe blank filler; trailing-whitespace trimming is forbidden unless the erase in (5) is guaranteed.
4. Row output ends in `RESET` so no palette state escapes the sprite area (the shipped code does this — keep it; the per-attribute-default escapes from (1) make it near-redundant but harmless).
5. Frame switches erase the previously occupied region (`\x1b[0K`/`\x1b[2K` per row or a rectangle clear) so frames of different widths cannot leave residue.
6. Whole-frame digests (sha256 over all rows) pin every frame against source art; a mismatch fails CI by frame name. No excerpt-only frame regressions.
7. Animation timers are owned by the component lifecycle: mounting starts them, unmount/teardown clears them, and background tickers are `.unref()`-ed so a mounted-but-finished host can still exit.

**Audit to run BEFORE flipping an animation feature default-on:**

1. **Render audit:** run every frame through the renderer and diff the produced cell grid (colors + blanks) against expected; verify no attribute leakage on transparent cells at right edges (the §1 defect class) and no residue across width-changing frame transitions (§2).
2. **Frame-data audit:** confirm all frames pass the whole-frame digest gate against source art (§3) — drift found after a default-on flip is a user-visible regression, not a test fix.
3. **Lifecycle audit:** for each host that mounts the animated component, assert the component is unmounted/disposed at completion, or that all timers it starts are unref-ed/cleared — prove the process can exit with the component mounted (§4). Concretely: run one CI-style scene host to completion and require clean exit within a short bound, with zero live Timeout handles at exit.
4. **Rollout blast radius:** enumerate the hosts that newly mount the component when the default flips (the channel-ui CI hosts here) versus hosts that already ran it interactively; test the first group explicitly — that is where a previously harmless behavior becomes a hang.
5. **Canary + kill criteria:** flip the default behind a flag on one CI group first, with the exit-liveness check from (3) as a hard gate, before enabling repo-wide.
