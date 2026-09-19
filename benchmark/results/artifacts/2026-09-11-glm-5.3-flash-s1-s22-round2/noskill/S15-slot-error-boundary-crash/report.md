# S15 · Vanishing Dock Chips — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.2.11 (hover-preview release). Symptom (user-thread.md, user mirren): after pasting a screenshot, the pending-attachment chip above the input no longer appears; the paste itself still sends, the attach button (`+` on `input.left`) is unaffected, and no error banner shows in the UI.

Evidence inspected (all read-only, under the fixture pack):
- `plugin-dock-chips.js` — `AttachmentChips` / `AttachmentDock` / `AttachButton` as shipped in v0.2.10
- `feature.diff` — the v0.2.11 hover-preview diff against `lib/client.js`
- `user-thread.md` — the user report plus the maintainer's own notes

---

## 1. Exact root cause

**The throwing expression is the `disabled` line in `AttachmentChips`**:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // plugin-dock-chips.js:34
```

`busy` is a **free identifier** in `AttachmentChips`. It exists only as a `useState` local of a *different* component — `plugin-dock-chips.js:7` even annotates it: `const [busy, setBusy] = React.useState(false); // <-- busy lives HERE` (inside `AttachButton`). `AttachmentChips` declares no `busy` and receives none via props. Reading an undeclared identifier throws `ReferenceError: busy is not defined` the moment that operand is evaluated. The fixture's own "`// <-- ???`" comment on line 34 marks exactly this dangling reference; the same operand is re-introduced by the v0.2.11 diff at `feature.diff:33` (`+ disabled: ... !== 'plain' || busy,`).

**Why it throws only when a chip renders.** The expression lives inside `occurrences.map(...)` (plugin-dock-chips.js:24–36), which is reached only after the guard at lines 22–23:

```js
const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
if (occurrences.length === 0) return null;
```

With an empty dock the component returns `null` and line 34 is never evaluated — this is why the attach button, the empty dock, and every non-chip render are all fine. Evaluating the right operand also requires the left `||` operand to be false (`phase === 'plain'`, the normal interactive state in which chips are shown and clickable). So the crash fires on exactly one render path: **dock entry + ≥1 occurrence + plain phase** — precisely the state created by pasting a screenshot. It is a render-time crash (the expression is evaluated while building the element props), not a click-handler failure.

**Why the `||` short-circuit kept it latent through v0.2.10.** The dangling reference is only *read* when the left operand is false; whenever the phase guard is true (input locked) the short-circuit skips the `busy` read entirely, and whenever the dock is empty the early `return null` skips the whole map. The bug is therefore path-conditional, not unconditional: it never fires in the empty state, never fires in locked states, and only fires in the one narrow state (chip present, plain phase) that no v0.2.10-era check exercised. The maintainer note in `user-thread.md:10–12` confirms the line predates the release ("In v0.2.10 the same component already had the line `disabled: ... || busy` (added in a hardening pass), and v0.2.10 users used the x button fine") — the reference was shipped earlier and stayed latent because ordinary evaluation paths never reached the operand. (Diagnostic caveat worth recording: a free-identifier read throws every time it is evaluated, so if v0.2.10 truly rendered chips in plain phase without error, the built v0.2.10 bundle must have resolved `busy` from some binding that the v0.2.11 rebuild of `lib/client.js` dropped — the rewrite of that very line at `feature.diff:32–33` is the natural place the binding was lost. Either way, the dangling reference and its fix are the same.)

**Why "the whole dock vanished" rather than "the remove button broke".** Per the maintainer note (`user-thread.md:13–15`): "a slot entry that throws during render is caught by the framework's error boundary and unmounted (the error is only visible in the browser console, which users never open)." `AttachmentDock` is registered as one InputZone slot entry; a throw anywhere in its render unmounts the **entire entry**, not the offending chip or button. So the user sees the whole dock gone, the paste flow still works (attachments still send — `user-thread.md:4–5`), and the attach button survives because it is a *separate* `input.left` slot entry (`plugin-dock-chips.js:1–3`). There is no UI banner because the error is captured console-side only.

**Secondary hazard on the same path (fix in the same change):** the v0.2.11 diff adds, *before/outside* the `map` callback (`feature.diff:9–11`):

```js
const imageItem = status !== 'missing'
  ? record?.items.find(item => isImagePath(item.path))
  : undefined;
```

Both `status` and `record` are declared only *inside* the `map` callback (`feature.diff:13–14`), so `status` here is a second free identifier — the same defect class — and `record?.items.find` also throws `TypeError` when a record exists but has no `items` array (`?.` short-circuits on nullish `record`, not on a missing `items`). Even with `busy` fixed, this line crashes the dock for any image-bearing occurrence.

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff is the most recent change and it *does* touch `AttachmentChips`, so "the new hover-preview feature broke the dock" is the reflexive read. But:

- **The diff's visible additions (imageItem, hover-card, onClick) are not the first thing the user hit.** The crashing `|| busy` operand appears in the *shipped v0.2.10 source* (`plugin-dock-chips.js:34`) and the maintainer's note attributes it to a v0.2.10 hardening pass; the diff merely re-writes/re-adds that line (`feature.diff:32–33`).
- **Correct bisection:** (a) roll the diff's feature hunks back (remove imageItem/onClick/hover-card) while keeping the shipped v0.2.10 component, or re-add the hover-preview changes one hunk at a time; or (b) mount the v0.2.10 `AttachmentChips` in isolation with one occurrence present. Either probe still throws at the `disabled` line — with **zero hover-preview code on the stack** — pinning the fault to the pre-existing line, not the feature.
- **Evidence distinguishing "new feature crashed the slot" from "old latent bug first exercised now":** the stack trace names the `disabled` props expression / `busy`, an identifier absent from the diff's new code paths; `git log -L` on `lib/client.js` shows the `|| busy` line landing in the v0.2.10 hardening commit; and the repro needs only the old component plus one occurrence — no image, no hover, no click. A genuinely new-feature crash would reproduce only with the diff applied and would name diff-introduced identifiers (`imageItem`, `openImageViewer`) in the stack.

## 3. The fix

1. **Remove the dangling reference** — delete `|| busy` from `AttachmentChips`'s `disabled` expression (`plugin-dock-chips.js:34` / `feature.diff:33`). `AttachmentChips` has no busy state and never did; if "disable remove while submitting" is genuinely wanted, thread an explicit `props.busy` (or a shared store value) into the component rather than referencing a sibling component's local.
2. **Scope the diff's preview data correctly** — move the `imageItem` computation *inside* the `occurrences.map` callback, after `const record = ...` / `const status = ...` are declared, and make the read defensive: `const imageItem = status !== 'missing' ? (record?.items ?? []).find(...) : undefined;`
3. **Hardening the diff should also get** (both called for by the brief and both cheap):
   - `record?.items ?? []`-style defensive reads before `.`-chaining into slot/record data — record payloads come from occurrence refs and can be missing or partial (`record?.label ?? occurrence.label` at `plugin-dock-chips.js:28` already models this pattern; `record?.items.find` violates it).
   - optional-chained `event.target.closest?.()` in the new chip `onClick` (`feature.diff:22`) — `event.target` may be a target without `closest` depending on what the browser dispatches.
   - **Why cheap insurance:** in a slot component the blast radius of one thrown expression is the whole slot entry (error-boundary unmount, console-only visibility — §1). A one-token `?.`/`?? []` guard costs nothing per render and converts a total-feature loss into a graceful degraded chip. The empty-dock early return means these lines run only when real user data is present — exactly when a crash is user-visible.

## 4. The regression that would have caught this before release

A **data-present render smoke** of the slot entry:

- Mount `AttachmentDock` (or `AttachmentChips(props, 'dock')`) via a test renderer with `props.input.occurrences` containing **one occurrence** for `SOURCE` and a matching entry in `records` — *not* the empty state, because `if (occurrences.length === 0) return null;` (`plugin-dock-chips.js:23`) returns before line 34 is ever evaluated; an empty-dock smoke passes forever while the crash ships.
- Assert the chip element renders (chip div with the filename and the `x` remove button) **and that no error boundary captured the render** — assert on rendered output plus absence of an error-boundary fallback/unmount, mirroring the slot error-boundary semantics from the maintainer note. A parse-only gate or a mount-without-data test gives a green light while the user-visible path is broken.
- The same smoke with an image-bearing record additionally covers the diff's `imageItem` path and would have caught the `status` free identifier before v0.2.11 shipped.

## 5. Release-process lesson: why `node --check` was insufficient

`node --check` (and any TypeScript parse) validates **syntax** only. `busy` and `status` are syntactically valid identifiers; their defect is semantic — unresolved at parse time, throwing `ReferenceError` only when **executed**. A lib-only plugin whose components run exclusively in the browser, rendering only when slot data is present, therefore passes every parse-level gate and still crashes on the user's first paste: no local unit test executes the component, and the browser console is the only place the error surfaces (`user-thread.md:13–15`), which users never open.

**Minimum viable pre-ship check for slot-rendering lib-only plugins:**

1. `eslint` with `no-undef` (or equivalent static undefined-reference analysis) on `lib/client.js` — this catches *both* `busy` and `status` at lint time, before any runtime cost.
2. A headless render smoke (React test renderer or jsdom) that mounts **every registered slot entry component with representative data present** (≥1 occurrence, a record, and a non-plain phase case) and asserts the entry rendered and no error boundary fired. Empty-state mounts are necessary but not sufficient — see §4.
3. Wire both into the pre-publish script so "it parsed" can never again be mistaken for "it renders".
