# S15 · Vanishing Dock Chips — the Silent Slot Crash (read-only diagnosis)

Plugin: `@org/dsh-attach-input` v0.2.10 → v0.2.11 (Web Client, lib-only, renders into two
composer slots: the attach button in `input.left` and the pending-attachment dock in the
InputZone occurrences slot). Evidence: `plugin-dock-chips.js` (v0.2.10 excerpt),
`feature.diff` (v0.2.11), `user-thread.md`. Mode: read-only diagnosis (skill Mode A);
nothing outside this report was written.

## 1. Exact root cause

**The throwing expression is the `disabled` prop of the chip's remove button:**

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- throws
```

`busy` is a **free identifier**. It is a `React.useState` hook local to `AttachButton`
(a sibling component rendered into a different slot); it is not declared in
`AttachmentChips`, not a module-scope binding, and not a global. When the `||` chain
actually reaches it, evaluation raises `ReferenceError: busy is not defined` — a
*runtime* error, invisible to any syntax check (`node --check` accepts it, because a
bare identifier reference is perfectly valid syntax).

**Why it throws only when a chip renders.** `AttachmentChips` starts with
`if (occurrences.length === 0) return null;`. With no pending attachments of this
plugin's `SOURCE`, the function returns before any chip — and therefore before the
`disabled` expression — is ever evaluated. The empty dock never reaches the throwing
line. The moment a paste creates an occurrence, React evaluates the chip's props object,
hits `busy`, and the render throws.

**Why the `||` short-circuit kept it latent.** `a || busy` evaluates `busy` only when
`a` is falsy — i.e. only when `phase === 'plain'`. Whenever the input is in a
non-plain phase (the very condition the hardening pass targeted), the left operand is
`true`, `busy` is never evaluated, and the button renders disabled with no error. So
the bug is doubly gated: it needs (a) at least one occurrence of this plugin's source on
screen **and** (b) `phase === 'plain'`. Any check that exercised the guard in a
non-plain phase, or with an empty dock, passed clean. v0.2.11 is simply the first release
that put a chip on screen in plain phase in front of a real user: the reporter pasted a
screenshot into an idle (plain) composer — the everyday case that had never been
exercised with data present.

> Evidence conflict, recorded per the skill's boundary ("record both, do not silently
> pick one side"): the v0.2.10 excerpt and the maintainer's note say the `|| busy` tail
> already shipped in v0.2.10, while `feature.diff`'s removed line
> (`disabled: (…) !== 'plain',`) shows a base without it. Either way the mechanism and
> the fix are identical: the dangling `busy` reference on the chip render path. If the
> diff did introduce it, the culprit is still not the hover-preview code but the
> `|| busy` tail that rode along on a pre-existing line (see §2).

**Why the symptom is "the whole dock vanished", not "the remove button is broken".**
The dock is registered through the InputZone **slot**. A slot entry that throws during
render is caught by the framework's slot-level error boundary, which unmounts the
*entire slot entry* — not the failing subtree fragment. React never gets far enough to
diff "button broken vs. working": the exception unwinds the whole `AttachmentChips`
render, the boundary replaces it with nothing, and the dock disappears as a unit. The
error surfaces only in the browser console (`ReferenceError` inside the boundary's
component stack), which users never open — hence "no error banner in the UI". The attach
button is unaffected because `AttachButton` is a separate component in a separate slot
(`input.left`) whose render never touches `busy`-in-`AttachmentChips`; the paste
itself still works because attachment *adding* happens through `props.add`, not through
the dock's render output.

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff is the obvious suspect (same component, same release as the regression), and
"revert the hover preview" is the tempting conclusion. It is wrong as a *first* move:

- The diff contains two logically independent changes: the hover-preview additions
  (`imageItem`, `data-image`, `onClick`, hover-card) and a modification of a
  **pre-existing line** (the `disabled` expression). "The diff touched the component"
  is not "the new feature crashed the slot".
- The symptom signature already points away from the feature: a broken hover preview
  would render chips *without* a thumbnail; a broken `onClick` would fail on click,
  not on mount. Instead the chips are gone entirely, on paste, in plain phase — a
  render-time throw, before any hover/click code runs.

**The correct bisection** (cheap, mechanical, no guessing):

1. **Rollback/re-add bisect**: check out v0.2.10, mount the dock with a chip — works
   (modulo the evidence conflict above; if the excerpt is right, mount it with
   `phase: 'plain'` and a chip and it *does* throw, immediately indicting the
   pre-existing line). Apply the diff **without** the `|| busy` tail — the crash
   disappears. Apply **only** the `|| busy` tail without any hover code — the crash
   reappears. One line is the entire causal delta.
2. **Minimal render mount**: a jsdom/testing-library mount of `AttachmentChips` with
   `props.input = { phase: 'plain', occurrences: [one SOURCE occurrence] }` against
   v0.2.10 vs v0.2.11 code isolates the component from the whole plugin/host and shows
   exactly which source version throws.
3. **Read the console**: the browser console shows `ReferenceError: busy is not defined`
   with a component stack pointing at the remove button's props — a free-identifier
   crash, not a TypeError inside `objectUrlOf`/`isImagePath`/`openImageViewer` that a
   genuinely broken hover feature would produce.

**Distinguishing evidence**: "new feature crashed the slot" would show the feature's own
functions in the stack (e.g. `record.items.find` on undefined, bad blob URL), would
typically fail only for image attachments, and would reproduce on hover/click rather
than on mount. "Old latent bug first exercised now" shows a `ReferenceError` on an
identifier the feature code never references, fires for any occurrence regardless of
type, and is gated by the doubly-short-circuited path described in §1.

## 3. The fix

**Primary**: remove the dangling reference — delete `|| busy` from
`AttachmentChips`'s remove button:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain',
```

`busy` semantically belongs to `AttachButton` (it tracks the in-flight `props.add`
of the attach *menu*). If chips really must disable during an attach in flight, scope it
properly: lift the busy state to the shared parent (or a context/store both slot entries
read) and pass it down as a prop — never reach for a sibling component's local.

**Hardening the diff should also get** (cheap insurance in slot components, where any
throw costs the whole entry):

- `record?.items ?? []` before `.find(…)` — the new `imageItem` line calls
  `record?.items.find(…)`: optional chaining stops at `record`, but if `record`
  exists with `items` absent/undefined, `.find` throws a TypeError and unmounts the
  dock the same way. A `?? []` makes the miss degrade to "no preview".
- `event.target.closest?.('.remove')` — `closest` exists on `Element`, but
  `event.target` can be a non-Element node in edge dispatch paths (e.g. SVG text or
  document-level retargeting); one optional chain turns a potential crash into a no-op
  guard.

Both cost one token each and convert "slot entry unmounts" into "feature quietly
no-ops" — the right failure gradient for decorative enhancements riding on a dock whose
primary job (showing pending attachments) must survive.

## 4. The regression that would have caught this before release

A **render smoke that mounts the dock WITH an occurrence present** — not the empty
state. The empty dock returns `null` before ever reaching the throwing line, so an
empty-mount test passes forever while the bug ships. Sketch (testing-library/jsdom,
React 18):

```js
import { render, screen } from '@testing-library/react';

test('dock renders a chip for a pending attachment (plain phase)', () => {
  // one occurrence of this plugin's SOURCE, phase plain — the everyday paste case
  const props = {
    input: {
      phase: 'plain',
      occurrences: [{
        source: SOURCE,
        ref: 'ref-1',
        occurrenceId: 'occ-1',
        label: 'screenshot.png',
      }],
    },
    remove: vi.fn(),
  };
  records.set('ref-1', { status: 'ready', label: 'screenshot.png', items: [] });

  render(h(AttachmentChips, props, 'dock'));

  // assert the chip element actually rendered…
  const chip = document.querySelector('.chip');
  expect(chip).not.toBeNull();
  expect(chip.dataset.status).toBe('ready');
  // …and that no render error escaped (an uncaught render throw fails the test
  // outright under testing-library; optionally also assert an error-boundary
  // capture did not fire — spy on console.error for "Uncaught error" boundaries).
});
```

Key properties: data present (occurrence + `records` entry), `phase: 'plain'` (so the
`||` short-circuit cannot mask the right-hand operand), and the assertion targets the
chip element itself, so a silent error-boundary unmount (null render) fails the test,
not passes it.

## 5. The release-process lesson

**Why "syntax check only" was insufficient.** `node --check` (and equivalent
parse-only gates) validate *syntax*. `busy` is a syntactically valid identifier
reference; its absence is only detectable when the expression is *evaluated* during a
real render with data present. For a lib-only plugin there is also no host boot to
smoke: the package ships compiled `lib/` with no runtime entry the publisher executes,
so "it built and parses" feels like verification while exercising exactly 0% of the
render path. The two gates that would have caught it — a non-plain phase during manual
testing (short-circuit) and an empty dock in the smoke (early return) — both masked the
same line.

**Minimum viable pre-ship check for slot-rendering lib-only plugins**: a CI render
smoke that, for **every slot component the plugin registers**, mounts it under
jsdom/testing-library with **representative non-empty data** (at least one occurrence /
item / record per list the component reads) and asserts the expected element renders
without an error-boundary capture. Pair it with `tsc --noEmit`/`no-undef`-style
lint where the source is TypeScript/analyzable, which *does* flag free identifiers
statically — `node --check` never will. That is minutes of CI per release and closes
the entire class: free identifiers, undefined-property reads on data-present paths, and
slot-boundary unmounts all become red builds instead of console-only user reports.

---

## Skill-conformant summary

- **pre-existing (baseline)**: not collected — read-only diagnosis task (Mode A); no
  builds, tests, installs, or migrations were run.
- **Completed**: root-cause identification (`|| busy` free-identifier ReferenceError in
  `AttachmentChips`), latency analysis (`||` short-circuit + empty-dock early return,
  fires only with an occurrence present and `phase === 'plain'`), slot error-boundary
  unmount semantics, bisection procedure distinguishing the hover-preview additions from
  the dangling reference (with the fixture's diff-vs-excerpt conflict recorded), fix and
  hardening recommendations, data-present render regression design, release-process
  recommendation.
- **Skipped**: no version-corridor cards apply (no DSH host upgrade involved — the crash
  is plugin-internal); no dependency/enablement/runtime validation layers, since no
  change was made.
- **Pending/residual risk**: the fixture conflict over whether `|| busy` shipped in
  v0.2.10 or entered in the v0.2.11 diff cannot be resolved from static evidence alone;
  the §2 bisect step 1 resolves it mechanically on a real checkout. `objectUrlOf` blob
  URLs and `openImageViewer` were not exercised (read-only task).
- **Rollback**: n/a — no files outside the report were touched; the fixture was not
  modified.
