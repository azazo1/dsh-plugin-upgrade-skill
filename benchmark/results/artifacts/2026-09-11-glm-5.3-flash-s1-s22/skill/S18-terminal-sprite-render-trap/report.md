# S18 · The Terminal Sprite Render Trap — Diagnostic Report

Task: S18-terminal-sprite-render-trap (read-only diagnosis). Evidence pack: the S18 fixture directory — `README.md`, `renderer-excerpt.ts`, `symptom-log.txt`, `frames-digest-report.txt`, `ci-hang-evidence.txt`. Nothing in the fixture was modified; no migrations, installs, or network access were performed. Per the plugin-upgrade skill's Mode A discipline (read-only investigation and report), this is inspection only.

The app renders a 25-row × 40-column pixel sprite (the whale) with the half-block technique: each terminal cell packs two vertical pixels into one glyph, foreground = upper pixel, background = lower pixel. An animation feature added around the sprite produced three symptoms (phantom pixels, ghost frames, one drifted frame) and, once the feature flipped default-on, a CI hang.

---

## 1. Phantom pixels — SGR state persists across cells

**Mechanism (from `renderer-excerpt.ts`).** The per-cell loop emits an SGR sequence only when the sequence *changes* versus the previous cell:

    if (seq !== current) {
      out += seq === '' ? RESET : seq
      current = seq
    }

Two facts combine into the trap:

1. The partially-filled branch draws a cell whose **upper pixel is colored and lower pixel is transparent** with `seq = fg(up)` and glyph `'▀'` only — it never emits a `bg` for its own empty lower half and never resets. The lower half of that ▀ cell is therefore painted with the **background SGR state left over from the most recent cell that did emit `bg(lo)`** (a neighboring body pixel). Terminal SGR state persists across cells until changed, so the stale background color from an earlier colored cell survives into the empty half of the edge cell.
2. Fully transparent cells emit `seq = ''` → `RESET` + space, which restores defaults; but the very next upper-only cell again emits only `fg(up)`, re-exposing the ambient background to the glyph's empty half. The `current` cache diffs against the previous cell's seq, so no redundant-but-complete re-specification ever happens.

**Which cells expose it.** Any cell with `up !== undefined && lo === undefined` — the renderer's upper-only branch. At the sprite's right edges the outline, the sleep-Z symbols, and the heart sit over transparent lower pixels (symptom-log item 1: "frame rows end in '.' at those columns"), so those right-edge columns show a 1-cell-wide stripe of "dim colored noise": the stale background color of a neighboring palette entry. Because the animation recolors and moves the edge each tick, the stale color changes too — the noise "appears and moves with the animation" and is not part of any frame's data.

**The precise escape fix.** Never let a half-filled cell rely on ambient SGR state: in the upper-only branch emit a complete sequence for both halves the glyph exposes — `fg(up) + bg(<transparent/default color>)` (e.g. the page background, or an explicit default-background escape after the fg set). Symmetrically, the lower-only branch (`seq = fg(lo)`, glyph `'▄'`) must explicitly pin the attribute of the cell's upper half. Each emitted `seq` must by itself fully specify the state the glyph paints, so the diff cache can stay but no half can inherit.

---

## 2. Ghost frames — trailing-whitespace trimming vs. erase semantics

**What the renderer drops from each row.** End of `renderSpriteRows`:

    let row = out.replace(/[ ]+$/, '')
    if (!row.endsWith(RESET)) row += RESET

Trailing spaces are stripped from every row. Spaces are the encoding of fully transparent cells, so a narrower pose's rows simply end earlier — the surplus right-hand columns (where the previous wide tail was) are **never addressed by the new frame at all**: no glyph, no SGR, no erase.

**What the text pipeline does to trailing whitespace.** The pipeline emits only the printed characters of the (trimmed) row; trailing blanks beyond the last character produce no overwriting blank glyphs and no erase-in-line. Erase semantics: writing a shorter row does not clear the remainder of the physical line — pixels the previous frame painted there stay on screen. Hence symptom-log item 2: switching from the wide pose (tail fully swung out) to a narrower pose renders the narrow frame fine, but the surplus columns keep showing the previous frame's tail — ghost pixels.

**The two-part fix that guarantees a clean frame switch.**

1. **Renderer side:** do not rely on trailing-space trimming — emit the full sprite extent per row (pad to the widest frame with explicitly-colored blanks, or write an explicit erase covering the full width) so every frame owns the entire rectangle it may previously have painted.
2. **Presentation side:** on frame switch, clear the previous frame's painted region first (erase-in-line / blank rows for the old frame's extent) before drawing the new frame, so even a trimmed row cannot leave stale glyphs.

Only together do they guarantee a clean switch: (1) fixes the row encoding, (2) fixes the transition path.

---

## 3. Frame data drift — the digest report and why the regression missed it

**What the digest report says.** `frames-digest-report.txt` compares sha256 of each ported frame's 25 rows against the source-art frames: every frame is OK except **`tail2` — MISMATCH**. Detail: row 2, ported `D` at col 26 vs source col 27 (1 column left shift); row 3, extra `D` at col 25, `DBD` at cols 26–28 shifted left 1, extra `DD` at cols 36–37; rows 4–6, the upper-right cluster shifted 1 column left throughout. Total **23 differing cells, all in the upper-right spout/tail-tip area** — the visible symptom (symptom-log item 3, the misplaced 6-pixel tail-tip cluster) is the user-noticeable subset of this 23-cell drift.

**Why the existing per-excerpt regression missed it.** The report states it directly: *"The ported tail2 was hand-copied during conversion; an excerpt-based regression (added later for a different frame) did not cover it."* The regression asserted excerpts of one frame only; `tail2`'s hand-copy errors were in an uncovered frame, and no whole-frame digest existed at conversion time.

**The gate that prevents recurrence.** Pin **every** frame with a whole-frame digest (sha256 over the full 25 rows vs source art) enforced as a CI gate that fails on any mismatch; new or hand-ported frames must either match the source digest or land with an explicitly reviewed, re-pinned digest. Excerpt tests may remain, but the all-frame digest gate is the complete-coverage floor that no hand-port can slip under.

---

## 4. The hang — timer-pinned event loop

**Mechanism (from `ci-hang-evidence.txt`).** Job `channel-ui` shows PASS for all scene checks, then sits idle until killed at the runner timeout (previously ~3 minutes; one local observation idled 19 minutes before manual kill). Process state at kill: no running test, no pending assertion; the event loop holds live handles of kind **Timeout — one per tick of the sprite animation planner, each re-arming the next**. The planner "reschedules a `setTimeout` for as long as its component stays mounted", and these hosts **mount the header component and finish WITHOUT unmounting it**. The missing unmount means the self-re-arming timer chain never terminates, so a finished process always has a pending timer keeping the event loop alive — "finished but hanging".

**Which hosts / why the interactive terminal is unaffected.** The affected hosts are the CI/scene hosts that mount the header component without unmounting it. The interactive terminal product is unaffected because its process is intentionally kept alive by TTY/stdin handles regardless of the timer chain — a lingering animation timer changes nothing there.

**The one-line fix.** Clear the timer on teardown so the last tick does not re-arm: `clearTimeout(timer)` (or `clearInterval` / the registration disposer) in the component's unmount/cleanup path — i.e. bind the tick timer to mount lifetime as a disposable effect.

---

## 5. Prevention — renderer contract checklist and pre-rollout audit

**Renderer contract checklist a terminal sprite implementation should ship with:**

1. **Complete SGR state per glyph.** Every cell that paints any half explicitly specifies the attributes of both halves its glyph exposes (▀ = fg upper + bg lower; ▄ = fg lower + bg upper). No cell inherits ambient fg/bg from a previous cell (S18 §1).
2. **Full-rectangle ownership.** Each frame addresses the entire region any recent frame painted; no reliance on trailing-whitespace trimming; rows padded or erased to the full sprite extent (S18 §2).
3. **Erase-before-switch.** Frame transitions clear the previous frame's extent before drawing the new frame.
4. **Deterministic pure output.** Rows are a pure function of (frame, palette); SGR run-length diffing is allowed only when each emitted sequence is complete for the halves it covers.
5. **Frame-data integrity gate.** Every frame carries a pinned whole-frame digest verified against source art in CI; a mismatch fails the build, and any intentional change re-pins the digest explicitly (S18 §3).
6. **Lifecycle teardown.** Every animation timer/tick registration is tied to mount lifetime and cleared on unmount; a mounted-but-never-unmounted component must not keep the event loop alive in batch/CI hosts — no self-re-arming timer without a stop hook (S18 §4).

**Audit to run BEFORE flipping an animation feature default-on:**

1. **Symptom sweep under both defaults:** run the sprite with the feature off and on, including wide→narrow frame switches; diff rendered rows/terminal output for phantom edge columns and ghost pixels; confirm items 1–2 of the checklist hold.
2. **Digest gate green for all frames:** whole-frame digests match source art for every frame (S18's hand-ported `tail2` drifted undetected precisely because only an excerpt test existed).
3. **Mount-without-unmount sweep:** run every host that mounts the component in fire-and-forget mode; assert process exit after PASS and scan for lingering `Timeout` handles; prove teardown stops the tick chain — this is exactly the `channel-ui` hang signature.
4. **Blast-radius containment:** confirm artifacts are confined to the sprite's cell area ("No other UI element is affected", symptom-log) and that intentionally long-lived (interactive TTY) processes are not behaviorally coupled to the animation timer chain.
5. **Flip with fixes, not alone:** land the teardown fix and the digest gate in the same change as the default flip, with a CI regression asserting "all checks PASS ⇒ process exits".

---

**Evidence index.** §1: `renderer-excerpt.ts` upper-only branch (`seq = fg(up)`, `'▀'`), `seq !== current` diffing, `RESET`-on-empty; `symptom-log.txt` item 1. §2: `renderer-excerpt.ts` trailing `replace(/[ ]+$/, '')`; `symptom-log.txt` item 2. §3: `frames-digest-report.txt` (`tail2 MISMATCH`, 23 differing cells, excerpt-regression statement). §4: `ci-hang-evidence.txt` (Timeout handles, planner re-arming, header mounted without unmount, TTY/stdin keeps interactive alive). §5: synthesis of all of the above.
