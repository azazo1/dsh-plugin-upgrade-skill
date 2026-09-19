# S9 · Composer Coordinate Trap — Diagnosis Report

**Plugin:** `@org/dsh-attach-input` v0.2.3 · **Host:** DSH `0.1.2-alpha.3`

**Evidence:** `fixture/plugin-client.js`, `fixture/console-session.txt`, `fixture/host-input-facade.ts`, `fixture/host-input-contract.ts` (all read-only; fixture untouched).

## TL;DR — one contract misread, two symptoms

The host input machine has **two text coordinate systems** over the same editor document (`host-input-contract.ts`, `EditorProjection`):

| Projection | A chip contributes | Used by |
|---|---|---|
| `clipboardText` (= `InputState.draft`, occurrence `offset`/`length`) | its full `clipboardText` (e.g. `"[attachment: screenshot.png]"`, 28 chars) | persistence, `InputState`, occurrence view |
| `detectText` (trigger/TokenSpan coordinates) | **exactly one U+FFFC character** | `insertReference(ref, span)` and `consumeToken` span guards |

Both facade verbs take a `TokenSpan` whose `start`/`end` are **detect-text coordinates**. The facade makes this explicit: it resolves spans against `this.projection.detectText` (`tail = detectText.slice(span.end, span.end + 1)`, `$replaceDetectSpanWithNodes(span, …)`, `$replaceDetectSpanWithText(guard.span, '')`), and its JSDoc says `@param span - pick-time span snapshot (detect coordinates)`.

The plugin computes every span from `snapshot.draft.length` and `occurrence.offset/length` — **clipboard-text coordinates** — and hands them to verbs that interpret them as detect-text coordinates. Both reported bugs are this single mismatch, surfacing on different code paths (insert vs remove).

## 1. Why paste #1 succeeds and every later paste fails

Walk of `add()` against the capture:

- **Paste #1** (empty composer): `snapshot.draft = ""`, so the span is `{start: 0, end: 0, draftRev: 0}`. On an empty document the two projections are **identical** (both length 0, no chips), and `draftRev === this.rev`, so the CAS passes; `tail = ""` (not a space) → chip + separating space inserted. After the edit: `draft = "[attachment: screenshot.png] "` (length 29, clipboard coords) while `detectText = "\uFFFC "` (length 2), `rev → 1`.
- **Paste #2**: `snapshot.draft = "[attachment: screenshot.png] "` (already space-terminated, so no `setDraft` happens). Span = `{start: 29, end: 29, draftRev: 1}`. The revision CAS still passes (`draftRev 1 === rev 1`) — the failure is **not** a stale-revision problem. It fails because the host resolves the span against `detectText`, which is only **2 characters long**: `span.end = 29` points far past the end of the detect text, so `$replaceDetectSpanWithNodes` cannot apply the edit and `insertReference` returns `false`. The plugin treats `false` as "composer changed", deletes its record, and throws → the toast, and no second chip anywhere.

**Why "first works, later fails" is the signature of a coordinate-space mismatch** (as opposed to, e.g., a revision-CAS bug): the two coordinate systems coincide exactly while the document contains **zero chips** — a chip is the only construct that expands differently in the two projections (its `clipboardText` length vs one U+FFFC). The first paste starts from an empty composer, so the wrongly-computed span happens to be correct. The moment one chip exists, every clipboard-coordinate position after it overshoots the detect coordinate by `Σ (lengthᵢ − 1)` — here 27 — and every subsequent guarded verb call fails while the revision check keeps passing. A stale-`draftRev` bug would instead fail on the *first* insert after any host edit and succeed whenever the snapshot is fresh; the observed pattern (fresh snapshot, correct rev, still failing, only once a chip exists) pins the cause to the coordinate space, not to revision tracking.

## 2. Why × turns the chip into `unavailable` instead of removing it

`remove()` computes `end = occurrence.offset + (occurrence.length ?? 1)` — i.e. the occurrence's **clipboard-text** range `[0, 28)` — and passes it straight as the detect-text span to `consumeToken`. The host guard passes its trivial checks (`draftRev` fresh, `start ≠ end`), but `$replaceDetectSpanWithText([0,28), '')` cannot splice a 28-character range out of a 2-character detect text, so the edit does not apply and `consumeToken` returns `false`.

The plugin then compounds the failure in three ways:

1. **It ignores the return value** ("returned (not inspected by the plugin code)"), so it never learns the removal failed.
2. It unconditionally runs `records.delete(occurrence.ref)` and re-renders.
3. The dock chip list is driven by the **host occurrences** (which still contain the chip, because the host edit failed), while the chip's size label is looked up from the plugin's `records` map. With the record deleted but the occurrence still rendered, the rendering excerpt hits exactly the `record === undefined ? 'unavailable'` branch.

Net effect: composer chip still present (host splice failed), dock chip still rendered (host occurrence list unchanged), label degraded to `unavailable` (plugin-side record deleted). Both visible symptoms of user report #3 are the same clipboard-vs-detect mismatch plus unchecked return values and premature bookkeeping.

## 3. Fix direction — the conversion rule and both call sites

**Rule (derived from `host-input-contract.ts` / `host-input-facade.ts`, not guesswork):** a `TokenSpan` given to `insertReference` / `consumeToken` must be expressed in **detect-text coordinates**, where each occurrence occupies exactly one U+FFFC. Converting a clipboard-text position `p`:

```
detect(p) = p − Σ over occurrences entirely before p of (occurrence.length − 1)
```

An occurrence's detect range is `[detect(occ.offset), detect(occ.offset) + 1)` — always length 1, never `occurrence.length`. If the host exposes the `EditorProjection` (`detectText`), the robust equivalent is to measure against `projection.detectText` directly (its `.length` is the insert-at-end coordinate).

**Insert path (`add()`):** the "insert at end of draft" span must be

```js
const detectEnd = snapshot.draft.length
  - snapshot.occurrences.reduce((n, o) => n + (o.length - 1), 0);   // == detectText.length
const accepted = input.insertReference({ /* ref fields */ },
  { start: detectEnd, end: detectEnd, draftRev: snapshot.draftRev });
```

(and keep re-reading the snapshot inside the items loop, as the code already does, so each iteration's `draftRev` and occurrence set are current — this also matters after the space-padding `setDraft` branch, which bumps `rev`). Once the coordinates are correct, `accepted === false` genuinely means a concurrent edit, and delete-and-throw is defensible.

**Removal path (`remove()`):**

```js
const shift = snapshot.occurrences
  .filter(o => o.offset + o.length <= occurrence.offset)
  .reduce((n, o) => n + (o.length - 1), 0);
const start = occurrence.offset - shift;
const consumed = input.consumeToken({
  kind: 'span',
  span: { start, end: start + 1, draftRev: snapshot.draftRev },  // one U+FFFC, not occurrence.length
});
if (!consumed) return;            // do NOT delete the record on failure
records.delete(occurrence.ref);
changed();
```

The `occurrence.length ?? 1` fallback and the `setDraft` string-slicing fallback branch must go: the fallback slices `snapshot.draft` at clipboard offsets assuming the chip text is literally present in the draft — wrong for the same reason, and it would corrupt the draft if it ever ran. Additionally, **check the boolean returns of both verbs** and make plugin bookkeeping (`records.delete`, re-render) conditional on success. Ideally compute the conversion in one shared helper used by both call sites.

## 4. Regression test plan

All against a fresh session, asserting both host state and plugin UI:

1. **Repeat insert (reported bug #2):**
   - paste #1 into empty composer → `accepted === true`; assert `occurrences.length === 1`, one dock chip with a real size label, one composer chip;
   - paste #2 immediately (no typing between) → `accepted === true`; assert `occurrences.length === 2`, `occurrences[1].offset === draft.length − occurrences[1].length` in clipboard coords, two dock chips, **no toast**;
   - paste #3 and beyond (≥ 3 chips) → still true; guards against accumulator off-by-ones.
2. **Insert with mixed content:** type text, paste, type more text, paste again; also paste when the draft does **not** end in whitespace (exercising the `setDraft` space-padding branch, after which `rev` changed and the snapshot must be re-read before computing the span). Assert each chip's clipboard `offset`/`length` matches its text position and the trailing-space logic.
3. **Removal (reported bug #3):**
   - one chip, click × → `consumeToken` returns `true`; assert `occurrences.length === 0`, `draft` no longer contains the clipboard text, dock chip **gone** (not `unavailable`), `records` empty;
   - three chips, remove the **middle** one → the remaining two keep correct offsets/labels; then remove the others one by one (middle removal is where a wrong per-occurrence shift shows up);
   - remove a chip that has typed text both before and after it → the text joins correctly, no leftover or duplicated characters;
   - **failure path:** force a stale `draftRev` (simulate a host edit between snapshot and verb) → the verb returns `false`; assert the plugin **keeps** the record, the dock chip still shows its size label (not `unavailable`), and the composer chip is untouched.
4. **Return-value discipline:** unit-test `add`/`remove` with a stubbed `input` whose verbs return `false`; assert the plugin never mutates `records` or re-renders after a `false` from `insertReference`/`consumeToken`.

Sequences 1 and 3 are the minimum that must be asserted so neither bug can silently return; 2 and 4 pin the general rule rather than only the two exact reproducers.

## 5. Routine host-source checks before calling input-machine verbs (unscored, for completeness)

- Read the **verb's guard parameter type and JSDoc** in the facade before calling it. Here the contract was explicit: `@param span - pick-time span snapshot (detect coordinates)` — the word "detect" names the coordinate system.
- Identify **which projection** each numeric field references. Any type touching the editor spans at least two text spaces (`detectText` vs `clipboardText`/`draft`); never mix values from one into an API expecting the other, even when a fresh empty document makes them equal — that equality is exactly what hides the bug in smoke tests.
- Note **what a chip costs in each space** (1 char vs `clipboardText.length`) and write the conversion as one helper used by every call site, rather than ad-hoc arithmetic per site.
- Treat **boolean returns as part of the contract**: `insertReference` / `consumeToken` report guarded-edit success; never perform destructive bookkeeping without checking them.
- Keep a regression test that performs the **second** interaction of any stateful verb, not just the first — first-call success is structurally uninformative for coordinate bugs.
