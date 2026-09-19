# S9 · Composer Coordinate Trap — Diagnosis Report

**Plugin:** `@org/dsh-attach-input` v0.2.3 · **Host:** DSH `0.1.2-alpha.3`
**Evidence:** `plugin-client.js`, `console-session.txt`, `host-input-facade.ts`, `host-input-contract.ts` (read-only fixture)

## Executive summary

Both user reports are **one contract misread, not two bugs**: the plugin computes every
`TokenSpan` it hands to the host input verbs (`insertReference`, `consumeToken`) in
**clipboard-text coordinates** (the `InputState.draft` / `Occurrence.offset`/`length`
projection), while the host verbs' guards and splices operate in **detect-text
coordinates** (the `EditorProjection.detectText` projection, where each chip is exactly
one `U+FFFC` character). The two coordinate spaces coincide only for an empty composer;
every existing chip makes the clipboard projection longer than the detect projection by
`clipboardText.length − 1` characters per chip. All spans the plugin derives from
`snapshot.draft.length` or `occurrence.offset + occurrence.length` are therefore
past-the-end / wrong-length in detect space once any chip exists, the splice helpers
(`$replaceDetectSpanWithNodes` / `$replaceDetectSpanWithText`) refuse or miss, the verbs
return `false`, and the plugin mishandles those `false` returns in two different ways
(insert path: throws the toast; removal path: ignores the return, deletes its record
anyway, producing the `unavailable` ghost chip).

The host source states this explicitly:

- `host-input-facade.ts`, `insertReference`: *`@param span - pick-time span snapshot
  (detect coordinates)`*, and the header comment: *`$replaceDetectSpanWithText /
  $replaceDetectSpanWithNodes splice the DETECT text and apply the edit.`*
- `host-input-contract.ts`, `Occurrence`: *`offset`/`length` — Offset/Length in the
  **clipboard-text projection**`; `InputState.draft` — *`Clipboard-text projection of
  the editor document (chips expanded to their clipboard form)`*; `EditorProjection.detectText`
  — *`Trigger/TokenSpan coordinate text (chip = one U+FFFC)`*.

So the plugin is reading `InputState` (clipboard currency) and feeding it to verbs that
consume `EditorProjection.detectText` currency. `draftRev` itself is fine — the plugin
re-snapshots before each call, so the revision CAS (`span.draftRev !== this.rev`) passes;
the rejection comes from the out-of-range / wrong-unit span handed to the detect-text
splice.

---

## 1. Why paste #1 succeeds and every later paste fails

### What the plugin computes

`add()` inserts at "the end of the draft":

```js
start: snapshot.draft.length,
end:   snapshot.draft.length,
```

`snapshot.draft` is the **clipboard-text projection** — chips expanded to their
`clipboardText` form.

### What the host compares against

`insertReference(ref, span)` splices `this.projection.detectText` via
`$replaceDetectSpanWithNodes(span, nodes)`. In `detectText`, a chip is **one `U+FFFC`
character**, not its 28-character `clipboardText`.

### The trace

- **Paste #1 (empty composer):** `draft = ""` (length 0) and `detectText = ""` (length 0).
  Both coordinate systems agree: `start = end = 0` is a valid caret position in both.
  The splice inserts one chip node + a separating space (tail check
  `detectText.slice(0,1)` is `""`, not `' '`, so chip + `' '` are inserted). Success —
  this is the captured state: `draft = "[attachment: screenshot.png] "` (length 29),
  `occurrences = [{offset: 0, length: 28, …}]`.
- **Paste #2:** the plugin re-snapshots: `snapshot.draft.length = 29`, so it passes
  `{start: 29, end: 29, draftRev}`. But the editor's `detectText` is now
  `"\uFFFC "` — **length 2**. Span end 29 points 27 characters past the end of the
  detect text. `$replaceDetectSpanWithNodes` cannot apply an out-of-range span, returns
  `false`, `applied` stays `false`, `insertReference` returns `false`, the plugin
  deletes the record and throws `"The DSH composer changed before the attachment could be
  inserted"`. No second chip anywhere — exactly the capture.

### Why "first works, later fails" is the signature of this mismatch

The two projections differ by exactly `Σ (clipboardText.length − 1)` over the existing
chips (each chip: 1 char in detect space vs `clipboardText.length` chars in clipboard
space; plain text is identical in both). With **zero chips the spaces are identical**, so
the very first interaction on an empty composer — the case every maintainer tests first —
passes. The divergence is strictly monotonic in the number of chips: after chip *k*, every
draft-derived end offset overshoots the detect text by `Σᵢ₌₁..k (lenᵢ − 1)` (here
28 − 1 = 27 per chip). So *any* second insert, on *any* non-empty composer, fails the same
way. A bug that only reproduces on the **repeat** interaction, never the first, and whose
failure magnitude grows with the number of existing chips, is the fingerprint of a
coordinate-unit mismatch between the state snapshot read and the verb's splice space —
not of a race or a stale-revision problem (a stale `draftRev` would fail randomly,
including on the first paste).

## 2. Why × turns the chip into `unavailable` instead of removing it

`remove()` derives the span from the occurrence's clipboard-space fields:

```js
const end = occurrence.offset + (occurrence.length ?? 1);
input.consumeToken({ kind: 'span',
  span: { start: occurrence.offset, end, draftRev: snapshot.draftRev } });
```

Two independent coordinate errors, plus a bookkeeping error:

1. **Start is in the wrong space.** `occurrence.offset = 0` happens to be right here only
   because the chip is first; with any preceding text or chips it is a clipboard-space
   offset, not a detect-space one.
2. **Length is in the wrong unit.** The comment says *"the removal must span
   occurrence.length, not one character"* — that is exactly backwards. In detect space a
   chip **is** one character (`U+FFFC`); `occurrence.length = 28` is its clipboard-space
   extent. The span `[0, 28)` covers the entire 2-character `detectText`
   (`"\uFFFC "`) and beyond — out of range for `$replaceDetectSpanWithText`, so
   `consumeToken` returns `false` and **the composer chip is never removed**. (Had the
   span been merely wrong-but-in-range, the plugin would have deleted unrelated text —
   the same unit error, different symptom.)
3. **The `false` return is ignored.** `consumeToken(...)` is called without inspecting
   the result (the capture even notes: *"consumeToken(...) returned (not inspected by the
   plugin code)"*). The plugin then unconditionally runs:

   ```js
   records.delete(occurrence.ref);
   changed();
   ```

So after a failed removal: the host still lists the occurrence → the composer chip stays;
the dock still renders the chip (docked from host occurrences) → but `records.get(ref)`
is now `undefined` → per the dock rendering excerpt, `record === undefined` renders meta
`"unavailable"`. That is precisely the captured state: *dock chip STILL rendered, meta
"unavailable", composer chip still present, records no longer contains the ref.*

Note the symmetry with bug 1: the insert path **checks** the `false` and throws a
misleading toast; the removal path **ignores** the `false` and corrupts its own
bookkeeping. Same root cause (clipboard-space span fed to a detect-space verb), two
different failure presentations.

## 3. Fix direction: the conversion rule and the call sites

### The rule (derived from the host source)

For any position or length the plugin feeds into a `TokenSpan`:

- **Plain text characters count 1:1 in both spaces** (`detectText` and `clipboardText`
  differ only at chips).
- **Each chip contributes `1` character in detect space and `occurrence.length`
  characters in clipboard space.** (From `EditorProjection`: *"detectText — chip = one
  U+FFFC"*; *"clipboardText — chip = clipboardText"*; `Occurrence.length` is its extent
  in the clipboard-text projection, `[offset, offset+length)`.)

Therefore, for a clipboard-space offset `o` and the set `P(o)` of occurrences entirely
before `o` (`occ.offset + occ.length <= o), the detect-space equivalent is:

```
detect(o) = o − Σ_{p ∈ P(o)} (p.length − 1)
```

and a chip's removable detect span is:

```
start = detect(occ.offset)          // = occ.offset − Σ (p.length − 1) over chips before it
end   = start + 1                    // a chip is exactly one U+FFFC in detect space
```

An end-of-draft caret is simply `detectText.length`, which the plugin cannot read from
`InputState` alone, so it must compute:

```
insertPoint = snapshot.draft.length − Σ_{all occ} (occ.length − 1)
```

`draftRev` needs no conversion — it is the editor revision in both contracts; keep
re-snapshotting immediately before each verb call so the CAS passes.

### Call site A — `add()` (insert path)

```js
const chips = snapshot.occurrences;                    // sorted by offset per contract
const shrink = chips.reduce((n, o) => n + (o.length - 1), 0);
const at = snapshot.draft.length - shrink;             // detect-space caret at draft end
const accepted = input.insertReference({...}, {
  start: at, end: at, draftRev: snapshot.draftRev,
});
```

(The existing pattern of re-snapshotting after each inserted item must stay, because each
successful insert appends a new occurrence and changes both `draft.length` and `draftRev`.)

### Call site B — `remove()` (removal path)

```js
const before = snapshot.occurrences.filter(o => o.offset + o.length <= occurrence.offset);
const shrink = before.reduce((n, o) => n + (o.length - 1), 0);
const start = occurrence.offset - shrink;
const ok = input.consumeToken({ kind: 'span',
  span: { start, end: start + 1, draftRev: snapshot.draftRev } });
if (!ok) return;            // or surface an error — never drop the record on failure
records.delete(occurrence.ref);
changed();
```

Two behavioral corrections bundled with the coordinate fix:

- the span **must be length 1** in detect space (delete the `length ?? 1` clipboard-space
  arithmetic and the comment justifying it);
- `records.delete` / `changed()` must run **only when `consumeToken` returns `true`**,
  so a failed removal can never produce the `unavailable` ghost (record kept, host chip
  kept, states stay consistent). The `setDraft` fallback branch has the same clipboard-space
  slicing and needs the same conversion (or should be derived from a fresh snapshot's
  `occurrences` rather than index arithmetic on `draft`).

Centralize both conversions in one helper (e.g. `toDetectSpan(snapshot, occurrence)` /
`detectEndOfDraft(snapshot)`) so the insert and removal paths cannot drift apart again.

## 4. Regression test plan

All sequences must run against a real (or high-fidelity mock) input machine whose
`insertReference`/`consumeToken` splices detect text — a mock that accepts clipboard
coordinates would pass the old bugs. Assert host state (`getSnapshot()`: `draft`,
`occurrences`, `draftRev`) **and** plugin state (`records`, dock rendering input).

1. **First paste on empty composer** (guard the baseline): one dock chip, one composer
   chip, `draft` ends with the `clipboardText` + one space, `occurrences.length === 1`.
2. **Second paste with ≥1 existing chip** (kills bug 1): no toast/throw;
   `insertReference` returned `true`; two composer chips; `draft` contains both
   `clipboardText`s; `occurrences.length === 2` with correct clipboard-space
   `offset`/`length`; both dock chips render byte-size meta (not `unavailable`).
3. **Third+ paste** (divergence grows per chip): repeat to ≥3 chips; same assertions —
   pins the `Σ(length−1)` conversion, not just the 2-chip case.
4. **Paste after plain typed text without trailing space**: exercises the `setDraft`
   padding branch — after the re-snapshot the insert must still land at the detect-space
   end and succeed.
5. **Remove the only chip** (baseline removal): × click → `consumeToken` returns `true`;
   composer chip gone; `draft` empty (no residue of the chip or its separator);
   `occurrences.length === 0`; dock chip unmounted; record removed.
6. **Remove one of several chips, then remove another** (kills bug 2 and pins
   re-derivation): with chips A, B, C, remove B → A and C remain with correctly shifted
   clipboard offsets; then remove C using a **fresh snapshot** → succeeds. Removing the
   *first* and *last* chip specifically must each be covered (off-by-shrink edges).
7. **Remove with a stale/failed verb**: simulate `consumeToken` returning `false`
   (e.g. concurrent rev bump between snapshot and call) → the record is **retained**, the
   dock chip still renders its size (never `unavailable`), the composer chip remains,
   and the failure is surfaced (return value / error), not swallowed.
8. **Property test** (optional but cheap): for randomized interleavings of pastes and
   removals, assert after each step that the plugin's computed detect span for the
   targeted chip equals the actual index of that chip's `U+FFFC` in the machine's
   `detectText`, and that `draft.length − Σ(occ.length − 1) === detectText.length`.

## 5. Routine host-source checks before calling input-machine verbs (unscored guidance)

- **Name the coordinate space of every span/offset parameter.** Read the verb's JSDoc and
  the projection types it references: `TokenSpan` is detect-space; `Occurrence.offset /
  .length` and `InputState.draft` are clipboard-space. If the value you pass was derived
  from a different projection than the one the verb splices, convert it explicitly at the
  call site.
- **Read the verb's guard clauses, not just its signature**: what the CAS compares
  (`span.draftRev !== this.rev`), what makes it return `false` (phase check, empty span,
  out-of-range splice), and which helper performs the edit (`$replaceDetectSpan…`
  names its target text).
- **Treat boolean returns as part of the contract.** Every `false` path must have a
  defined plugin-side behavior (retry with a fresh snapshot, or surface an error); never
  mutate local bookkeeping (`records`, dock state) before confirming success.
- **Test the repeat interaction, not just the happy path.** Coordinate-space divergence is
  invisible on an empty editor by construction — always exercise N ≥ 2 items and a removal
  after an insertion before releasing.
- **Distrust comments that justify arithmetic against the type's documented units** (the
  "must span `occurrence.length`, not one character" comment was the removal bug written
  down as a rationale).
