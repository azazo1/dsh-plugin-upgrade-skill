# S9 · Composer Coordinate Trap — Diagnosis Report

**Plugin:** `@org/dsh-attach-input` v0.2.3 (community Web plugin)
**Host:** DSH `0.1.2-alpha.3`
**Evidence:** `fixture/plugin-client.js`, `fixture/console-session.txt`, `fixture/host-input-facade.ts`, `fixture/host-input-contract.ts` (read-only)
**Mode:** plugin-upgrade skill, Mode A (read-only inspection/diagnosis). No migrations, installs, or writes to the fixture were performed.

---

## TL;DR

Both user reports are **one bug, not two**: the plugin computes `TokenSpan` coordinates in the
**clipboard-text projection** (`InputState.draft` lengths and `Occurrence.offset/length`), but every
span-guarded input-machine verb (`insertReference`, `consumeToken` with `kind: 'span'`) interprets
its span against the **detect projection**, where each chip is exactly **one U+FFFC character**.
The two projections are identical only in an empty composer, which is exactly why paste #1 succeeds
and every later interaction fails. The removal path additionally ignores the verb's boolean return,
so a failed splice still deletes the plugin-side record, producing the `unavailable` ghost chip.

---

## 1 · Why paste #1 succeeds and every later paste fails

### The exact mismatch

From `host-input-facade.ts`, `insertReference(ref, span)`:

- its JSDoc states the span is a *"pick-time span snapshot (**detect coordinates**)"*;
- its guard is `if (span.draftRev !== this.rev) return false`, then it splices via
  `$replaceDetectSpanWithNodes(span, nodes)` and inspects
  `this.projection.detectText.slice(span.end, span.end + 1)` — i.e. **span offsets index into
  `detectText`**, where (per `host-input-contract.ts`) *"chip = one U+FFFC"*.

From `host-input-contract.ts`:

- `InputState.draft` is the **clipboard-text projection** (*"chips expanded to their clipboard form"*);
- `Occurrence.offset`/`length` are *"in the clipboard-text projection"*;
- `EditorProjection.detectText` vs `clipboardText` are two different coordinate texts over the
  same document: a chip contributes **1 char to `detectText`** but **`clipboardText.length` chars
  to `clipboardText`**.

The plugin (`add()`) computes:

```js
start: snapshot.draft.length,   // clipboard-projection length
end:   snapshot.draft.length,
draftRev: snapshot.draftRev,
```

i.e. an offset measured in clipboard characters, handed to a verb that measures in detect
characters. (The `draftRev` value itself is fine — the contract says `draftRev` is *"the monotonic
editor revision (span CAS compares against this)"*, the same `this.rev` the facade guards on, and
the plugin re-snapshots after every insert. The failing part is the offset pair.)

### Why "first works, later fails" is the signature of exactly this mismatch

The capture (`console-session.txt`) shows the divergence numerically:

- **Paste #1 (empty composer):** `draft = ''` → clipboard length **0**; `detectText` is also empty →
  detect length **0**. The two projections coincide (`0 == 0`), so `start = end = 0` is accidentally
  valid in *both* coordinate systems. The guard passes, the splice applies, the chip is created, and
  the host appends the separating space. → **OK**.
- **After paste #1:** `draft = "[attachment: screenshot.png] "` (length **29**: 28-char
  `clipboardText` + 1 host-appended space), but `detectText` is `"\uFFFC "` (length **2**: one
  U+FFFC + one space). The projections have diverged by `length − 1 = 27` chars per chip.
- **Paste #2:** the plugin passes `start = end = 29` — 27 characters past the end of the
  2-character detect text. `$replaceDetectSpanWithNodes` cannot apply a span beyond the document,
  `applied` stays `false`, `insertReference` returns `false`, and the plugin throws
  *"The DSH composer changed before the attachment could be inserted"*. No chip, no dock entry. → **ERROR**.

This monotone divergence is the tell-tale signature: the mismatch is **invisible in the identity
case** (empty composer, no chips — the only state the plugin was evidently tested in) and grows by
`clipboardText.length − 1` for every chip already in the document, so *every* interaction after the
first chip exists is guaranteed to fail, and fails *harder* (further out of range) the more chips
there are. A stale-`draftRev` race, by contrast, would be timing-dependent and would also fail on
paste #1; a phase guard would fail independently of chip count. Only a coordinate-system mismatch
produces exactly "first works, all later fail, worsens with each chip".

## 2 · Why the × click turns the chip into `unavailable` instead of removing it

Trace of `remove()` on the captured state (one occurrence, `offset: 0`, `length: 28`,
`detectText` length 2):

1. The plugin computes `end = occurrence.offset + (occurrence.length ?? 1) = 0 + 28 = 28` — again
   **clipboard-projection** arithmetic (`Occurrence.offset/length` are documented as clipboard-text
   coordinates), with a comment that already guesses at the right idea ("the removal must span
   `occurrence.length`, not one character") — but in the wrong coordinate system: in detect
   coordinates the chip occupies exactly `[0, 1)`, one U+FFFC.
2. It calls `input.consumeToken({ kind: 'span', span: { start: 0, end: 28, draftRev } })`.
   In `host-input-facade.ts`, the span branch guards `draftRev` (passes — same revision currency),
   `start !== end` (passes), then splices **detect text** via `$replaceDetectSpanWithText(span, '')`.
   A `[0, 28)` span over a 2-character detect text cannot apply → `applied = false` →
   `consumeToken` returns **`false`**. The capture confirms: *"consumeToken(...) returned (not
   inspected by the plugin code)"*. The composer chip is untouched.
3. **The plugin ignores the return value** and unconditionally runs
   `records.delete(occurrence.ref); changed();`.
4. Dock chip rendering (excerpt comment): the chip row is driven by the **host occurrence list**
   (still containing the ref, because the splice failed), and only the metadata comes from
   `records.get(occurrence.ref)`. With the record deleted, `record === undefined` → meta renders
   **`unavailable`**. The chip cannot disappear because the occurrence it renders still exists in
   the composer.

So the `unavailable` ghost is the same coordinate misread (step 1–2) compounded by a second,
smaller defect in the same function: treating a guarded, boolean-returning verb as fire-and-forget
(step 3). The bookkeeping (`records`) and the document (host occurrences) desynchronize, and the
render path surfaces the desync as `unavailable`.

## 3 · Fix direction

**One rule, derived from the host source excerpts:** convert every clipboard-projection coordinate
into a detect-projection coordinate before building a `TokenSpan`. From
`host-input-contract.ts`, per occurrence the chip occupies exactly `[offset, offset + length)` in
clipboard coordinates and exactly **one** U+FFFC character in detect coordinates; plain text maps
1:1. Therefore, for any clipboard-projection position `p`:

```text
detectPos(p) = p − Σ (occ.length − 1)  for every occurrence occ with occ.offset + occ.length ≤ p
```

and conversely `detectText.length = draft.length − Σ (occ.length − 1)` over all occurrences —
check: after paste #1, `29 − 27 = 2` ✓. Equivalently, if the shell exposes
`EditorProjection.detectText`, its `.length` is the insert position directly and per-occurrence
detect offsets can be derived as "index of the occurrence's U+FFFC" = `occurrence.ordinal +
text-before-it`; the arithmetic rule above is the same thing expressed only in terms of the
published `InputState`.

**Insert path (`add()`):**

- Replace `start/end: snapshot.draft.length` with the **detect** end-of-document position:
  `start = end = detectEnd(snapshot)` where
  `detectEnd = snapshot.draft.length − Σ(snapshot.occurrences.map(o => o.length − 1))`
  (or `projection.detectText.length` when available).
- Keep `draftRev: snapshot.draftRev` unchanged — it is already the correct CAS currency
  (contract: the facade compares it against `this.rev`).
- Note the host appends a separating space itself when needed; the plugin's own
  "append a space if draft lacks trailing whitespace" pre-step operates on `draft` (clipboard
  coords) and is fine, but it must re-snapshot (it already does) so the subsequent span uses the
  post-edit `draftRev` **and** recomputed detect end.
- The `if (!accepted)` branch should stay, but with correct coordinates it now fires only on real
  races (phase `busy`-like or genuine concurrent edit), where the right behavior is to re-snapshot
  and retry once rather than throw immediately.

**Removal path (`remove()`):**

- Convert the occurrence range: `start = detectPos(occurrence.offset)`,
  `end = start + 1` — **one** U+FFFC, not `occurrence.length` and not the `?? 1` fallback bolted
  onto a clipboard length. (For the captured state: `start = 0`, `end = 1`.)
- Keep `draftRev: snapshot.draftRev` from a fresh snapshot.
- **Check the return value**: only on `consumeToken(...) === true` delete the record and re-render.
  On `false`, re-snapshot and retry once with recomputed coordinates; if it still fails, surface
  the failure (toast/flag) and **keep the record**, so the dock can never render a ghost
  `unavailable` chip for an occurrence that is still in the composer. The `unavailable` label
  should be reserved for genuinely orphaned host occurrences (record missing for a ref the host
  still reports), not manufactured by premature bookkeeping.
- The `setDraft` fallback splice is clipboard-correct (`draft` is the clipboard projection) and may
  stay as the no-`consumeToken` legacy path, but note it rewrites the whole draft and collapses any
  concurrent edits; prefer the span verb.

Also fix the module-level invariant that made this hard to see: all helpers that compute positions
for spans should be named/typed for the detect projection (e.g. `detectOffsetOf`,
`detectEndOf`), so clipboard-projection values (`draft.length`, `occ.offset`, `occ.length`)
cannot silently flow into a `TokenSpan`.

## 4 · Regression test plan

All sequences start from a fresh session with an **empty** composer, because that is the only
state where the two projections coincide — precisely the state in which the original bug was
invisible. Assertions must check **both** projections' observable results: the composer
occurrences, the `InputState.draft` text, the dock chips, and the plugin `records`.

**R1 — repeat-insert (kills bug #1):**
1. Paste file A → assert: dock chip A with size label (not `unavailable`), composer occurrence for
   A, `draft = A.clipboardText + " "`.
2. Paste file B (same or different size) → assert: **no toast**, `insertReference` accepted, dock
   shows 2 chips, `occurrences` has 2 entries sorted by offset, `draft` ends with
   `B.clipboardText + " "`.
3. Paste file C → same assertions with 3 chips (divergence grows monotonically; a coordinate
   mismatch that survives two chips survives only by luck at three).
4. Variant: type text not ending in whitespace, then paste → the `setDraft` pre-step runs; assert
   the insert still lands at the detect end-of-document after the re-snapshot.

**R2 — removal after insert (kills bug #2, same root cause):**
1. Paste A, paste B (via R1, so a chip exists).
2. Click × on chip **A** (offset 0) → assert: `consumeToken` returned true; composer occurrence A
   gone, occurrence B still present with updated offset; dock chip A gone; `records` no longer has
   A's ref; **no chip anywhere renders `unavailable`**.
3. Click × on chip B (the last/middle chip — different offset case) → same assertions.
4. Variant: text before/between chips; remove a middle chip and assert neighboring text and chip
   offsets shift correctly.

**R3 — failed-removal bookkeeping (kills the ignored-return-value half of bug #2):**
1. Paste A. Force a stale `draftRev` (or a concurrent edit between snapshot and verb call).
2. Click × → `consumeToken` returns false → assert: the plugin **keeps** the record, the dock chip
   still shows its size label (not `unavailable`), and either a retry with fresh coordinates
   succeeds or an error is surfaced. The invariant under test: *the dock never renders
   `unavailable` while the plugin still owns the ref, and `records` never orphans a host
   occurrence the plugin inserted.*

**R4 — projection invariant (property test, guards both paths):**
For every reachable state: `detectText.length === draft.length − Σ(occ.length − 1)`, and every
span the plugin builds satisfies `0 ≤ start ≤ end ≤ detectText.length`. Assert this around each
verb call in R1–R3. Any future coordinate confusion violates it immediately.

## 5 · Routine host-source discipline before calling input-machine verbs (unscored, guidance)

- **Read the verb's guard body, not its name.** For each facade verb, note (a) which projection its
  span indexes (`detectText` here — the JSDoc said "detect coordinates" and the body slices
  `projection.detectText`), (b) which revision the CAS compares (`this.rev` ↔ `InputState.draftRev`),
  (c) which phases it accepts (`plain`/`claimed` for insert), and (d) what the boolean return
  means ("edit applied" — a value you must branch on, not log-and-forget).
- **Map every published field to its coordinate system before arithmetic.** The contract documents
  each field's projection (`Occurrence.offset/length` → clipboard; `detectText` → U+FFFC per
  chip). Never mix values from two projections in one expression; if the shell publishes
  `EditorProjection`, prefer reading detect coordinates from it over deriving them.
- **Test the non-identity case.** Any interaction whose correctness depends on a projection
  coincidence must be tested with ≥1 and ≥2 chips already present (the empty-state test proves
  nothing — that is exactly how v0.2.3 shipped).
- **Treat guarded verbs as transactions:** mutate plugin-side bookkeeping only after the verb
  reports success, and design UI states (`unavailable`) so they can only be produced by the host,
  never by premature local cleanup.

---

## Skill-mode notes

- Mode A (read-only inspection). Per the benchmark authorization, no confirmation pause was needed;
  no files outside `benchmark-runs/glml-5.2-r2/skill/S9-composer-coordinate-trap/` were written,
  and the fixture was only read.
- **Completed:** full diagnosis of both symptoms from the host source excerpts; correction rule
  derived from `host-input-contract.ts`/`host-input-facade.ts`; per-call-site fix directions;
  regression plan (R1–R4); maintainer discipline (item 5).
- **Skipped:** no runtime reproduction was possible (static fixture only); the numeric verification
  `29 − (28 − 1) = 2` against the captured `detectText` length serves as the consistency check.
- **Pending/residual risk:** the exact API names for obtaining `EditorProjection.detectText` from a
  community plugin on 0.1.2-alpha.3 are not in the excerpt; if it is not exposed, use the derived
  arithmetic rule (`detectPos(p) = p − Σ(length − 1)`), which depends only on published
  `InputState`.
