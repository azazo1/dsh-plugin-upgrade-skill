# S15 · Vanishing Dock Chips — Diagnostic Report (@org/dsh-attach-input v0.2.11)

Evidence pack (read-only): README.md, plugin-dock-chips.js (v0.2.10 shipped lib/client.js excerpt), feature.diff (v0.2.11 hover-preview diff), user-thread.md.

## 1. Exact root cause

**The throwing expression** is in AttachmentChips, on the remove button:

    disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???

`busy` is a **free identifier**: it is declared by `React.useState(false)` **inside AttachButton** (plugin-dock-chips.js: `const [busy, setBusy] = React.useState(false);          // <-- busy lives HERE`). AttachmentChips is a separate component with no `busy` binding of any kind, so evaluating this expression at render time throws `ReferenceError: busy is not defined`.

**Why it throws only when a chip renders.** The function computes `const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE)` and then `if (occurrences.length === 0) return null;`. The empty dock exits **before** the chip `h(...)` construction, so the `disabled` expression (an argument to `h`, evaluated eagerly when the element tree is built) is never touched. Only a data-present render — at least one occurrence with `source === SOURCE` — evaluates it.

**Why the `||` kept it latent through v0.2.10.** The expression short-circuits: when the left operand `(props.input?.phase ?? 'plain') !== 'plain'` is **true** (the composer is uploading/pending — exactly the state in which a *pending-attachment* chip exists), JavaScript never evaluates the right operand, so `busy` is never resolved and no ReferenceError occurs. In v0.2.10 a chip was on screen only while the input was in a non-`plain` phase, so every chip render in practice took the short-circuit path; the line was landmined in the v0.2.10 "hardening pass" (the shipped file's own comment says so) but never detonated. It detonates in v0.2.11 the first time a chip renders while the phase is (or returns to) `plain` — e.g. after the pasted image commits/sends and the phase resets while the occurrence is still listed.

**Why the whole dock vanished, not just a broken x button.** The dock is registered as one slot entry (InputZone occurrences; `AttachmentDock` → `AttachmentChips(props, 'dock')`). Per the maintainer note in user-thread.md: "a slot entry that throws during render is caught by the framework's error boundary and unmounted (the error is only visible in the browser console, which users never open)". So one throw during the map unmounts the **entire** AttachmentDock entry — filename span, hover card, and all x buttons disappear together. AttachButton is a *separate* slot entry (`input.left`) that never throws, which is why the user still sees the `+` button. No error banner exists because slot error boundaries swallow the error to the console only — exactly matching mirren's report ("the paste itself worked… the + is still there… no error banner in the UI").

Secondary latent defects of the same class introduced by the diff: `record?.items.find(item => isImagePath(item.path))` is a TypeError if a record exists without an `items` array; and `status` is referenced in the `imageItem` line before its `const status` declaration inside the `map` callback (temporal dead zone). Neither is the v0.2.11 trigger, but both sit on the same crash path.

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff *touched the same component* (AttachmentChips) and shipped minutes before the report, so "the new hover preview crashed the slot" is the natural — and wrong — first read. Three facts redirect it:

- **The crashing line is not the diff's new code.** The throw is `busy` in the `disabled` prop of the remove button. The shipped v0.2.10 source (plugin-dock-chips.js) already contains `|| busy` with the comment "v0.2.10 hardening pass added the phase guard — and this busy reference"; the maintainer note confirms v0.2.10 already carried that line.
- **The artifacts contradict each other about that line.** feature.diff shows the `disabled` line changing from `!== 'plain',` to `... || busy,` in v0.2.11, while the shipped v0.2.10 excerpt and the maintainer note both attribute `busy` to v0.2.10. Precisely because the diff and the changelog disagree, neither should be trusted; the code must be bisected, not read.
- **The failure mode is data/phase-dependent, not feature-dependent.** The new feature code (`imageItem`, `onClick`, hover card) never executes before the crash, and the crash requires `phase === 'plain'` with a chip present — a combination the short-circuit previously masked.

**Correct bisection:**

(a) Rollback/re-add bisect — take the v0.2.10 build, revert *only* the hover-preview additions, mount the dock with a chip present at `phase: 'plain'`; it still throws `ReferenceError: busy is not defined`, proving the bug predates v0.2.11. Equivalently, re-apply the v0.2.11 feature diff onto a build with the `busy` reference removed: it renders fine.

(b) A minimal render mount (jsdom + React, one occurrence, `records` populated, phase `plain`) isolates the throw to the `disabled` line's `busy` identifier, with a stack naming AttachmentChips rather than any hover-card expression.

**Distinguishing evidence.** A new-feature crash would throw from the added expressions (`imageItem`, `objectUrlOf`, `openImageViewer`, the chip `onClick`) and would reproduce with v0.2.11's additions reverted to v0.2.10. An old-latent crash throws from a line the diff only *carried along*, reproduces on the v0.2.10 build under a minimal data-present render at `phase: 'plain'`, and its onset timing is explained by the paste/send phase sequence, not by the feature code itself.

## 3. The fix

Remove the dangling reference — `busy` has no meaning in AttachmentChips:

    disabled: (props.input?.phase ?? 'plain') !== 'plain',

If the remove button genuinely needs a busy state, scope it properly: declare `const [busy, setBusy] = React.useState(false)` inside AttachmentChips (or receive it as a prop) — never reference a sibling component's hook binding. Also fix the diff's own fragile reads: resolve `status` before the `imageItem` line, and use `(record?.items ?? []).find(item => isImagePath(item.path))`.

**Two hardening patterns the diff should also get, and why they are cheap insurance:**

- `record?.items ?? []`-style defensive reads: slot components receive live occurrences and records from the host; a record that exists without an `items` array turns a cosmetic feature into a render crash that silently unmounts the whole slot entry. `?? []` degrades to "no image preview" instead of "dock disappears".
- Optional-chained `event.target.closest?.('.remove')`: `event.target` may be a non-Element node or lack `closest`; the optional call turns a potential click-handler TypeError into the normal "open viewer" fallback.

Both are one-token changes. In slot components the cost/benefit is extreme: the error boundary punishes *any* throw during render by deleting the entire entry with console-only visibility, so every defensive read buys full-dock availability for near-zero code.

## 4. The missing regression

A **data-present render smoke** that mounts the dock WITH an occurrence present:

- Mount AttachmentDock (via the same slot registration path, or directly with the slot's prop shape) with one occurrence `{ source: SOURCE, occurrenceId: 'o1', ref: 'r1', label: 'shot.png' }`, a populated `records` map (`records.get('r1')` returns `{ status: 'ready', label: 'shot.png', items: [...] }`), and `props.input.phase: 'plain'` — the exact combination that defeats the `||` short-circuit.
- Assert the `.chip` element renders (name span + remove button present) **and** no error-boundary capture occurred (render inside a spy error boundary, or assert the slot entry's unmount/console.error callback never fired).
- Include the `phase: 'plain'` case explicitly; testing only the uploading/pending phase passes via short-circuit and re-plants the landmine.
- The empty dock is explicitly *not* sufficient coverage: `if (occurrences.length === 0) return null;` exits before the throwing line, so an empty-state smoke passes vacuously while the bug ships. This is exactly the gap the maintainer admits: "We shipped without a render smoke that mounts the dock with a chip present."

## 5. Release-process lesson

`node --check` (any syntax-only gate) validates grammar only. `busy` is a syntactically legal free identifier; its failure is a **runtime binding resolution** that happens only when the browser renders the component with real occurrence data in the right phase. For a lib-only plugin (built lib/client.js loaded straight into the host page) there is no bundler static analysis pass to flag the undefined global, no server render to exercise it, and the framework error boundary converts the crash into a silent console-only unmount — so the release went out green while the chip UI was entirely dead for the core paste workflow.

**Minimum viable pre-ship check for slot-rendering lib-only plugins:** after building lib/, run a headless DOM render smoke (jsdom/happy-dom + React) against the *built artifact* that mounts every registered slot component **with representative data present** — non-empty occurrences, populated records, and each host phase including `plain` — inside an error-boundary spy, failing the release if any entry throws or is unmounted by the boundary. That one check would have caught this before v0.2.11 — and, run against the v0.2.10 build, would have caught the latent `busy` reference one release earlier.
