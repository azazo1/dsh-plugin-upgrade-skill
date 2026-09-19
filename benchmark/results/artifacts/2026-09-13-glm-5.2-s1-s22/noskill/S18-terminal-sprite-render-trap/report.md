# S18 · The Terminal Sprite Render Trap — Report

Evidence base: `renderer-excerpt.ts` (renderer as shipped), `symptom-log.txt`,
`frames-digest-report.txt`, `ci-hang-evidence.txt` (all read in full, unmodified).
The sprite is 25 pixel rows × 40 columns; each terminal cell packs two vertical pixels
into one half-block glyph (foreground = upper pixel, background = lower pixel),
producing 13 terminal rows.

---

## 1. Phantom pixels at the sprite's right edges

### Mechanism

SGR color state is **persistent terminal-wide state**: `38;2;r;g;b` (fg) and
`48;2;r;g;b` (bg) stay in effect until explicitly changed or reset. The renderer
tracks only what *it* last emitted, in the local variable `current`, and emits codes
only on change:

```ts
if (seq !== current) {
  out += seq === '' ? RESET : seq
  current = seq
}
```

For a **half-filled** cell the code emits only *one* of the two colors:

- `up` present, `lo` absent → `seq = fg(up)`, glyph `▀`. The glyph body (upper half)
  is correct, but the cell's **background — the empty lower half — is whatever bg the
  terminal still has set** from an earlier cell.
- `lo` present, `up` absent → `seq = fg(lo)`, glyph `▄`. The upper half of that cell
  is the cell background, again inherited.

So the empty half of a half-filled cell is painted with the stale color left behind by
the last fully-filled cell (any cell where both pixels existed emitted `fg+bg`).

### Which cells expose it

Exactly the half-filled cells along the sprite's right edges — precisely where the
symptom log reports the artifacts:

- the **dark outline** cells (outline pixel on top, transparent below, after interior
  pair-cells that set both fg and bg);
- the **sleep-Z symbols** (isolated top-row pixels with transparent lower pixels);
- the **right edge of the heart glyph** (single-pixel-wide edge columns).

In every case the cell to the left was fully filled and left `bg` set; the half-filled
edge cell inherits it, and the empty half renders as a dim block of stale color — the
"1-cell-wide column of dim colored noise" that moves with the animation, because each
frame's edge cells sit at different columns. The artifacts are not in any frame's data
(frame rows end in `.` there) — they are pure SGR-state leakage. (Fully-empty cells are
safe: `seq = ''` emits `RESET` on transition, clearing both colors — the bug only hits
half-filled cells, whose `seq` sets one color and leaves the other armed.)

### Precise escape fix

Make every non-blank cell **fully specify both halves** instead of relying on the
terminal default for the absent pixel:

- `up` only: `seq = fg(up) + '\x1b[49m'` (49 = default background) — or explicitly
  `bg` of the sprite's erase color;
- `lo` only: `seq = fg(lo) + '\x1b[49m'` (the '▄' upper half is the cell background);
- both: `fg(up) + bg(lo)` (unchanged);
- neither: `''` → `RESET` (unchanged).

With every `seq` self-contained, the `seq !== current` change-detection becomes sound:
no cell can inherit a color it did not emit.

---

## 2. Ghost frames after switching to a narrower frame

### Mechanism — two compounding causes

**(a) The renderer drops trailing cells.** After building each row it trims:

```ts
let row = out.replace(/[ ]+$/, '')
```

A narrow pose produces rows that are simply *shorter* — the renderer never emits
anything for the columns where the wide pose previously drew the tail.

**(b) The text pipeline strips trailing whitespace.** Even if the renderer emitted
trailing spaces to overwrite the old tail, the write pipeline discards
trailing-whitespace-only content (a row whose only difference from the previous frame
is trailing blanks is treated as unchanged / trimmed before reaching the terminal).
Space-based erasure therefore never reaches the terminal.

Result: on a wide → narrow frame switch, the narrow frame renders correctly, but the
surplus right-hand columns are never repainted or erased, so the previous frame's tail
pixels stay on screen at their old positions — the ghost tail.

### Two-part fix that guarantees a clean frame switch

1. **Erase with explicit escape sequences, not spaces.** After writing each row's
   content, emit `\x1b[K` (EL — erase to end of line) with default SGR state. EL is
   unaffected by whitespace trimming: the terminal itself clears everything to the
   right of the new content, no matter how much shorter the row got.
2. **Erase the previous frame's full extent.** Track the bounding box / per-row width
   actually drawn for the *previous* frame, and on every frame switch erase the union
   of the previous and current extents (per-row `\x1b[K` after the new content, or
   `\x1b[2K`/`\x1b[J` over the sprite area before redrawing). This makes the switch
   correct even for transitions the pipeline would classify as "row only got shorter".

Together: content never relies on trailing spaces surviving the pipeline, and nothing
a previous frame drew lies outside what the erase covers.

---

## 3. Frame data drift (tail2)

### What the digest report says

Of all frames, only **tail2 MISMATCH**es the source art. The hand-ported tail2 (copied
by hand during conversion) differs in **23 cells, all in the upper-right spout/tail-tip
area**: the cluster is shifted **1 column left** throughout (row 2: ported `D` at col
26 vs source col 27; row 3: extra `D` at col 25, `DBD` at 26–28 shifted left, stray
extra `DD` at cols 36–37; rows 4–6 shifted left 1). This is exactly the "misplaced
6-pixel tail-tip cluster" in symptom 3.

### Why the existing regression missed it

The regression in place was **excerpt-based** and was added later for **a different
frame** — it asserted on a hand-picked excerpt of one other frame's rows, so tail2 had
no coverage at all. Excerpt-based pinning only catches drift in the excerpt; a 1-column
shift plus stray pixels outside the excerpt passes silently.

### Gate that prevents recurrence

Pin **every frame by full-content digest**: sha256 over each frame's complete 25 rows,
compared in CI against digests derived from the source art (a checked-in golden digest
manifest, or — stronger — auto-generating the frames from the source art so no hand
port exists). Any hand edit, column shift, or stray pixel then fails the build
regardless of which frame or which region drifted. (Complement with the visual
regression of §2's frame-switch test so drift and rendering are both pinned.)

---

## 4. The CI hang ("finished but hanging")

### Mechanism

The animation planner drives each tick with `setTimeout` and **re-arms a new timeout
for the next tick for as long as its component stays mounted**. Each live `Timeout`
handle **refs the Node event loop**, so the process cannot exit while the chain
continues — even though every scene check has already PASSED and there is no running
test or pending assertion. The process state at kill confirms it: idle, no test, and
live handles of kind `Timeout`, one per planner tick, each re-arming the next.

The **channel-ui CI hosts mount the header component and finish without unmounting it**,
so the planner never stops rescheduling. After the animation feature flipped
default-on, those hosts gained a permanently re-arming timer chain; the job that always
finished in ~3 minutes now idles until the runner kills it (one observation: 19 minutes).

**Why the interactive terminal is unaffected:** its process is kept alive by its
TTY/stdin handles regardless of the timer chain — the animation timer adds no *new*
keep-alive there, and the product runs until the user exits, so the re-arm-forever
behavior was invisible in interactive use and only became observable in short-lived CI
processes.

### One-line fix

Make the animation timer **unref'd** so it never keeps the event loop alive:

```ts
setTimeout(tick, interval).unref()
```

(Equivalently, ensure hosts unmount/dispose the component — but the unref is the
one-line, host-independent fix.)

---

## 5. Prevention

### Renderer contract checklist (ship with any half-block sprite renderer)

1. **Self-contained SGR per cell.** Every non-blank cell emits both fg and bg (using
   `39m`/`49m` or an explicit erase color for absent pixels); never rely on SGR state
   persisting across cells. Change-detection must compare full color pairs.
2. **Blank cells reset.** Transparent cells paint as `RESET` + space (or are covered
   by erase), never as bare spaces inheriting state.
3. **Erase via escapes, not spaces.** `\x1b[K` after each row (and `\x1b[J` over the
   sprite area on teardown); never depend on trailing spaces surviving a pipeline that
   trims trailing whitespace.
4. **Frame-switch extent rule.** On every frame switch, erase the union of the previous
   and current frames' drawn extents; test explicitly wide→narrow, narrow→wide, and
   equal-width transitions.
5. **Frame data integrity gate.** Full-content digest (sha256 of all rows) of *every*
   frame against source art in CI; prefer generating frames mechanically over hand
   porting; excerpt assertions are supplementary, never the only pin.
6. **Timer ownership.** Every animation timer is either disposed on unmount or
   `unref()`'d; no scheduler handle may outlive its component or keep the event loop
   alive after the owning work finishes.
7. **Edge-case frames in visual tests.** Frames whose edges are half-filled cells
   (single-pixel outlines, isolated glyphs like Z/heart) are in the test matrix, since
   they are exactly where SGR leakage surfaces.

### Audit to run BEFORE flipping an animation feature default-on

1. **Host inventory:** enumerate every host (CI jobs, tests, embedded surfaces) that
   mounts the animated component; verify each unmounts/disposes it — or that its
   timers are unref'd.
2. **Event-loop hygiene check:** run each affected CI job with an active-handle
   assertion at job end (e.g. `process._getActiveHandles()` / why-is-node-running) so
   any lingering `Timeout` fails the job instead of hanging it.
3. **Digest gate green:** all frame digests pass (full-content, all frames) — no known
   MISMATCH like tail2 ships behind a default-on animation that renders every frame.
4. **Visual regression of transitions:** ghost-frame test (wide→narrow) and
   right-edge-phantom test pass with the new default.
5. **Wall-time guard:** measure job duration before/after the flip; alert on any
   significant regression (the 3 min → timeout jump here).
6. **Interactive vs headless diff:** confirm the feature behaves identically where the
   process lifetime differs (TTY-kept-alive vs short-lived CI), since default-on
   changes which hosts run the animation at all.
