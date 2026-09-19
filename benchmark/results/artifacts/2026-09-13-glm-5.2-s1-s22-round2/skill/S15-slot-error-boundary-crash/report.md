# S15 · Vanishing Dock Chips — the Silent Slot Crash (Read-Only Analysis)

Plugin: `@org/dsh-attach-input`, v0.2.10 (shipped) → v0.2.11 (hover-preview release).
Evidence: `fixture/plugin-dock-chips.js` (v0.2.10 as shipped), `fixture/feature.diff` (v0.2.11), `fixture/user-thread.md`.
Mode: A-style read-only diagnosis (plugin-upgrade skill); no migrations, installs, or writes outside this report.

## 1. Exact root cause

There are **two free-identifier (dangling reference) bugs** in `AttachmentChips`; the v0.2.11 one is the proximate crasher, the v0.2.10 one is the latent predecessor.

### The expression that throws in v0.2.11

```js
const imageItem = status !== 'missing'
  ? record?.items.find(item => isImagePath(item.path))
  : undefined;
```

The diff hoists this hover-preview lookup **above the `return h('div', …)`**, outside the `occurrences.map(occurrence => { … })` callback. But `record` and `status` are declared **inside** that callback (`const record = records.get(occurrence.ref);`, `const status = record?.status ?? 'missing';`). At the hoisted position neither identifier exists in any enclosing scope, so evaluating `status` throws `ReferenceError: status is not defined` on **every render in which the component gets past the empty-state guard**. It is a free identifier, not `undefined` — parsing succeeds, the module loads, and the plugin registers fine; only the render pass dies.

### Why it throws only when a chip renders

`AttachmentChips` starts with:

```js
const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
if (occurrences.length === 0) return null;
```

With no pending attachments of this plugin's source, the function returns `null` before reaching the throwing line. The empty dock therefore renders (as nothing) without error; the crash needs **data present** — at least one occurrence — which is exactly the paste-a-screenshot flow.

### Why the `||` short-circuit kept the v0.2.10 bug latent

The v0.2.10 hardening pass added to the remove button:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,
```

`busy` is a **dangling reference**: it is `useState`d in `AttachButton`, a sibling component — it does not exist in `AttachmentChips`'s scope or module scope. Reading it is a `ReferenceError`. The `||` is what hid it: `a || busy` evaluates `busy` **only when `a` is falsy**, i.e. only when the composer phase is exactly `'plain'`. Whenever the chip rendered while the input was in a non-plain phase (upload in flight, composer locked), the left operand was `true`, the right operand was short-circuited away, and the bug stayed invisible. In the v0.2.10 flows that users actually exercised, chip-visible renders happened predominantly in those non-plain states, so the reference was never read during testing or normal use — and in the rare case it was, the symptom was the same silent dock disappearance (see below), which nobody attributed or even noticed without the console open. Result: v0.2.10 shipped a live landmine that needed only "chip rendered while phase is `'plain'`" to fire.

### Why v0.2.11 made it 100% reproducible

The hoisted `imageItem` line executes **unconditionally once any occurrence exists**, regardless of phase — no short-circuit shields it. Paste a screenshot → one occurrence → `ReferenceError` on the next render → chip never appears. The paste itself still works because the attachment pipeline (`props.add`, the host-side occurrence record) is independent of the dock's rendering; the attach button is unaffected because `AttachButton` is registered in a **different slot** (`input.left`) and its own code is healthy.

### Why the symptom is "the whole dock vanished", not "the remove button is broken"

The throw happens **during the render of the slot entry**, before React commits any DOM for it. The framework mounts each slot entry (here the InputZone occurrence dock) inside a **slot-level error boundary**; a render-phase exception is caught by that boundary, which **unmounts the entire entry** — not the single offending element. There is no partial render, no red button, no error banner in the product UI; the only trace is the `ReferenceError` stack in the browser console, which users never open. That is why the report reads "the chip is GONE" rather than "the x is broken": the whole dock entry is torn down, silently, on every render attempt.

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The recency bias is understandable — the diff touches the very component that now crashes — but it misidentifies the defect class and would produce a fix that leaves the landmine in place:

- **The diff is not even anchored to shipped code.** Its `-` context line is `disabled: (props.input?.phase ?? 'plain') !== 'plain',` — without `|| busy` — yet the shipped v0.2.10 excerpt (and the maintainer's own note) shows v0.2.10 **already contained** `|| busy` from an earlier hardening pass. The diff was generated against a stale base, so "the diff added `busy`" is factually wrong. Any conclusion drawn purely from the diff inherits that error.
- **Two defects coexist.** The new hover-preview hunk contributes its own free identifiers (`status`, `record` read outside the map), but the dangling `busy` predates it. Reverting the diff removes the deterministic crasher yet keeps the latent plain-phase crash.

### The correct bisection

1. **Read the console stack first.** The `ReferenceError` names the free identifier and the line. If it names `status` at the hoisted `imageItem` line, the proximate cause is the new code; if it names `busy` inside the button props, it is the pre-existing line. This single observation splits "new feature crashed the slot" from "old latent bug first exercised now".
2. **Rollback / re-add bisect.** Ship v0.2.10 → symptom disappears (v0.2.10's crash needs the narrow plain-phase-with-chip state). Re-apply the diff hunks one at a time: the pasted-screenshot crash returns with the `imageItem` hoist hunk — but a plain-phase chip render also crashes v0.2.10 alone.
3. **Minimal render mount (the decisive test).** Mount `AttachmentChips` in isolation, with **one occurrence present**, once with `phase: 'plain'` against the **v0.2.10** source: it throws `ReferenceError: busy is not defined`. That proves the latent bug predates v0.2.11. Mount the v0.2.11 source with one occurrence in any phase: it throws `ReferenceError: status is not defined`. Both facts together give the true account: *an old latent bug, plus a new line that made the crash phase-independent and deterministic*.

Distinguishing evidence, in short: v0.2.10 + data-present plain-phase render throws (old bug); v0.2.11 + any data-present render throws at a different, new line (new crasher). "New feature crashed the slot" alone predicts neither the v0.2.10 throw nor the differing stack.

## 3. The fix

1. **Remove the dangling `busy` reference.** Either restore `disabled: (props.input?.phase ?? 'plain') !== 'plain'`, or, if chips genuinely need to reflect in-flight work, derive it from data the component actually owns (e.g. read it from the record/occurrence state or lift shared busy state to a common parent) — never reference another component's local state.
2. **Scope the hover-preview lookup properly.** Move the `imageItem` computation **inside the map callback, after `record` and `status` are declared**, so each chip resolves its own image item.

Hardening the diff should also get (cheap insurance in slot components, where any throw costs the whole entry):

- **`record?.items ?? []`** before `.find(...)`: a record whose `items` is absent/empty then yields `undefined` instead of a `TypeError` on `.find` of `undefined`. Optional chaining guards the *reference*; `?? []` guards the *member access on the result* — you need both.
- **`event.target.closest?.('.remove')`**: if the click target is ever a non-Element node (or a renderer that does not provide `closest`), the guard degrades to "no match" instead of throwing and unmounting the dock from a click handler.
- Optionally `imageItem?.file`-style chaining where the item shape is not locally guaranteed.

These cost nothing on the happy path and each removes a whole class of "dock silently vanished" reports.

## 4. The regression that would have caught this before release

A **data-present render smoke** for every slot-rendering component:

- Mount the dock/chip component (real or minimal harness around `AttachmentChips`) **with at least one occurrence present** — *not* the empty state, because the empty dock returns `null` before reaching the throwing lines and would pass forever.
- Exercise both phase variants (`'plain'` and a locked phase) so both the `busy` path and the unconditional `imageItem` path are reached.
- Assert (a) the chip element (e.g. `.chip`, with its `data-status`) is present in the rendered DOM, and (b) **no error-boundary capture occurred** — e.g. render inside a test error boundary that records captures, and/or fail on `console.error` containing `ReferenceError`/React's "uncaught error" log. Asserting only "mount did not reject" is insufficient: the product's own boundary swallows the throw, so the test must detect the *capture*, not the absence of an exception at the mount call site.

One such test fails on v0.2.10 (the `busy` line) and on v0.2.11 (the hoisted `status` line) — it would have caught both the latent bug and the regression before either shipped.

## 5. Release-process lesson

`node --check` (and any syntax-only gate) verifies the file **parses**. A free identifier is not a syntax error — it is a `ReferenceError` that exists only at execution time, and here only on a specific execution path: *render, with data present, on the right side of a short-circuit or after an early return*. A lib-only plugin (no build-time bundling that would resolve/flag unknown identifiers, no type checker in the pipeline) whose surface is slot rendering therefore passes `node --check` while every chip render crashes.

**Minimum viable pre-ship check for slot-rendering lib-only plugins:** a CI render smoke that mounts **every registered slot entry with representative non-empty props/data** (attachments present, plain and locked phases) in a DOM environment (jsdom/happy-dom or the client dev harness), asserting the entry renders its expected elements and that **no slot error-boundary capture fires**. Cheap to maintain (one mount per slot component), and it is the only automated layer that observes the exact failure mode users see. A static layer (lint rule for undefined identifiers, e.g. `no-undef`, or a one-off typecheck of the shipped lib) is a useful supplement, but the render smoke is the minimum.

## Summary

- **Proximate cause (v0.2.11):** `status !== 'missing'` in the hoisted `imageItem` line reads `status`/`record` outside the map callback where they are declared → `ReferenceError` on every data-present render, phase-independent.
- **Latent cause (v0.2.10):** dangling `busy` reference in `disabled: phase !== 'plain' || busy`; `||` short-circuit prevented its evaluation except in plain-phase chip renders, so it shipped unnoticed.
- **Symptom shape:** slot-level error boundary unmounts the whole dock entry; console-only visibility; paste pipeline and the separate `input.left` attach button unaffected.
- **Fix:** scope `imageItem` inside the callback; remove/own the `busy` reference; add `record?.items ?? []` and `event.target.closest?.()` hardening.
- **Regression:** data-present render smoke asserting the chip renders with no boundary capture.
- **Process:** syntax checks cannot see free identifiers on conditional render paths; require per-slot data-present render smokes before shipping lib-only slot plugins.
