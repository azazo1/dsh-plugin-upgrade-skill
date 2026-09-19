# S9 · Composer Coordinate Trap — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.2.3 · Host: DSH `0.1.2-alpha.3`
Evidence: `plugin-client.js`, `console-session.txt`, `host-input-facade.ts`, `host-input-contract.ts`

## One root cause behind both symptoms

The host input machine exposes **two text projections** of the same editor document
(`host-input-contract.ts`, `EditorProjection`):

- `detectText` — "Trigger/TokenSpan coordinate text (**chip = one U+FFFC**)"
- `clipboardText` — "Persistence/InputState draft text (chip = clipboardText)"

and `TokenSpan` guards/facade verbs (`insertReference`, `consumeToken(span)`) operate in
**detect coordinates** (`$replaceDetectSpanWithNodes` / `$replaceDetectSpanWithText` splice the
DETECT text, per the facade header comment). `InputState.getSnapshot()` returns `draft` —
the **clipboard-text** projection — plus `draftRev` and `occurrences` whose `offset`/`length`
are also clipboard-text coordinates ("Offset in the clipboard-text projection",
"Length in the clipboard-text projection").

The plugin computes all span coordinates from `snapshot.draft` (clipboard text) and passes
them to verbs that expect detect coordinates. That single misread produces both bugs.

## 1. Why paste #1 succeeds and every later paste fails

Paste #2: `add()` re-reads the snapshot — `draft = "[attachment: screenshot.png] "` (length 29,
per `console-session.txt` line 8) — and calls:

```js
input.insertReference(ref, { start: snapshot.draft.length, end: snapshot.draft.length, draftRev: snapshot.draftRev })
```

i.e. `{ start: 29, end: 29 }`, but the host's `this.projection.detectText` for the same
document is only `"\uFFFC "` — 2 characters, because the existing chip collapses to one
U+FFFC in detect coordinates. `draftRev` is fresh, phase is `'plain'`, so both early guards in
`insertReference` (`phase`, `span.draftRev !== this.rev`) pass; the failure is inside the edit:
`$replaceDetectSpanWithNodes(span, nodes)` receives a span (`start: 29, end: 29`) far outside
the 2-character detect document, cannot apply it, and `applied` stays `false`. The facade
returns `false`, the plugin throws "The DSH composer changed before the attachment could be
inserted" and rolls back its record (`records.delete(ref)`). The toast message is misleading:
the composer did not change since the snapshot — the span coordinates were in the wrong plane.

Why "first works, later fails" is the signature: on the **first** paste the composer is empty,
so `detectText === clipboardText === ''` and the two coordinate systems coincide; wrong-plane
coordinates are indistinguishable from correct ones. After the first chip exists, the projections
diverge by `clipboardText.length − 1` characters per chip (28 characters for the first chip:
29 vs 2), so every subsequent paste hands the host an out-of-range span. Any bug that only
appears on the *second* interaction with a state-ful span guard is exactly this coordinate-plane
divergence pattern.

## 2. Why the × click yields "unavailable" instead of removal

The removal path has the same plane mismatch, plus plugin bookkeeping that ignores the verb's
result:

1. `remove()` reads `occurrence` (clipboard-text coordinates: `offset: 0, length: 28`) and builds
   `consumeToken({ kind: 'span', span: { start: 0, end: 28, draftRev } })` — again clipboard
   coordinates into a detect-coordinate splice (`$replaceDetectSpanWithText(guard.span, '')`).
2. The guards that *do* run pass (`phase === 'plain'`, fresh `draftRev`, `start !== end`), but the
   splice fails because `end: 28` exceeds the 2-character detect document. `consumeToken`
   returns `false` — which `console-session.txt` line 18 confirms the plugin "returned (not
   inspected by the plugin code)".
3. `remove()` then unconditionally runs `records.delete(occurrence.ref)` and `changed()`,
   regardless of the return value.
4. On re-render, the dock chip's meta line (`plugin-client.js` lines 63–65) finds
   `record === undefined` and renders `'unavailable'` (bytes label branch). The composer chip
   was never spliced out, so it also remains.

So "unavailable" is the plugin's own render fallback for a record it deleted even though the
host rejected the removal; the composer state is untouched.

## 3. Fix direction and call sites

**Rule (derived from the host sources):** every `TokenSpan` handed to `insertReference` or
`consumeToken({kind:'span'})` must be in **detect coordinates**, where each occurrence
contributes exactly **1** character (U+FFFC) instead of its `clipboardText.length`. Conversion
between the planes uses the published `InputState.occurrences` / `EditorProjection`: a
clipboard-text position `p` maps to detect position `p − Σ (occ.clipboardText.length − 1)` over
all occurrences lying wholly before `p`; equivalently, an occurrence's detect range is
`[d, d+1)` where `d = occ.offset − Σ_{occ' before occ} (occ'.clipboardText.length − 1)`. Plain
text between chips converts 1:1. `draftRev` needs no conversion — it is plane-independent.

- **Insert path (`add`, plugin-client.js lines 28–32):** convert the target position before
  calling `insertReference`. For the "append at end of draft" case:
  `const detectEnd = snapshot.draft.length − snapshot.occurrences.reduce((n,o)=>n+o.clipboardText.length-1, 0)`
  and pass `{ start: detectEnd, end: detectEnd, draftRev: snapshot.draftRev }`. (Note the host
  then reads `detectText.slice(span.end, span.end+1)` to decide on the separating space — that
  only makes sense in detect coordinates, further confirming the plane.)
- **Removal path (`remove`, lines 49–54):** derive the occurrence's detect span from
  `snapshot.occurrences` (match by `occurrenceId`/`ref`), not from `occurrence.offset` directly:
  `start = detectOffset(occ)`, `end = start + 1`. Additionally, honor `consumeToken`'s return
  value: only `records.delete(ref)` + `changed()` when it returns `true`; on `false`, refresh the
  snapshot and re-reconcile records with `occurrences` instead of deleting the record (this
  alone removes the `unavailable` state even if a splice ever fails again).

## 4. Regression test plan

Assert these exact sequences against a composer that already contains at least one chip and
arbitrary draft text (never only the empty composer):

1. **Empty-composer paste** (known-good baseline): chip in composer + dock chip with correct
   byte label; snapshot has 1 occurrence, `draft === clipboardText` projection of the chip.
2. **Second paste with one chip present** (the reported bug): second chip inserts; composer
   detect document contains two U+FFFC; dock shows two chips with correct labels; no toast;
   `insertReference` returned `true`. Repeat to N pastes.
3. **Paste into a non-empty draft with a trailing chip mid-text** (chip not at end, text after
   it): insert lands at the requested position, trailing text preserved, space-separator rule
   verified (host adds a space unless one is next).
4. **× removal with one chip and draft text present**: `consumeToken` returns `true`; composer
   chip gone (detect draft loses exactly 1 char), dock chip gone, record gone.
5. **× removal of the first of two chips**: only that chip's range disappears; the other chip's
   offsets re-render correctly after snapshot refresh.
6. **Stale-guard negative test**: mutate the composer between snapshot and verb call (simulated
   `draftRev` bump) and assert the verb returns `false` and the plugin does **not** delete its
   record and does **not** render `unavailable` — the record/reconcile path is exercised.
7. **Coordinate-plane invariant test**: for any composer state, assert the plugin's computed
   detect span end ≤ `projection.detectText.length` (or equivalent mapping round-trip), so a
   future plane regression fails loudly in tests rather than as a user toast.

## 5. Routine host-source checks before calling input-machine verbs

- Identify which **text projection** each verb's span/offset parameters use: read the facade and
  the `$replace*` helpers (`detectText` vs `clipboardText` — chip = U+FFFC vs full
  `clipboardText`) and never assume `InputState.draft` shares coordinates with `TokenSpan`.
- Check every guard a verb applies (`phase`, `draftRev` CAS, `start === end`, trimmed-draft
  equality for bare tokens) and what each failure returns — then **check the boolean return
  value** at every call site and keep bookkeeping (record deletion, re-render) conditional on it.
- Read the projection contract (`EditorProjection`, `Occurrence`) for which fields are
  "insert-time cache" vs live, and which plane `occurrence.offset/length` are documented in.
- Test the second interaction, not the first: any span guard only diverges once state (a chip)
  makes the projections differ.