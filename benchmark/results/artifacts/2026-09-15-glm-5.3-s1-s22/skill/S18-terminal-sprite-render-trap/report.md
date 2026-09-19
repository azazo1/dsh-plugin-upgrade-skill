# S18 · The Terminal Sprite Render Trap — Read-Only Diagnosis Report

Task: S18-terminal-sprite-render-trap (benchmark, unattended, BENCHMARK-AUTH-v1).
Skill: plugin-upgrade, Mode A (inspect / read-only diagnosis). No files outside the
designated output directory were written; the fixture was only read.

Evidence used (all under `environment/fixture/`, read-only):
- `renderer-excerpt.ts` — the half-block sprite renderer as it shipped
- `symptom-log.txt` — phantom/ghost pixel positions
- `frames-digest-report.txt` — per-frame sha256 vs source art
- `ci-hang-evidence.txt` — channel-ui job that stopped exiting after the default flip

Framework mapping: sprite = 25 pixel rows × 40 columns of palette chars ('.' = transparent);
each terminal cell packs two vertical pixels into one glyph (13 terminal rows per frame).

---

## 1. Phantom pixels at the sprite's right edges

### Mechanism

The renderer tracks only the *last emitted SGR string* (`current`) and emits a new
sequence only when it changes:

```ts
if (seq !== current) {
  out += seq === '' ? RESET : seq
  current = seq
}
```

For a **half-filled** cell it emits a sequence that colors only *one* half of the glyph:

- upper pixel set, lower transparent: `seq = fg(up)`, `ch = '▀'`
- lower pixel set, upper transparent: `seq = fg(lo)`, `ch = '▄'`

SGR state is **persistent per row** (it is a terminal-wide modal attribute, not
per-character). Two consequences combine into the phantom:

1. The **background color set by an earlier, fully-filled cell still applies** when the
   renderer later emits only `fg(...)` for a half-filled cell. Emitting `fg(up)`
   does not touch the current SGR background.
2. The *empty* half of a half-block glyph is painted with the **current background**,
   not with "nothing": for `'▀'` the lower half is the bg color; for `'▄'` the upper
   half is the bg color.

So the empty half of the glyph shows whatever `bg(...)` was last set earlier in the
row — a dim stale color. Because the row's transparent run only triggers `RESET` when
the cell becomes *fully* transparent (`seq === ''`), half-transparent edge cells keep
the stale bg alive.

### Which cells expose it

Exactly the cells where **exactly one of `up`/`lo` is defined** *after* an earlier
cell in the same row has set both fg and bg — i.e. the sprite's right edges where the
art tapers off asynchronously:

- the **dark outline** column: outline pixels in the upper half with transparent ('.')
  lower half (frame rows end in '.' there, per the symptom log);
- next to the **sleep-Z symbols** and to the right of the **heart glyph** — same
  one-pixel-set taper;
- they "appear and move with the animation" because each frame tapers at slightly
  different columns, so the stale-bg half-cells land at different positions per frame.
  They are not in any frame's data — they are rendered SGR residue.

### Precise escape fix

Give the empty half of every half-filled cell an **explicit background** instead of
inheriting the stale one — emit the default-background escape `ESC[49m` (or the app's
known terminal background as `bg(termBg)`) alongside the fg:

```ts
} else if (up !== undefined) {
  seq = fg(up) + '\x1b[49m'   // lower half = default bg, not stale bg
  ch = '▀'
} else if (lo !== undefined) {
  seq = fg(lo) + '\x1b[49m'   // upper half ('▄' gap) = default bg
  ch = '▄'
}
```

Equivalently, end every color *run* (not just the row) with `RESET` before switching
glyph kinds; the minimal, precise fix is the explicit empty-half background above. Note
the existing trailing `row += RESET` does not help — it runs after the damage.

---

## 2. Ghost pixels of the previous frame after switching to a narrower frame

### What the renderer drops

```ts
let row = out.replace(/[ ]+$/, '')
```

Every row is **right-trimmed**: trailing transparent cells (rendered as plain spaces)
are stripped, and the row is only padded with a trailing `RESET`.

### What the text pipeline does

Terminal text pipelines (and any wrapping/scrolling layer) treat **trailing whitespace
as non-existent** — they do not write, move through, or overwrite cells past the last
non-space glyph. When the new frame is *narrower* (tail tucked in), the emitted row
simply ends earlier; the columns beyond the last glyph of the new row are **never
touched**, so the previous wide pose's tail pixels remain on screen at their old
positions. The renderer never erases the frame region; it only paints where it has
glyphs.

### Two-part fix that guarantees a clean frame switch

1. **Erase to end of line every frame**: after the last glyph of each row (and before/with
   the `RESET`), emit `ESC[K` (EL — erase to end of line). That clears any surplus
   columns left by a wider previous frame regardless of trimming:
   ```ts
   row += RESET + '\x1b[K'
   ```
2. **Do not rely on trimming for correctness** (or stop trimming): either emit every row
   padded to the full 40-column sprite width with reset-colored spaces, or keep the trim
   purely as a byte optimization *after* adding `ESC[K`. Optionally also `ESC[2K`
   (or repaint the full previous bounding box) when a frame can also shrink in *row*
   count.

With both, a narrow frame overwrites its own cells and explicitly clears everything to
the right; no previous-frame residue can survive.

---

## 3. Frame data drift (tail2)

### What the digest report says

`tail2` is the only MISMATCH among 22 frames: **23 differing cells**, all in the
upper-right spout/tail-tip area — the ported frame's upper-right cluster is shifted
**1 column left** (row 2: D at col 26 vs source col 27; rows 4–6 shifted throughout),
plus extra pixels (extra `D` at col 25 row 3, extra `DD` at cols 36–37). It was
**hand-copied during conversion** — a transcription drift, not a rendering bug. The
misplaced 6-pixel cluster the user saw is that shifted tail tip.

### Why the existing regression missed it

The regression was **per-excerpt and added later for a different frame**: it asserted an
excerpt of one frame's rendering, so `tail2` (and most of the corpus) had no coverage
at all. An excerpt-based check verifies a rendering property, not the ported data, so a
whole-frame transcription shift passes silently.

### The gate that prevents recurrence

A **whole-corpus per-frame digest gate**: sha256 of each frame's full 25 rows (as the
digest report computes) compared against digests derived from the source art, asserted
for **every** frame in the suite — any MISMATCH fails the build. Adding a new frame
requires regenerating the digest manifest from the source art, never by hand.

---

## 4. The CI hang ("finished but not exiting")

### Mechanism

Per `ci-hang-evidence.txt`: all scene checks PASS, then the process sits idle with
**no running test and no pending assertion** — but the event loop holds live handles of
kind **Timeout, one per animation tick, each re-arming the next**. The animation
planner schedules `setTimeout(nextTick)` for as long as its component stays mounted.
Node exits when the event loop drains; a self-re-arming timer chain means the loop
**never drains**, so the job never exits and is killed at the runner timeout (~3 min
normally; one observed 19 min idle). It appeared exactly in the push that flipped the
animation feature **default-on**, which is why previously-always-green hosts started
mounting (and animating) the header.

### Which hosts mount without unmounting

The **channel-ui test hosts**: they mount the header component (which now starts the
planner by default) and finish their scene checks **without unmounting it**, leaving
the planner's timer chain armed.

### Why the interactive terminal is unaffected

Its process is intentionally long-lived: **TTY/stdin handles** keep the event loop busy
independently of the timer chain, so it never relies on loop drainage to exit. The
timer chain adds one more keep-alive handle to a process that already has them — no
observable change.

### One-line fix

Dispose the planner when the host finishes — e.g. in the test harness teardown:

```ts
afterAll(() => host.unmount(header))   // unmounting stops/clears the planner's timer
```

(Defense-in-depth on the component side: register the timer via `ctx.effect()` /
return the `clearTimeout` disposer so unmount always cancels the re-arm — but the
single line that fixes the observed hang is the teardown unmount.)

---

## 5. Prevention

### Renderer contract checklist (ship with any half-block sprite renderer)

1. **SGR hygiene**: every glyph is fully specified — the empty half of a half-filled
   cell gets an explicit background (`ESC[49m` or the app bg). Never rely on SGR
   state carrying "nothing"; fg/bg persist until reset.
2. **Row-finality**: each row ends with `RESET` **and** `ESC[K` (erase-to-EOL) so a
   narrower frame cannot leave previous-frame residue; full-width padding or `ESC[2K`
   when rows can shrink vertically.
3. **No whitespace-dependent clearing**: trailing-space trimming is a byte optimization
   only; correctness must not depend on the text pipeline writing trailing spaces
   (it won't).
4. **Frame data integrity**: whole-frame digests (sha256 of all rows) pinned against
   the source art for every frame; excerpt tests are additional, never a substitute.
5. **Effect ownership**: every timer/animation loop is registered as a reversible
   effect (`ctx.effect` / disposer) so unmount always stops the chain; a mounted
   component must not keep the event loop alive after its host is done.
6. **Determinism**: identical frame + palette → byte-identical output (snapshot-testable).

### Audit before flipping an animation feature default-on

1. **Inventory every host** that mounts any component containing the animated sprite
   (product interactive host *and* every test/CI host), and confirm each one either
   unmounts/disposes it or is intentionally long-lived.
2. **Event-loop audit**: grep for `setTimeout`/`setInterval` in the feature's path;
   verify each has a teardown path that actually clears the *re-arm*, not just the
   current tick.
3. **Frame-corpus gate green**: all per-frame digests OK (this alone would have caught
   nothing here — but tail2 must be fixed and pinned before the flip ships the
   misplaced tail to every user).
4. **Edge-art audit**: render frames with tapered/asynchronous right edges and check
   the empty halves of half-filled cells for stale-color phantoms (the exact symptom
   class in §1).
5. **Frame-transition matrix test**: render every adjacent (and wide→narrow worst-case)
   frame pair onto a virtual buffer and assert zero residual cells from the previous
   frame.
6. **CI canary**: run the affected job group with the default flipped *before* the
   release flip lands, and treat "passes but doesn't exit" as a failure (runner
   timeouts, not green checkmarks).

---

## Status

- **Completed**: full read-only diagnosis of all five questions from the shipped
  renderer source and the three evidence files; report written.
- **Skipped**: no code changes, migrations, installs, or executions (Mode A read-only
  per skill and brief); fixture untouched.
- **Pending/residual risk**: none blocking this report. The recommended fixes (§1–§4)
  are stated as exact escapes/one-liners but not applied, per the read-only scope.
- **Rollback**: not applicable — nothing was modified.
