# S15 · Vanishing Dock Chips: the Silent Slot Crash — Diagnostic Report

Plugin: `@org/dsh-attach-input`, v0.2.11 ("hover-preview" release). Evidence pack (read-only): `fixture/README.md`, `fixture/plugin-dock-chips.js` (v0.2.10 shipped `lib/client.js` excerpt), `fixture/feature.diff` (v0.2.11 diff), `fixture/user-thread.md` (user report from mirren). Mode A (read-only inspect) per the plugin-upgrade skill; nothing in the fixture was modified.

## 1. Exact root cause

**Throwing expression** — in `AttachmentChips` (v0.2.10 source, `fixture/plugin-dock-chips.js`), the remove button's props:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???
```

`busy` is a dangling identifier: it is a `React.useState` value declared **only in the other component**, `AttachButton` ("busy lives HERE" comment on `const [busy, setBusy] = React.useState(false);`). `AttachmentChips` is a separate function whose props contain no `busy`; evaluating the identifier raises `ReferenceError: busy is not defined` at render time.

**Why it throws only when a chip renders** — the throw is on the per-chip button line, inside the `occurrences.map(...)` callback, which executes only after the early return:

```js
const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
if (occurrences.length === 0) return null;
```

With zero pending occurrences the function returns `null` before reaching the map, so the dangling reference is never evaluated. The moment one chip must render (the user pastes a screenshot → one InputZone occurrence appears), the map body runs and `busy` throws.

**Why the `||` short-circuit kept it latent through v0.2.10** — it did not, by itself. `a || b` evaluates `b` only when `a` is falsy, so in a locked phase (`phase !== 'plain'`, left operand truthy) `busy` is genuinely skipped; but in the normal `'plain'` phase — exactly the user's state — the right operand is evaluated, and evaluating the identifier `busy` at all throws. The real latency is **data-latency**: the line was added in the v0.2.10 "hardening pass" (in-source comment: "v0.2.10 hardening pass added the phase guard — and this busy reference") and no v0.2.10 render reached it with a chip present, because the empty dock returns `null` first. The short-circuit added a *phase* condition on top of the *data* condition (crash requires ≥1 occurrence AND `phase === 'plain'`), deepening the mask; the primary mask is the empty-state early return.

**Why the symptom is "the whole dock vanished" rather than "the remove button is broken"** — the plugin registers the dock through the **InputZone slot**; per the maintainer note in `user-thread.md`, "a slot entry that throws during render is caught by the framework's error boundary and unmounted (the error is only visible in the browser console, which users never open)". React error boundaries capture at the component level, not the element level: the `ReferenceError` thrown while rendering `AttachmentChips`/`AttachmentDock` unmounts the entire slot entry — the whole dock container and every chip — not just the malformed button. There is no UI error banner, so the only trace is a browser-console error users never see. The attach button survives because `AttachButton` renders into the separate `input.left` slot and is a different component whose own `busy` is in scope — it never throws.

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff (`fixture/feature.diff`) visibly touched `AttachmentChips`, and the regression surfaced in the very release that touched it — the natural-but-wrong first conclusion is "the hover-preview feature crashed the slot." Three things correct it:

- **The crash line is not in the diff.** `disabled: ... || busy` exists verbatim in the v0.2.10 shipped source (`fixture/plugin-dock-chips.js`), annotated as added by the v0.2.10 hardening pass; the v0.2.11 diff's `disabled` change is only `... || busy` carried along unchanged. The genuinely new code (`imageItem`, `record?.items.find`, the new `onClick`, the hover card) never references the bare `busy` identifier.
- **Correct bisection**: (a) rollback/re-add bisect — take v0.2.11 and revert *only* the hardening-pass `|| busy` (or take v0.2.10 and re-apply the whole hover-preview diff): the dock renders with chips, proving the feature innocent and the pre-existing line guilty; conversely, unmodified v0.2.10 crashes the moment any chip renders. (b) a minimal render mount — mount `AttachmentDock` in isolation with one occurrence present, on either version: it throws `ReferenceError: busy is not defined` on v0.2.10 too, dating the bug to the earlier release.
- **Distinguishing evidence, "new feature crashed the slot" vs "old latent bug first exercised now"**: the faulting identifier resolves to state in a *different* component (feature-independent); the user's failing scenario needs only paste → chip, no hover or click of the new preview (the new `onClick` and hover card never execute); the maintainer note records v0.2.10 users using the x button "fine" — consistent with the empty-state early return masking the line until the first data-present render in the wild, plausibly triggered by the release drawing users to paste images. "First exercised now" is exactly how a data-latent bug presents after a feature release.

## 3. The fix

Remove the dangling reference — `AttachmentChips` has no `busy` state of its own, and the correct disabled semantics there are the phase guard alone:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain',
```

(If the dock genuinely needs busy suppression, scope it properly: own the state locally with `const [busy, setBusy] = React.useState(false);` inside `AttachmentChips`, or receive an explicit `props.busy` — never a cross-component bare identifier, which `no-undef`/typecheck would also flag statically.) The diff should additionally get two hardening patterns: `record?.items?.find(...) ?? undefined` (a `record?.items ?? []`-style defensive read, so a record without an items list cannot throw either) and optional-chained `event.target.closest?.()` in the new `onClick` (guards targets lacking `closest`). Both are cheap insurance in slot components because a render throw costs the **entire slot entry** — whole-dock unmount with a console-only error — while the guard costs one token; slot components render late inside a live page whose inputs the author does not fully control.

## 4. The regression that would have caught this before release

A render smoke that mounts the dock/chip component **with an occurrence present** — not the empty state, because the empty dock returns `null` at `if (occurrences.length === 0) return null;` and never reaches the throwing line (an empty-state smoke would pass to this day). Concretely: render `AttachmentDock` with `props.input` carrying one occurrence `{ ref, source: SOURCE, occurrenceId }` plus a matching `records` entry, then assert (a) a `.chip` element renders with the filename label and the `x` remove button, and (b) **no error-boundary capture occurred** — the boundary did not swallow a render throw and unmount the entry. That single data-present mount fires `busy` immediately and fails the build pre-ship. The maintainer note confirms the gap: "We shipped without a render smoke that mounts the dock with a chip present."

## 5. Release-process lesson

`node --check` performs a **syntax check only**: it parses and validates grammar, never executes, so a free identifier that raises `ReferenceError` at runtime passes cleanly (`busy` is a syntactically valid expression). For a lib-only plugin with no bundler or type checker in the ship path, there is no other static net — and the component only fails at render time **with data present**, which nothing shipped exercised. Minimum viable pre-ship check for slot-rendering lib-only plugins: one headless render smoke per slot-entry component in its **data-present** state (mount with realistic slot props, assert expected elements render and no error boundary captured), run under the module loader the host actually uses — plus a lint/typecheck pass, since `no-undef`/tsc would have flagged the dangling `busy` statically at near-zero cost. A syntax gate answers "does it parse", never "does it render".

## Summary

| Item | Finding |
|---|---|
| Root cause | `busy` (state of `AttachButton`) referenced in `AttachmentChips`' remove-button `disabled:` line → `ReferenceError` on every chip render in `'plain'` phase |
| Latency | Empty dock returns `null` before the map; the `||` adds a phase condition (`'plain'` only); first data-present render was post-release |
| Symptom | InputZone slot error boundary unmounts the whole dock entry; error visible only in the browser console |
| Bisection | Revert only `|| busy` while keeping v0.2.11 features → renders; minimal data-present mount crashes v0.2.10 too |
| Fix | Delete `|| busy` (or own `busy` in `AttachmentChips`); add `record?.items ?? []` and `event.target.closest?.()` hardening |
| Regression | Data-present render smoke asserting the chip renders with no error-boundary capture |
| Process | `node --check` is parse-only; require a headless data-present render smoke (plus lint/typecheck) for lib-only slot plugins |
