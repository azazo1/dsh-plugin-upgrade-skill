# S9 · Composer Coordinate Trap — Diagnosis Report

Plugin: @org/dsh-attach-input v0.2.3 · Host: DSH 0.1.2-alpha.3
Evidence: plugin-client.js, console-session.txt, host-input-facade.ts, host-input-contract.ts (fixture, read-only).

## TL;DR — one contract misread, two symptoms

The host publishes **two coordinate systems** for the composer document:

| Text | Currency | A reference chip occupies |
|---|---|---|
| `InputState.draft`, `Occurrence.offset/.length` | **clipboard-text projection** | the chip's full `clipboardText` (here 28 chars: `[attachment: screenshot.png]`) |
| `TokenSpan` accepted by `insertReference` / `consumeToken` (spliced by `$replaceDetectSpanWithText/Nodes`) | **detect-text projection** | exactly **one U+FFFC character** |

(`host-input-contract.ts`: `EditorProjection.detectText` — “Trigger/TokenSpan coordinate text (chip = one U+FFFC)”; `Occurrence.offset/length` — “in the clipboard-text projection”. `host-input-facade.ts` JSDoc: `span` is “pick-time span snapshot (**detect coordinates**)” and both verbs splice the **DETECT** text.)

The plugin computes its `TokenSpan` values from `InputState.draft.length` and `Occurrence.offset + length` — i.e. it feeds **clipboard coordinates into verbs that guard and splice in detect coordinates**. Both reported bugs are this single mismatch.

## 1. Why paste #1 succeeds and every later paste fails

In `add()` the plugin inserts at the end of the draft:

```js
start: snapshot.draft.length,   // clipboard-projection length
end:   snapshot.draft.length,
draftRev: snapshot.draftRev,
```

- **Paste #1 (empty composer):** clipboard draft and detect text are both ``. Offset 0 is identical in both currencies, `draftRev` CAS passes, `insertReference` applies. Capture confirms: draft becomes `[attachment: screenshot.png] ` (29 clipboard chars) while the detect text is only `\uFFFC ` (2 chars).
- **Paste #2:** the plugin re-reads the snapshot, so `draftRev` is fresh and the CAS in `insertReference` (`span.draftRev !== this.rev`) **passes** — the failure is *not* a revision problem. The plugin sends `start = end = 29` (clipboard length), but the detect text is 2 characters long. `$replaceDetectSpanWithNodes` is asked to replace a span at 29 in a 2-char text — out of range, the edit does not apply, `applied` stays `false`, `insertReference` returns `false`, and the plugin throws the observed toast.

**Why “first works, later fails” is the signature of a coordinate-currency mismatch:** the two projections agree exactly while the document is chip-free and diverge by `clipboardText.length − 1` (here 27) characters **per inserted chip**. The first interaction starts from the empty document where the currencies coincide, so the bug is invisible; every subsequent interaction is offset by the accumulated divergence and fails deterministically. A stale-`draftRev` bug would look different (timing-dependent, and it would equally fail on the first paste after any other edit); a hard guard rejection would fail on paste #1 too.

## 2. Why × turns the chip into `unavailable` instead of removing it

`remove()` builds its span from the published occurrence:

```js
const end = occurrence.offset + (occurrence.length ?? 1);   // clipboard coords: 0 + 28
input.consumeToken({ kind: 'span', span: { start: occurrence.offset, end, draftRev } });
...
records.delete(occurrence.ref);   // runs unconditionally
```

Trace on the captured state (occurrence `{ offset: 0, length: 28 }`, detect text `\uFFFC `):

1. `consumeToken` span guard: `draftRev` CAS passes (snapshot is fresh) and `start !== end` (0 ≠ 28) passes, so the verb proceeds to the splice.
2. `$replaceDetectSpanWithText({start: 0, end: 28}, '')` targets 28 detect characters in a 2-character detect text — out of range, the edit does not apply, `consumeToken` returns `false`.
3. The plugin **ignores the return value** and unconditionally runs `records.delete(occurrence.ref)` + `changed()`.

Result: the chip node is still in the composer (edit never applied), and the dock chip still renders because it is driven by the still-present occurrence — but its record lookup now fails, and per the rendering excerpt `record === undefined ? 'unavailable'` the label flips to `unavailable`. That is exactly the capture at 12:40:30. The plugin's own comment (“the removal must span `occurrence.length`, not one character”) is the misread made explicit: in detect coordinates the chip **is** one character; `occurrence.length` is its clipboard-projection length.

(The `setDraft` fallback branch is accidentally correct: `setDraft` takes the clipboard-projection draft, and slicing it by clipboard `offset/length` is the right currency there. The asymmetry between the two branches is itself a clue that the coordinates were not chosen per verb.)

## 3. Fix direction — the conversion rule and call sites

Rule, derived from the host excerpts (`EditorProjection` + the facade splicing detect text): **map clipboard-projection positions to detect-projection positions by charging each existing chip one character instead of its `clipboardText`.** For a document with occurrences `o_1..o_n` (sorted by offset), the divergence before occurrence `o_i` is `D_i = Σ_{j<i} (o_j.length − 1)` (each chip's `length` equals its `clipboardText` length; the same chip is 1 char in detect text). So:

```
detectPos(clipboardPos) = clipboardPos − Σ over occurrences with offset < clipboardPos of (length − 1)
```

Equivalently: detect length of the draft = `draft.length − Σ (occ.length − 1)`, and an occurrence's detect span is `[detectPos(occ.offset), detectPos(occ.offset) + 1)` — start at the chip's single U+FFFC, end one char later. Keep taking `draftRev` straight from a fresh snapshot — it is already the correct currency for the CAS.

Call sites to change:

- **Insert path (`add`)**: replace `start/end: snapshot.draft.length` with the detect length, i.e. `snapshot.draft.length − Σ over snapshot.occurrences of (occ.length − 1)` (append at end of detect text). With one chip present that is `29 − 27 = 2`, in range. Alternatively expose/derive the projection's `detectText` and use its length. `draftRev` unchanged.
- **Removal path (`remove`)**: compute `start = detectPos(occurrence.offset)` and `end = start + 1` (not `offset + occurrence.length`). And **handle the boolean**: only `records.delete(occurrence.ref)` and re-render when `consumeToken` (or the `setDraft` fallback) actually succeeded; on `false`, keep the record (and ideally surface a toast) so the dock chip can never degrade to `unavailable` while the chip persists.

After the fix, keep re-reading the snapshot after each successful verb (as `add`'s loop already does) so multi-item pastes re-derive coordinates from the new occurrence list.

## 4. Regression test plan

All against the real input facade, asserting state via `input.state.getSnapshot()` and the projection, not just the plugin's own records:

1. **Repeat-insert sequence (bug #1)**: empty composer → paste file A → assert `insertReference` returned true, `occurrences.length === 1`, draft = A's clipboardText + `" ". Then paste file B **without any other edit** → assert true, `occurrences.length === 2`, both chips visible, draft = A-text + B-text (with separator). This is the exact first-works/later-fails signature and must be asserted as a *sequence*, not two independent single-paste cases.
2. **Insert with mixed content**: type text, paste, type more, paste again → assert each insert applies and the occurrence offsets in the snapshot match the clipboard projection (offset/length sums consistent with `draft`).
3. **Remove sequence (bug #2)**: after two pastes, click × on the dock chip for occurrence #1 → assert `consumeToken` returned true; the snapshot shows that occurrence gone and the other intact; the dock no longer renders the chip; `records` no longer contains the ref; and the rendered meta is **never** `unavailable` while the occurrence still exists.
4. **Remove middle vs last chip**: with chips A, B, C remove B, then A, then C, asserting correct survivors each step (catchs off-by-divergence errors that a two-chip test can miss).
5. **Failed-removal hygiene**: force a stale `draftRev` (or out-of-range span) → assert `consumeToken` returns false, the record is **still present**, and the dock chip still shows its size label — not `unavailable`. This pins the “check the boolean before bookkeeping” half of the fix.
6. **Fallback branch parity**: run 3–4 with `consumeToken` hidden (forcing the `setDraft` fallback) and assert identical end states, so the two branches cannot diverge in currency again.

## 5. Routine host-source checks before calling input-machine verbs (unscored guidance)

- Read the **verb's parameter JSDoc for the coordinate currency** — here `insertReference`'s `@param span - pick-time span snapshot (detect coordinates)` states it outright. Never assume a published state field (`draft`, `occurrence.offset`) shares a verb's currency.
- Read what the verb **splices**: the facade names `$replaceDetectSpanWithText/Nodes`; the `Detect` prefix says which projection bounds the span must satisfy.
- Check the **per-chip unit in each projection** (`EditorProjection`: detect = one U+FFFC, clipboard = `clipboardText`) and derive the conversion from those documented units rather than from one successful call.
- Check the **return-value contract** of every verb (`@returns whether the edit applied`) and handle `false`; a boolean return means bookkeeping must be conditional on it.
- Check the **CAS field** (`draftRev` compares against the facade's `rev`) and re-read the snapshot immediately before the call, so a guard failure is unambiguous rather than entangled with coordinate errors.
- Add a canary assertion in tests that `detectText.length === draft.length − Σ(occ.length − 1)`; if a host update ever changes a projection's chip unit, the canary fails loudly instead of resurfacing this defect.
