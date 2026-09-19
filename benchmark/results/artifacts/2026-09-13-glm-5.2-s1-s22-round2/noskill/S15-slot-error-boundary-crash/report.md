# S15 · Vanishing Dock Chips — the Silent Slot Crash (Read-Only Analysis)

Fixture: `environment/fixture/` — `plugin-dock-chips.js` (shipped component), `feature.diff` (v0.2.11 hover-preview diff), `user-thread.md` (symptom report). No fixture files were modified; this report is the only output.

## 1. Exact root cause

There are **two free-identifier defects in `AttachmentChips`**, and the v0.2.11 code hits the first one before ever reaching the second:

### Primary crash site (v0.2.11): TDZ access of `status`/`record` in the `imageItem` computation

`feature.diff` inserts, immediately after the empty-state guard and **before** the `.map()` callback that declares `const record` and `const status`:

```js
const imageItem = status !== 'missing'
  ? record?.items.find(item => isImagePath(item.path))
  : undefined;
```

`status` and `record` are declared with `const` *inside* the `.map(occurrence => { ... })` callback below; the `imageItem` line sits in the enclosing function body. So when this line runs it reads block-scoped bindings from their temporal dead zone / out of scope: the expression throws `ReferenceError: Cannot access 'status' before initialization` (or `status is not defined`, depending on scope layout) on **every render in which at least one occurrence with `source === SOURCE` exists**.

This is exactly why the symptom is conditional:

- `if (occurrences.length === 0) return null;` — the empty dock returns **before** reaching the throwing line. No pending attachment → no throw → the rest of the plugin (paste, attach button) looks fine.
- Paste a screenshot → an occurrence appears → `imageItem` line executes → throw.

### Secondary latent defect: the free `busy` identifier and the `||` short-circuit

`busy` is a `React.useState` local of **`AttachButton`**, a sibling component. `AttachmentChips` references it as a bare free identifier:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???
```

`A || busy` evaluates `busy` **only when `A` is falsy**, i.e. only when `phase === 'plain'` (the unlocked, normal-typing state — precisely when a user is looking at a pending chip). When the composer is locked (`phase !== 'plain'`, truthy left operand) JavaScript short-circuits and never touches `busy`, so the bug is invisible. That is the short-circuit latency: the reference is only *conditionally* dereferenced, so it survives any code path that keeps the left operand truthy (or keeps the occurrence list empty via the early return). It was latent through v0.2.10 because in practice the throwing path required the conjunction "at least one chip rendered" **and** "left operand falsy" — and v0.2.10's shipped base line (see the diff's `-` side, `disabled: (props.input?.phase ?? 'plain') !== 'plain'`) did not yet evaluate `busy` at all in the released lib.

> Evidence conflict worth naming: the fixture excerpt `plugin-dock-chips.js` is labeled "v0.2.10 as shipped" yet already contains `|| busy`, while `feature.diff`'s minus side shows the v0.2.10 base **without** it, and the maintainer note claims v0.2.10 had it. The diff is the machine-checkable ground truth of what changed between the two releases; the excerpt appears to be the post-hardening working copy. Either way the mechanics below are unchanged — in the v0.2.11 build both `status`/`record` (TDZ) and `busy` (free identifier, short-circuit-gated) are dangling references, and the first one reached at render time is the TDZ read.

### Why "the whole dock vanished" instead of "the remove button is broken"

The throw happens while evaluating the `props` objects passed to `h()` — i.e. **during the render of the slot entry itself**, before any DOM for the chip exists. The framework wraps each slot entry (the InputZone occurrence) in an **error boundary**; a render-time throw is caught there and the *entire entry* is unmounted. There is no partial render: React discards the whole subtree of that slot entry, so no chip, no filename, no x button — the dock is simply gone. The error surfaces **only in the browser console**, which users never open, hence "no error banner, nothing else looks broken". The paste pipeline and the attach button live in *other* slot entries/components (`input.left`), outside this boundary, so they keep working.

## 2. Why blaming the v0.2.11 diff is the wrong *first* conclusion — and the correct bisection

The v0.2.11 diff is *where the crash first fired*, not necessarily *what introduced the defect*. The diff touched the same component for an unrelated feature (hover preview), so it is a tempting but confounded suspect. Distinguish "new feature crashed the slot" from "old latent bug first exercised now" with:

- **Rollback/re-add bisect**: revert only the `imageItem` block (keep the rest of the hover-preview diff). If the dock comes back, the inserted block is the trigger. Then re-apply the block minus the pre-`map` computation → still works → the crash is the *placement/scope* of the new lines (TDZ), not the feature.
- **Minimal render mount**: a standalone harness that mounts `AttachmentChips` with `props.input = { phase: 'plain', occurrences: [{ source: SOURCE, occurrenceId: 'a1', ref: 'r1', label: 'shot.png' }] }` and a seeded `records` map. It reproduces with **zero** hover-preview code if the `|| busy` line is evaluated (phase `'plain'`), proving the `busy` defect predates v0.2.11; and it reproduces with the v0.2.11 diff alone even in `'locked'` phase via the TDZ read — the two failure modes are separable by phase, which is the discriminating evidence.
- **Console evidence**: `ReferenceError: Cannot access 'status' before initialization` points at the diff's inserted line; `ReferenceError: busy is not defined` points at the pre-existing hardening line. The error *message itself* attributes the crash.

Verdict: v0.2.11's insertion *did* introduce an immediate TDZ crash (the diff is genuinely guilty of that), but it also *exposed* the pre-existing free-`busy` bug that the `||` short-circuit and the empty-state guard had kept dormant. Both must be fixed; rolling back only the feature would leave the latent landmine.

## 3. The fix

1. **Move the `imageItem` computation inside the `.map()` callback**, after `record`/`status` are declared, so it is computed per occurrence and only from in-scope bindings:
   ```js
   return h('div', { className }, ...occurrences.map(occurrence => {
     const record = records.get(occurrence.ref);
     const status = record?.status ?? 'missing';
     const imageItem = status !== 'missing'
       ? record?.items.find(item => isImagePath(item.path))
       : undefined;
     ...
   ```
2. **Remove the dangling `busy` reference** from `AttachmentChips` (restore `disabled: (props.input?.phase ?? 'plain') !== 'plain'`), or scope it properly: if chips must reflect upload-busy state, that state must live in (or be threaded into) `AttachmentChips` — e.g. derive it from `records`/props, not reference a sibling component's local. A bare identifier from another function's scope never works at runtime; `node --check` cannot see it.
3. **Hardening patterns the diff should also carry** (cheap insurance in slot components, because a throw costs the whole entry):
   - `record?.items ?? []` — the `imageItem` line already optional-chains `record?.items.find(...)` but a `record` with `items === undefined` would throw at `.find`; coerce with `?? []`. Defensive reads at the data boundary cost one token each and prevent entry-level unmounts.
   - `event.target.closest?.('.remove')` — the click handler assumes `event.target` is always an Element with `closest`; text nodes / detached targets can break that. Optional-chaining the method keeps the handler a no-op instead of a runtime throw.
   - Slot components should fail *small*: anything that can be evaluated defensively (`?? `, `?.`) should be, because the error boundary's unit of failure is the entire slot entry, not the offending sub-element.

## 4. The regression that would have caught this before release

A **data-present render smoke**:

- Mount the dock/chip component (or the whole client plugin against a mock `ctx`) **with at least one occurrence present** — `occurrences: [{ source: SOURCE, occurrenceId: 'a1', ref: 'r1', ... }]` and a matching seeded `records` entry — and with `phase: 'plain'` (so the `|| busy` right operand is actually evaluated).
- Assert the chip element renders: container contains `.chip`, `data-status` set, the remove button present.
- Assert **no error-boundary capture**: wrap the mount in a capturing error boundary (or `jest`/`vitest` + `testing-library` with an error-boundary spy / `window.onerror` sink) and assert zero captures.

The empty-state variant of this test is useless by construction: `if (occurrences.length === 0) return null;` returns before reaching either throwing line, which is exactly how "we had a render test" coexisted with the crash. Both phases (`'plain'` and a locked phase) should be covered so the short-circuit-gated `busy` read cannot hide again.

## 5. Release-process lesson

`node --check` (syntax check only) validates parse-ability, nothing else. For a **lib-only plugin** whose component only fails *at render time with data present*, syntax checking is structurally insufficient: free identifiers, TDZ accesses, and undefined-property reads are all legal syntax and only manifest when React actually evaluates the component with non-empty props. The minimum viable pre-ship check for slot-rendering lib-only plugins is:

1. **A headless render smoke in CI** that mounts every exported slot component with representative *non-empty* props (occurrence present, plain phase), asserting output renders and no error boundary fires — essentially the regression from §4, run as a release gate, not just a postmortem test.
2. Ideally a tiny **integration mount** of the built `lib/client.js` (the artifact actually shipped, not the source) into a stub host with mock slot props, so scope/identifier mistakes in the build output are caught.
3. Treat "console-only error visibility" as a gap: a slot entry that unmounts silently gives users no signal — consider logging boundary catches to a visible channel during canary/release-candidate rollout so "the chips are GONE" reports arrive with a stack trace attached.

**Summary**: v0.2.11's hover-preview diff inserted an `imageItem` computation that reads `status`/`record` outside their `const` scope (TDZ ReferenceError) on every chip-bearing render; the component also carried a pre-existing free `busy` identifier (evaluated only when `phase === 'plain'` via `||` short-circuit, and only when occurrences exist via the early `return null`). Either throw happens during slot-entry render, so the framework's error boundary unmounts the whole dock with only a console trace. Fix: scope/move the computation and delete (or properly thread) `busy`; add `?? []`/`?.` defensive reads; gate releases on a data-present render smoke of the built lib.
