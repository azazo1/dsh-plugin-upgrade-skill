# S18 · Terminal Sprite Render Trap — Diagnostic Report

Evidence pack: `fixture/` (README.md, renderer-excerpt.ts, symptom-log.txt, frames-digest-report.txt, ci-hang-evidence.txt). All findings below are grounded in those files.

---

## 1. Phantom pixels at the sprite's right edges

**Mechanism (from `renderer-excerpt.ts`).** The renderer packs two vertical pixels per cell into a half-block glyph: foreground = upper pixel, background = lower pixel. SGR state is **persistent** in a terminal: once `ESC[48;2;r;g;bm` (background) is emitted, every following cell keeps that background until it is explicitly changed or reset. The renderer exploits this with a diff emitter (lines 35–38): it only emits an SGR sequence when `seq !== current`, and it emits `RESET` (`ESC[0m`) only for the "both transparent" case.

The bug is in the two single-sided branches:

- Line 25–27, `up !== undefined` only: emits `seq = fg(up)` and glyph `'▀'`. The ▀ glyph paints only the **upper** half; the **lower half of the cell** is left showing whatever background SGR is still active — the background of the previous cell.
- Line 28–30, `lo !== undefined` only: emits `seq = fg(lo)` and glyph `'▄'`. The ▄ glyph paints only the **lower** half; the **upper half** is left showing the stale background — and critically, this branch's `seq` contains **no background set at all**, so the diff emitter (line 35) does not change the background state either.

**Which cells expose it.** Exactly the cells the symptom log describes: cells where one half is a drawn pixel and the other half is transparent ('.'). At the sprite's **right edges**, the dark outline's bottom pixel typically extends one row below the top pixel, so the renderer hits the `lo`-only branch (▄, empty upper half) right after a fully-painted cell that set a dark `48;2` background. The stale dark background then fills the empty upper half as a dim phantom pixel — "directly to the right of the dark outline cells, next to the sleep-Z symbols, and to the right of the heart glyph" (`symptom-log.txt` item 1). The log confirms the data is clean ("frame rows end in '.' at those columns"), so the pixels are painted, not ported. They "appear and move with the animation" because the stale background is whatever colored cell happened to precede each edge cell in scan order, which shifts per frame.

**Precise escape fix.** Never leave an SGR half unspecified. In both single-sided branches, emit the full state for the empty half:

- `up`-only: `seq = fg(up) + '\x1b[49m'` (default background) — or pair the ▀ with an explicit transparent bg.
- `lo`-only: `seq = fg(lo) + '\x1b[49m'` — the missing `49m` (background default) is what lets the neighbor's `48;2` survive.

Equivalently, reset both planes and re-emit: `seq = RESET + fg(...) + bg(transparent)`. After the fix, the diff emitter compares complete fg+bg state, so a transparent half always clears the carried background instead of inheriting it.

---

## 2. Ghost pixels of the previous frame after switching to a narrower frame

**What the renderer drops.** Line 41: `let row = out.replace(/[ ]+$/, '')` — every row string has its **trailing space cells stripped** before emission. On a wide pose (tail swung out), the tail's rightmost cells are fully-painted; on the narrower pose, those columns fall into the transparent ' ' case, get emitted as spaces, and are then trimmed off the row entirely.

**What the text pipeline does.** The trimmed row is simply shorter, so nothing — neither the renderer nor the line-writing pipeline — writes anything at the surplus columns, and no erase is issued. Terminals are over-write devices: cells are only changed when characters are drawn at them. The old wide-tail pixels at columns beyond the narrow frame's last written column are therefore never touched and remain on screen — exactly `symptom-log.txt` item 2: "the narrow frame renders fine, but the surplus columns keep showing the previous frame's tail."

**Two-part fix that guarantees a clean frame switch.**

1. **Stop shrinking rows**: emit the full sprite width (40 columns) every frame — trailing transparent cells are written as background-cleared spaces (with the SGR fix from item 1 so they don't inherit color), rather than being trimmed by `replace(/[ ]+$/, '')`.
2. **Erase what you don't write**: after the `RESET` on line 42, append an erase-to-end-of-line sequence, `ESC[0K` (Erase in Line, right), to each row. Even if a row is ever shorter than what a previous frame painted, the EL explicitly clears the remainder of that terminal line. Full-width rows + per-row `ESC[0K` makes a frame switch idempotent regardless of what was on screen before — no residue is possible.

---

## 3. Frame data drift (hand-ported `tail2`)

**What the digest report says.** `frames-digest-report.txt` compares sha256 of each frame's 25 rows against the source art: all frames OK except **`tail2` — MISMATCH**. Detail: the upper-right spout/tail-tip cluster is shifted **1 column left** throughout (row 2: D at col 26 vs col 27; row 3: extra D at col 25, DBD shifted left 1, extra DD at cols 36–37; rows 4–6 shifted left 1) — **23 differing cells total**, all in the upper-right cluster. This is the "6-pixel cluster drawn at the wrong position" of `symptom-log.txt` item 3. The report states the cause directly: "The ported tail2 was hand-copied during conversion."

**Why the existing regression missed it.** The report: the per-excerpt regression was "added later for a different frame" — it asserts hand-picked excerpts, and `tail2` was simply not among the covered frames. Excerpt-based tests only pin the cells someone thought to look at; a wholesale hand-copy error outside those excerpts passes green.

**The gate that prevents recurrence.** A whole-frame digest gate: for **every** frame, compute the sha256 of its 25 rows (exactly what the digest report already does) and compare against the source-art digests in CI, failing the build on any mismatch. This is precisely the check that caught `tail2` post-hoc — promoting it from a manual report to an executed CI gate covering all frames (no excerpts, no omissions) pins the ported data to the source art permanently. Any future hand-edit or conversion drift is rejected at build time with the per-row/per-cell diff the report already shows how to produce.

---

## 4. The CI hang ("finished but never exits")

**Mechanism (from `ci-hang-evidence.txt`).** The `channel-ui` job shows **PASS for all scene checks**, then sits idle and is eventually killed at the runner timeout (historically ~3 minutes; one local observation idled 19 minutes before a manual kill). At kill: "no running test, no pending assertion; the event loop has live handles of kind **Timeout** — one per tick of the sprite animation planner, each **re-arming the next**." The planner reschedules a `setTimeout` for as long as its component stays mounted, and **the CI hosts mount the header component and finish WITHOUT unmounting it** — so the self-rescheduling timer chain never stops, and those pending Timeout handles keep the Node event loop alive after the test suite has completed. The hang first appeared "in the same push that flipped the animation feature's default from off to on": with the feature off, no planner timer ever existed, so nothing pinned the loop.

**Why the interactive terminal is unaffected.** Per the evidence: the interactive terminal product's process is kept alive by its **TTY/stdin handles regardless of the timer chain** — the process is meant to run until the user quits, so extra live timers are invisible. Only the short-lived CI host process, whose correct terminal state is "zero live handles → exit," exposes the leak.

**One-line fix.** Mark the animation timer non-keeping: call `.unref()` on the planner's `setTimeout` handle (one line), so the re-arming chain no longer holds the event loop open; a properly-unmounted component plus unref covers both host shapes.

---

## 5. Prevention

### Renderer contract checklist a terminal sprite implementation should ship with

1. **No half-specified SGR state**: every emitted cell sets both planes it doesn't paint as explicitly default (`39`/`49`), or the diff key covers full fg+bg+glyph state. A transparent half must never inherit a neighbor's color. (Item 1)
2. **Full-width rows, every frame**: no trailing-cell trimming; transparent pixels are drawn as cleared cells, so frame N+1 overwrites every column frame N touched. (Item 2)
3. **Explicit erase semantics**: emit `ESC[0K` (or full-row clear) after each row / before each frame so a narrower frame can never leave residue from a wider one. (Item 2)
4. **Reset at row end**: every row terminates in `ESC[0m` (the shipped line 42 does this — keep it) so state never leaks past the sprite.
5. **Frame data pinned to source**: every frame's content is digest-verified (sha256 per frame) against source art in CI; excerpts are tests, digests are the gate. (Item 3)
6. **Bounded lifetime of animation timers**: animation ticks are `unref()`'d (or otherwise not keep the event loop alive) and are torn down on unmount via a registered disposer. (Item 4)
7. **Odd-height handling defined**: a 25-row sprite yields 13 cell rows; the last half-pair renders the missing lower row as transparent (the `?? ''` on line 14) — the contract states this, and the transparent half follows rule 1.

### Audit to run BEFORE flipping an animation feature default-on

1. **Timer lifecycle sweep**: enumerate every timer/interval the feature creates; verify each is (a) disposed on unmount AND (b) `unref()`'d or registered so a host that mounts-without-unmount can still exit with zero live handles. Test: run a headless host that mounts the component, finishes, and asserts process exit within a bounded time.
2. **Host-shape inventory**: list every host that mounts the component (CI scene hosts, interactive TTY, web). For each, ask "what keeps this process alive?" — the CI evidence shows CI hosts expose leaks that TTY hosts mask.
3. **Render-diff audit on feature-on**: capture frames with the feature on vs off; assert the on-frames differ only in intended animation cells (this is what surfaces the phantom-pixel SGR leak — new artifacts appear exactly at cell edges adjacent to painted cells).
4. **Data integrity gate active**: the whole-frame digest gate must pass for every frame the animation will show before rollout (it would have caught `tail2`'s 23-cell drift first).
5. **Rollback readiness**: keep the previous default one flag-flip away and record the CI job baseline runtime, so a "PASS but never exits" regression is instantly attributable to the flip (the evidence's own timeline did this).
