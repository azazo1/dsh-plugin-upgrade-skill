# S18 · The Terminal Sprite Render Trap — Analysis Report

Evidence base (read-only): `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`, `ci-hang-evidence.txt`.
Sprite: 25 pixel rows × 40 columns of palette chars (`.` = transparent), packed 2-vertically into 13 terminal rows via half-block glyphs (`▀` fg=upper/bg=lower, `▄` fg=lower/bg=upper).

---

## 1. Phantom pixels — stale SGR background painting the EMPTY half of a half-filled cell

### Mechanism

SGR escape sequences are **cell-cursor state, not per-cell attributes**: once emitted, `38;2` (fg) and `48;2` (bg) stay in effect for every subsequent cell until replaced or reset. The renderer tracks only its *own* notion of "current" (`current`) and emits a partial sequence whenever a cell is half-transparent:

```ts
} else if (up !== undefined) {
  seq = fg(up)      // ▀ with fg=upper pixel — background NOT set
  ch = '▀'
} else if (lo !== undefined) {
  seq = fg(lo)      // ▄ with fg=lower pixel — background NOT set
  ch = '▄'
}
```

A `▀` glyph paints its **lower half with the current background**; a `▄` paints its **upper half with the current background**. For a half-transparent cell the renderer never sets a background, so the empty half inherits whatever `48;2;...` is still armed.

Concretely, walking a right-edge column: cell A (outline body, both pixels opaque) emits `fg(up)+bg(lo)`; cell B (sprite tapering — upper pixel opaque, lower `. `transparent) emits only `fg(up)` + `▀`. Cell B's lower half — a pixel whose frame data says *transparent* — is rendered in **cell A's background color**. The `seq !== current` comparison compares only the emitted string, so it cannot detect that the *unmentioned* bg channel changed meaning. The full-transparent branch does emit `RESET`, but only *after* the damage: the phantom is already inside cell B, and the reset lands on cell C.

### Which cells expose it

Exactly the half-filled cells (one vertical pixel opaque, the other transparent) that **follow a fully-opaque cell** on the same terminal row — i.e. every column where the sprite's silhouette steps in or down. On the whale that is the one-cell-wide column hugging the dark outline's right edge, the cells beside the sleep-Z glyphs, and the cells right of the heart glyph — matching the symptom log's "1-cell-wide column of dim colored noise" that "appears and moves with the animation" (different frames taper at different columns, so the stale-bg color and position change per frame, and no frame's data contains those pixels — frame rows end in `.` there).

### Precise escape fix

Never rely on inherited background for the empty half: make every emitted cell carry an **explicit background**. In the half-filled branches emit the canvas/terminal background color for the empty half:

```ts
} else if (up !== undefined) {
  seq = fg(up) + bg(CANVAS_BG)   // ▀: lower half explicitly canvas-colored
} else if (lo !== undefined) {
  seq = fg(lo) + bg(CANVAS_BG)   // ▄: upper half explicitly canvas-colored
} else {
  seq = bg(CANVAS_BG)            // or RESET — but be consistent, see §2
}
```

i.e. append the `\x1b[48;2;r;g;bm` escape for the panel background to every partial sequence, so no `48;2` from a previous cell can persist into a transparent half. (Equivalent strict form: terminate every run with `RESET` and always emit complete `fg+bg` pairs; the invariant is *no cell ever renders with an SGR channel it did not itself set*.)

---

## 2. Ghost frames — trimmed rows + whitespace-dropping pipeline leave the wide frame's surplus columns unerased

### Mechanism

```ts
let row = out.replace(/[ ]+$/, '')   // trailing transparent cells are DELETED
```

The renderer drops the trailing transparent cells from every row. Transparent cells are emitted as plain ` `, and then the regex strips them, so a rendered row ends at its **last non-transparent pixel**. On a frame switch nothing erases the previous frame's cell area: the renderer writes the new (narrower) rows over the old ones, but only up to the narrow rows' trimmed length. The surplus columns of the WIDE pose (tail fully swung out) are simply never touched again — the narrow frame renders fine and the old tail pixels stay on screen at their old positions. Symptom 2, exactly.

Even if the spaces were kept, the fix would still fail: the **text pipeline strips/trims trailing whitespace** on written lines (both when lines are stored as row strings and at the terminal/VT layer, where trailing blanks with default attributes are not retained as cell state). So "pad with spaces" is not a durable erase — the spaces never reach the terminal as overwriting cells.

### Two-part fix

1. **Explicit erase, not implicit whitespace**: end every rendered row with `\x1b[K` (EL — Erase to end of Line) so the erase is carried by an escape sequence the pipeline cannot trim. Any columns to the right of the new row — including a wider previous frame's tail — are erased by the terminal itself.
2. **Region clear on frame switch**: track the widest/tallest region ever drawn (per-frame bounding box, or the max width seen so far in the animation) and, when switching frames, erase that full region (per-row EL plus `\x1b[J`-style region clear if the frame count of rows can shrink) before drawing the new frame — so a narrow successor can never leave surplus cells outside its own trimmed extent.

Together: each row self-terminates its line (EL) and each frame switch resets the shared canvas region — a clean switch is then guaranteed regardless of trailing-whitespace behavior anywhere in the pipeline.

---

## 3. Frame data drift — hand-ported `tail2` shifted 1 column left; excerpt regression didn't cover it

### What the digest says

`tail2` is the only MISMATCH among all frames (standard/blink/fin1-2/spout1-6/tail1/3/4/heart1-3/sleep1-5 all OK). 23 differing cells, all in the **upper-right spout/tail-tip area**:

- row 2: ported `D` at col 26, source at col 27 (1-column left shift);
- row 3: extra `D` at col 25; the `DBD` cluster at cols 26–28 shifted left 1; extra `DD` at cols 36–37;
- rows 4–6: the upper-right cluster shifted 1 column left throughout.

This is symptom 3: the "misplaced tail tip" is a 6-pixel-ish cluster drawn one column left of where the source art puts it, plus stray extra dark pixels — a classic hand-copy transposition during conversion.

### Why the regression missed it

The existing regression was **excerpt-based**: it asserted a short, hand-picked excerpt of pixel data, and it was written for a *different* frame (added around another frame's change). `tail2` was never in its sample, so a wholesale column shift inside `tail2` passed untouched. Any sampled/partial assertion structurally cannot catch drift in the cells it doesn't sample.

### The gate that prevents recurrence

Pin **every frame's full content** with a digest: compute sha256 over each frame's complete 25 rows and compare against digests derived from the **canonical source art** (not from the ported files — otherwise drift becomes the baseline) for all frames in CI. Any single-cell mismatch, missing frame, or added frame fails the build. The digest report in this pack is exactly that gate's output format; making it a hard CI check (rather than a one-off report) closes the hole, because exhaustive full-content digests have no unsampled region where drift can hide.

---

## 4. The hang — an ever-re-arming setTimeout chain pins the event loop after the tests finish

### Mechanism

From the CI evidence: the job prints PASS for all scene checks, then sits idle (no running test, no pending assertion). At kill time the event loop holds live handles of kind **Timeout — one per tick of the sprite animation planner, each re-arming the next**. The animation planner reschedules `setTimeout` for as long as its component stays **mounted**; the channel-ui hosts **mount the header component and finish without unmounting it**. In Node, a pending `Timeout` is a ref'd handle that keeps the event loop alive — so the process finishes all work, yet can never drain: each timer fires, mounts nothing new, and schedules the next tick, forever. The job is killed only at the runner timeout (~3 min historically; one observed 19 min idle). The hang appeared in the very push that flipped the animation default **off → on**: with the feature off, the planner never started, so the leak existed latently before the flip.

### Why the interactive terminal is unaffected

The interactive terminal process is intentionally long-lived: its **TTY/stdin handles** keep the event loop open regardless of any timer chain, and the process exits on user quit, which unmounts components and stops the planner. In CI there is no TTY and no explicit teardown — only the timer chain remains, and it alone is enough to hold the loop. So the same leak is invisible in interactive use and fatal in batch use.

### One-line fix

Un-ref the animation timer so it never holds the event loop open:

```ts
setTimeout(tick, interval).unref()
```

i.e. call `.unref()` on each handle the planner creates. The animation keeps running whenever anything *else* keeps the process alive (the TTY product), but a finished CI job with only timers left drains and exits normally. (Complementary hygiene — unmounting the header component in host teardown — fixes this host but not the class; `unref()` is the one-line fix.)

---

## 5. Prevention

### Renderer contract checklist (ship with any half-block sprite renderer)

1. **SGR completeness — no inherited channels.** Every emitted cell sets both fg and bg explicitly (empty halves get the canvas background). No cell may render with an SGR channel it did not set; state never crosses a cell boundary unowned.
2. **Explicit erase semantics.** Rows never rely on trailing whitespace to clear: every row terminates with `EL` (`\x1b[K`), and frame switches erase the union region of all frames (widest/tallest extent) before drawing. Whitespace trimming anywhere in the pipeline must be assumed.
3. **Full-content frame pinning.** Every frame's complete pixel grid is pinned by digest against the canonical source art in CI — no excerpt sampling, no ported-file-derived baselines.
4. **Timer discipline.** Any recurring scheduler must `.unref()` its handles and must stop on component unmount; mounted components have a teardown path exercised by tests.
5. **Deterministic cell accounting.** Sprite width × height maps to an exact terminal-cell extent (⌈rows/2⌉ × cols); rendering must never write outside it, and erasing must cover exactly it.
6. **Symptom-oriented golden renders.** A golden test renders edge-tapering frames (right edge, isolated glyphs like Z/heart) into a VT emulator and asserts both glyph and *complete SGR state per cell*, catching phantoms (state leaks) and ghosts (stale cells) at the cell level.

### Pre-flip audit for turning an animation feature default-on

1. **Timer/handle census**: enumerate every timer, interval, listener, and ref'd handle the feature creates; verify each is unref'd or deterministically stopped; grep for `setTimeout`/`setInterval` without `.unref()`/clear in the feature's path.
2. **Lifecycle coverage**: list every host that mounts the component (interactive, CI scene checks, headless/smoke) and confirm each unmounts or tears it down; run the exact CI jobs with the flag forced on *before* the default flips.
3. **Frame-data gate green**: full-digest comparison over all frames against source art passes (this pack's `tail2` would have been caught).
4. **Edge render review**: render the extreme poses (widest and narrowest) and the transition both directions; assert no cells outside the new frame's extent survive (ghost check) and no cell carries a color absent from frame data at that position (phantom check).
5. **Baseline diff of job behavior**: compare event-loop handle dumps and exit latency for affected jobs pre/post flip; a finished-but-not-exiting job is the signature this audit exists to catch.

---

## Verdict summary

| Symptom | Root cause | Fix |
|---|---|---|
| Phantom pixels at right edges | half-filled cells emit fg-only; stale `48;2` bg from the previous opaque cell paints the empty half of `▀`/`▄` | emit explicit `bg(CANVAS_BG)` for empty halves (complete fg+bg per cell) |
| Ghost pixels after wide→narrow switch | `replace(/[ ]+$/, '')` drops trailing erase cells and the pipeline trims trailing whitespace; nothing erases surplus columns | per-row `\x1b[K` + erase the union region on frame switch |
| Drifted frame (`tail2`) | hand-copy shifted upper-right cluster 1 col left (23 cells); excerpt regression sampled a different frame | exhaustive per-frame sha256 digest gate vs canonical source art in CI |
| CI "finished but hanging" | animation planner re-arms `setTimeout` while mounted; channel-ui hosts never unmount; ref'd Timeout chain pins the event loop; interactive product masked by TTY/stdin handles | `.unref()` the planner timer (one line) |
