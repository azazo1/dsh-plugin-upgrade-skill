# S9 · Composer Coordinate Trap — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.2.3 · Host: DSH `0.1.2-alpha.3` · Evidence: read-only pack `fixture/` (`plugin-client.js`, `console-session.txt`, `host-input-facade.ts`, `host-input-contract.ts`, `README.md`). Read-only diagnosis; nothing in the fixture or the plugin was modified.

## Executive summary

Both symptoms are one contract misread: the plugin builds `TokenSpan` coordinates from the **clipboard-text projection** (`snapshot.draft`, where a chip occupies its full `[attachment: …]` string), while `insertReference` / `consumeToken` guards and splice in the **detect-text projection** (`projection.detectText`, where a chip is exactly one U+FFFC). The published contract states this explicitly — `host-input-contract.ts` documents `InputState.draft` as "Clipboard-text projection of the editor document (chips expanded to their clipboard form)" and `EditorProjection.detectText` as "Trigger/TokenSpan coordinate text (chip = one U+FFFC)".

---

## 1. Why the first paste succeeds and every later paste fails

### The exact mismatch

In `plugin-client.js`, `add()` computes the insert span from the clipboard projection:

```js
const snapshot = input.state.getSnapshot();
...
start: snapshot.draft.length,
end: snapshot.draft.length,
draftRev: snapshot.draftRev,
```

But `host-input-facade.ts` · `insertReference(ref, span)` splices the **detect** text:

```ts
if (span.draftRev !== this.rev) return false
const tail = this.projection.detectText.slice(span.end, span.end + 1)
...
applied = $replaceDetectSpanWithNodes(span, nodes)
```

The header comment confirms it: the `span` parameter is a "pick-time span snapshot (**detect coordinates**)".

### Why "first works, later fails" is the signature

- **Paste #1 (empty composer):** `snapshot.draft === ''`, so the plugin sends `{ start: 0, end: 0, draftRev }`. In an empty document the two coordinate systems coincide (offset 0 in both, no chips to diverge). The revision CAS passes, `$replaceDetectSpanWithNodes` splices at detect offset 0, and the chip lands. `console-session.txt` [12:39:41] confirms: draft becomes `"[attachment: screenshot.png] "` (length 29 clipboard chars), one occurrence at `offset: 0, length: 28`.
- **Paste #2:** the composer now holds one chip. In **clipboard** coordinates the draft is 29 chars, so the plugin sends `start: end: 29`. In **detect** coordinates the same document is only 2 characters (`U+FFFC` + separator space — one char per chip; `insertReference` appends the space). The `draftRev` CAS passes (the revision is a single monotonic editor revision, identical in both projections — `InputState.draftRev`: "Monotonic editor revision (span CAS compares against this)"), so this is not a stale-revision race. The guard succeeds and `$replaceDetectSpanWithNodes({start:29,end:29}, …)` runs against a 2-char detect text, cannot apply, and `insertReference` returns `false`. `console-session.txt` [12:40:05]: "`insertReference` returned false". `add()` then hits `if (!accepted)`: deletes the fresh record and throws `'The DSH composer changed before the attachment could be inserted'` — the toast. The message is misleading; the composer did not change, the coordinates were in the wrong space.

Any document containing at least one chip makes the two projections diverge, so exactly the first paste into an empty composer ever succeeds — the canonical fingerprint of a coordinate-space mismatch rather than a race.

## 2. Why the × click turns the chip into `unavailable` instead of removing it

### The removal path

`remove()` reads the occurrence from `InputState.occurrences` — whose `offset`/`length` are **clipboard-text** coordinates (`host-input-contract.ts`: `EditorProjection.occurrences` is the "InputState-compatible occurrence view (**clipboardText coordinates**)"; `Occurrence.length`: "the occurrence occupies exactly [offset, offset+length)" of the clipboard-text projection):

```js
const end = occurrence.offset + (occurrence.length ?? 1);   // 0 + 28 = 28, clipboard coords
input.consumeToken({ kind: 'span', span: { start: occurrence.offset, end, draftRev: snapshot.draftRev } });
```

`consumeToken` (`host-input-facade.ts`) splices the **detect** text:

```ts
if (guard.span.draftRev !== this.rev || guard.span.start === guard.span.end) return false
applied = $replaceDetectSpanWithText(guard.span, '')
```

For the captured state, detect text is `"\uFFFC "` (length 2); the plugin asks to clear detect range `[0, 28)`. The revision CAS passes and `start !== end`, so the guard is entered, but the splice over a 2-char detect text cannot remove a 28-char range — `applied` stays `false` and `consumeToken` returns `false` with the composer chip untouched.

### The plugin-side bookkeeping bug

`remove()` never inspects the return value:

```js
records.delete(occurrence.ref);
changed();
```

So even on a failed removal the record is dropped from `records`. The dock renderer (`plugin-client.js` excerpt) then evaluates `record === undefined ? 'unavailable' : humanBytes(record.total)` — `console-session.txt` [12:40:30] shows exactly that: "dock chip STILL rendered, meta now reads 'unavailable'; composer chip still present; records no longer contains the ref". The `unavailable` label is the renderer's missing-record fallback leaking through the unguarded `records.delete`; the leftover composer chip is the failed detect-coordinate splice. (The `?? 1` default on `length` is also a latent wrong-space guess — a chip is one detect char, not one clipboard char.)

## 3. Fix direction (rule derived from the host source)

### The rule

The host publishes **two projections of one document** (`EditorProjection`): `detectText` (chip = one `U+FFFC`) and `clipboardText` (= `InputState.draft`; chip = its full `clipboardText` string). `TokenSpan` — every `start`/`end` passed to `insertReference` and to `consumeToken({kind:'span'})` — is in **detect** coordinates (`insertReference`'s `@param span` and its `this.projection.detectText.slice(span.end, …)` tail check prove it). `Occurrence.offset/length` are in **clipboard** coordinates. Therefore:

> Convert a clipboard offset `c` to a detect offset by replacing every occurrence that ends at or before `c` with 1 character and keeping plain-text runs 1:1: `detect(c) = (number of occurrences entirely before c) + (plain-text chars before c)`. An occurrence at clipboard `[offset, offset+length)` maps to the single detect char at `detect(offset)`, i.e. span `[detect(offset), detect(offset) + 1)`. The plugin can compute this from `occurrences` (each contributes `occurrence.length - 1` extra clipboard chars) or, for append-at-end, directly from the projection's `detectText.length`.

### Call sites

1. **Insert path — `add()`:** do not use `snapshot.draft.length`. Append-at-end spans must be `start = end = detectText.length` (2 after paste #1, per the capture), or the converted equivalent. Re-derive after each insert inside the `for` loop — each chip grows the detect text by 1 `U+FFFC` plus the separator space, not `clipboardText.length + 1`. Keeping `draftRev: snapshot.draftRev` is correct and must stay.
2. **Removal path — `remove()`:** convert `occurrence.offset` to detect coordinates and remove exactly one detect char: `span = { start: detect(occurrence.offset), end: detect(occurrence.offset) + 1, draftRev: snapshot.draftRev }` — not `offset + length`. Drop the `?? 1` fallback (it encodes the wrong space).
3. **Honor the verb result:** run `records.delete(occurrence.ref)` (and `changed()`) only when `consumeToken` returned `true`; the same discipline already exists in `add()`'s `if (!accepted)` cleanup. This is what currently turns a failed splice into a ghost `unavailable` chip. The `setDraft` fallback branch in `remove()` is fine as-is — `setDraft` takes the full draft in clipboard coordinates.
4. **Snapshot source:** read both projections (the snapshot's `draft` + the editor projection's `detectText`, or reconstruct detect offsets from `occurrences`) at the same `draftRev`; never mix a fresh occurrence with a stale span.

## 4. Regression test plan

Assert these exact interaction sequences (client tests against a real input machine, plus a manual Web GUI pass):

1. **Repeat paste (bug #2):** empty composer → paste file A → assert chip A in composer + dock, `records.size === 1`; paste file B → assert **no toast**, `records.size === 2`, detect text === `"\uFFFC \uFFFC "`, `InputState.draft === "[attachment: A] [attachment: B] "`, both dock chips show byte-size labels.
2. **Paste after plain text:** type `"hello"` → paste → assert insert succeeds with span `{start:5,end:5}` in detect coords (proves non-zero plain-text offset conversion).
3. **Paste after chip + text mix:** text, chip, text → paste → assert the detect offset counts each chip as 1 char.
4. **Remove chip (bug #3):** after sequence 1, click × on chip A → assert `consumeToken` returned `true`, composer draft === `"[attachment: B] "`, dock chip A gone, `records.size === 1`, remaining chip keeps its correct bytes label and its re-read occurrence shows the shifted offset.
5. **Remove middle chip:** three chips → remove the middle → the outer two chips and their records remain intact.
6. **Failed-removal honesty:** force a stale `draftRev` (mutate the draft between snapshot and × click) → assert `consumeToken` returns `false`, **the record is NOT deleted**, the dock chip still shows its size (never `unavailable`), and a retry after re-snapshot removes it.
7. **Guard intact:** attempt an insert with a deliberately stale revision → the toast still fires and no orphan record remains (the plugin's own CAS error path must survive the fix).

## 5. Routine host-source checks before calling input-machine verbs (guidance)

- **Identify the coordinate space of every positional argument** — read the verb's `@param` JSDoc and, decisive here, the body: whichever projection the guard slices or the splice helper mutates (`this.projection.detectText.slice(…)`, `$replaceDetectSpanWith*`) is the coordinate space the span must be in. Cross-check against the contract file's per-field projection annotations.
- **Distinguish the projections**: any host type offering two texts of one document (`detectText` vs `clipboardText`/`draft`) means a snapshot usable for display is not automatically usable for spans; note which fields are "insert-time cache" vs live coordinates.
- **Read each guard literally**: what the CAS compares (`draftRev`), what makes it return `false` silently, and that `false` is a normal outcome, not an exception — so the return value must be checked before any local bookkeeping (`records.delete`).
- **Check phase/state preconditions** (`phase !== 'plain' && phase !== 'claimed'`) and side effects the verb performs for you (the auto separator space in `insertReference`) so you do not double-apply them.
- **Re-read the verbs on every DSH host bump** (plugin-upgrade Mode A/C corridor review): guard semantics and coordinate spaces are host-owned contracts; a corridor card or diff touching the input facade invalidates any span math committed against the old source.
