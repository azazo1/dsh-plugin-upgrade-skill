# S9 · Composer Coordinate Trap — Diagnosis Report

**Task:** S9-composer-coordinate-trap (read-only analysis)
**Plugin:** `@org/dsh-attach-input` v0.2.3 (community Web plugin, client face)
**Host:** DSH `0.1.2-alpha.3`
**Evidence:** fixture pack — `plugin-client.js`, `console-session.txt`, `host-input-facade.ts`, `host-input-contract.ts`
**Mode:** A · inspect (read-only; no migration, no install, fixture untouched)

---

## Executive summary

Both reported bugs are **one contract misread, not two unrelated defects**. The host input
machine has **two coordinate systems over the same composer document**:

- the **clipboard-text projection** (`InputState.draft`, `Occurrence.offset/length`), where
  each chip is expanded to its `clipboardText` (e.g. `[attachment: screenshot.png]`, 28 chars);
- the **detectText projection** (`EditorProjection.detectText`), where each chip is a **single
  U+FFFC object-replacement character** (`$createReferenceChipNode` → one node → one char).

The verbs the plugin calls — `insertReference(ref, span)` and `consumeToken({kind:'span', span})`
— take `TokenSpan`s in **detect coordinates**: their bodies call
`$replaceDetectSpanWithNodes` / `$replaceDetectSpanWithText`, which splice the **detect**
text. The plugin, however, computes every span from `snapshot.draft.length` and
`occurrence.offset/length`, which are **clipboard coordinates**. Both call sites feed
clipboard-coordinate values into detect-coordinate verbs. Paste #2 fails and the × click
"fails" for the same reason: the span is wrong in the verb's coordinate system.

---

## 1. Why the first paste succeeds and every later paste toasts

### The exact mismatch

In `add()` the plugin inserts at end-of-draft:

```js
start: snapshot.draft.length,   // clipboard-projection length
end:   snapshot.draft.length,
draftRev: snapshot.draftRev,
```

The verb's guard and splice operate on detect text:

```ts
insertReference(ref, span) {
  if (span.draftRev !== this.rev) return false          // rev CAS — plugin passes a fresh snapshot's rev, OK
  const tail = this.projection.detectText.slice(span.end, span.end + 1)
  this.applyEdit(() => { ... applied = $replaceDetectSpanWithNodes(span, nodes) })
  return applied
}
```

`span.start/end` are used to splice `detectText`. The two projections have **equal length
only while the composer holds no chips**; each chip contributes `clipboardText.length`
chars to `draft` but exactly **1** char (`U+FFFC`) to `detectText`.

### Why "first works, later fails" is the signature

- **Paste #1 (empty composer):** `draft.length === detectText.length === 0`. The span
  `{0, 0}` is valid in *both* coordinate systems, so the (wrongly computed) position
  coincidentally lands at the end of the detect text. The splice applies, the chip renders,
  and the plugin's bookkeeping looks correct — the bug is invisible.
- **After paste #1:** `draft = "[attachment: screenshot.png] "` (29 chars) but
  `detectText = "\uFFFC "` (2 chars — one chip char plus the separating space the facade
  appends). Every later `add()` computes `start = end = 29` — a position **27 characters
  past the end of the detect text**. The detect-span splice cannot apply
  (`$replaceDetectSpanWithNodes` returns `false`), so `insertReference` returns `false`,
  the plugin rolls back its record and throws the toast
  `"The DSH composer changed before the attachment could be inserted"`.

This is exactly the observed signature: the two coordinate systems diverge by
`Σ (occ.length − 1)` over the chips present, i.e. they agree **only** on an empty (or
chip-free) composer. Hence insert #1 succeeds and every insert after the first chip exists
fails — even though the `draftRev` CAS (the guard the toast message points at) is actually
satisfied, because the plugin re-snapshots after every mutation. The failure is the span
*geometry*, not the revision.

(Note the smaller corollary: because the facade itself appends a separating space when the
char after the span is not a space, the plugin's own "append a trailing space via
`setDraft`" preamble is unnecessary — and each `setDraft` bumps `rev`, which is why
re-snapshotting afterwards is load-bearing for the CAS.)

## 2. Why the × click turns the chip into `unavailable`

The removal path makes the **same coordinate mistake plus a bookkeeping error**:

```js
const end = occurrence.offset + (occurrence.length ?? 1);   // clipboard coords
input.consumeToken({ kind: 'span',
  span: { start: occurrence.offset, end, draftRev: snapshot.draftRev } });
...
records.delete(occurrence.ref);   // executed unconditionally
changed();
```

`Occurrence.offset/length` are explicitly documented as *"Offset/Length in the
clipboard-text projection"* (`host-input-contract.ts`). `consumeToken`'s span guard
checks `draftRev` (satisfied — fresh snapshot), then splices **detect** text via
`$replaceDetectSpanWithText(guard.span, '')`. The span `{0, 28}` in a detect text of
length 2 is out of range; the splice does not apply and `consumeToken` returns `false`.

The plugin **ignores the return value** and unconditionally deletes the record and
re-renders. Trace of the observed UI:

1. The composer chip **stays** — the host edit never applied.
2. `records.delete(ref)` runs anyway, so the dock chip's render lookup
   `records.get(occurrence.ref)` now returns `undefined`.
3. Per the plugin's own rendering excerpt, `record === undefined` renders the meta label
   `'unavailable'` — the size label flips from `48.2 KiB` to `unavailable` while the chip
   itself persists, matching user report #3 and the capture verbatim.

So the removal bug is the same projection misread (clipboard span → detect splice), with a
secondary defect that the plugin desyncs its bookkeeping (`records`) from host state by not
gating `records.delete` on `consumeToken`'s boolean.

## 3. Fix direction — the conversion rule, derived from the host source

From `EditorProjection` in `host-input-contract.ts`: the detect projection replaces each
occurrence — `length` clipboard characters — with **one** `U+FFFC` character. Therefore,
for any clipboard-projection offset `c`:

```
detect(c) = c − Σ (o.length − 1)   over occurrences o with o.offset + o.length ≤ c
```

and an occurrence occupying `[offset, offset+length)` in clipboard coordinates occupies
exactly `[detect(offset), detect(offset) + 1)` — **one detect character** — in detect
coordinates. (Equivalently: `detectText.length = draft.length − Σ (o.length − 1)`.)

### Insert path (`add`)

At each `insertReference` call site, convert the end-of-draft position before building the
span:

```js
const chipsBefore = snapshot.occurrences
  .filter(o => o.offset + o.length <= snapshot.draft.length)
  .reduce((n, o) => n + (o.length - 1), 0);
const detectEnd = snapshot.draft.length - chipsBefore;
// span = { start: detectEnd, end: detectEnd, draftRev: snapshot.draftRev }
```

Sanity property to assert: `detectEnd === detectText.length` when inserting at end of draft
(paste #2: `29 − 27 = 2`, exactly the chip + space in `detectText`). Keep passing the
**fresh** `snapshot.draftRev` after any `setDraft` preamble (or drop the preamble — the
facade already inserts a separating space when needed). Continue rolling back the record
when `insertReference` returns `false` — that handling is already correct.

### Removal path (`remove`)

```js
const detectStart = occurrence.offset - snapshot.occurrences
  .filter(o => o.offset + o.length <= occurrence.offset)
  .reduce((n, o) => n + (o.length - 1), 0);
const consumed = input.consumeToken({ kind: 'span',
  span: { start: detectStart, end: detectStart + 1, draftRev: snapshot.draftRev } });
if (!consumed) return;          // keep record; optionally retry with a fresh snapshot
records.delete(occurrence.ref); // only after the host actually removed the chip
changed();
```

Two changes: (a) the span must be **one detect character** wide starting at
`detect(occurrence.offset)` — not `occurrence.length` wide; (b) `records.delete` and the
re-render must be gated on `consumeToken === true` so plugin bookkeeping never desyncs
from host state. The `setDraft` string-slicing fallback branch has the identical flaw (it
slices `snapshot.draft` by clipboard offsets but would need the same conversion relative to
whatever coordinate `setDraft` accepts — verify against the facade before keeping it; the
primary fix is the span conversion).

## 4. Regression test plan

All sequences run against a real composer shell (or a faithful facade double that owns both
projections and the rev counter), asserting **host state and plugin bookkeeping together**:

1. **First paste on empty composer** — chip appears; `draft` ends with a separating space;
   one occurrence with correct clipboard `offset/length`; record status `ready`. (This
   alone passed before, so it must stay green while 2–7 are added.)
2. **Repeat paste without clearing (the toast bug)** — paste file A, then paste file B in
   the same composer: `insertReference` returns `true`; **two** occurrences; `draft`
   contains both `clipboardText`s; detect length equals
   `draft.length − Σ(length−1)`; **no toast**; both dock chips show byte sizes (not
   `unavailable`). This is the exact paste #1 → paste #2 sequence from the capture.
3. **Third+ paste** — repeat once more (divergence grows by 27 per chip; catches any fix
   that only handles the two-chip case).
4. **Paste after typed text** — type `"see this"` (with and without trailing space), then
   paste twice; chips land after the text; the `setDraft` preamble path is exercised.
5. **× on the only chip (the unavailable bug)** — after one paste, click ×:
   `consumeToken` returns `true`; occurrence list empty; `draft` has the chip's clipboard
   text removed; dock chip **gone** (not `unavailable`); `records` empty.
6. **× on a middle chip with three chips present** — removal must splice exactly one
   detect character: the other two occurrences survive, their clipboard `offset/length`
   re-project correctly, and surrounding text is preserved.
7. **× with a stale revision (CAS rejection)** — simulate an intervening edit between
   snapshot and `consumeToken` so the verb returns `false`: assert the plugin **keeps**
   the record (dock chip still shows its byte size, never `unavailable`), keeps the
   composer chip, and either retries with a fresh snapshot or surfaces the failure.
8. **Insert with a stale revision** — same for `insertReference` returning `false`:
   record rolled back, error toast raised (already correct today; pin it so the fix does
   not regress the CAS handling).

Sequences 2/3 pin the coordinate conversion on the insert path; 5/6 pin it on the removal
path; 7/8 pin return-value-gated bookkeeping so neither bug can silently return.

## 5. Routine host-source discipline before calling input-machine verbs (unscored)

- **Read the verb's listener body, not just its published type.** The signature
  `insertReference(ref, span: TokenSpan)` does not say which projection the span indexes;
  the body (`$replaceDetectSpanWithNodes`, `this.projection.detectText.slice`) does.
- **Identify the coordinate system of every published field you consume** — the contract
  JSDoc states it (`Occurrence.offset`: "in the clipboard-text projection";
  `EditorProjection.detectText`: "chip = one U+FFFC"). When a module exposes two
  projections of one document, never mix positions between them.
- **Check the guards and their return values**: the `draftRev` CAS against `this.rev`, the
  `phase` gate, and the boolean return — treat `false` as "host state unchanged", and keep
  plugin-side mirrors (`records`) in lockstep with the boolean, never with the intent.
- **Look for the "empty state works" trap**: any conversion bug whose two coordinate
  systems coincide on the empty document will pass a single-shot smoke test. Always test
  the *second* interaction against a shared-state surface.
- Consult the corridor references when upgrading: Web Client composer/input seams changed
  across alpha edges (e.g. `details`→`rightbar`, injection-surface signature changes), so
  re-verify the verb bodies on each host bump.

---

### Report status

- **Completed:** full read-only diagnosis of both symptoms tied to one contract misread
  (clipboard-projection coordinates fed to detect-projection verbs), the conversion rule
  derived from `host-input-contract.ts` / `host-input-facade.ts`, call-site-level fix
  direction for insert and removal, and an eight-sequence regression plan.
- **Skipped:** no dependency/enablement/runtime validation layers — this is a Mode A
  read-only analysis; no code was changed.
- **Pending/residual risk:** the `setDraft` fallback branch's coordinate expectations and
  the exact out-of-range behavior of `$replaceDetectSpanWith*` are trimmed from the
  excerpts; the fix should confirm them against the full host source before landing.
- **Rollback:** none needed — fixture untouched, no writes outside the report directory.
