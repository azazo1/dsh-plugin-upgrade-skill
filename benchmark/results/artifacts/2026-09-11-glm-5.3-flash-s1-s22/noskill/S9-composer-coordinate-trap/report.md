# S9 · Composer Coordinate Trap — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.2.3 · Host: DSH `0.1.2-alpha.3`
Evidence: `fixture/plugin-client.js`, `fixture/console-session.txt`, `fixture/host-input-facade.ts`, `fixture/host-input-contract.ts`.

## Root cause in one sentence

Both symptoms come from a single contract misread: the plugin computes every span in **clipboardText coordinates** (from `snapshot.draft` / `occurrence.offset`/`length`), while both host verbs — `insertReference` and `consumeToken` — validate and splice spans in **detectText coordinates**, where each chip occupies exactly **one character (U+FFFC)** instead of its multi-character `clipboardText` string.

The contract states this explicitly (`host-input-contract.ts`):

- `InputState.draft` — "Clipboard-text projection of the editor document (chips expanded to their clipboard form)."
- `EditorProjection.detectText` — "**Trigger/TokenSpan coordinate text (chip = one U+FFFC)**."
- `EditorProjection.clipboardText` — "Persistence/InputState draft text (chip = clipboardText)."
- `Occurrence.offset`/`length` — "Offset/Length **in the clipboard-text projection**."

And the facade (`host-input-facade.ts`) confirms the verbs consume detect coordinates: `insertReference` reads `this.projection.detectText.slice(span.end, span.end + 1)` and splices via `$replaceDetectSpanWithNodes(span, nodes)`; `consumeToken` splices via `$replaceDetectSpanWithText(guard.span, '')`. The JSDoc on `insertReference`'s `span` parameter says "pick-time span snapshot (**detect coordinates**)."

## 1. Why the FIRST paste succeeds and every later paste fails

What the plugin computes (`plugin-client.js`, `add`):

```js
start: snapshot.draft.length,
end: snapshot.draft.length,
draftRev: snapshot.draftRev,
```

`snapshot.draft` is the **clipboardText projection**; the host compares and splices this span against `projection.detectText`.

- **Paste #1 (empty composer):** `draft.length === 0`, so the plugin sends span `{start: 0, end: 0}`. In an empty document the two coordinate systems coincide (no chips yet to diverge), and `span.draftRev` matches `this.rev`, so `$replaceDetectSpanWithNodes` succeeds at offset 0. The host then expands the chip to its clipboard form in the published draft — which is why the capture shows `draft = "[attachment: screenshot.png] "` (length 29) while the detect text is only `<U+FFFC>` plus a space (length 2; the occurrence has `length: 28` in clipboard coordinates).
- **Paste #2:** the plugin re-reads `snapshot` and sends span `{start: 29, end: 29}` with a valid, current `draftRev`. But the host's `detectText` is now only 2 characters long. The `draftRev` CAS passes, yet `$replaceDetectSpanWithNodes` cannot splice at offset 29 of a 2-character document, so `insertReference` returns `false`. The plugin then does `records.delete(ref)` and throws 'The DSH composer changed before the attachment could be inserted' — the toast both users saw.

Why "first works, later fails" is the signature of this mismatch: the mismatch only manifests once the two projections have different lengths, i.e. once at least one chip exists. With zero chips, clipboard coordinates and detect coordinates are numerically identical, so the first operation on a fresh composer always succeeds; every subsequent operation carries offsets inflated by the sum of `(occurrence.clipboardText.length − 1)` over existing chips (here 28 − 1 = 27 extra characters) and lands past the end of the detect text. The toast message is misleading — the composer did **not** change between snapshot and call (the `draftRev` CAS would have caught a genuine race); the guard that actually fired is the out-of-range splice.

## 2. Why the × click turns the chip into `unavailable` instead of removing it

Trace of `remove()` (`plugin-client.js`) against the session capture (`console-session.txt`, 12:40:30):

1. The dock chip's occurrence is the host's published view: `{ offset: 0, length: 28, clipboardText: "[attachment: screenshot.png]" }` — clipboard coordinates per the contract.
2. The plugin computes `end = occurrence.offset + occurrence.length = 0 + 28 = 28` and calls `input.consumeToken({ kind: 'span', span: { start: 0, end: 28, draftRev: snapshot.draftRev } })`.
3. In the host, `consumeToken`'s span branch checks only `draftRev !== this.rev` (passes — rev is current) and `start === end` (passes — 0 ≠ 28), then calls `$replaceDetectSpanWithText(guard.span, '')` on the **detect text** of length 2 (`<U+FFFC>` + space). A span of 0..28 is out of range; the splice fails and `consumeToken` returns `false`.
4. The plugin **never inspects the return value** (the capture notes: "consumeToken(...) returned (not inspected by the plugin code)"). Unconditionally it executes `records.delete(occurrence.ref)` and `changed()`.
5. Result: the host-side chip is untouched (the composer chip stays, and the dock — which renders chips from the still-present occurrence — keeps the chip), but the plugin's own `records` Map no longer has the ref. The dock renderer's lookup (`record === undefined ? 'unavailable' : humanBytes(record.total)`) therefore renders the meta as **"unavailable"**.

So "unavailable" is a bookkeeping desynchronization the plugin created itself: it deleted local state for a removal that never happened, because it ignored the verb's `false` return while feeding it a detect-coordinate span built from clipboard-coordinate occurrence fields.

## 3. Fix direction

**Rule (derived from the host contract, not guesswork):** any span passed to `insertReference` or `consumeToken(kind:'span')` must be in detectText coordinates, where each occurrence contributes exactly **1** character (U+FFFC), while `InputState.draft` and `Occurrence.offset`/`length` are clipboard coordinates where an occurrence contributes `clipboardText.length` characters. Therefore:

> detectCoord(x) = clipboardCoord(x) − Σ over occurrences whose clipboard range ends at or before x of (occ.clipboardText.length − 1)

Since the plugin does not receive `detectText` through `getSnapshot()`, derive detect coordinates from `occurrences` (sorted by offset): the k-th occurrence's detect offset is `occ_k.offset − Σ_{j<k}(occ_j.clipboardText.length − 1)`, and its detect span is exactly **1** character wide.

**Insert path (in `add`):** do not use `snapshot.draft.length`. Compute the detect-coordinate end-of-document position:

```js
const plainLength = snapshot.draft.length
  - snapshot.occurrences.reduce((n, o) => n + o.clipboardText.length, 0);
const detectEnd = plainLength + snapshot.occurrences.length; // each chip = 1 U+FFFC
input.insertReference({...}, { start: detectEnd, end: detectEnd, draftRev: snapshot.draftRev });
```

(General form for an arbitrary clipboard offset x: subtract one per chip lying entirely before x. For end-of-draft this reduces to the plain-text length plus the chip count.)

**Removal path (in `remove`):** convert the occurrence's clipboard range to its 1-character detect span, and honor the return value:

```js
const k = snapshot.occurrences.findIndex(o => o.ref === occurrence.ref);
const detectStart = occurrence.offset
  - snapshot.occurrences.slice(0, k).reduce((n, o) => n + o.clipboardText.length - 1, 0);
const accepted = input.consumeToken({
  kind: 'span',
  span: { start: detectStart, end: detectStart + 1, draftRev: snapshot.draftRev },
});
if (!accepted) return;          // keep the record; do NOT records.delete / render "unavailable"
records.delete(occurrence.ref);
changed();
```

Secondary fixes the same trace exposes: (a) gate `records.delete` + `changed()` on the verb result in **both** paths — the insert path already does this correctly; (b) the fallback `setDraft` branch in `remove` slices `snapshot.draft` by clipboard offsets, which is acceptable only because `setDraft` takes clipboard text — keep it as a fallback for a genuinely absent `consumeToken`, never as a response to a `false` return; (c) re-snapshot `draftRev` immediately before each verb call — the insert loop already re-reads after each insert; keep that, since inserting advances the revision.

## 4. Regression test plan

Sequences that must be asserted (unit-level against a fake host facade mirroring the real guards, plus a manual pass on DSH):

1. **Repeat insert (reported bug #2).** Fresh composer → paste chip A → assert `insertReference` true, one occurrence, `draft` contains A's clipboardText; paste chip B → assert `insertReference` true, **two** occurrences, toast absent, dock shows both records. Fails today (paste #2 returns false).
2. **Insert after typing.** Type "hello " → paste → assert the chip lands after the text with a separating space, and detect coordinates account for the typed characters (no chip present, so the coordinate systems coincide — pins the plain-text case).
3. **Insert with a preceding chip.** Chip A → chip B → remove A → insert C → assert C's span converts correctly when a **preceding** chip exists (offset inflation with leading, not only trailing, chips).
4. **Remove first of two chips (bug #3).** Chip A, chip B → click × on A → assert `consumeToken` returned true, A gone from `occurrences` and the composer, B's detect span re-based correctly, `records` no longer has A, and the dock renders B with its byte size — **never** "unavailable".
5. **Remove the last chip.** Chip A → × → assert empty composer, empty occurrences, empty dock.
6. **Stale-revision rejection is surfaced, not swallowed.** Mutate the composer (via `setDraft`) between snapshot and verb call → assert the verb returns false, the record is **retained** (no `records.delete`), the chip stays, and the user sees the retry/wait message rather than a phantom success.
7. **Renderer guard.** With a record deliberately missing for an existing occurrence, assert the dock shows "unavailable" — keeps the existing fallback meaningful but proves it is reachable only through a real desync, which sequences 4 and 6 now prevent.

## 5. Maintainer's routine source-reading discipline (guidance, not scored)

Before calling any input-machine verb:

- **Identify the coordinate system of every span argument** in the host facade source: which projection (`detectText` vs `clipboardText`) the guard splices, and how chips are encoded in each (`detectText`: one U+FFFC; `draft`/`occurrences`: full `clipboardText`). Never derive spans from a projection you did not confirm the verb consumes.
- **Check field ownership in the published contract** (`Occurrence.offset`/`length` are documented "in the clipboard-text projection") — published views are often in a different coordinate system than verb arguments.
- **Check every verb's return contract**: a boolean here means "CAS/splice applied"; treating `false` as ignorable turns a rejected edit into silent state desync (the "unavailable" bug).
- **Check what invalidates the guard**: the `draftRev` CAS means any host-side edit (including your own previous verb) advances the revision — re-snapshot immediately before each call in a loop.
- **Exercise the second interaction before release**: any flow that works on an empty composer must be re-tested with at least one existing chip; "first call works, repeat call fails" is the fingerprint of a coordinate-space mismatch, and it is invisible in a single-shot smoke test.
