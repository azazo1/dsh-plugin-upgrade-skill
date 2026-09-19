# S15 · Vanishing Dock Chips — the Silent Slot Crash (Read-Only Analysis)

Plugin: `@org/dsh-attach-input`, community Web (Client) plugin. Symptom reported against
v0.2.11 (hover-preview release): paste a screenshot → the pending-attachment chip dock
above the input never appears; the paste itself still delivers the attachment; the attach
button (+) is unaffected; no error banner in the UI.

Evidence used (read-only fixture):
- `plugin-dock-chips.js` — `AttachButton` (input.left slot) and `AttachmentChips`/`AttachmentDock` (InputZone occurrences slot) as shipped in v0.2.10
- `feature.diff` — the v0.2.11 hover-preview diff touching the same component
- `user-thread.md` — user report + maintainer note

---

## 1. Exact root cause

### The expression that throws

In v0.2.11 the diff **hoisted a new statement above the `occurrences.map(...)` callback**:

```js
const imageItem = status !== 'missing'
  ? record?.items.find(item => isImagePath(item.path))
  : undefined;
```

`status` and `record` are declared **inside** the `.map(occurrence => { ... })` callback:

```js
...occurrences.map(occurrence => {
  const record = records.get(occurrence.ref);   // inner scope only
  const status = record?.status ?? 'missing';   // inner scope only
  ...
})
```

From the outer position, `status` and `record` are **free identifiers** — there is no
binding for them in `AttachmentChips`'s scope (and none shown at module scope). The moment
that line executes, the engine throws `ReferenceError: status is not defined` (or
`record`, depending on evaluation order of the condition). This is a **runtime** error,
not a syntax error: `node --check` and any parser accept it happily.

### Why it throws only when a chip renders

The early return guards the empty state:

```js
if (occurrences.length === 0) return null;   // empty dock never reaches imageItem
```

With zero pending attachments the component returns `null` **before** the `imageItem`
line, so the empty dock (and the rest of the composer) renders fine. The ReferenceError
fires on the first render with **at least one occurrence** — exactly "paste a screenshot".
The paste/ingestion path (`props.add`, host-side attachment handling) is independent of
the dock's render, which is why the message still sends with the image attached.

### Why the `||` short-circuit kept `busy` latent through v0.2.10

The v0.2.10 hardening pass left a second dangling free identifier in the same component:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,  // busy lives in AttachButton
```

`busy` is a `useState` binding of **`AttachButton`** — a sibling function, not a
module-scope variable — so it is also a free identifier in `AttachmentChips`. But
`||` **short-circuits**: whenever the left operand
`(props.input?.phase ?? 'plain') !== 'plain'` is truthy (any non-`plain` input phase —
the busy/locked/sending states the hardening pass was written for), JavaScript never
evaluates `busy`, so no ReferenceError escapes. The landmine only arms in the exact
`phase === 'plain'` branch. The v0.2.11 hover-preview change then made the component
fragile in a much broader way (the `imageItem` free references throw on *every*
data-present render, plain or not), which is why the latent class of bug finally became
user-visible. Honest caveat: the fixture is an excerpt — since v0.2.10 users demonstrably
used the x button in plain phase, either a module-scope `busy` binding existed in the
full build, or the guard was truthy in the states users actually saw chips in; either way
`busy` as written is an undeclared reference whose safety depends entirely on
short-circuit luck, and it must be removed.

### Why the symptom is "the whole dock vanished", not "the remove button is broken"

The throw happens **before any chip element is created** — during evaluation of the
`imageItem` statement, at the top of the component body, not inside the remove button's
props. The exception propagates out of `AttachmentChips`/`AttachmentDock` into the
InputZone **slot's error boundary**, and the boundary's recovery is to **unmount the entire
slot entry** (the whole dock), not to degrade the single offending child. So no chip, no
filename, no x — nothing above the input. Because the boundary swallows the render error,
**no error banner appears in the UI**; the only trace is a `ReferenceError` stack in the
browser console, which users never open. `AttachButton` lives in a *different* slot entry
(`input.left`) with its own boundary scope, so the + button keeps working.

---

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff is the **trigger**, not the whole disease:

- It is true the crash path is only reachable after the diff (the `imageItem` line is new,
  and it throws on every data-present render). A wholesale rollback to v0.2.10 would
  "fix" the report — which is exactly why rollback is a misleading bisection step: it
  conflates "the diff exposed it" with "the diff caused it".
- The **same defect class already shipped in v0.2.10**: the dangling `busy` free
  identifier inside the remove button's `disabled` expression, masked only by the `||`
  short-circuit. The component was already one evaluation-order change away from crashing.

**Correct bisection:**

1. **Rollback/re-add bisect at hunk granularity** — revert the diff, confirm chips return;
   re-apply the hunks one at a time. The hover-preview hunk (the hoisted `imageItem`)
   alone reproduces the crash. That tells you *where* it fires, not *when it was born*.
2. **Minimal render mount per version** — mount each version's `AttachmentChips` in
   isolation (jsdom / testing-library, no host) with one occurrence present:
   - v0.2.11 component + occurrence → `ReferenceError: status/record is not defined` at
     the **new** `imageItem` line → diff-introduced instance.
   - v0.2.10 component + occurrence in `phase: 'plain'` → the `busy` reference is on the
     evaluation path → the same crash class exists **before** the diff.

**Evidence that distinguishes the two hypotheses:**

| Hypothesis | Predicted evidence |
|---|---|
| "New feature crashed the slot" | Stack trace points only at lines added by the diff; v0.2.10 mount is clean under all inputs |
| "Old latent bug first exercised now" (actual) | v0.2.10 mount with plain-phase data also throws (at `busy`); the diff merely added a *second*, always-reachable instance and made the empty-state guard the only thing standing between the user and a crash |

Conclusion: the correct fix addresses the **component's dangling-reference fragility**,
not just the new line — otherwise the next refactor re-arms `busy`.

---

## 3. The fix

1. **Remove/repair the dangling references:**
   - Move the `imageItem` computation **inside** the `.map()` callback, after
     `record`/`status` are declared (it is per-occurrence data anyway — computing it once
     outside was both a scope bug and a logic bug).
   - Delete the bare `busy` from `AttachmentChips`'s `disabled` expression. If the chip's
     remove button genuinely needs busy state, thread it explicitly through props
     (`props.busy`) from wherever that state actually lives; a sibling component's
     `useState` is never implicitly in scope.
2. **Two cheap hardening patterns the diff should also get:**
   - `record?.items ?? []` (i.e. `(record?.items ?? []).find(...)` or
     `record?.items?.find(...)`): even with the scope fixed, a record in `'missing'`
     status makes `record?.items` evaluate to `undefined`, and `undefined.find` is a
     `TypeError`. The nullish defaults turn that into a benign "no image" path.
   - `event.target.closest?.('.remove')` in the chip's `onClick`: `event.target` is not
     guaranteed to be an `Element` (text nodes, SVG internals, portal retargeting), and
     calling `.closest` on such a target throws.
   - **Why this is cheap insurance in slot components:** a throw anywhere in a slot
     component doesn't degrade that child — it unmounts the *entire slot entry* silently
     (console-only). The blast radius of one missing `?` is the whole dock, so defensive
     reads at every optional-data edge cost nothing and eliminate the worst failure mode.

---

## 4. The regression that would have caught this before release

A **render smoke that mounts the dock WITH an occurrence present**:

- Mount `AttachmentDock` (or `AttachmentChips`) under the real slot registration or a
  minimal React tree, with props containing at least one occurrence
  (`source: SOURCE`, a resolvable `ref`, an `occurrenceId`) and a records entry.
- **Not the empty state**: with `occurrences: []` the component returns `null` before the
  throwing line — an empty-dock smoke passes forever and proves nothing. The regression's
  whole value is the data-present path.
- Assert: the `.chip` element exists in the container, its `data-status` is set, and the
  error boundary captured nothing (e.g. an `onError` spy / boundary test double stays
  uncalled). For v0.2.11 specifically, also cover a record **with** an image item (hover
  card renders) and one **without / missing** (defensive-read path).
- Run it in both plain and non-plain `input.phase` so the `busy` short-circuit branch is
  exercised too — that is the only way the pre-existing landmine gets lit up in CI.

## 5. Release-process lesson

- **Why `node --check` was insufficient:** it only *parses*. Free identifiers
  (`status`, `record`, `busy`) are perfectly legal syntax — they become
  `ReferenceError` only when the engine evaluates them at runtime, which for a component
  means **at render time with data present**. A lib-only plugin has no bundler, no
  typecheck, no dead-code elimination between "build" and ship, so the shipped bytes are
  the source and nothing static caught the dangling names.
- **Minimum viable pre-ship check for slot-rendering lib-only plugins:** a data-present
  render smoke (item 4) executed against the exact shipped `lib/client.js` — mount with a
  realistic occurrence fixture, assert the chip renders, assert no boundary capture.
  Optionally add `eslint` `no-undef` on the lib as a zero-cost static complement; it
  flags free identifiers like `busy`/`status`/`record` immediately. The render smoke is
  the non-negotiable half, because it is the only check that reproduces the failure mode
  users actually hit: a silent, whole-entry slot unmount with a console-only trace.

---

## Summary

| Item | Finding |
|---|---|
| Throwing expression | hoisted `const imageItem = status !== 'missing' ? record?.items.find(...) : undefined` — `status`/`record` are free identifiers (declared only inside the `.map` callback) → `ReferenceError` on every data-present render |
| Latency | empty dock early-returns `null` before the line; the pre-existing `busy` free identifier was masked by || short-circuit whenever the phase guard is truthy |
| Symptom shape | slot error boundary unmounts the whole InputZone entry; error visible only in the browser console; attach button is a separate slot entry |
| Bisection | hunk-level rollback/re-add finds the trigger; per-version minimal render mount with data present proves the defect class pre-existed (`busy`, v0.2.10) |
| Fix | move `imageItem` into the map callback; delete/scope `busy` via explicit props; add `record?.items ?? []` and `event.target.closest?.()` hardening |
| Regression | data-present render smoke asserting the chip renders with no boundary capture (empty-state smoke is worthless here) |
| Process | `node --check` parses but never renders; minimum bar = data-present render smoke of the shipped lib (+ `no-undef` lint) |

*Analysis is read-only; the fixture was not modified.*
