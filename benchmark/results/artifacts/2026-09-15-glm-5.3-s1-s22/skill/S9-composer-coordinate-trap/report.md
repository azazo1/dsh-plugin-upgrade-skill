# S9 · Composer Coordinate Trap — Diagnosis Report

**Task:** S9-composer-coordinate-trap (read-only analysis)
**Plugin:** `@org/dsh-attach-input` v0.2.3 · **Host:** DSH `0.1.2-alpha.3`
**Evidence:** fixture pack (plugin-client.js, console-session.txt, host-input-facade.ts, host-input-contract.ts) — read only, unmodified.
**Mode:** Skill Mode A (inspect / read-only diagnosis). No migrations, installs, or writes outside this report.

---

## Executive summary

Both user-visible bugs are **one contract misread, not two unrelated defects**: the plugin
computes editor spans in **clipboard-text projection coordinates** (where each chip expands
to its full `clipboardText`, e.g. 28 chars), but both host verbs it calls —
`insertReference` and `consumeToken` — interpret their `TokenSpan` arguments in
**detect-text projection coordinates**, where each chip is exactly **one U+FFFC character**.

- **Bug 1 (paste #2 toast):** `start: snapshot.draft.length` = 29 (clipboard projection),
  but the editor's detect text is `"\uFFFC "` (length 2). The span end overflows the
  detect text, the splice `$replaceDetectSpanWithNodes` cannot apply, `insertReference`
  returns `false`, and the plugin throws the (misleading) "composer changed" toast.
- **Bug 2 (× → `unavailable`):** the removal span `[occurrence.offset, offset+length)`
  = `[0, 28)` is likewise a clipboard-projection range; `$replaceDetectSpanWithText`
  fails on a 2-character detect text, `consumeToken` returns `false`, but the plugin
  **ignores the return value**, deletes its own record, and re-renders — the dock renderer
  then hits its `record === undefined ? 'unavailable'` branch while the real chip is still
  in the composer.

"First paste works, every later paste fails" is the fingerprint of a coordinate-system
mismatch: the two projections are **identical while the document contains no chips** (each
chip contributes `clipboardText.length` chars to `draft` but only 1 char to
`detectText`). The empty composer on paste #1 has offset 0 == offset 0, so the wrong
coordinate happens to be correct; from the moment one chip exists, every clipboard-
coordinate offset is too large, and every subsequent verb fails.

---

## 1. Why paste #1 succeeds and paste #2 fails

### The two projections (from `host-input-contract.ts`)

`EditorProjection` documents the host's dual coordinate systems:

| Projection | A chip contributes | Produced text for the session |
|---|---|---|
| `detectText` | **one U+FFFC char** ("Trigger/TokenSpan coordinate text") | `"\uFFFC "` |
| `clipboardText` / `InputState.draft` | its full `clipboardText` ("chip = clipboardText") | `"[attachment: screenshot.png] "` |

`Occurrence.offset`/`length` in `InputState` are explicitly **"in the clipboard-text
projection"** — i.e. the coordinates the plugin reads back from `getSnapshot()` are
clipboard coordinates.

### The verbs compare and splice in detect coordinates (from `host-input-facade.ts`)

- `insertReference(ref, span)` — `span` is documented as *"pick-time span snapshot
  (detect coordinates)"*; its body splices `this.projection.detectText` via
  `$replaceDetectSpanWithNodes(span, nodes)`.
- `consumeToken(guard)` — the `kind: 'span'` branch splices the detect text via
  `$replaceDetectSpanWithText(guard.span, '')` after the `draftRev` CAS.

### The mismatch in `plugin-client.js` (insert path)

```js
start: snapshot.draft.length,   // clipboard-projection length
end:   snapshot.draft.length,
draftRev: snapshot.draftRev,
```

Traced against the capture:

- **Paste #1:** fresh composer, `draft === ''`. Clipboard length 0 == detect length 0,
  `draftRev` is current → CAS passes, splice at [0,0) applies → chip + separating space
  inserted. Post-state confirms: `draft` length **29** (clipboard projection:
  `[attachment: screenshot.png]` = 28 + space), one occurrence `{offset: 0, length: 28}`.
  The host's detect text is now `"\uFFFC "` — **length 2**.
- **Paste #2:** plugin re-snapshots and computes `start = end = 29` in clipboard
  coordinates. The detect text is 2 characters long, so a span ending at 28+ is outside the
  document; `$replaceDetectSpanWithNodes` cannot apply, `applied` stays `false`,
  `insertReference` returns `false`. The plugin cleans up its record and throws the
  toast. `draftRev` was **not** stale (the snapshot was taken fresh, and no `setDraft`
  padding ran because the draft already ends in a space) — the failure is purely the
  coordinate overflow.

### Why "first works, later fails" is the signature

For a document with occurrences `o₁..oₙ`:

```
detectLength = draftLength − Σ (occurrence.length − 1)
```

The two lengths are equal **iff every chip's `clipboardText` is exactly one character**
(in practice: iff there are no chips). So the very first insertion into an empty (or
chip-free) composer lands on the coincidence where wrong == right; the first successful
insert creates a chip, and from then on every clipboard-coordinate span the plugin computes
is strictly larger than the detect document — the splice fails deterministically. A
one-time-then-permanent failure of this shape is the classic fingerprint of a
unit/coordinate-system mismatch, not of a race (a race would fail intermittently,
including sometimes on paste #1).

A secondary defect on the same path: the plugin's error message ("The DSH composer changed
before the attachment could be inserted") conflates the two distinct `false` causes of
`insertReference` (phase/rev CAS rejection vs. splice-not-applied), which is why the
maintainer could not reproduce the failure logic from the message alone.

## 2. Why × turns the chip into `unavailable` instead of removing it

The removal path in `plugin-client.js`:

```js
const end = occurrence.offset + (occurrence.length ?? 1);   // [0, 28) — clipboard coords
input.consumeToken({ kind: 'span',
  span: { start: occurrence.offset, end, draftRev: snapshot.draftRev } });
...
records.delete(occurrence.ref);   // runs unconditionally
changed();
```

Trace against the capture:

1. `occurrence = {offset: 0, length: 28}` → span `[0, 28)`. `draftRev` is current and
   `start !== end`, so both `consumeToken` guards pass — but
   `$replaceDetectSpanWithText([0,28), '')` targets a detect text of length 2 and cannot
   apply → `applied = false` → **`consumeToken` returns `false`**.
2. The plugin **never inspects the return value** (the capture notes exactly this:
   "consumeToken(...) returned (not inspected by the plugin code)"), so it proceeds to
   `records.delete(occurrence.ref)` and re-renders.
3. Result — both observed symptoms:
   - the **composer chip survives** (the host edit never applied), and
   - the **dock chip re-renders from a missing record**: the dock renderer's excerpt reads
     `record === undefined ? 'unavailable' : humanBytes(record.total)`, so the chip stops
     showing its size and shows `unavailable` — while still being rendered, because the
     chip list itself is driven by the composer occurrences, which still contain the ref.

So the `unavailable` label is not a host state — it is the plugin's own fallback branch
for "record lost while occurrence still present", reached because the plugin's bookkeeping
(`records` map) was updated as if the host removal had succeeded. The capture confirms:
"dock chip STILL rendered, meta now reads 'unavailable'; composer chip still present;
records no longer contains the ref."

This is the same coordinate misread expressing itself on the removal verb, compounded by
an unchecked boolean return.

## 3. Fix direction — the conversion rule and the call sites

### The rule, derived from the host source

Per `EditorProjection`'s own field docs (detect: "chip = one U+FFFC"; clipboard: "chip =
clipboardText"; `InputState.occurrences` are clipboard-coordinate), a clipboard-projection
offset `O` converts to a detect offset by shrinking every occurrence before it from
`length` chars to 1:

```
detect(O) = O − Σ { occ.length − 1 | occ.offset < O }        (occ from InputState.occurrences)
detectLen = draft.length − Σ { occ.length − 1 | occ }          (for end-of-document inserts)
```

For a **chip's own range**, the detect span is exactly one character:
`start = detect(occ.offset)`, `end = start + 1`.

`draftRev` needs no conversion — it is the same monotonic editor revision in both
projections — but it must come from the **same snapshot** as the coordinates (CAS).

### Call site A — insert path (`add`)

Compute the insertion point in detect coordinates from the snapshot:

```js
const detectEnd = snapshot.draft.length
  - snapshot.occurrences.reduce((n, o) => n + (o.length - 1), 0);
input.insertReference({ ... }, {
  start: detectEnd,
  end: detectEnd,
  draftRev: snapshot.draftRev,
});
```

(If the shell exposes `EditorProjection.detectText` to plugins, prefer
`detectText.length` directly.) Keep the existing per-item re-snapshot so each subsequent
item in one paste sees the post-edit `draftRev`. Note the host already appends the
separating space itself when the tail is not `' '` (`insertReference`'s `tail` check),
so the plugin's draft-padding `setDraft` is redundant — and each `setDraft` bumps the
revision, so dropping it also removes a CAS-staleness hazard for multi-item pastes.

### Call site B — removal path (`remove`)

```js
const shift = (snap) => snap.occurrences
  .filter(o => o.offset < occurrence.offset)
  .reduce((n, o) => n + (o.length - 1), 0);
const start = occurrence.offset - shift;
const consumed = input.consumeToken({ kind: 'span',
  span: { start, end: start + 1, draftRev: snapshot.draftRev } });
if (!consumed) return;            // keep record + dock in sync with the host
records.delete(occurrence.ref);
changed();
```

Two changes at this site: (a) span converted to detect coordinates with **length 1** per
chip (the plugin's old comment "the removal must span occurrence.length" is precisely
backwards — that is the clipboard-projection length); (b) **check the boolean return** and
only mutate plugin bookkeeping when the host actually consumed the token. The
`setDraft`-fallback branch (`slice(0, offset) + slice(end)`) is also a clipboard-
coordinate splice against `InputState.draft` — verify against the host which projection
`setDraft` accepts before keeping it as a fallback.

## 4. Regression test plan

Assert these exact interaction sequences against a real input machine (or a facade-level
harness seeded with a real projection), so neither bug can silently return:

1. **Repeat insert (bug 1):**
   1. paste file A into an **empty** composer → `insertReference` returns true; snapshot
      shows 1 occurrence, `draft.length === A.clipboardText.length + 1`;
   2. paste file B (different name **and** same name) → returns true; **2** occurrences;
      both chips rendered inside the composer; **no toast**; detect text length
      `=== occurrence count + plain-text length`.
2. **Insert after plain text:** type `"see this"` (no trailing space), paste → insert
   succeeds and the host's separating space lands exactly once (no double space, no CAS
   failure from a padding `setDraft` between snapshot and insert).
3. **Multi-item single paste:** paste two files in one `items` array → both accepted
   (exercises the per-item re-snapshot / rev bump path).
4. **Remove the only chip (bug 2):** paste once, click × on the dock chip →
   `consumeToken` returns true; composer occurrences become empty; `draft === ''`;
   dock chip **gone** (not `unavailable`); `records` no longer contains the ref.
5. **Remove a chip with a preceding chip:** paste A then B, × on **B** → A's text and chip
   intact, B gone; `draft` shrinks by exactly `B.clipboardText.length`; offsets of any
   occurrence after the removed one shift correctly in the next snapshot.
6. **Remove while a chip precedes AND text follows:** paste A, type `"tail"`, paste B,
   × on A → final draft `"tail"` + B's chip intact (guards the shift computation for
   mid-document spans).
7. **CAS still honored:** snapshot, make an unrelated edit (bump `draftRev`), then call
   `insertReference`/`consumeToken` with the stale span → both return false, plugin
   keeps its record (no `unavailable` state), and the error surfaced names the CAS cause.
8. **Phase guard:** repeat 4 and 5 while `phase !== 'plain'` → verb returns false, chip
   and record unchanged, no partial bookkeeping.
9. **Round-trip:** paste → × → paste again → succeeds (the removal correctly restored the
   coordinate invariants the next insert relies on).

Assertions in 1, 4, and 5 are the direct regression bars for the two reported bugs; 2, 3,
6–9 keep the conversion rule and the return-value discipline honest.

## 5. Routine host-source checks before calling input-machine verbs (unscored guidance)

- **Read the verb's span parameter contract in the facade source**, not just the published
  state types: `insertReference`'s `span` is documented "detect coordinates" while
  `InputState.occurrences` are documented clipboard-projection — the two live in
  different files, and reading only one hides the mismatch.
- **Map every coordinate-bearing field to its projection**: `Occurrence.offset/length`
  (clipboard), `TokenSpan.start/end` (detect), `EditorProjection.detectText` vs
  `.clipboardText`. If a value crosses a projection boundary, write the conversion next
  to the call site with the rule's source comment.
- **Check the guard list, not just the happy path**: phase guard, `draftRev` CAS,
  `start === end` rejection, trimmed-equality for bare tokens — and know which `false`
  you received.
- **Never ignore boolean returns** on edit verbs; treat them as "host state unchanged —
  do not mutate local bookkeeping", and log which guard family caused the rejection.
- **Re-read these contracts on every DSH upgrade** (input/editor facade + projection
  types); the skill's version cards track API drift, but coordinate semantics of a
  projection pair must be re-verified at the source.

---

## Skill-mode compliance

- Mode A (inspect): read-only; fixture untouched; no installs, migrations, or executes.
- Findings tie both symptoms to one underlying contract misread (clipboard-projection
  spans passed to detect-projection verbs), with the correction rule derived from the host
  source excerpts' own documentation, not trial and error.
