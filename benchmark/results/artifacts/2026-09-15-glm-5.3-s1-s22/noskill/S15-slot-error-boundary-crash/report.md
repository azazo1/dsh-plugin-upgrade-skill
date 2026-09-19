# S15 · Vanishing Dock Chips — the Silent Slot Crash

Plugin: `@org/dsh-attach-input`, community Web plugin. Symptom reported against v0.2.11: after
pasting a screenshot, the pending-attachment chip dock above the input box no longer appears;
the paste itself still works and the attach button (+) is unaffected. No error banner in the UI.

Evidence used (read-only fixture):
- `plugin-dock-chips.js` — the shipped v0.2.10 `lib/client.js` excerpt (`AttachButton`, `AttachmentChips`, `AttachmentDock`)
- `feature.diff` — the v0.2.11 hover-preview diff touching `AttachmentChips`
- `user-thread.md` — user report + maintainer note

---

## 1. Exact root cause

**The throwing expression is the free identifier `busy` in `AttachmentChips`:**

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // ReferenceError
```

`busy` is React state that lives in **`AttachButton`** (`const [busy, setBusy] = React.useState(false)`,
fixture line 7). `AttachmentChips` is a separate component with no `busy` binding in its scope
chain — no parameter, no local, no module-level declaration. Evaluating the identifier is not
`undefined`; it is an unresolvable reference, so the expression throws
`ReferenceError: busy is not defined` at **render time**, before React can produce any output
for the chip.

**Why it throws only when a chip renders.** `AttachmentChips` starts with:

```js
const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
if (occurrences.length === 0) return null;          // early exit, fixture line 23
```

With an empty dock the component returns `null` and never reaches the `disabled` prop inside the
`.map()` callback. The throwing line is *data-dependent*: it executes only when at least one
occurrence with `source === SOURCE` is present — exactly the state a paste creates. This also
explains why the empty-state and the attach button (a different component entirely) are fine.

**Why the `||` short-circuit kept it latent through v0.2.10.** `a || b` only evaluates `b` when
`a` is falsy. The left operand, `(props.input?.phase ?? 'plain') !== 'plain'`, is *truthy*
whenever the input zone reports any non-plain phase. In every such render the `busy` reference is
short-circuited away and never evaluated, so no throw. The hardening pass that pasted
`locked || busy` from `AttachButton` into `AttachmentChips` (fixture comment, line 33–34) thus
shipped a landmine that fires only under the conjunction **occurrences present AND plain phase**.
Pending chips typically appear while an upload is settling, and renders with a locked/non-plain
phase skip the right operand entirely; the crash needs both conditions at once, so v0.2.10 users
mostly hit the short-circuit or the empty-dock early return. v0.2.11 made the failure easy to hit
on the very first paste (see below), which is why the latent bug surfaced now.

**Why the symptom is "the whole dock vanished" rather than "the remove button is broken".** The
plugin registers the dock through the **InputZone slot**. A slot entry that throws during render is
caught by the framework's slot-level **error boundary**, which unmounts the *entire slot entry* —
not the failing sub-element. The error never propagates to the page and never renders an error
banner; it is visible only in the browser console (a `ReferenceError` logged by the boundary),
which users never open. So one bad prop on the remove button takes down the whole dock: the chip,
the filename, the x button, everything above the input simply does not exist. The attach button
survives because it is a separate component in a different slot entry (`input.left`) with its own
boundary scope — `AttachButton` owns `busy` legitimately and does not throw.

**Contributing v0.2.11 defect (same component, worth naming).** The diff hoists a hover-thumbnail
lookup above the `.map()`:

```js
const imageItem = status !== 'missing' ? record?.items.find(...) : undefined;
```

`status` and `record` are declared *inside* the map callback below (`const record = records.get(...)`,
`const status = ...`). At the hoisted position they are not yet in scope, so this line also throws
(`ReferenceError: status is not defined`) whenever `occurrences.length > 0` — unconditionally,
no `||` guard involved. This made the crash deterministic on every chip render in v0.2.11 and is
part of why the bug went from latent to user-visible. Both defects must be fixed; the *pre-existing*
one is the `busy` reference.

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion — correct bisection

It is tempting to read `feature.diff` and conclude "the hover-preview feature crashed the slot."
Two facts refute that as a *first* conclusion:

1. **The shipped v0.2.10 lib already contains the throwing line.** `plugin-dock-chips.js` (labeled
   "as shipped in v0.2.10") has `disabled: ... || busy` with the maintainer's own comment that the
   v0.2.10 hardening pass added it, and the maintainer note in the user thread confirms it. The
   diff's minus line showing `disabled: ... !== 'plain'` without `|| busy` means the diff was
   generated against an **older base than the shipped v0.2.10 lib** — diff context lines are not
   proof of what users were running. The recent diff is *correlated* evidence, not causal proof.
2. **The diff touched the same component**, so any change there is a confounder: the feature did
   not have to be the mechanism — it only had to *exercise* the component on a path users had not
   reliably reached before (first paste → occurrence present → chip render).

**Correct bisection:**

- **Rollback/re-add bisect.** Ship v0.2.10's exact lib under a test build and paste a screenshot:
  if the dock still vanishes, the v0.2.11 diff is exonerated for the primary crash. Then re-apply
  the diff in halves (hover-thumbnail block vs. the button-prop block) to find which hunk matters.
  Here the rollback would still crash *if the plain-phase + chip-present conjunction is hit*,
  pointing at the pre-existing line.
- **Minimal render mount.** Mount `AttachmentChips` alone in a test renderer with one occurrence
  present and `phase: 'plain'`. It throws `ReferenceError: busy is not defined` with **zero**
  v0.2.11 code present. That isolates the root cause to the v0.2.10 file.

**Evidence separating "new feature crashed the slot" from "old latent bug first exercised now":**

| Observation | New-feature crash | Old latent bug (what happened) |
| --- | --- | --- |
| v0.2.10 lib mounts with chip + plain phase | renders fine | **throws `busy is not defined`** |
| Throwing expression's provenance | inside diff  lines | pre-existing line; diff base is stale |
| Trigger conditions | any use of hover preview | data-present render under specific phase |
| Console error | references new identifiers (`status`/`record`) | references `busy` |

The actual browser-console `ReferenceError` text is the cheapest discriminator: `busy is not defined`
names a v0.2.10 identifier; `status is not defined` names the v0.2.11 hoist. Both appear in v0.2.11
(the hoist throws first), which is precisely why the misleading conclusion is easy to reach and why
the rollback bisect matters.

## 3. The fix

**Primary:** remove the dangling reference — the phase guard alone is the correct disable condition
for the chip's remove button (there is nothing in `AttachmentChips` to be busy about; upload busy
state belongs to `AttachButton`):

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain',
```

If chip-level busy state is genuinely wanted later, scope it properly: add `const [busy, setBusy] =
React.useState(false)` inside `AttachmentChips` (or pass it down as a prop from the owner that
owns the operation) — never reference another component's state binding by name.

**Secondary (fix the v0.2.11 hoist):** move the `imageItem` computation *inside* the `.map()`
callback after `record`/`status` are declared, so `status`/`record` resolve.

**Hardening patterns the diff should also get:**

- `record?.items ?? []`-style defensive reads — `record?.items.find(...)` is only half-guarded:
  if `record` resolves to an entry whose `items` is momentarily absent (records map mid-update,
  revision lag), `.find` throws. `(record?.items ?? []).find(...)` degrades to "no preview" and
  costs one expression.
- Optional-chained `event.target.closest?.()` — the click handler assumes a standard
  `EventTarget`; `event.target.closest?.('.remove')` tolerates targets where `closest` is missing.

Both are cheap insurance in **slot components** specifically: a slot entry has no partial-failure
mode — one throw unmounts the whole entry with only a console trace, so any single unguarded read
converts a cosmetic missing-preview into a vanished dock. Defensive reads turn crashes into
feature degradation.

## 4. The regression that would have caught this before release

A **render smoke that mounts the dock WITH an occurrence present** — not the empty state:

```js
// render-smoke.test.js (client lib test)
import { createElement as h } from 'react';
import { renderToString } from 'react-dom/server';   // or a headless client render
import { AttachmentDock } from '../lib/client.js';

test('dock renders a chip when an occurrence is present', () => {
  const props = {
    input: {
      phase: 'plain',                       // must be plain: exercises the 