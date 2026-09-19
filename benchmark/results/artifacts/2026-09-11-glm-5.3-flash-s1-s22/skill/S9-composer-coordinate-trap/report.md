# S9 · Composer Coordinate Trap — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.2.3 · Host: DSH `0.1.2-alpha.3` · Read-only analysis of the S9 evidence pack (`README.md`, `plugin-client.js`, `console-session.txt`, `host-input-facade.ts`, `host-input-contract.ts`).

## Executive summary

Both symptoms are one contract misread: the host input machine exposes **two coordinate systems** for the composer document — the **detect projection** (each chip is exactly one U+FFFC character) and the **clipboard projection** (each chip expands to its `clipboardText`, e.g. `[attachment: screenshot.png]`). `InputState` (`draft`, `occurrences[].offset/length`) is published in **clipboard coordinates**, but the facade verbs `insertReference` and `consumeToken` take `TokenSpan` values in **detect coordinates**. The plugin computes spans from `snapshot.draft.length` and `occurrence.offset/length` — clipboard values — and passes them to detect-coordinate verbs. The two systems coincide only when the document contains no chips, which is exactly why paste #1 works and everything after it fails.

---

## 1. Why the FIRST paste succeeds and every later paste fails

### The exact mismatch

The plugin (`plugin-client.js` lines 27–32) builds the insert span from the clipboard projection:

```js
{
  start: snapshot.draft.length,
  end: snapshot.draft.length,
  draftRev: snapshot.draftRev,
}
```

Per `host-input-contract.ts`, `InputState.draft` is the *"Clipboard-text projection of the editor document (chips expanded to their clipboard form)"* and `Occurrence.offset/length` are *"Offset/Length in the clipboard-text projection"*. So after paste #1, `snapshot.draft = "[attachment: screenshot.png] "` with **length 29**.

The host verb (`host-input-facade.ts`) works in detect coordinates:

- `insertReference(ref, span)` line 18: `const tail = this.projection.detectText.slice(span.end, span.end + 1)` — it indexes `projection.detectText` with `span.end`.
- `EditorProjection.detectText` is documented as *"Trigger/TokenSpan coordinate text (**chip = one U+FFFC**)"*, versus `clipboardText`: *"Persistence/InputState draft text (**chip = clipboardText**)"*.

So the guard compares `span.draftRev` correctly (the plugin re-snapshots, so the revision CAS at facade line 17 passes), but the span endpoints are interpreted against a completely different text: after paste #1 the detect text is `<FFFC> ` — **2 characters** — while the plugin claims the insertion point is at offset **29**. `$replaceDetectSpanWithNodes(span, nodes)` cannot splice a span anchored at 29–29 into a 2-character detect document; `applied` stays `false` and `insertReference` returns `false`. The plugin maps that to the toast at `plugin-client.js` line 35: *"The DSH composer changed before the attachment could be inserted"* — a misleading message, because the composer did **not** change unexpectedly; the span was simply expressed in the wrong coordinate system.

### Why "first works, later fails" is the signature of this mismatch

- **Paste #1**: the composer is empty. Detect text `""` and clipboard text `""` are identical, and offset 0 is a valid endpoint in both systems. The splice at 0–0 succeeds, the chip is created, and the snapshot confirms `draft = "[attachment: screenshot.png] "` (length 29) with `occurrences = [{ offset: 0, length: 28, ... }]` (`console-session.txt` lines 7–9). Note the divergence is born at this very moment: the chip occupies **1** character in detect coordinates but **28** in clipboard coordinates.
- **Paste #2**: the plugin recomputes `start = end = snapshot.draft.length = 29` from the clipboard projection, but the detect text is only 2 characters long. The coordinates diverge by exactly `28 − 1` per chip already in the document. Every subsequent paste re-derives the span from clipboard coordinates, so every subsequent insert fails. The error is deterministic and permanent for the session — matching the capture (paste #2 at 12:40:05, `insertReference returned false; no second chip anywhere`).

"First call succeeds, every repeat fails" is therefore the fingerprint of a coordinate-system mismatch that only materializes once the first chip exists — not of a stale-revision race (the plugin re-snapshots, so the `draftRev` CAS is satisfied both times).

## 2. Why the × click turns the chip into `unavailable` instead of removing it

### The removal path

`remove()` (`plugin-client.js` lines 43–60):

1. It computes `end = occurrence.offset + (occurrence.length ?? 1)`. For the captured chip that is `0 + 28 = 28` — again **clipboard** coordinates (`occurrence.length` is the length of `[attachment: screenshot.png]`), while `consumeToken`'s span guard splices `$replaceDetectSpanWithText(guard.span, '')` in **detect** coordinates where the chip is one U+FFFC (detect text `<FFFC> `, length 2).
2. The cheap guards pass: `phase === 'plain'`, `guard.span.draftRev` is current, and `start (0) !== end (28)` — so the guard at facade line 38 does **not** reject. The verb then attempts the detect-coordinate splice `$replaceDetectSpanWithText(span, '')` on a 2-character detect text with a span reaching to 28. The chip node is not removed (the capture confirms `composer chip still present`); the splice either no-ops/fails against out-of-range detect coordinates or at most consumes trailing plain characters — in no case the intended chip.
3. `consumeToken`'s return value is discarded: *"consumeToken(...) returned (not inspected by the plugin code)"* (`console-session.txt` line 18). `remove()` then unconditionally runs `records.delete(occurrence.ref); changed();` (lines 58–59).

### The plugin-side bookkeeping consequence

The dock renderer (lines 62–65) derives the size label from the record:

```js
... : record === undefined ? 'unavailable' : humanBytes(record.total);
```

Because `records.delete(occurrence.ref)` ran even though the host-side removal never applied, the next `changed()` re-render finds `record === undefined` for the still-existing host occurrence — hence the chip remains rendered with its size label flipped to `unavailable`, and the composer chip survives too. All three observed facts (chip not removed, label `unavailable`, `records` no longer contains the ref) follow from one failed splice whose `false` result was ignored, compounded by the same clipboard-vs-detect coordinate error as bug #1.

## 3. Fix direction

### The conversion rule (derived from the host source, not guesswork)

The host contract defines the mapping explicitly. Each chip is **one** `U+FFFC` in `detectText` and exactly `occurrence.clipboardText.length` characters in `clipboardText` (`host-input-contract.ts`: detectText — *"chip = one U+FFFC"*; clipboardText — *"chip = clipboardText"*; `Occurrence.clipboardText` — *"Clipboard / persistence projection, e.g. /name"*). Occurrences are *"sorted by offset"*, so for position *p* in the clipboard projection:

```
detectOffset(p) =
  (p − Σ clipboardText.length of occurrences entirely before p)   // plain characters, identical in both
  + (number of occurrences entirely before p)                     // each chip contributes 1 FFFC
```

Equivalently, a clipboard→detect shift of `−(Σ lengths before) + (count before)` per position. For a specific occurrence *i* (0-based in the sorted list):

- detect span start = `occurrence.offset − Σ_{j<i} occurrences[j].clipboardText.length + i`
- detect span length = **1** (never `occurrence.length`; the chip is a single U+FFFC in detect coordinates)

### Call site 1 — the insert path (`add`, lines 21–32)

The insert appends at the end of the document, so the correct detect span is simply the detect projection's length — no arithmetic needed:

```js
const proj = input.projection.get();          // EditorProjection: detectText/clipboardText/occurrences
const end = proj.detectText.length;           // chips count as 1 each here
input.insertReference({ source: SOURCE, ref, label: item.path, appearance: 'file',
                        clipboardText: `[attachment: ${item.path}]` },
  { start: end, end, draftRev: snapshot.draftRev });
```

If a general conversion helper is preferred, `detectOffset(snapshot.draft.length)` via the rule above yields the same value. `draftRev` is system-independent (one monotonic editor revision, facade line 17: *"span CAS compares against this"*) and the plugin already re-snapshots, so it needs no conversion. The pre-pad `setDraft(`${snapshot.draft} `)` at line 14 operates on the clipboard form and is fine as-is — but re-snapshot (as the code already does) before deriving the span.

### Call site 2 — the removal path (`remove`, lines 43–60)

Convert the occurrence's clipboard span to a **1-character** detect span, and honor the verb's result:

```js
const proj = input.projection.get();
const i = proj.occurrences.findIndex(o => o.ref === occurrence.ref);
const before = proj.occurrences.slice(0, i);
const start = occurrence.offset
  - before.reduce((n, o) => n + o.clipboardText.length, 0)
  + before.length;
const ok = input.consumeToken({ kind: 'span', span: { start, end: start + 1, draftRev: snapshot.draftRev } });
if (ok) { records.delete(occurrence.ref); }
changed();
```

Two independent corrections: (a) coordinate conversion per the rule above — `occurrence.length` must never be used as a detect span length; (b) only delete the record and update the dock when `consumeToken` returns `true`, so a failed removal can never manufacture the `unavailable` state. The fallback `setDraft(slice…)` branch (line 56) likewise mixes systems — `InputState.draft` is the clipboard projection, so slicing it with detect spans is wrong; if retained at all, it must use clipboard coordinates (`occurrence.offset .. occurrence.offset + occurrence.clipboardText.length`) — but on 0.1.2-alpha.3 the `consumeToken` branch is the live one.

## 4. Regression test plan

All sequences on a real mounted composer (not mocked snapshots), asserting both the composer DOM/occurrence state and the dock chip state:

1. **Repeat insert (bug #1)**: paste screenshot A → assert 1 dock chip, 1 composer chip, `insertReference === true`. Paste screenshot B immediately → assert **2** dock chips, **2** composer chips, no toast, and `InputState.occurrences.length === 2` with correct offsets. Paste a third → 3/3.
2. **Insert after typed text**: type `hello`, paste → chip appended after `hello`; type `world`, paste again → second chip inserted (typed text between chips is the classic multi-chip coordinate drift case).
3. **Insert after other-origin chips**: insert a reference from a different source, then paste → asserts the conversion is per-occurrence, not per-plugin (a foreign chip's `clipboardText` length must still be subtracted).
4. **Single removal (bug #2)**: paste once, click × → assert `consumeToken === true`, the composer chip is gone (`occurrences.length === 0`, `draft === ""`), the dock chip disappears, and the record is deleted.
5. **Middle removal with multiple chips**: paste A, B, C; remove B → assert C's remaining offset equals `old offset − 1` in detect coordinates / recomputed correctly in `occurrences`, and A, C still render; remove A then C → empty composer.
6. **Failed-removal bookkeeping**: force `consumeToken` to fail (e.g. set `phase` ≠ `plain` before the click) → assert the record **stays** in `records`, the dock label still shows the byte size (never `unavailable`), and the composer chip is untouched.
7. **Removal after a failed insert**: paste #1 ok, paste #2 fails (simulated by a stale `draftRev`) → assert no orphan record for paste #2 and × on chip #1 still removes cleanly (guards the `records.delete` on the insert-failure path, line 34).
8. **U+FFFC boundary**: a chip whose `clipboardText` length equals 1 (e.g. `/n`) → both coordinate systems coincide; insert and remove must still be correct (regression against an off-by-one in the conversion).

## 5. Routine source-reading discipline before calling input-machine verbs

- **Read the verb implementation, not just its name.** The facade shows exactly which projection each verb indexes (`this.projection.detectText.slice(span.end, …)`, `$replaceDetectSpanWithText(guard.span, …)`). Any `TokenSpan` parameter must be traced to the text it is applied against before use.
- **Check the contract file for dual projections.** Wherever a type documents two coordinate texts (`EditorProjection.detectText` vs `.clipboardText`; `InputState` marked *"clipboard-text projection"* vs spans marked *"detect coordinates"*), assume values from one cannot be passed to the other without conversion, and derive the conversion from the documented chip-width rule (1 U+FFFC vs `clipboardText.length`).
- **Enumerate every guard before the first call**: `phase` must be `plain`/`claimed`, `span.draftRev` must equal the current revision (re-snapshot immediately before building the span), `start !== end` for consume spans — and note which failures are silent (`return false`).
- **Never discard verb return values.** `insertReference`/`consumeToken` return `boolean` precisely so bookkeeping (`records.delete`, dock re-render, toast) can be gated on success. Also read the toast string the plugin emits against what the `false` actually means — here it blamed "the composer changed" when the real cause was the plugin's own span.
- **Test the repeat interaction before release**: any state-machine verb whose input coordinates depend on prior chips must be exercised at least twice in one session (second paste, second removal, removal of a middle chip). "Works the first time" is the expected symptom of this entire defect class, so first-use-only smoke tests provide no signal.

## Conclusion

One misread — treating clipboard-projection coordinates (`InputState.draft`, `occurrence.offset/length`) as the detect-projection coordinates the facade verbs require — explains both bugs: inserts fail once a chip exists because the span endpoint overshoots a detect text where the chip is one character, and removals silently no-op because a 28-character clipboard span is applied to a 1-character chip in detect text, after which the ungated `records.delete` renders the ghost `unavailable` chip. The fix is the single documented conversion rule (chips = 1 U+FFFC in detect coordinates) applied at both call sites, plus gating record deletion on the verb's return value.
