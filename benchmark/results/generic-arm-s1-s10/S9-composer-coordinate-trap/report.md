# S9 · Composer Coordinate Trap — Diagnosis Report

Plugin: `@org/dsh-attach-input` v0.2.3 on DSH `0.1.2-alpha.3`.
Evidence used (read-only): `fixture/plugin-client.js`, `fixture/host-input-facade.ts`,
`fixture/host-input-contract.ts`, `fixture/console-session.txt`.

**One-sentence diagnosis:** both reported bugs are the same defect — the plugin computes
spans in the **clipboard-text projection** coordinate system and hands them to host verbs
whose guards and splice operations expect **detect-text projection** coordinates. The two
projections coincide only while the composer contains no chips, so the very first paste is
accidentally correct and everything after it is deterministically wrong. The `unavailable`
chip is the same misread on the removal path, compounded by the plugin deleting its own
bookkeeping record without checking the verb's boolean result.

---

## 0. The contract the plugin misread

The host publishes **two text projections of the same composer document**
(`host-input-contract.ts:34-42`, `EditorProjection`):

- `detectText` — "Trigger/TokenSpan coordinate text (chip = one U+FFFC)". Each reference
  chip occupies **exactly one character** here.
- `clipboardText` — "Persistence/InputState draft text (chip = clipboardText)". Each chip
  occupies the full length of its clipboard form (e.g. 28 chars for
  `[attachment: screenshot.png]`).

And per field (`host-input-contract.ts:14-17`, `Occurrence`):

- `offset` — "Offset **in the clipboard-text projection**."
- `length` — "Length **in the clipboard-text projection**; the occurrence occupies exactly
  `[offset, offset+length)`."

`InputState.draft` is likewise the clipboard-text projection
(`host-input-contract.ts:26-27`).

But the verbs operate on the other projection:

- `insertReference(ref, span)` — "`span` — pick-time span snapshot (**detect
  coordinates**)" (`host-input-facade.ts:11`). Its guard reads
  `this.projection.detectText.slice(span.end, ...)` and splices via
  `$replaceDetectSpanWithNodes(span, nodes)` (`host-input-facade.ts:18,24`) — i.e. the span
  is applied to `detectText`.
- `consumeToken({kind:'span', span})` — "Span guard: revision CAS then splice"
  (`host-input-facade.ts:31-32`), spliced via `$replaceDetectSpanWithText(guard.span, '')`
  (`host-input-facade.ts:41`) — again detect coordinates.

The plugin never converts. It passes clipboard-projection numbers straight into
detect-coordinate parameters at two call sites:

- Insert: `start: snapshot.draft.length, end: snapshot.draft.length`
  (`plugin-client.js:29-30`). `draft` is clipboard-text coordinates.
- Removal: `span: { start: occurrence.offset, end: occurrence.offset + occurrence.length }`
  (`plugin-client.js:49,53`). `offset`/`length` are documented clipboard-text coordinates.

That is the entire root cause. Everything below is the two symptoms derived from it.

---

## 1. Why paste #1 succeeds and every later paste fails

**The exact mismatch.** `add()` computes the insertion span as
`{start: snapshot.draft.length, end: snapshot.draft.length, draftRev: snapshot.draftRev}`
(`plugin-client.js:28-31`). `draft.length` is a length in the clipboard-text projection.
`insertReference` treats `span.start`/`span.end` as offsets into `detectText`
(`host-input-facade.ts:18,24`). The guard that actually rejects the call is not the
revision CAS — the snapshot is freshly read inside `add()`, so `span.draftRev === this.rev`
holds — but the splice itself: `$replaceDetectSpanWithNodes` is asked to splice at a
position that does not exist in `detectText`, so `applied` stays `false` and the verb
returns `false` (`host-input-facade.ts:19-26`). The plugin then throws
`'The DSH composer changed before the attachment could be inserted'`
(`plugin-client.js:33-35`) — a message that blames a draft revision race and thereby
misdiagnoses its own coordinate bug.

**The numbers from the session log prove it.** After paste #1
(`console-session.txt:7-10`):

- `draft = "[attachment: screenshot.png] "` → `draft.length = 29` (28-char chip form + 1
  trailing space the facade appended, `host-input-facade.ts:21-23`).
- `detectText` for the same document is 2 characters: one U+FFFC + one space.

On paste #2 the plugin therefore passes `span = {start: 29, end: 29}` against a 2-character
detect text. The splice target is 27 characters past the end of the string; the verb
returns `false`; the toast fires; no chip is created (`console-session.txt:12-15`).

**Why "first works, later fails" is the signature.** The two coordinate systems are equal
exactly when the document contains no chips, because a chip is the only thing whose length
differs between projections (1 in detect, `length` in clipboard). Paste #1 runs against an
empty composer, so `start = end = 0` is simultaneously correct in both systems and the verb
succeeds — not because the code is right, but because the wrongness is multiplied by zero.
The instant one chip exists, every subsequent clipboard-computed position overshoots the
detect text by `Σ(lengthᵢ − 1)` over the chips before it, and failure is deterministic, not
flaky. That profile — first interaction always fine, every repeat always fails, on a fresh
session with no concurrent edits — rules out a genuine revision-CAS race (which would be
intermittent and could also strike the first paste) and points at a unit/coordinate
mismatch that is zero only on an empty document.

---

## 2. Why the × click produces `unavailable` instead of removing the chip

**The removal path, step by step.**

1. `remove()` reads `occurrence.offset` and `occurrence.length` and computes
   `end = occurrence.offset + (occurrence.length ?? 1)` (`plugin-client.js:49`). For the
   pasted chip that is `start: 0, end: 28` (`console-session.txt:9`) — clipboard-text
   coordinates, per the contract.
2. It calls `input.consumeToken({kind: 'span', span: {start: 0, end: 28, draftRev}})`
   (`plugin-client.js:51-54`). The facade's span guard checks
   `guard.span.draftRev !== this.rev || guard.span.start === guard.span.end`
   (`host-input-facade.ts:38`). The draftRev is fresh, and `0 !== 28`, so the guard
   **passes** — the verb proceeds to splice.
3. `$replaceDetectSpanWithText({start: 0, end: 28}, '')` is asked to delete 28 characters
   from a 2-character detect text. The range is out of bounds, the edit does not apply,
   `applied` stays `false`, and `consumeToken` returns `false`
   (`host-input-facade.ts:39-44`). The composer chip survives —
   `console-session.txt:20` confirms "composer chip still present".
4. The plugin **never reads the return value** (`console-session.txt:18`: "returned (not
   inspected by the plugin code)"). It unconditionally executes
   `records.delete(occurrence.ref); changed();` (`plugin-client.js:58-59`).

**Why `unavailable`.** The dock renders one chip per host-reported occurrence and joins
each to the plugin's own `records` map: `const record = records.get(occurrence.ref)`, with
meta `record === undefined ? 'unavailable' : humanBytes(record.total)`
(`plugin-client.js:63-65`). After step 4, the occurrence still exists in the host state
(the splice failed) but its record is gone from `records`, so the renderer takes the
`undefined` branch and shows `unavailable` (`console-session.txt:19-21`). The chip "does
not go away" because the dock is driven by host occurrences, which were never actually
removed.

So the second bug is the same coordinate misread on the removal path (step 3), plus a
bookkeeping defect that converts a failed host operation into corrupt plugin state (step
4): the plugin's map and the host's document are now permanently out of sync, and the UI
faithfully displays that corruption as `unavailable`.

---

## 3. Fix direction

**The conversion rule, derived from the host source.** One chip = exactly one U+FFFC in
detect coordinates (`host-input-contract.ts:36`), while the same chip spans
`occurrence.length` characters starting at `occurrence.offset` in clipboard coordinates,
and `occurrences` is sorted by offset (`host-input-contract.ts:16-17,30`). Therefore a
clipboard-text position `p` converts to a detect position `d` by subtracting the surplus
of every occurrence that lies entirely before `p`:

```
d(p) = p − Σ (lengthᵢ − 1)   over all occurrences with offsetᵢ + lengthᵢ ≤ p
```

and, conversely, an occurrence `[offset, offset+length)` maps to the detect span
`[d(offset), d(offset) + 1)`. Since `InputState` publishes `draft` and `occurrences` but
not `detectText` (`host-input-contract.ts:25-32`), this arithmetic on the published
snapshot is the supported way for a plugin to obtain detect coordinates — reading the
facade's internal `projection.detectText` would couple to a non-published surface.

**Insert path (`plugin-client.js:21-32`).** Convert the span endpoints before calling
`insertReference`:

- For "insert at end of draft": `start = end = snapshot.draft.length − Σ(lengthᵢ − 1)`
  over all occurrences in the snapshot (all of them are before the end). In the logged
  session the correct second-paste span is `{start: 2, end: 2, draftRev}` — with that
  span the facade's `tail = detectText.slice(2, 3)` is `''`, so it appends a chip plus a
  separating space, exactly mirroring paste #1's behavior (`host-input-facade.ts:18-23`).
- Keep passing `draftRev: snapshot.draftRev` unchanged — the revision is shared by both
  projections and the CAS is correct as-is (`host-input-facade.ts:17`).
- The error message should distinguish a `false` caused by stale revision from a rejected
  span; at minimum it must stop claiming "the composer changed" for a coordinate bug, or
  the next maintainer will misread the same toast.

**Removal path (`plugin-client.js:43-59`).**

- Convert the occurrence's clipboard range to the detect span:
  `start = occurrence.offset − Σ(lengthᵢ − 1)` over occurrences with
  `offsetᵢ < occurrence.offset`, and `end = start + 1` (the chip is one detect character).
  For the logged chip: `{start: 0, end: 1, draftRev}` — this passes the
  `start === end` guard and splices exactly the U+FFFC, leaving the trailing space.
- Inspect the boolean: only run `records.delete(occurrence.ref)` and `changed()` when
  `consumeToken` returns `true`. On `false`, keep the record and surface the failure (or
  retry with a fresh snapshot); never delete bookkeeping for an edit the host rejected.
- The `setDraft` fallback branch (`plugin-client.js:55-57`) is already correct as written:
  it slices `snapshot.draft`, which is the clipboard projection, so clipboard coordinates
  are the right units there. It should stay clipboard-based — do not "convert" it.
- The `?? 1` fallback for a missing `length` (`plugin-client.js:49`) is dead weight on
  this host version — the contract declares `length` required
  (`host-input-contract.ts:17`) — and on the `consumeToken` path `length ?? 1` also
  produces the clipboard-system `end`; after conversion the detect `end` is always
  `start + 1` regardless.

**Order of work** (per the generic migration discipline: map, then edit, in dependency
order): fix the shared conversion helper first, then the insert call site, then the
removal call site, then the bookkeeping/return-value handling, then the toast message —
each verifiable independently against the session log's numbers.

---

## 4. Regression test plan

Each test asserts the host-facing span values (via a spy/fake facade), not just UI
outcomes, because the original defect is invisible whenever the composer is empty.

**Repeat-interaction (bug 1):**

1. *Double paste, empty composer.* Paste file A, then file B. Assert: two composer chips,
   two dock chips, no toast; the second `insertReference` call received
   `span = {start: 2, end: 2, draftRev: <current>}` given A's 28-char clipboard form + 1
   trailing space; final `draft` is both clipboard forms space-separated and
   `occurrences.length === 2`.
2. *Triple paste.* Repeat a third time; assert the third span's `start` equals
   `draft.length − Σ(lengthᵢ − 1)` — guards against a "fix" that hard-codes the
   one-chip case.
3. *Paste after typed text.* Type `hello ` (no trailing-space ambiguity), paste twice.
   Assert spans account for the typed prefix plus preceding chips, and both chips land at
   the end in order.
4. *Stale revision still reported correctly.* Force `draftRev` mismatch (edit the draft
   between snapshot and insert). Assert the insert is rejected and the surfaced message is
   the revision-race one — so the coordinate fix doesn't mask genuine CAS failures and the
   two failure modes stay distinguishable.

**Removal (bug 2):**

5. *Remove the only chip.* Paste once, click × on the dock chip. Assert `consumeToken`
   received `span = {start: 0, end: 1, draftRev: <current>}` (not `{0, 28}`); the composer
   chip is gone; the dock chip is gone; `records` no longer holds the ref.
6. *Remove the first of two.* Paste A and B, click × on A's dock chip. Assert span
   `{0, 1}`; B's composer and dock chips remain with correct labels; a fresh snapshot shows
   exactly one occurrence.
7. *Remove the second of two.* Paste A and B, click × on B's dock chip. Assert the span
   start equals A's clipboard length minus `(lengthA − 1)` converted — i.e. the conversion
   subtracts only occurrences *before* the target. Then click × on A: assert it now
   resolves to `{0, 1}` against a fresh snapshot.
8. *Failed consume keeps bookkeeping.* Stub `consumeToken` to return `false` (e.g. stale
   draftRev). Click ×. Assert: record is **not** deleted, dock chip still shows the real
   size label (never `unavailable`), an error is surfaced, and a subsequent × with a fresh
   snapshot succeeds.
9. *Interleave.* Paste, remove, paste again. Assert the second paste's span is computed
   from the post-removal snapshot (the remaining document, not stale offsets).
10. *Fallback path unchanged.* With `consumeToken` absent, remove via the `setDraft`
    fallback and assert the draft splice uses the original clipboard coordinates
    `[offset, offset+length)` — pinning the asymmetry so a future "consistency" refactor
    doesn't break the correct branch.

Tests 1–3 pin the insert conversion, 5–7 pin the removal conversion, 8 pins the
return-value bookkeeping, and 4/10 pin the two places where the *old* behavior was
actually correct, so the fix cannot over-convert.

---

## 5. Routine pre-release source-reading discipline (guidance, not scored)

Before calling any input-machine verb — and again on every host upgrade — check, in the
host source (not from memory or a changelog one-liner):

1. **Which projection each parameter lives in.** Whenever the host maintains multiple
   text projections of one document (here: `detectText` vs `clipboardText`/`draft`), find
   the doc comment on each span/offset/length field and on each verb parameter, and write
   down which coordinate system every number at every call site is in. Never mix
   projections in one call.
2. **The verb's guard chain.** Read every early-return in the verb (`phase`, `draftRev`
   CAS, empty-span rejection, trimmed-draft equality here) and confirm the plugin's
   preconditions actually establish each one — and that the plugin's error messages
   distinguish which guard can fire, so toasts don't misattribute failures.
3. **What the verb splices.** The substring the guard inspects (`detectText.slice(...)`,
   `clipboardText.trim()`) reveals the operative projection even when comments are thin.
4. **Return-value semantics.** Any verb returning a boolean "applied" must have its result
   consumed; a fire-and-forget call followed by unconditional local bookkeeping is a state
   desync waiting to happen (exactly the `unavailable` chip here).
5. **Field optionality vs the contract.** Defensive fallbacks like `length ?? 1` should be
   checked against the published type — a required field guarded as optional hides
   contract drift instead of surfacing it.

---

## Honesty notes

- The claim that `$replaceDetectSpanWithNodes`/`$replaceDetectSpanWithText` return `false`
  on an out-of-range span is inferred from their names, the facade's
  `applied = ...` boolean plumbing, and the session log's observed outcomes
  (no second chip; chip survives ×); their bodies are not included in the evidence pack,
  so their exact failure mode on an out-of-bounds span cannot be confirmed from the given
  material. All other conclusions follow directly from the provided sources and log.
- Any mapping of this defect class to specific DSH release notes, migration cards, or card
  IDs would require the upstream changelog/migration documentation, which was not part of
  the provided materials; where such a mapping is needed, the correct procedure is to diff
  the contract and facade files across the host's release corridor and classify each change
  (breaking / behavioral / additive) before editing.
