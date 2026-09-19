# S15 · Vanishing Dock Chips — Root-Cause Report

Plugin: `@org/dsh-attach-input` v0.2.11 (community Web plugin). Symptom: paste a screenshot → the
pending-attachment chip dock above the input never appears; the paste still attaches; the `+` attach
button still works; no error banner in the UI.

Evidence used: `fixture/plugin-dock-chips.js` (v0.2.10 shipped excerpt), `fixture/feature.diff` (the
v0.2.11 hover-preview diff), `fixture/user-thread.md` (user report + maintainer note).

## 1. Exact root cause

**The throwing expression is the remove button's `disabled` prop in `AttachmentChips`**
(`fixture/plugin-dock-chips.js:34`):

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???
```

- **`busy` is unbound in `AttachmentChips`.** It is a `React.useState` local declared inside the
  *sibling* component `AttachButton` (`fixture/plugin-dock-chips.js:7`: `const [busy, setBusy] =
  React.useState(false); // <-- busy lives HERE`). It was evidently copy-pasted from
  `AttachButton`'s own `disabled: locked || busy` line (`plugin-dock-chips.js:17`) during the
  v0.2.10 "hardening pass" (the comment at `plugin-dock-chips.js:33` says exactly that). Lexical scoping
  means `AttachButton`'s `busy` is invisible here; the identifier is not declared / not in scope in
  `AttachmentChips`, so evaluating it raises `ReferenceError: busy is not defined`.

- **Why it throws only when a chip renders.** `AttachmentChips` early-returns `null` when there are
  no matching occurrences (`plugin-dock-chips.js:23`: `if (occurrences.length === 0) return null;`).
  With an empty dock, execution never reaches the `h('button', {...})` props object containing `busy`.
  The moment an occurrence exists (a paste), the props object is evaluated during render and the
  free identifier throws.

- **Why the `||` short-circuit kept it latent through v0.2.10.** `||` is lazy: the right operand
  `busy` is only evaluated when the left guard is falsy, i.e. when
  `(props.input?.phase ?? 'plain') !== 'plain'` is `false` — the **plain** phase. Whenever the
  input is in any non-plain phase (locked/submitting/etc.) the left side is `true` and `busy` is
  never touched, so the line "works". The hardening pass that introduced the line evidently only
  exercised the locked path (plus `node --check`-style checks, see §5), where the short-circuit
  hides the dangling reference. It only detonates in the combination *occurrence present **and**
  phase === 'plain'* — the exact state produced by pasting a screenshot into an idle composer.

- **Why the symptom is "the whole dock vanished", not "the remove button is broken".** The dock is
  registered as a single entry in the `InputZone` slot. A render exception anywhere inside that
  entry is caught by the framework's **slot-level error boundary**, which unmounts the *entire slot
  entry* — not the individual button that referenced `busy`. The throw happens while constructing
  the props object, before React reconciles any chip DOM, so nothing of the dock renders at all.
  The `AttachButton` lives in a different slot (`input.left`) with its own boundary, which is why it
  keeps working. And because the error boundary swallows the exception, the only trace is a
  `ReferenceError` in the browser console (devtools) — users never open it, hence "nothing else
  looks broken, no error banner" (`fixture/user-thread.md:7`).

## 2. Why blaming the v0.2.11 hover-preview diff is the wrong first conclusion

The diff (`fixture/feature.diff`) did touch `AttachmentChips`, so "new feature crashed the slot"
is tempting — but the shipped v0.2.10 code (`plugin-dock-chips.js:34`) **already contains
`|| busy`**, and the maintainer's own note (`user-thread.md:10-11`) confirms v0.2.10 shipped that
line. The defect is pre-existing in the baseline; v0.2.11 is merely the release in which a user
first rendered a chip in plain phase (paste-a-screenshot-to-try-the-new-preview is precisely that
interaction), which explains the timing correlation without the hover code being the thrower.

**Correct bisection:**

1. **Baseline mount (minimal, decisive):** mount the *v0.2.10* `AttachmentDock` in isolation with
   one matching occurrence (`source === SOURCE`) and `props.input.phase === 'plain'`. The v0.2.10
   component throws `ReferenceError: busy is not defined` on its own — no hover code involved.
   That alone establishes the dangling reference is in the baseline.
2. **Rollback / re-add bisect:** revert `feature.diff` on top of the shipped v0.2.10 lib and mount
   again with data present — the crash persists (the dangling `busy` line is in the base).
   Re-adding only the hover additions cannot be the isolated cause of a `busy` ReferenceError.

**Evidence distinguishing "new feature crashed the slot" from "old latent bug first exercised
now", and honest inconsistencies in the pack:**

- `feature.diff` is **inconsistent with the shipped baseline** about the old line: the diff's minus
  line (`feature.diff:32`) shows v0.2.10 as `disabled: ... !== 'plain'` *without* `|| busy`,
  while the actual v0.2.10 excerpt (`plugin-dock-chips.js:34`) and the maintainer note show
  `|| busy` already present. The diff's hunk context therefore cannot be trusted as history; the
  shipped artifact is the authority. If the diff were right instead, the baseline mount would
  render cleanly with data present and the crash would isolate to the v0.2.11 `+ || busy` line —
  either way the *hover-preview* additions are not the thrower, and the bisect (not diff recency)
  decides.
- The hover additions do add a **second defect of the same free-identifier class**: the new
  `const imageItem = status !== 'missing' ? record?.items.find(item => isImagePath(item.path))
  : undefined;` (`feature.diff:9-11`) sits *above* the `.map()` callback but references `status` and
  `record`, which are declared *inside* the callback (`feature.diff:13-14`). In
  `AttachmentChips`'s scope both are unbound, so this line also throws a `ReferenceError` whenever
  any occurrence exists — it must be relocated inside the callback (see §3). So the v0.2.11 lib
  would crash even with `busy` fixed; the fix must address both.
- The evidence does **not** prove exactly when every historical user first exercised the failure
  (a v0.2.10 user pasting into a plain composer could have hit it too); what it proves is that the
  dangling-`busy` pattern predates the hover feature per the shipped baseline, and that the
  diff's own new code is unreliable evidence for attribution.

## 3. The fix + hardening

**Primary fix — remove the dangling reference (or scope it properly), preserving the phase guard:**

```js
// AttachmentChips, remove button:
disabled: (props.input?.phase ?? 'plain') !== 'plain',
```

Either delete `|| busy` entirely (the chip dock has no in-flight operation of its own), or, if a
busy state is genuinely wanted there, own it explicitly: `const [busy, setBusy] =
React.useState(false)` inside `AttachmentChips`/`AttachmentDock`, or pass it down as a prop from the
component that actually owns the upload operation. Never reference `AttachButton`'s state from the
sibling component.

**Hardening the v0.2.11 diff should also get:**

- **Scope the hover lookup where `record`/`status` are defined:** move the `imageItem` computation
  inside the `.map()` callback, after `const record = records.get(occurrence.ref);` and
  `const status = record?.status ?? 'missing';`.
- **`record?.items ?? []`-style defensive reads:** `record?.items.find(...)` still throws when `record` exists
  but `items` is `undefined` (optional chaining stops at `record`, then `.find` on `undefined` throws).
  Write `(record?.items ?? []).find(item => isImagePath(item.path))`. Slot components re-render on
  every composer revision with data crossing component boundaries; a missing array must degrade
  to "no image preview", never unmount the whole slot entry.
- **Optional-chained DOM target:** `event.target.closest?.('.remove')` (or an `instanceof Element` /
  `event.target instanceof Element` check first). Synthetic/DOM event targets are not guaranteed to
  be Elements (text nodes, retargeted portal events); `.closest` on a non-Element throws inside
  the click handler.

These are cheap insurance in slot components precisely because of §1's failure mode: any single
throw — during render *or* in an event handler — silently takes down the entire slot entry, with
only a console message as a trace.

## 4. The regression that would have caught this before release

A **data-present render smoke** that mounts the dock/chip component through the real slot (or a
minimal harness with an error-boundary spy):

```js
const onError = vi.fn();            // or render inside the real InputZone slot boundary
renderWithBoundary(
  h(AttachmentDock, {
    input: { phase: 'plain', occurrences: [
      { source: SOURCE, occurrenceId: 'occ-1', ref: 'rec-1', label: 'shot.png' },
    ]},
    remove: () => {},
  }), { onError });

expect(onError).not.toHaveBeenCalled();                          // boundary captured nothing
expect(screen.queryAllByLabelText(/^Remove /)).toHaveLength(1);  // chip + x button exist
expect(document.querySelector('.chip')).toBeTruthy();
```

Key points:

- **An occurrence is present** (matching `source === SOURCE`). The empty dock returns `null` at
  `plugin-dock-chips.js:23` before ever reaching the throwing line, so an empty-state-only test passes
  vacuously — that is exactly how the bug survived previous checks.
- **Plain phase** (`phase: 'plain'`): makes the `||` left guard false, forcing evaluation of the
  dangling right operand. A locked-phase mount short-circuits and misses it — the same trap that
  hid the bug during the v0.2.10 hardening pass.
- **Both assertions matter**: the chip/remove control exists in the DOM **and** the error boundary
  captured no exception (no `componentDidCatch`/`onError` call, no unmount-to-fallback).
- Include a record-backed case (`records.get(ref)` returns an entry with `items`, ideally an
  image-path item) so the v0.2.11 `imageItem` branch is exercised as well.

## 5. Release-process lesson

The ship gate was effectively `node --check` (syntax check) on the built `lib/client.js`. That is
insufficient for a lib-only slot-rendering plugin:

- `node --check` validates **syntax only**. A free identifier like `busy` — or `status`/`record` used
  out of scope — is perfectly legal syntax; the failure is *semantic* and is resolved only when
  the identifier is looked up at **run time during render**. A parse cannot resolve free
  identifiers and cannot execute the component, so it can never see this class of bug.
- The plugin is **lib-only**: no type-check over authored source, no test suite, no bundler that
  would have flagged the unresolved binding. The only machine that ever evaluates the expression
  is the browser — and only with (a) an occurrence present and (b) plain phase. The release
  checks exercised neither condition.
- The failure is **invisible by design**: the slot error boundary unmounts the entry and logs to
  the console only; the paste still works, the attach button still works, so even a manual "does
  the page load" smoke passes — with an empty dock the component returns `null` and everything
  looks fine.

**Minimum viable pre-ship check for slot-rendering lib-only plugins:** a data-present,
default-phase (plain) render smoke (§4) that mounts every registered slot component (dock *and*
attach button) with representative non-empty props, observed by an error boundary, asserting the
expected element renders and no boundary capture occurred. Pair it with a cheap static complement:
run ESLint `no-undef` (or equivalent) over the shipped lib — it would have flagged `busy`,
`status`, and `record` immediately without executing anything.

## Summary

| Item | Conclusion |
| --- | --- |
| Throwing expression | `disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy` in `AttachmentChips` (`plugin-dock-chips.js:34`) — `busy` is `AttachButton`-local and unbound here |
| Latency | `||` short-circuit: `busy` evaluated only in plain phase; empty dock returns `null` before the line |
| Symptom | Slot-level error boundary unmounts the whole InputZone dock entry; console-only error; the `input.left` attach button unaffected |
| Attribution | Dangling `busy` pre-exists in the shipped v0.2.10 baseline; the diff's minus-line is inconsistent with it; the hover additions add a second out-of-scope `imageItem` defect but are not the root cause; decide by baseline mount / rollback-re-add bisect, not diff recency |
| Fix | Drop `|| busy` (or own the state/prop), keep the phase guard; move `imageItem` inside the callback; `(record?.items ?? [])`; `event.target.closest?.(...)` |
| Regression | Data-present, plain-phase render smoke asserting the chip renders with zero error-boundary captures |
| Process | `node --check` is syntax-only; lib-only slot plugins need a mounted, data-present render smoke (+ `no-undef` lint) before ship |
