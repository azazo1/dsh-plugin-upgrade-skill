# S15 · Vanishing Dock Chips — the Silent Slot Crash

Plugin: `@org/dsh-attach-input` · analyzed from the read-only evidence pack
(`plugin-dock-chips.js` v0.2.10 as shipped, `feature.diff` v0.2.11, `user-thread.md`).

## Symptom recap

After v0.2.11, pasting a screenshot produces **no pending-attachment chip** above the input.
The paste itself works (host-side attach succeeds), the `+` attach button is unaffected,
and there is **no error banner in the UI** — the failure is visible only in the browser
console. Empty-input state looks completely normal.

---

## 1. Exact root cause

Two free-identifier defects of the same class exist in `AttachmentChips`; the v0.2.11
render path hits them as soon as a chip would render.

### The throwing expression(s)

**Primary trigger (new in v0.2.11):** the hover-preview preamble

```js
const imageItem = status !== 'missing'
  ? record?.items.find(item => isImagePath(item.path))
  : undefined;
```

This line sits **above** the `occurrences.map(occurrence => { ... })` callback in which
`const record = records.get(occurrence.ref)` and `const status = record?.status ??
'missing'` are declared. At the point where `imageItem` is computed, `record` and
`status` are **not in any enclosing scope of that line** — they live only inside the map
callback below it. Identifier resolution therefore falls through to the global object:

- `status` accidentally resolves in a browser (`window.status`, the legacy string
  property, `""`), so `"" !== 'missing'` is `true` and the ternary takes the `record` branch;
- `record` has no global binding → **`ReferenceError: record is not defined`**.

Crucially, `record?.items` does **not** save you: optional chaining guards *values* that
are `null`/`undefined`; it does not guard an **unresolvable binding**. Reading the
identifier `record` itself throws before `?.` ever applies.

**Pre-existing latent defect (already in the shipped v0.2.10 lib):** the remove button's

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,
```

`busy` is `AttachButton`'s `React.useState` local. `AttachmentChips` is a sibling
top-level function, so `busy` is a **dangling reference** — a free identifier with no
binding in scope and no global fallback → `ReferenceError: busy is not defined` whenever
the right operand is evaluated.

### Why it throws only when a chip renders

Both throwing lines live **after** the empty-state guard:

```js
const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
if (occurrences.length === 0) return null;
```

With no pending attachments the function returns `null` before reaching either
expression — the empty dock renders nothing, throws nothing, and the plugin looks healthy.
Only when at least one occurrence exists does control flow reach the `imageItem` line and
the per-occurrence `disabled` expression. That is exactly the paste-a-screenshot path:
attach succeeds host-side (so the paste "works" and the message sends), but the client-side
chip render throws.

### Why `||` kept `busy` latent through v0.2.10

`A || busy` short-circuits: `busy` is read **only when** the left operand
`phase !== 'plain'` is falsy, i.e. only when the composer is in the plain phase. In
v0.2.10's real usage the chip's render paths were concentrated in states where the guard
was already `true`: a freshly attached item renders while the input is still in a
non-plain/locked phase, so the left operand satisfied the `||` and the dangling right
operand was never dereferenced. The bug was therefore latent — present in the shipped lib,
armed, but not evaluated. (Two aggravating factors make "v0.2.10 users used the x button
fine" consistent with this: a slot-level error boundary turns even an occasional hit into a
silently vanished chip with only a console error, so sporadic v0.2.10 hits would look like
"the chip didn't show" and go unreported; and the v0.2.11 hover-preview feature is the
first change that re-renders chips in plain phase with image data, systematically
evaluating the previously-skipped operand — plus the new `imageItem` line throws even
earlier in the same render.)

### Why "the whole dock vanished" instead of "the remove button is broken"

The unit of failure is not the button — it is the **slot entry**. `AttachmentDock`
registers through the InputZone slot, and the framework wraps each slot entry in an error
boundary. When `AttachmentChips` throws during render, React cannot commit a partial
element tree: the boundary catches the exception and **unmounts the entire entry**. There
is no degraded "chip without a working x" state. The attach button renders through a
different slot (`input.left`) in its own boundary, so it survives; the host-side attach
pipeline is untouched, so the paste still works. And because the boundary logs to the
browser console only — which users never open — the symptom is pure disappearance with no
error banner: a *silent* crash.

---

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff *looks* guilty: it touched `AttachmentChips`, and the regression arrived with
v0.2.11. But "the same component was edited in the failing release" is correlation, not
causation. Note also that the evidence pack itself is internally inconsistent about the
`|| busy` line — the diff's *removed* side shows `disabled` without `|| busy`, while
the shipped v0.2.10 lib excerpt and the maintainer's own note say the hardening pass
already shipped `|| busy` in v0.2.10. The diff was evidently generated against a stale
base; trusting it as "what v0.2.10 contained" is exactly the trap.

**Correct bisection:**

1. **Rollback/re-add bisect** — revert only the hover-preview hunks (`imageItem`, the
   `data-image`/`onClick` props, the hover-card) on top of v0.2.11 and reproduce with a
   pasted image. If chips are still gone, the feature additions are exonerated and the bug
   is pre-existing. Then re-add hunks one at a time to identify the first-failing line.
2. **Minimal render mount** — mount `AttachmentChips` in a test renderer with a single
   occurrence (`records` populated, `input.phase = 'plain'`). Run this against the
   **v0.2.10** artifact: it throws `ReferenceError: busy is not defined` (and against
   v0.2.11 additionally trips the `imageItem` line). A crash on the old artifact is
   definitive: an old latent bug first exercised now, not a new-feature crash.

**Evidence that distinguishes the two hypotheses:**

| New feature crashed the slot | Old latent bug first exercised now |
| --- | --- |
| Reverting the feature hunks fixes it | Reverting the feature hunks does **not** fix it |
| v0.2.10 artifact passes a data-present render mount | v0.2.10 artifact **fails** the same mount |
| Console stack points only at added lines (`openImageViewer`, `objectUrlOf`, hover-card) | Console stack points at `record`/`busy` identifier resolution — lines the diff did not meaningfully change |

The actual console error here is the tell: a `ReferenceError` on *free identifiers*
(`record`, `busy`) — i.e. broken scoping — not a `TypeError` inside the new preview
code paths (`objectUrlOf`, `openImageViewer`). The v0.2.11 feature's real contribution
was to change *when the component renders with data present in plain phase*, first
exercising the latent lines.

---

## 3. The fix

**Remove the dangling references / restore correct scoping:**

```js
function AttachmentChips(props, className) {
  const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
  if (occurrences.length === 0) return null;
  return h('div', { className }, ...occurrences.map(occurrence => {
    const record = records.get(occurrence.ref);
    const status = record?.status ?? 'missing';
    // Move the image lookup INSIDE the callback, after record/status are declared,
    // with defensive reads:
    const imageItem = status !== 'missing'
      ? (record?.items ?? []).find(item => isImagePath(item.path))
      : undefined;
    return h('div', {
      className: 'chip',
      'data-status': status,
      'data-image': imageItem === undefined ? undefined : '1',
      key: occurrence.occurrenceId,
      onClick: imageItem === undefined ? undefined : event => {
        if (event.target.closest?.('.remove') !== null) return;
        openImageViewer({ src: objectUrlOf(imageItem.file), name: imageItem.path });
      },
    },
      h('span', { className: 'name' }, record?.label ?? occurrence.label),
      imageItem !== undefined && h('div', { className: 'hover-card' },
        h('img', { src: objectUrlOf(imageItem.file), alt: imageItem.path })),
      h('button', {
        type: 'button',
        className: 'remove',
        'aria-label': 'Remove ' + (record?.label ?? occurrence.label),
        // busy belongs to AttachButton; either thread it through props
        // (e.g. props.busy) or delete the operand:
        disabled: (props.input?.phase ?? 'plain') !== 'plain',
        onClick: () => props.remove(occurrence),
      }, 'x'));
  }));
}
```

Key changes: (a) the `imageItem` computation moves **inside** the map callback so
`record`/`status` are actually in scope; (b) the `|| busy` operand is deleted unless
`busy` is explicitly threaded down as a prop — the correct scoping decision, not a
`typeof busy` guard that would merely re-hide the bug.

**Two hardening patterns the diff should also carry:**

- `record?.items ?? []` — coalesce to an empty array before `.find`, so a record whose
  `items` is missing/undefined degrades to "no preview" instead of throwing
  `TypeError: Cannot read properties of undefined (reading 'find')`.
- `event.target.closest?.('.remove')` — optionally chain the DOM method so an event
  whose `target` is not an Element (or a polyfilled/DOM-less test environment) skips the
  guard instead of throwing.

These are cheap insurance in **slot components** specifically because the failure mode is
amplified: any throw unmounts the whole slot entry with only a console trace, so a
one-character defensive read converts a user-visible "feature vanished" into an invisible
no-op.

---

## 4. The regression that would have caught this before release

A **render smoke that mounts the dock/chip component with an occurrence present** — the
empty state is useless here because `AttachmentChips` returns `null` before reaching
the throwing lines. Sketch (React Testing Library / react-test-renderer style):

```js
it('renders a pending-attachment chip without tripping the slot error boundary', () => {
  const records = new Map([[REF, { status: 'ready', label: 'shot.png',
    items: [{ path: 'shot.png', file: fakeFile }] }]]);
  let captured; // capture the slot boundary's onError, must stay uncalled
  const view = render(h(ErrorBoundarySpy, { capture: e => captured = e },
    h(AttachmentChips, {
      input: { phase: 'plain', occurrences: [
        { source: SOURCE, ref: REF, occurrenceId: 'occ-1', label: 'shot.png' } ] },
      remove: () => {},
    }), 'dock'));
  // assert the chip element exists and no error was captured
  expect(view.getByRole('button', { name: /^Remove shot.png/ })).toBeTruthy();
  expect(captured).toBeUndefined();
  expect(view.container.querySelector('.chip[data-status="ready"]')).toBeTruthy();
});
```

Two assertions matter: the **chip element renders** (positive presence, not "did not
throw at import time") and the **error boundary captured nothing**. Drive it with
`phase: 'plain'` — the exact configuration the `||` short-circuit depends on — and
with at least one occurrence and a populated `records` map. The same test run against
v0.2.10 fails with `ReferenceError: busy is not defined`, which doubles as the bisection
evidence from §2. A hover/preview variant (image item present) covers the `imageItem`
line and the `closest` guard.

---

## 5. Release-process lesson

The plugin shipped with what amounted to a **syntax check only** (`node --check` on the
lib). That is categorically insufficient for a **lib-only plugin whose component only
fails at render time with data present**:

- `node --check` parses; a free identifier like `busy` or an out-of-scope `record` is
  *syntactically perfect*. ReferenceErrors are resolved at evaluation time, and evaluation
  happens only when React renders the component with `occurrences.length > 0` — a
  runtime, data-dependent condition no parser can see.
- The failure is then *doubly hidden*: the slot error boundary swallows it from the UI, and
  the user never opens the console. So neither ship-time checks nor user reports surface
  it — the maintainer learned about it from a "chips are gone" issue.

**Minimum viable pre-ship check for slot-rendering lib-only plugins:** a CI render smoke
that (1) loads the actual built `lib/client.js` (not the source), (2) mounts every
registered slot component **with representative non-empty data** — real occurrences,
records, plain phase, an image item — and (3) asserts the expected element renders and no
error-boundary capture fires. Pair it with a lint rule that is free-identifier-aware
(`no-undef` with the browser/plugin globals configured) so dangling references like
`busy` fail statically too. Syntax checking alone verifies the plugin can *load*; only a
data-present mount verifies it can *render* — and for slot components, render failure is
user-invisible by design.

---

### Summary

- **Root cause:** `ReferenceError` from free identifiers in `AttachmentChips` — the
  v0.2.11 `imageItem` preamble reads `record`/`status` outside the map callback where
  they are declared (optional chaining does not protect unresolvable bindings), and the
  pre-existing `|| busy` operand references `AttachButton`'s state from a sibling
  function. Both sit after the empty-state `return null`, so they fire only when a chip
  renders.
- **Latency:** `||` short-circuit left `busy` unevaluated through v0.2.10.
- **Blast radius:** the InputZone slot error boundary unmounts the whole dock entry;
  console-only visibility; attach button (separate slot) and host-side paste unaffected.
- **Fix:** scope `imageItem` inside the callback, delete/thread `busy`; add
  `record?.items ?? []` and `event.target.closest?.()` hardening.
- **Regression:** data-present render smoke asserting chip presence and zero boundary
  captures.
- **Process:** `node --check` cannot see render-time, data-dependent failures; require a
  built-lib mount with non-empty data before shipping slot-rendering plugins.
