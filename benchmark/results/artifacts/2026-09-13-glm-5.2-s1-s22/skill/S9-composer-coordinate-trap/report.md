# S9 · Composer Coordinate Trap — Diagnosis Report

Plugin: `@org/dsh-attach-input` v0.2.3 (community Web plugin) on DSH `0.1.2-alpha.3`.
Evidence: `plugin-client.js` (insert + remove + dock-chip excerpt), `console-session.txt`
(repro capture), `host-input-facade.ts` (verb guards), `host-input-contract.ts` (published
types + projection docs). Read-only analysis; nothing outside the report directory was written.

## Root cause in one sentence

Both user-visible bugs are one contract misread: **the plugin computes token-span coordinates
against `InputState.draft` (the *clipboard-text projection*, where a chip expands to its full
`clipboardText`), but the host verbs `insertReference` and `consumeToken` guard and splice
against `projection.detectText` (the *detect projection*, where a chip is exactly one U+FFFC
character)** — the two projections agree only while the composer holds zero chips, which is
exactly why the first paste works and every later one fails.

The host source states this directly:

- `Occurrence.offset` / `Occurrence.length`: *"Offset/Length in the **clipboard-text
  projection**… the occurrence occupies exactly `[offset, offset+length)`"*.
- `InputState.draft`: *"Clipboard-text projection of the editor document (**chips expanded to
  their clipboard form**)"*.
- `EditorProjection.detectText`: *"**Trigger/TokenSpan coordinate text (chip = one U+FFFC)**"*
  — i.e. this is the coordinate system `TokenSpan` uses.
- `insertReference` reads `this.projection.detectText.slice(span.end, span.end + 1)` for its
  tail-space check and edits via `$replaceDetectSpanWithNodes(span, nodes)`; `consumeToken`'s
  span guard splices via `$replaceDetectSpanWithText(guard.span, '')`. Both consume `span`
  as **detect coordinates**; the only scalar guard besides the splice is the CAS
  `span.draftRev !== this.rev`.

## 1 · Why paste #1 succeeds and every later paste toasts

Plugin insert path:

```js
const snapshot = input.state.getSnapshot();          // InputState: clipboard-projection coords
…
input.insertReference({ … }, {
  start: snapshot.draft.length,                      // ← clipboard-projection coordinate
  end: snapshot.draft.length,
  draftRev: snapshot.draftRev,                       // ← correct: rev CAS matches this.rev
});
```

**Paste #1** (empty composer): `draft === ''`, so `start = end = 0`. Zero is zero in *every*
projection — clipboard length and detect length are both 0 — and `draftRev` is current, so the
guard passes and the splice applies at detect offset 0. Capture confirms success: after the
insert, `draft` (clipboard projection) is `"[attachment: screenshot.png] "` (length 29) while
the occurrence occupies `[0, 28)`; on the detect side the document is just `"\uFFFC "`
(length 2). The projections have now **diverged by 27 characters**, and they diverge further
with every chip (clipboard grows by `clipboardText.length + 1` per chip — the facade appends a
separating space unless one is already next; detect grows by exactly 2).

**Paste #2**: the plugin again passes `start = end = snapshot.draft.length = 29`. The host
CAS still passes (`draftRev` is fresh — the plugin re-snapshots after its optional
`setDraft`, and on paste #2 the trailing-space check `/\s$/` already matches, so no
`setDraft` even runs), but `span.end = 29` is far beyond the end of `detectText` (length 2).
`$replaceDetectSpanWithNodes` cannot apply an out-of-range detect span, `applied` stays
`false`, `insertReference` returns `false`, and the plugin throws the toast
`"The DSH composer changed before the attachment could be inserted"` and rolls back its
record — hence no second chip anywhere.

**"First works, later fails" is the signature of a coordinate-system mismatch**: the two
projections are identical only in the chip-free state, so the very first interaction after a
fresh/emptied composer succeeds and every interaction after any chip exists fails — the failure
count tracks *chips present*, not *paste count*, not timing, not revision races (a genuine
`draftRev` CAS failure would be intermittent, not deterministic on paste #2).

## 2 · Why the × click yields `unavailable` instead of removing the chip

Plugin removal path:

```js
const end = occurrence.offset + (occurrence.length ?? 1);   // [0, 28) — clipboard-projection coords
input.consumeToken({
  kind: 'span',
  span: { start: occurrence.offset, end, draftRev: snapshot.draftRev },
});
…
records.delete(occurrence.ref);                            // ← runs unconditionally
changed();
```

`Occurrence.offset/length` are documented clipboard-projection coordinates, but
`consumeToken`'s span guard splices `detectText`. The span `[0, 28)` fails the detect-side
splice (the whole detect document is 2 characters), so `consumeToken` returns `false` — and
the plugin **never inspects the return value**, so it cannot notice the rejection. It then
unconditionally executes `records.delete(occurrence.ref)` and re-renders.

Result, matching the capture exactly:

- Host side: no edit applied → the composer chip stays.
- Plugin side: the record is gone → the dock-chip renderer looks up
  `records.get(occurrence.ref)`, gets `undefined`, and the rendering excerpt maps
  `record === undefined` to the label `'unavailable'`. The chip is still rendered (the dock
  derives from occurrences), only its size label collapses.

So `unavailable` is not a host status — it is the plugin's own fallback for "occurrence still
exists but my bookkeeping no longer knows it", reached because a rejected verb was treated as
success. One misread (clipboard vs detect coordinates) causes the insert failure; the same
misread plus an ignored boolean return causes the removal symptom.

## 3 · Fix direction — conversion rule derived from the host source

**Rule (from `host-input-contract.ts`, not guesswork):** a chip occupies `clipboardText.length`
characters in `InputState.draft` / `Occurrence` coordinates but exactly **1** character
(`U+FFFC`) in `TokenSpan` / detect coordinates. Therefore, for any clipboard-projection
offset `o`:

```
detect(o) = o − Σ (occurrence_j.clipboardText.length − 1)   for every occurrence_j with offset_j < o
```

(`occurrences` are sorted by offset, so this is a simple prefix walk over the snapshot's
`occurrences` array. Equivalently: detect length = `draft.length` − Σ(`len_j − 1`).) The
`draftRev` field needs **no** conversion — it is the same monotonic revision in both worlds;
take it from the same fresh snapshot as the offsets.

**Insert path (`add`)** — convert the insertion point to detect coordinates and stop
re-implementing the trailing space:

- Replace `start/end: snapshot.draft.length` with the converted end-of-document detect offset:
  `detectEnd = snapshot.draft.length − Σ(occ.clipboardText.length − 1)`; pass
  `{ start: detectEnd, end: detectEnd, draftRev: snapshot.draftRev }`.
- Drop the plugin's own trailing-space `setDraft(snapshot.draft + ' ')` logic: the facade
  already inserts a separating space unless `detectText[span.end] === ' '`. Appending a space
  yourself is both redundant and a second coordinate hazard (it mutates the clipboard
  projection and bumps `rev`, forcing the extra re-snapshot the code currently carries).
- Keep the `phase === 'plain'` check and the rollback on `false`; that part is correct.

**Removal path (`remove`)** — convert the occurrence range and honor the return value:

- Convert `[occurrence.offset, occurrence.offset + occurrence.length)` to
  `[detect(occurrence.offset), detect(occurrence.offset) + 1)` — a chip is exactly one detect
  character, so the detect span length is always **1**, never `occurrence.length` (the
  plugin's own comment — "must span `occurrence.length`" — is the misread spelled out; note
  the guard also hard-fails when `start === end`, so an empty converted span can never apply).
- Pass `draftRev` from the fresh snapshot (already done).
- Only `records.delete(ref)` and `changed()` **after `consumeToken(...) === true`**. On
  `false`, surface the failure (or re-snapshot and retry once) — never leave the record map
  diverged from the live occurrences; that divergence is precisely what renders `unavailable`.
- The `setDraft` fallback branch has the same coordinate bug in reverse (it slices
  `snapshot.draft` — clipboard coords — with detect-intent offsets); if kept, it must slice in
  one coordinate system consistently, and it should also clear/rebuild the chip, which a plain
  draft edit does not do — prefer fixing `consumeToken` usage and deleting the fallback.

## 4 · Regression test plan

Assert these exact sequences against a real mounted input facade (not mocks of the plugin's own
math), on a fresh session and on a non-empty composer:

1. **Repeat-insert (the toast bug).** Empty composer → paste #1 → assert `insertReference`
   returned `true`, one occurrence, `draft` ends with `clipboardText + ' '`. Without
   re-creating the session, paste #2 and then #3 → each insert returns `true`, occurrence
   count reaches 3, offsets/lengths are clipboard-projection consistent, and **no toast**.
   This is the sequence that fails today: any test whose second paste happens on a chip-free
   composer cannot catch the bug.
2. **Insert with typed text.** Type `"see this"` (no trailing space) → paste → insert returns
   `true`; then type more text after a chip → paste again → still `true` (exercises the
   trailing-space/typed-text interaction now that the plugin no longer `setDraft`s its own
   space).
3. **Remove middle chip.** With chips A, B, C inserted, click × on the dock chip for B →
   `consumeToken` returned `true`; composer contains exactly A and C; `draft` shrank by
   exactly B's `clipboardText.length` (+ separating space); remaining occurrence offsets
   re-derived and sorted; dock chip for B is gone entirely (assert the rendered label is **not**
   `unavailable` and the occurrence list no longer contains B's ref).
4. **Remove the only chip, then remove again.** × on the single chip → chip gone, `draft`
   empty, `records` empty. This also covers the empty-composer path that made paste #1 look
   healthy.
5. **Rejected removal leaves bookkeeping intact (the `unavailable` bug).** Force a
   `insertReference`/`consumeToken` rejection (e.g. `draftRev` stale: snapshot, mutate the
   draft, then call remove with the old snapshot) → assert the plugin does **not** delete the
   record: dock chip still shows its size label, never `unavailable`, and the plugin surfaces
   the failure. Guards against reintroducing "ignore the boolean return".
6. **Concurrent-edit CAS.** Snapshot → external draft edit → insert at the converted offset →
   assert `false` and that the plugin rolled its record back with the exact toast (the one
   legitimate use of that error message).

Sequences 1 and 3 are the scored core: repeat-interaction after a successful chip insert, and
removal of a chip that still exists host-side.

## 5 · Routine host-source checks before calling input-machine verbs (unscored guidance)

Before every release that calls `insertReference` / `consumeToken` (or any input-machine
verb), read — not assume — the following in the host source:

- **Which projection a parameter lives in.** `packages/client/ui-conversation/src/client/
  contract/input.ts` and `input/editor/projection.ts` publish the mapping: `draft` and
  `Occurrence.offset/length` are clipboard-text coordinates; `TokenSpan` / trigger /
  `detectText` are detect coordinates (chip = one `U+FFFC`). Any value you compute from
  `InputState` and hand to a span guard must be converted.
- **The verb guard body**, in `input/facade.ts`: what phase values are accepted
  (`plain`/`claimed` vs `plain`-only), which scalar the CAS compares (`span.draftRev` vs
  `this.rev`), and any cheap-reject conditions (`start === end`, empty token,
  trimmed-draft equality) that return `false` without an edit.
- **The return value's meaning** — these verbs report rejection as `false`; treat `false` as
  "nothing happened" and never mutate plugin-side bookkeeping on an uninspected return.
- **What the verb does for you** (trailing-space insertion, chip-node creation) so the plugin
  does not re-implement it in the wrong coordinate system.
- Re-check these on every DSH upgrade: the projection docs are the contract, and a rename or
  re-documentation of `detectText`/`clipboardText` is exactly where this class of defect
  re-enters.

## Status

- **Completed**: full read-only diagnosis of both symptoms from the fixture evidence; both tied
  to the single clipboard-projection vs detect-projection coordinate misread (plus the ignored
  `consumeToken` boolean); conversion rule derived from `host-input-contract.ts` /
  `host-input-facade.ts`; fix directions for insert and removal paths; six-sequence
  regression plan; maintainer checklist.
- **Skipped**: none of the requested items.
- **Pending/residual risk**: no live host was mounted (task is read-only by design); the exact
  out-of-range behavior of `$replaceDetectSpanWithNodes` is inferred from its role as the
  detect-splice primitive plus the captured `false` return, not from its source body, which
  the fixture trims. This does not change the diagnosis or the rule.
