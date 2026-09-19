# S15 · Vanishing Dock Chips: the Silent Slot Crash — Diagnostic Report

Plugin: `@org/dsh-attach-input` · shipped v0.2.11 (hover-preview) · evidence pack: `README.md`, `plugin-dock-chips.js`, `feature.diff`, `user-thread.md`

---

## 1. Exact root cause

**The throwing expression** is in `AttachmentChips` as shipped in v0.2.10 (`plugin-dock-chips.js`):

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???
```

`busy` is a **free identifier** in this scope. It is a `useState` pair declared only inside the *other* component, `AttachButton`:

```js
function AttachButton(props) {
  const [busy, setBusy] = React.useState(false);          // <-- busy lives HERE
```

No module-level `busy` exists in the excerpt, so evaluating `busy` inside `AttachmentChips` raises `ReferenceError: busy is not defined`.

**Why it throws only when a chip renders.** The line sits inside `occurrences.map(...)`, which is reached only after:

```js
const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
if (occurrences.length === 0) return null;
```

An empty dock returns `null` before the throwing line is ever built. So the crash requires the exact state combination **occurrence present AND `phase === 'plain'`** (the left operand `(phase ?? 'plain') !== 'plain'` must be false for `||` to evaluate the right side).

**Why the `||` short-circuit kept it latent through v0.2.10.** `a || b` never evaluates `b` when `a` is truthy. Whenever the composer was in a non-plain phase (locked/submitting), the left operand was true, `busy` was never read, and the chip rendered and its remove button worked — which is exactly the path v0.2.10 users exercised ("v0.2.10 users used the x button fine", maintainer note in `user-thread.md`). Only a *plain-phase render with a chip present* reaches `busy`. The fixture comment on the line ("v0.2.10 hardening pass added the phase guard — and this busy reference") shows the dangling identifier was introduced alongside the guard, and the short-circuit masked it on every path that was actually exercised.

**Why the symptom is "the whole dock vanished", not "the remove button is broken".** The throw happens during render of `AttachmentChips` — before any chip element is produced. Per the maintainer note: "a slot entry that throws during render is caught by the framework's error boundary and unmounted (the error is only visible in the browser console, which users never open)." So the entire slot entry (`AttachmentDock` -> `AttachmentChips`) is unmounted — no chips, no filename, no x button, no error banner. `AttachButton` is a separate slot entry (registered on `input.left`; the dock is on the InputZone occurrences slot), so the + button is untouched — matching mirren's report exactly: paste still worked, the message sent with the image attached, the attach button is still there, "I don't see any error banner in the UI" (`user-thread.md`).

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff (`feature.diff`) is temporally and spatially adjacent — it edits the same `AttachmentChips` function to add hover thumbnails — so "the new feature crashed the slot" is the instinctive read. It is wrong as a first conclusion because the crash is a **pre-existing dangling reference with short-circuit latency**, not a bad new API call.

**The correct bisection is over state combinations, not just commits:**

- *Rollback/re-add bisect:* revert only the v0.2.11 hunks (back to exact v0.2.10 `lib/client.js`) and mount the dock with **one occurrence present at `phase: 'plain'`** — it still throws `ReferenceError: busy is not defined`. Re-add the diff: same throw, same line. The diff is therefore not the necessary cause; the pre-existing `disabled:` line is.

- *Minimal render mount:* mount `AttachmentChips` alone with a stubbed `records` map and one occurrence, and read the stack trace: it points at the `disabled: ... || busy` line inside `occurrences.map` — a line that exists verbatim in shipped v0.2.10 — not at the new `imageItem`/onClick/hover-card additions. (The new `imageItem` line is itself a smell worth fixing — see §3 — but the console stack and the minimal mount attribute the crash to the pre-existing free identifier.)

**Evidence distinguishing "new feature crashed the slot" from "old latent bug first exercised now":**

1. Stack-trace coordinates: the failing frame is the v0.2.10 `disabled:` line, not any hunk the diff introduced.

2. Condition analysis: the crash condition is a state combination (chip present × plain phase) that exists identically in both versions; the new paste-a-screenshot flow is simply the first user flow that renders the dock in that combination — v0.2.10 users interacted with the x button while the composer was in a non-plain phase, where `||` short-circuited before `busy`.

3. Rollback bisect: v0.2.10 code crashes under the same data-present, plain-phase mount.

## 3. The fix and hardening

**Primary fix:** remove the dangling reference — restore the line to:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain',
```

If "disable remove while busy" is genuinely desired, scope it properly: give `AttachmentChips` its own `useState`, or pass busy-ness down through props from the component that owns it — never reference another component's hook state by name.

**Two hardening patterns the diff should also get:**

1. `record?.items ?? []`-style defensive reads. The new line `record?.items.find(...)` optional-chains `record` but not `items`; write `(record?.items ?? []).find(...)` (or `record?.items?.find(...)`). In slot components a missing nested field throws during render, and the error boundary unmounts the **whole entry** — so one absent nested array kills the entire dock, exactly like the `busy` crash. The cost is two characters; the failure it prevents is total-entry unmount.

2. Optional-chained `event.target.closest?.()`. In the new onClick, `event.target` is not guaranteed to be an Element exposing `closest` in every browser/path; `event.target.closest?.('.remove')` degrades to undefined instead of throwing inside a click handler. Same calculus: cheap, and a handler throw is invisible to users (console only) while silently breaking the intended behavior.

Both are cheap insurance precisely because of the slot error-boundary semantics established in §1: any render-time or handler-time throw in a slot component is *silent at the UI level and total at the entry level*, so defensive reads are disproportionately valuable compared to ordinary component code.

## 4. The regression that would have caught this before release

A render smoke that mounts the dock/chip component **WITH an occurrence present and `phase: 'plain'`** — the exact state combination the release flow produces after a paste:

- mount `AttachmentDock` with `props.input` holding one occurrence with `source === SOURCE` and `phase: 'plain'`, plus a stubbed `records` map;
- assert the chip element renders (a .chip node with the .name span and the .remove button exists in the output);
- assert **no error-boundary capture** occurred (the boundary recorded no error / the entry was not unmounted).

Critically, this must be the **data-present** state, not the empty state: with zero occurrences, `AttachmentChips` returns `null` before reaching `disabled: ... || busy`, so an empty-state smoke passes vacuously and would have shipped this bug anyway. (A sibling plain-phase render of `AttachButton` for the `input.left` slot is the symmetric check for the other entry.)

## 5. Release-process lesson: why `node --check` was insufficient

`node --check` validates **syntax only**. `busy` as a free identifier is perfectly legal syntax — `ReferenceError` is a *runtime* resolution failure, and here it fires only when the component renders with data present (occurrences non-empty and plain phase). A lib-only plugin whose components execute exclusively inside the browser page gets zero coverage from a Node syntax check: nothing in the pipeline ever *runs* `AttachmentChips`, so the crash ships. (Relatedly, `no-undef` in ESLint would have flagged `busy` statically — a lint pass is strictly stronger than `node --check` for exactly this class of bug.)

**Minimum viable pre-ship check for slot-rendering lib-only plugins:** in a headless DOM environment, mount every registered slot component with representative non-empty data (at least one occurrence, realistic `input.phase` / `records` values) and fail the check if any mount throws or is captured by the error boundary. That single data-present render smoke would have reproduced the user's report deterministically before release; paired with `no-undef` linting of the client bundle, both the runtime crash and its static cause are caught pre-ship.
