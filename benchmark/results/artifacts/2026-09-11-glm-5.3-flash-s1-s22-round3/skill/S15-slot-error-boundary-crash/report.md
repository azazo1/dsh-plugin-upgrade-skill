# S15 · Vanishing Dock Chips — Diagnostic Report

**Plugin:** `@org/dsh-attach-input` v0.2.11 · **Symptom:** pending-attachment chip/dock disappears after pasting a screenshot; paste still works; attach button unaffected (user thread `user-thread.md`, user *mirren*).

Evidence examined (read-only fixture pack): `plugin-dock-chips.js` (v0.2.10 shipped component excerpt), `feature.diff` (v0.2.11 hover-preview diff), `user-thread.md`, `README.md`.

---

## 1. Exact root cause

### The throwing expression

In `plugin-dock-chips.js`, line 34 of the remove button inside `AttachmentChips`:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???
```

`busy` is a **free identifier in this function**. It is declared with `React.useState(false)` **only inside `AttachButton`** (`plugin-dock-chips.js` line 7, with the in-file comment `// <-- busy lives HERE`). `AttachmentChips` receives only `(props, className)` (line 21) — there is no `busy` binding anywhere in its scope, no module-level `busy`, and no import. The v0.2.11 diff re-adds this exact line as a `+` change (`feature.diff`: `+        disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,`), so the dangling reference ships in v0.2.11 too.

Evaluating it raises `ReferenceError: busy is not defined`.

### Why it throws only when a chip renders

Two guards sit before the line:

1. `AttachmentChips` line 23: `if (occurrences.length === 0) return null;` — the empty dock (no attachment occurrences for `SOURCE`) returns **before** any JSX is built, so the line is never evaluated in the empty state. The line is only reached when at least one occurrence exists, i.e., exactly when a chip is about to render.
2. `AttachmentDock` (line 40) is the slot entry registered for the InputZone dock; it renders only when the slot framework calls it during a composer render.

So the crash path is: paste creates an occurrence → slot re-render → `AttachmentDock` → `AttachmentChips` with `occurrences.length > 0` → `h('div', { className }, ...occurrences.map(...))` → the remove-button `disabled` expression → `ReferenceError`. This matches the user report: the crash happens specifically on paste, the first action that creates an occurrence.

### Why the `||` short-circuit kept it latent through v0.2.10

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy
```

`||` evaluates left-to-right and never touches the right operand when the left one is truthy. Whenever the dock rendered with chips present in v0.2.10, the composer was in a non-`plain` phase (composing/locked, which is the only state in which pending attachment occurrences exist), so `(props.input?.phase ?? 'plain') !== 'plain'` was `true`, the `||` short-circuited, and `busy` was **never read**. The maintainer's note in `user-thread.md` confirms the line was already present in v0.2.10 ("added in a hardening pass") and that "v0.2.10 users used the x button fine". The bug was real but unreachable-by-luck: it needed a render with chips present **and** `phase === 'plain'` — a combination v0.2.10 traffic never produced (or never noticed, since the same error boundary would have eaten it).

(The v0.2.11 diff adds a second latent free-identifier hazard of the same class — its pre-map block references `status` and `record`, which are declared only *inside* the `occurrences.map` callback, and `record?.items.find(...)` would also throw on `record == null` since `record?.items` is `undefined` — but the first crash on any data-present render is the `busy` reference in the shipped `disabled` line.)

### Why the symptom is "the whole dock vanished", not "the remove button is broken"

The maintainer note in `user-thread.md` states the mechanism directly: "The plugin registers the dock through the InputZone slot; a slot entry that throws during render is caught by the framework's error boundary and unmounted (the error is only visible in the browser console, which users never open)."

The throw happens **during the render of the entire slot entry** (`AttachmentDock`), before any DOM is committed — not in the remove button's click handler. React-style slot error boundaries operate at the entry level: one render throw inside the component tree unmounts the whole entry registered in the slot, so every chip (filename span, hover card, and x button together) disappears from the composer. There is no partial render to leave a "broken button" behind. Consequences visible in the user thread:

- The dock is gone entirely ("the little chip … never showed up").
- Paste still works — that is the host's attachment pipeline, not the plugin's slot UI ("the message sent with the image attached").
- The attach button is unaffected — it is a **separate slot entry** (`input.left` → `AttachButton`, per the comment at the top of `plugin-dock-chips.js`), so its error boundary state is untouched.
- No error banner — the error exists only in the browser console, which end users never open.

---

## 2. Why the v0.2.11 diff is the wrong first conclusion

The diff is a tempting suspect: it is the only recent change, it touches the exact component that vanished (`AttachmentChips`), and the crash surfaced in the hover-preview release. But:

- The throwing expression (`|| busy` in `disabled`) is **not new**. The maintainer's own note says the line existed in v0.2.10 ("added in a hardening pass"), and `plugin-dock-chips.js` (the v0.2.10 snapshot) shows it at line 34 flagged `// <-- ???`, with `// <-- busy lives HERE` at line 7 pointing at `AttachButton`'s unrelated state.
- The user-visible failure is not hover-preview behavior failing (no broken thumbnail, no viewer crash) — the entry never renders at all, which is a render-time identifier resolution failure, not a feature-logic failure.

### The correct bisection

1. **Rollback/re-add bisect:** take the shipped v0.2.10 `lib/client.js`, revert the v0.2.11 diff hunks — but keep the pre-existing `disabled: … || busy` line (it is a v0.2.10 line, so a faithful revert keeps it) — and mount `AttachmentDock` with an occurrence present and `phase: 'plain'`. It still throws `ReferenceError: busy is not defined`. That proves the culprit is the pre-existing line, not the hover-preview additions.
2. **Minimal render mount:** mount `AttachmentChips`/`AttachmentDock` in isolation with a stub `records` map containing one occurrence, and delete hunks of the diff one at a time. Removing *all* of the hover-preview code does not stop the crash; neutralizing only the `disabled` expression does. The minimal failing surface is the `|| busy` line.

### Evidence distinguishing "new feature crashed the slot" from "old latent bug first exercised now"

- **Provenance of the throwing line:** `plugin-dock-chips.js` line 34 (labeled v0.2.10 "as shipped") already contains `|| busy`; `feature.diff` merely re-states it. A new-feature crash would trace to a `+` line unique to the diff.
- **Stack-frame location:** the `ReferenceError` frame points at the `disabled` prop of the remove button, not at `imageItem`, `openImageViewer`, `objectUrlOf`, or any hover-preview helper.
- **Short-circuit history:** v0.2.10 was saved only by `||` short-circuiting on `phase !== 'plain'`; the release that changed *when the right operand gets evaluated* (a render reaching it with `phase === 'plain'`) is the trigger, not the code that introduced the hazard. "First exercised now" ≠ "introduced now".
- **Empty-state pass:** v0.2.10 mounts fine with no occurrences (line 23 returns `null` first) — the latent line is data-dependent, the signature of a pre-existing bug awaiting its data combination.

---

## 3. The fix

### Primary fix — remove the dangling reference

Delete `|| busy` from `AttachmentChips`'s remove button:

```js
disabled: (props.input?.phase ?? 'plain') !== 'plain',
```

The v0.2.10 "hardening pass" evidently copy-pasted the `disabled` expression from `AttachButton` (where `busy` legitimately disables the `+` button during accept) without noticing `busy` does not exist in `AttachmentChips`. Alternatives if a busy state is genuinely wanted: scope it properly — declare `const [busy, setBusy] = React.useState(false);` in `AttachmentChips`/`AttachmentDock` with its own accept flow, or lift the busy state to a shared hook/context both components consume. What must not happen is referencing another component's local state.

### Two hardening patterns the diff should also get

1. **Defensive reads of optional records:** the diff's `record?.items.find(item => isImagePath(item.path))` uses optional chaining on `record` but not on `items` — if a record exists with `items === undefined`, `.find` throws and kills the whole slot entry again. Write `const imageItem = status !== 'missing' ? (record?.items ?? []).find(...) : undefined;` — `(record?.items ?? [])` degrades to "no image" instead of unmounting the dock.
2. **Optional-chained DOM lookup:** `event.target.closest('.remove')` assumes `event.target` is an `Element`. A click on a text node, an SVG element in some engines, or a synthetic target can lack `.closest`. Write `event.target.closest?.('.remove') !== null` (ideally with an `event.target instanceof Element` guard). If it throws inside the chip's `onClick`, the error boundary again unmounts the entry — the same "whole dock vanishes" failure mode.

**Why cheap insurance:** in slot components, *any* render- or handler-time throw is amplified by the framework's error boundary from "one expression failed" to "the entire slot entry is unmounted and the error is invisible to end users" (console-only, per the maintainer note). Each of these guards costs one token pair (`?.` / `?? []`) and converts a slot-unmounting crash into a graceful empty value. In a boundary-protected surface, a thrown error has the worst possible blast-radius-to-likelihood ratio, so defensive reads are disproportionately cheap.

---

## 4. The regression that would have caught this before release

A **data-present render smoke** for the slot entry — not the empty state:

```js
test('AttachmentDock renders a chip when an occurrence is present', () => {
  records.set('ref-1', { status: 'ready', label: 'screenshot.png', items: [] });
  const props = { input: { phase: 'plain', occurrences: [
    { source: SOURCE, ref: 'ref-1', occurrenceId: 'occ-1', label: 'screenshot.png' },
  ] }, add: () => {}, remove: () => {} };
  const consoleError = jest.spyOn(console, 'error').mockImplementation(() => {});
  const el = h(AttachmentDock, props);           // mount through a renderer (jsdom)
  render(el);
  expect(document.querySelector('.dock .chip .name')).toBeTruthy(); // chip renders
  expect(document.querySelector('.dock .chip .remove')).toBeTruthy();
  expect(consoleError).not.toHaveBeenCalled();   // no error-boundary capture
  consoleError.mockRestore();
});
```

Requirements, per the brief:

- **WITH an occurrence present.** The empty dock is worthless as a regression: line 23 (`if (occurrences.length === 0) return null;`) returns before the throwing line, so an empty-state smoke would have stayed green through v0.2.10 **and** v0.2.11. The crash needs `occurrences.length > 0` *and* a record in `records` so the `record?.` reads resolve.
- **Assert the chip element renders** (`.chip`, its `.name` span, and the `.remove` button), not just "did not throw".
- **Assert no error-boundary capture** — spy on console.error / the error boundary's componentDidCatch so a swallowed render error fails the test even though the test process itself would not crash. Without this assertion, an error boundary can eat the throw and the test still passes with an empty slot.
- Include the trigger combination: occurrence present **and** `phase: 'plain'` — the exact state pair the `||` short-circuit had been hiding.
- The maintainer note confirms this test did not exist: "We shipped without a render smoke that mounts the dock with a chip present."

---

## 5. The release-process lesson

### Why `node --check` was insufficient

`node --check` performs a **parse-time syntax check only**. It verifies the file tokenizes and parses; it never executes, so it cannot catch:

- **Free identifiers.** `busy` in `AttachmentChips` is syntactically legal — identifier resolution is a runtime concern. `ReferenceError: busy is not defined` is invisible to a parser.
- **Render-time evaluation.** The component only fails when the slot framework actually calls it with data (`occurrences.length > 0`, `phase === 'plain'`). A lib-only client plugin ships code that runs exclusively inside the host's browser page, mounted under an error boundary — so in normal use there is no stack trace, no crash log, and no UI banner; the failure is a silent vanishing UI plus a console line the maintainer must reproduce themselves.

For a plugin whose entire product surface is "JSX built at render time from host data", parse checks validate the one failure class (syntax) that was never at risk.

### Minimum viable pre-ship check for slot-rendering lib-only plugins

1. **Mount every slot-registered component in a headless DOM (jsdom) with representative data** — at minimum the populated state (occurrence present, record present, both `phase` values 'plain' and non-'plain'), not just the empty state. Assert rendered output exists and **no console.error/error-boundary capture occurred** (item 4's smoke).
2. **Gate on uncaught render errors:** run the mount under a renderer that surfaces render throws (or an error boundary that fails the test), so a `ReferenceError` in any prop expression blocks the release.
3. Bundle this as a `prepublishOnly`/CI step so it cannot be skipped — for slot components, "it parses" must mean "it renders with data and the boundary stays silent", because the error boundary guarantees the worst failures are the ones users will never report.
