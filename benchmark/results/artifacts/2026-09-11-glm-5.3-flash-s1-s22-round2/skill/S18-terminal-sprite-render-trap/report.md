# S18 · The Terminal Sprite Render Trap — Diagnostic Report

Evidence pack inspected (read-only): `README.md`, `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`, `ci-hang-evidence.txt`. The fixture was not modified. This is a read-only inspection; no writes, installs, or executions were performed against the pack.

---

## 1. Phantom pixels in the EMPTY half of a half-filled cell

### Mechanism (from `renderer-excerpt.ts`)

Each terminal cell packs two vertical pixels: foreground = upper pixel, background = lower pixel. The renderer builds an SGR sequence per cell:

```ts
if (up !== undefined && lo !== undefined) { seq = fg(up) + bg(lo); ch = '▀' }
else if (up !== undefined)               { seq = fg(up);          ch = '▀' }   // ← bug
else if (lo !== undefined)               { seq = fg(lo);          ch = '▄' }
else                                     { seq = '';              ch = ' ' }
```

The **upper-only branch emits only `fg(up)`** — a `38;2` foreground selector — and never touches the background. SGR state persists across cells in a terminal: whatever background color an *earlier* cell set remains active until explicitly changed or reset. So a cell with a solid upper pixel and a transparent (`'.'`) lower pixel draws `▀` with the correct foreground but with **the background color of some previous opaque cell** — the empty lower half is painted in a leftover color instead of the screen background.

The delta-emission logic makes it position-dependent:

```ts
if (seq !== current) { out += seq === '' ? RESET : seq; current = seq }
```

The upper-only branch's `seq` differs from a solid cell's `fg+bg` string, so the renderer does emit at each state change — but the emitted sequence re-asserts only the foreground. The background plane keeps carrying the last `bg(...)` emitted, potentially many cells back. The `'' → RESET` transition (fully transparent cell) does clear both planes, which is why the noise appears exactly at edge-adjacent cells rather than everywhere. The final per-row `if (!row.endsWith(RESET)) row += RESET` guard only cleans the row tail; it cannot repair mid-row stale background.

### Which cells expose it

Matches `symptom-log.txt` item 1 exactly: "a 1-cell-wide column of dim colored noise directly to the right of the dark outline cells, next to the sleep-Z symbols, and to the right of the heart glyph", appearing and moving "with the animation". These are precisely the sprite's right edges where:

- the upper row of a pair has a solid outline/Z/heart pixel (upper-only branch fires, no `bg` emitted), and
- the lower row of the pair is transparent there (the `.` padding region past the silhouette), and
- the *previous* cell in the scan left a non-default background (the solid body/outline pixel to the left).

The stale background is then visible in the lower half of that edge cell — phantom pixels that are not in any frame's data ("frame rows end in `.` at those columns"). They move with the animation because which cells take the upper-only branch changes per frame.

### Precise escape fix

In the upper-only branch, explicitly reset the background plane:

```ts
seq = fg(up) + '\x1b[49m'   // 49 = default background (or RESET, then fg(up))
```

Every SGR combination the renderer emits must fully specify both planes (or deliberately reset the unused one): solid = `fg+bg`; upper-only = `fg + \\x1b[49m`; empty = `RESET`. (The lower-only branch already re-targets the foreground, so it is safe on the foreground plane, but it too should reset the background for symmetry.)

---

## 2. Ghost pixels of the previous frame surviving a switch to a narrower frame

### What the renderer drops

`renderer-excerpt.ts` trims each rendered row:

```ts
let row = out.replace(/[ ]+$/, '')
```

Transparent cells render as spaces, so on a narrower pose the tail end of every row is trailing spaces — and they are stripped. A wide-pose row that once reached the sprite's full width is re-emitted on the narrow frame as a much shorter string.

### What the text pipeline does to trailing whitespace

The terminal is a stateful character grid: writing a short line updates only the cells the glyphs actually occupy; it does **not** erase cells to the right of what was written. The renderer emits no erase, and its rows are now shorter, so the surplus columns on screen still hold the wide frame's glyphs and colors — the wide tail "REMAINS on screen at their old positions" (`symptom-log.txt` item 2) while the narrow frame itself "renders fine".

### The two-part fix

1. **Emit full-width rows or an explicit erase per row.** Stop dropping trailing transparent cells: pad each row to the sprite's fixed 40-column width with spaces, or append `\x1b[K` (erase to end of line) after each row so everything past the drawn cells is cleared.
2. **Erase the previous frame's footprint on frame switch.** Per-row `\x1b[K` already covers same-row shrinkage; additionally, before drawing a new frame, clear the sprite's bounding region (the union of the previous and current frame extents) — e.g. blank out the previous frame's rows or issue a region clear — so no column the new frame does not address can survive.

Together, every cell the previous frame touched is either overwritten by the new frame or explicitly erased — a guaranteed clean frame switch.

---

## 3. Frame data drift (digest report)

### What the digest report says

`frames-digest-report.txt` hashes each frame's 25 rows against the source art: everything OK except **`tail2    MISMATCH`**. The detail: 23 differing cells, all in the upper-right spout/tail-tip area — row 2: ported `D` at col 26 vs source col 27 (1-column left shift); row 3: extra `D` at col 25, `DBD` at cols 26–28 shifted left 1, extra `DD` at cols 36–37; rows 4–6: the whole upper-right cluster shifted one column left. This is exactly symptom 3's "6-pixel cluster drawn at the wrong position". The report states the cause: "The ported tail2 was hand-copied during conversion" — a manual transcription error.

### Why the existing per-excerpt regression missed it

Per the report: "an excerpt-based regression (added later for a different frame) did not cover it." The regression asserted only a hand-picked excerpt of a *different* frame; `tail2`'s rows — especially its upper-right cluster — were never compared against the source art, so a wholesale 1-column shift plus duplicated cells passed CI silently.

### The gate that prevents recurrence

A **whole-frame digest gate**: for *every* ported frame, compute sha256 over the canonicalized 25 rows and compare against digests generated from the source art (a checked-in golden manifest). Run it in CI as a hard gate; a frame missing from the manifest fails loud (no silent skip — new or changed frames must deliberately update the manifest, with the diff shown). Excerpt tests may remain for readability, but the digest gate is the completeness guarantee: it converts "we tested the frame we thought about" into "every frame is byte-identical to source".

---

## 4. The hang (CI evidence)

### Mechanism

From `ci-hang-evidence.txt`: job `channel-ui` shows **PASS for all scene checks, then the process sits idle** until killed at the runner timeout (previously ~3 minutes; one local run idled 19 minutes before a manual kill). At kill: "no running test, no pending assertion; the event loop has live handles of kind Timeout — one per tick of the sprite animation planner, each re-arming the next." A Node process cannot exit while the event loop holds a live ref'd handle; a self-rescheduling `setTimeout` chain pins it forever even after all work is done.

### Which hosts mount without unmounting

Same evidence: "these particular hosts mount the header component and finish WITHOUT unmounting it" — the CI/headless hosts mount the header (which hosts the animation planner) and exit the test phase without triggering unmount, so the planner's stop/clear path never runs. Before the flip the component was inert (feature default-off → no planner, no timers), which is why "the same job had always finished".

### Why the interactive terminal is unaffected

Per the evidence: "its process is kept alive by the TTY/stdin handles regardless of the timer chain." A long-running interactive process intends to stay alive and already holds ref'd stdin/TTY handles, so an extra ref'd timer changes nothing observable.

### The one-line fix

Stop the timer from holding the process alive — in the planner:

```ts
timer.unref()   // the chain keeps animating but no longer pins the event loop
```

(equivalently a guaranteed `clearTimeout` on unmount; `unref()` is the single-line form that fixes headless hosts without depending on unmount ever being called).

---

## 5. Prevention

### Renderer contract checklist for a terminal sprite implementation

1. **SGR plane completeness**: every emitted cell state fully specifies foreground AND background, or explicitly resets the unused plane (`\x1b[49m`/`\x1b[39m`/`\x1b[0m`). Never rely on SGR carryover between cells; never emit a foreground-only sequence after a cell that set a background.
2. **Row width and erase semantics**: rows are emitted at fixed width (padded) or terminated with `\x1b[K`; a frame switch erases the previous frame's full bounding region before drawing.
3. **Frame data integrity**: every frame is digest-pinned (sha256 over canonical rows) against source art in CI; a missing digest fails the gate.
4. **Timer lifecycle**: every animation timer is cleared on unmount and/or `unref()`'d; a headless run must reach a zero-handle state after work completes.
5. **Reset at boundaries**: a `RESET` at end of each row and at renderer exit so sprite SGR state never leaks into surrounding UI. `symptom-log.txt` notes "No other UI element is affected" — keep that an invariant, not luck.

### Pre-flip audit before turning an animation feature default-on

1. **Handle audit in headless/CI mode**: with the feature on, run the affected suites and assert the process exits by itself; enumerate live handles (`process.getActiveResourcesInfo()`) at suite end — any surviving `Timeout`/interval attributable to the feature is a blocker.
2. **Visual and digest audit**: re-run the per-frame digest gate and a frame-switch visual check (wide→narrow poses) with the feature enabled, confirming the erase path actually executes (those code paths were never exercised while default-off).
3. **Timer-code review**: grep the newly-default-on path for `setTimeout`/`setInterval` without `unref`/clear-on-unmount, and for SGR emissions that specify only one color plane.
4. **Before/after comparison**: a default flip must not change exit behavior; `ci-hang-evidence.txt` shows "the hang first appeared in the same push that flipped the animation feature's default from off to on" — any such correlation is a release blocker until explained.
