# S18 · The Terminal Sprite Render Trap — Diagnostic Report

Evidence pack: `README.md`, `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`, `ci-hang-evidence.txt` (read-only fixture).

## 1. Phantom pixels in the EMPTY half of a half-filled cell

**Mechanism.** In `renderer-excerpt.ts`, each output cell needs two SGR attributes when both pixels are opaque: `seq = fg(up) + bg(lo)` with glyph `'▀'`. When only the **lower** pixel is opaque, the renderer emits `seq = fg(lo)` with glyph `'▄'` — but it emits **only the foreground SGR**. It never emits a background sequence, and it never emits `RESET` before relying on the terminal's default background. That is the leak: **the background SGR (the `\x1b[48;2;r;g;bm` set by the previous `▀` cell) persists across cells.** SGR state survives until explicitly changed or reset; a plain foreground change does not clear it.

**Which cells expose it.** Any cell where `up === undefined` and `lo !== undefined` (the `else if (lo !== undefined)` branch) that **follows** a cell which set a background color. At the sprite's right edges, the frame data is transparent (`'.'`) above and colored below (the bottom half of the outline, the sleep-Z symbols, the heart) — exactly the layout in `symptom-log.txt` item 1: frame rows "end in `.` at those columns", yet the terminal keeps painting the previous cell's `48;2` background under the new `▄`/space glyph, producing the "1-cell-wide column of dim colored noise". The `current` dedup cache makes it worse: after a run of `seq === ''` cells the code correctly emits `RESET` once, but on the *first* half-filled cell after opacity it compares only the new `fg(lo)` string against `current`; the stale background is invisible to that comparison, so nothing ever corrects it.

**Escape fix.** Every branch that emits a sequence must fully specify the state it depends on. Concretely: in the lower-only branch emit `RESET + fg(lo)` (or equivalently `fg(lo) + bg(default)` / reset the background explicitly, e.g. `\x1b[49m`), and treat that full sequence as the value cached in `current`. Symmetrically the transparent branch already emits `RESET` — keep it — so each cell's rendered state is a pure function of its own two pixels and never of the preceding cell.

## 2. Ghost pixels of the previous (wider) frame

**What the renderer drops.** The last line of `renderSpriteRows`: `let row = out.replace(/[ ]+$/, '')` — every run of trailing spaces (transparent cells) is stripped from each row string, and only that trimmed row is emitted.

**What the text pipeline does with trailing whitespace.** A terminal never implicitly erases the rest of a physical line when a written line ends early. Because the renderer also never emits an erase-to-end-of-line sequence (`\x1b[K` / `EL`) and never pads cells with the background color, the columns beyond the trimmed row keep whatever glyphs the previous frame painted there. Hence `symptom-log.txt` item 2: switching from the wide tail pose to a narrower pose leaves the "surplus columns ... showing the previous frame's tail", while the narrow frame itself renders fine.

**Two-part fix.**
1. **Erase what you don't draw:** after trimming (or instead of relying on trimming), append `\x1b[0m\x1b[K` (reset SGR, then erase-to-end-of-line) to every emitted row — or render the trailing transparent cells as spaces painted with the default background. Either way each frame fully owns its whole row width.
2. **Don't trim into ambiguity / clear per switch:** either keep the rows at fixed sprite width (40 columns, padding transparent cells as explicitly-reset spaces) so row length is frame-invariant, or have the animation frame-switch clear the sprite region (cursor-home + `EL` per row, or a region erase) before blitting the new frame. Both parts together guarantee no column survives a wide→narrow switch.

## 3. Frame data drift (hand-ported frames)

**What the digest report says.** `frames-digest-report.txt` hashes each frame's 25 rows against the source art: all frames OK except **`tail2` = MISMATCH**, with **23 differing cells**, all in the upper-right spout/tail-tip area — e.g. row 2: "ported D at col 26, source D at col 27 (1 col left shift)"; row 3: "ported extra D at col 25; DBD at cols 26-28 shifted left 1; extra DD at cols 36-37"; rows 4–6: "the upper-right cluster is shifted 1 column left throughout". This is the misplaced 6-pixel tail-tip cluster in `symptom-log.txt` item 3. The report states the cause: "The ported tail2 was hand-copied during conversion."

**Why the existing regression missed it.** Per the digest report, the existing test was an "excerpt-based regression (added later for a different frame) did not cover it" — it asserted only a hand-picked excerpt of one other frame, so tail2's shifted cluster never entered any assertion.

**The gate.** Pin every frame with a content digest: the sha256-per-frame comparison already in the report should run as a CI check that (a) covers **all** frames in the sprite set, not excerpts, (b) compares against a committed digest manifest of the source art, and (c) fails loudly on any byte difference, forcing hand ports to be regenerated/verified against the source art. Any new or edited frame must update the manifest through review.

## 4. The CI hang (finished job that never exits)

**Mechanism.** From `ci-hang-evidence.txt`: job "channel-ui" shows "PASS for all scene checks, then the process sits idle". At kill time there is "no running test, no pending assertion; the event loop has live handles of kind Timeout — one per tick of the sprite animation planner, each re-arming the next." The planner "reschedules a `setTimeout` for as long as its component stays mounted" — a self-perpetuating timer chain that keeps the Node.js event loop's ref-count non-empty, so the process never exits even though all work is done, until the runner timeout kills it (previously ~3 minutes; one local observation idled 19 minutes).

**Which hosts.** The CI test hosts: "these particular hosts mount the header component and finish WITHOUT unmounting it" — so the planner's unmount-driven timer teardown never runs.

**Why the interactive terminal is unaffected.** Its process is "kept alive by the TTY/stdin handles regardless of the timer chain" — the app is meant to stay alive, and teardown happens on real exit; the stray timers change nothing user-visible.

**One-line fix.** Unmounting must clear the timer: in the component's unmount/cleanup path call `clearTimeout` (or return a disposer that clears it) for the planner's pending tick — i.e. make the planner's `setTimeout` chain cancel itself on unmount so no orphaned Timeout handle outlives the component.

## 5. Prevention

**Renderer contract checklist** (ship with any terminal half-block sprite renderer):
- **SGR self-containedness:** every emitted cell's fg+bg state is a function of that cell only; any branch that sets only one of fg/bg explicitly resets the other (or emits `RESET` first). No branch relies on inherited SGR state.
- **Dedup cache correctness:** the run-length cache compares the *full* SGR sequence, including resets; state carried across cells is always intentional.
- **Row ownership:** each row either covers its full width or ends with `RESET + \x1b[K` (erase-to-EOL); no transparent cell is ever rendered as an implicit no-op.
- **Frame-switch erase semantics:** switching to a narrower frame erases or overwrites every column the widest frame ever touched (fixed-width padding or explicit region clear).
- **Frame data integrity:** every frame is digest-pinned (sha256 per frame) against the source art in a committed manifest; the digest check covers all frames and runs in CI; hand ports are prohibited or verified by the digest.
- **Glyph packing correctness:** upper pixel → fg of `▀`, lower pixel → fg of `▄` (or bg of `▀`), documented and snapshot-tested.
- **Lifecycle:** every timer/interval the renderer or its animation planner starts is registered with a disposer cleared on unmount/stop; no orphaned event-loop handles in headless runs.

**Pre-flip rollout audit** (before turning an animation feature default-on):
1. Run the headless/CI suite in exactly the default-on configuration and verify the test process **exits** on its own (assert zero remaining event-loop handles, e.g. `process._getActiveHandles()`-style check or a watchdog), not just that checks PASS — "PASS then idle" is a hang.
2. Audit every new timer/interval for paired teardown on unmount, including hosts that mount without unmounting (test harnesses, snapshot renderers).
3. Re-run the full frame digest check against the source-art manifest — the flip must not ship with any MISMATCH frame (today: tail2, 23 cells).
4. Exercise wide→narrow frame switches and right-edge transparent-column cases in a snapshot/emulator that compares rendered screen cells (not emitted strings), so phantom/ghost pixels are caught before users see them.
5. Confirm interactive and headless hosts behave identically with respect to teardown, since TTY handles can mask timer leaks.
