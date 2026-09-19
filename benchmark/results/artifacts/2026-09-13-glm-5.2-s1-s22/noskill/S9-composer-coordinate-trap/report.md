# S9 · Composer Coordinate Trap — Diagnosis Report

Plugin under review: `@org/dsh-attach-input` v0.2.3 vs DSH `0.1.2-alpha.3`.
Evidence: `plugin-client.js`, `console-session.txt`, `host-input-facade.ts`, `host-input-contract.ts` (read-only fixture).

## Executive summary

Both reported symptoms are one defect, not two: **the plugin computes every span in the
clipboard-text projection, but the host verbs it calls (`insertReference`, `consumeToken`)
guard and splice in the detect-text projection.** In the clipboard projection a chip expands
to its full `clipboardText` (e.g. `[attachment: screenshot.png]` = 28 chars); in the detect
projection the same chip is a single U+FFFC object-replacement character. The two coordinate
systems agree only while the composer holds **zero chips**, which is exactly why paste #1
succeeds and every later interaction fails. The removal path additionally ignores the
verb's boolean return, converting a failed splice into silent bookkeeping corruption
(`unavailable` chip).

## 1. Why paste #1 succeeds and every later paste fails

**What the plugin computes** (`add`): `snapshot = input.state.getSnapshot()` returns
`InputState`, whose `draft` and `occurrences` are documented as the *clipboard-text
projection* (`host-input-contract.ts`: "chips expanded to their clipboard form", offsets
"in the clipboard-text projection"). It inserts at `start = end = snapshot.draft.length`
— a clipboard-projection offset.

**What the host compares against** (`insertReference` in `host-input-facade.ts`): the
span is checked `span.draftRev !== this.rev` (this part the plugin gets right — it
re-reads the snapshot, so the CAS passes) and then applied via
`$replaceDetectSpanWithNodes(span, nodes)`, which **splices `this.projection.detectText`**
("chip = one U+FFFC", per `EditorProjection`). So the span must be in **detect
coordinates**.

**The divergence:** after paste #1, the capture shows
`draft = "[attachment: screenshot.png] "` (length 29) in clipboard coordinates, but the
detect text is only `"<U+FFFC> "` (length 2): one char for the chip plus the separating
space the verb appends. Every chip inflates the clipboard length by
`clipboardText.length − 1` = 27 relative to detect length.

- **Paste #1 (empty composer):** clipboard and detect coordinates are identical (draft
  empty, no chips), `start = end = 0` is valid in both spaces, the splice applies → OK.
- **Paste #2:** plugin computes `start = end = 29`; the host splices a 2-character detect
  text at 29 — out of range, `$replaceDetectSpanWithNodes` cannot apply, `applied` stays
  `false`, `insertReference` returns `false`, and the plugin throws the observed toast.
  The record is rolled back (`records.delete(ref)`), so no second chip appears anywhere.

"First works, later fails" is the fingerprint of a projection mismatch: the two coordinate
systems coincide exactly until the first chip is inserted, and each surviving chip widens
the gap by `length − 1`, so *every* subsequent paste fails, not just some.

## 2. Why × turns the chip into `unavailable` instead of removing it

Trace of `remove(sessionId, occurrence)`:

1. The occurrence comes from `InputState.occurrences` — **clipboard coordinates**:
   `offset: 0, length: 28` in the capture. The plugin even comments that "the occurrence
   owns its whole inline range" and builds `end = offset + length = 28`.
2. `consumeToken({ kind: 'span', span: { start: 0, end: 28, draftRev } })` hits the host's
   span guard: `draftRev` matches (fresh snapshot) and `start !== end`, so it proceeds to
   `$replaceDetectSpanWithText(guard.span, '')` — again a **detect-text** splice. The whole
   detect text is `"<U+FFFC> "` (2 chars); splicing `[0, 28)` does not match the chip's real
   detect range `[0, 1)` and the edit fails to apply, returning `false`.
3. The plugin **never inspects the return value** ("returned (not inspected by the plugin
   code)" in the capture) and unconditionally runs `records.delete(occurrence.ref)` and
   `changed()`.
4. Dock re-render: `records.get(occurrence.ref)` is now `undefined`, so the rendering
   excerpt's fallback kicks in: `record === undefined ? 'unavailable'`. The composer chip
   survives because the host edit never applied.

So symptom #3 = same projection mismatch (splice misses the chip) **plus** a second,
independent plugin error: mutating local bookkeeping without gating on the verb's
success boolean. The `unavailable` label is the visible artifact of deleting the record
for a chip that still exists.

## 3. Fix direction

One rule, derived from the host sources: **convert clipboard-projection coordinates to
detect (token-span) coordinates before calling any span-guarded verb.** Per
`EditorProjection`, each chip contributes `clipboardText.length` chars to
`clipboardText` but exactly **1 char (U+FFFC)** to `detectText`. Therefore, for any
occurrence `o` (sorted by offset, as `InputState.occurrences` guarantees):

```
detectOffset(o) = o.offset − Σ (p.length − 1)  for every occurrence p with p.offset < o.offset
```

and a clipboard-projection caret position `c` in a draft with occurrences `O` maps to

```
detectPos(c) = c − Σ (o.length − 1)  for every o ∈ O with (o.offset + o.length) ≤ c
```

(i.e. subtract the inflation of every chip entirely left of the position).

**Insert path (`add`)** — the span passed to `insertReference` must be in detect
coordinates: `start = end = detectPos(snapshot.draft.length)`. With the capture's state
that is `29 − 28 = 1` — pasting after the existing chip's U+FFFC. Equivalently, since
insertion is always at the end of the draft: `snapshot.draft.length − Σ(o.length − 1)`
over all current occurrences. Note the tail-space peek (`tail === ' '`) is the host's own
detect-space check and needs no plugin-side adjustment.

**Removal path (`remove`)** — the span must cover the chip's detect cell, not its
clipboard expansion: `span = { start: detectOffset(occ), end: detectOffset(occ) + 1,
draftRev: snapshot.draftRev }`. (The plugin's current comment — "must span
occurrence.length" — is the contract misread itself.) The `setDraft` fallback branch is
projection-safe by construction (it operates on `snapshot.draft`, a clipboard string) but
destroys other chips' identities; prefer the corrected `consumeToken`.

**Both paths** — gate plugin-side bookkeeping on the verb's return:
only delete the record if `consumeToken` returned `true`; never mutate `records`
after a `false` (the insert path already rolls back on `!accepted`; mirror that for
remove).

## 4. Regression test plan

All sequences run against a fresh session and assert both host state and plugin bookkeeping:

1. **Repeat paste (kills bug #2):** paste file A → assert one occurrence, `draft` ends
   with A's clipboardText + a space; paste file B **without any other edit** → assert
   `insertReference` returned `true`, two occurrences sorted by offset, detect text is
   `"<U+FFFC> <U+FFFC> "`, and both dock chips render with real size labels (not
   `unavailable`). Paste file C after two chips → still accepted (guards against
   "handles exactly one prior chip" fixes).
2. **Paste with typed text:** type `"hello "`, paste A, type `" world"`, paste B →
   assert both spans landed at the correct detect positions and the clipboard draft reads
   `"hello [attachment: A] world [attachment: B] "` (order and inter-chip text intact).
3. **Removal (kills bug #3):** paste A, paste B; click × on dock chip A → assert
   `consumeToken` returned `true`, exactly one occurrence remains (B), detect text is
   `"<U+FFFC> "`, the composer chip for A is gone, and the dock chip for A is gone
   (not `unavailable` — assert `records` still contains B and the re-render removed A's
   chip entirely).
4. **Removal failure path:** force a `false` from `consumeToken` (e.g. stale
   `draftRev` obtained before another actor edits) → assert `records` is **unchanged**
   and the dock chip still shows its size label (no `unavailable`, no silent delete).
5. **Remove-then-paste:** paste A, remove it, paste B → assert B inserts at detect
   position 0 and no stale A state remains (chip count exactly 1).
6. **CAS discipline:** between snapshot and verb call, mutate the draft via another
   client; assert the verb returns `false`, the plugin surfaces the retryable error, and
   no partial record survives (`accepted === false` ⇒ `records` rollback, already
   present for `add`; add the mirror assertion for `remove`).

## 5. Routine host-source checks before calling input-machine verbs (unscored)

- **Match the projection, not just the type.** For every span/offset parameter, read the
  verb's body (or JSDoc) and identify which projection string it slices — here
  `$replaceDetectSpanWith*` ⇒ detect text (chip = 1 char), while `InputState` /
  `Occurrence` publish clipboard coordinates (chip = clipboardText). Same `number`
  type, different space; the signature alone cannot tell you.
- **Check the guard order and semantics:** which fields are CAS'd (`draftRev` vs
  trimmed-draft equality for bare tokens), what makes the verb return `false` vs throw,
  and whether `false` means "retryable conflict" or "coordinate mismatch".
- **Confirm unit lengths:** how one logical unit (chip, token, mention) expands in each
  projection — the conversion rule is always derivable from that expansion factor.
- **Never ignore a boolean return from a mutating verb**; treat it as the commit signal
  for all plugin-side bookkeeping.
- Re-read these after any host version bump: projection semantics live in
  `editor/projection.ts` and can change expansion rules without changing the verb
  signatures.
