# S15 · Vanishing Dock Chips — Diagnostic Report (@org/dsh-attach-input v0.2.11)

Evidence base: fixture `plugin-dock-chips.js` (v0.2.10 lib/client.js excerpt), `feature.diff` (v0.2.11 hover-preview diff), `user-thread.md` (user mirren's report + maintainer note), `README.md`.

---

## 1. Exact root cause

### The throwing expression

In `feature.diff`, the hover-preview block was added at the **body scope of `AttachmentChips`, before and outside the `occurrences.map(...)` callback**:

```js
const imageItem = status !== 'missing'
  ? record?.items.find(item => isImagePath(item.path))
  : undefined;
```

But in the shipped v0.2.10 component (`plugin-dock-chips.js`), `status` and `record` are local `const`s declared **inside the map callback**:

```js
return h('div', { className }, ...occurrences.map(occurrence => {
  const record = records.get(occurrence.ref);
  const status = record?.status ?? 'missing';
  ...
}));
```

The hoisted line therefore references two **free identifiers**. The very first one evaluated is `status` in the ternary condition — and immediately after, `record?.items.find(...)`. Optional chaining (`record?.items`) does **not** protect against an *undeclared* variable: `record?` still throws `ReferenceError: record is not defined` when `record` is not in scope at all. So the first chip render executes `ReferenceError: status is not defined` / `record is not defined` at the top of `AttachmentChips`'s body, before a single element is created.

### Why it throws only when a chip renders

`AttachmentChips` opens with:

```js
const occurrences = (props.input?.occurrences ?? []).filter(item => item.source === SOURCE);
if (occurrences.length === 0) return null;
```

The empty dock early-returns `null` **before** the hoisted `imageItem` block. The throwing lines are reachable only when at least one occurrence with `source === SOURCE` exists — exactly the paste-a-screenshot case. With no attachments, v0.2.11 renders null and never touches the free identifiers; that is why the feature diff could pass any empty-state check.

### Why the `||` short-circuit kept it latent through v0.2.10

The v0.2.10 file contains a *second* dangling reference planted by an earlier "hardening pass":

```js
// v0.2.10 hardening pass added the phase guard — and this busy reference:
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???
```

`busy` is a `useState` value that lives in `AttachButton` (`const [busy, setBusy] = React.useState(false);` — the fixture even annotates `// <-- busy lives HERE` in `AttachButton`), not in `AttachmentChips`. In JS, `A || B` never evaluates `B` when `A` is truthy. During the chip-render path in v0.2.10, the left operand `(props.input?.phase ?? 'plain') !== 'plain'` was truthy (the composer phase is locked/non-`'plain'` while an attachment is pending), so `busy` was **never evaluated** and its `ReferenceError` stayed masked. Every v0.2.10 render that produced a chip short-circuited past the landmine; the latent bug shipped and sat inert. The v0.2.11 diff then moved a *different* free-identifier read (`record`/`status`) into an unconditional position where no operator shields it — and the crash fires on the first chip render.

### Why the symptom is "the whole dock vanished", not "the remove button is broken"

The plugin registers the dock through the **InputZone slot**. Per the maintainer note in `user-thread.md`: "a slot entry that throws during render is caught by the framework's error boundary and unmounted (the error is only visible in the browser console, which users never open)."

Because the throw happens at the **top of `AttachmentChips`'s body** — before it returns any element — the component fails as a whole, not in one child. The slot-level error boundary therefore unmounts the *entire dock entry*: no chip, no filename, no `x` button, no hover card. There is no UI error banner (the boundary consumes it into the console), which matches mirren's report: "the little chip ... never showed up ... I don't see any error banner in the UI."

The attach button is unaffected because it is a **separate slot entry** (`input.left` per the fixture header comment: "renders into two composer slots: the attach button (input.left) and the pending-attachment dock"), in its own error-boundary scope. The paste itself works because acceptance is handled by the plugin's input handling (`props.add`/`accept`), not by the dock renderer — the message "sent with the image attached" while the chip never rendered.

---

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff visibly touches `AttachmentChips`, and the crash starts with v0.2.11 — "new feature crashed the slot" is the seductive read. But the diff's own additions are internally coherent *for the scope it assumes*; the failure is that the assumed scope never existed. The correct bisection:

- **Rollback / re-add bisect on the diff hunks.** Revert individual hunks of `feature.diff` one at a time (or re-apply them onto a fresh v0.2.10 base). The hover-card `h('div', { className: 'hover-card' }, ...)` hunk and the `onClick` hunk do **not** fix the crash; reverting the hoisted `imageItem` block does. That isolates the failing line to the hoist, not the feature.
- **Minimal render mount.** Mount `AttachmentDock` alone with one occurrence present, first on the pristine v0.2.10 source — it renders (the `||` short-circuit masks `busy`) — then apply only the `imageItem` hoist: it throws `ReferenceError` on the first chip. The minimal repro pins the throw to the pre-existing scoping mistake being *newly exercised*, not to the hover-preview logic itself.
- **Distinguishing evidence, "new feature crash" vs "old latent bug first exercised":**
  - The error class is `ReferenceError` on a plain identifier (`status`/`record`), not a TypeError on feature data (`items.find is not a function`, bad blob URL, etc.). A new feature's bugs fail on *data*; this fails on *scope*, before any of the new feature's data is touched.
  - The v0.2.10 source already contains the same species of defect — `|| busy` with `busy` undeclared in this component (fixture comment: `// <-- ???`). One confirmed dangling reference in shipped code makes "the diff introduced carelessness" the wrong prior; the diff merely relocated an unscoped read to an unconditional line.
  - The empty-dock path (the only path most smoke testing exercises) never executes either the v0.2.10 `busy` read or the v0.2.11 hoist — consistent with the bug surviving v0.2.10's usage and escaping the empty-state checks.

Conclusion: the diff is the *trigger* (it first evaluates an out-of-scope read unconditionally), the latent defect class is *pre-existing* (v0.2.10's masked `busy` proves it), and v0.2.11 just removed the accident of scope that hid it.

---

## 3. The fix

**Primary fix — remove the dangling references or scope them properly:**

1. Move the `imageItem` computation **inside the map callback**, where `record` and `status` actually exist:
   ```js
   ...occurrences.map(occurrence => {
     const record = records.get(occurrence.ref);
     const status = record?.status ?? 'missing';
     const items = record?.items ?? [];
     const imageItem = status !== 'missing'
       ? items.find(item => isImagePath(item.path))
       : undefined;
     return h('div', { className: 'chip', /* hover-card props using imageItem */ }, ...);
   })
   ```
   (Or, if a single `imageItem` for the whole dock is genuinely intended, derive it from the first matching occurrence's record explicitly — but it must read from an in-scope `record`.)
2. Delete the `|| busy` from the remove button's `disabled` — `busy` does not exist in `AttachmentChips`. If a busy state is truly wanted there, it must be introduced as real state/props in this component, not borrowed by name from `AttachButton`.

**Two hardening patterns the diff should also get, and why they are cheap insurance:**

- **Defensive collection read: `record?.items ?? []` before `.find(...)`.** Optional chaining stops at `record`; if `record` exists but `items` is `undefined`/`null`, `record?.items.find` still throws `TypeError`. Slot components render on *every* input mutation with externally shaped occurrence/record data the plugin does not fully control; one malformed record should degrade a chip to `data-status: 'missing'` (which the component already models: `record?.status ?? 'missing'`), not unmount the whole dock.
- **Optional-chained DOM query: `event.target.closest?.()`.** In the new `onClick`, `event.target` may be a text node, a shadow/portal boundary case, or otherwise lack `closest` in exotic embedding; `event.target.closest?.('.remove')` degrades to "treat as chip click" instead of throwing inside a handler. Same insurance logic: a slot-component throw is catastrophically visible (whole entry unmounts, console-only) while the defensive form costs one character.

Both are cheap because they convert worst-case "slot entry silently vanishes with an error only in devtools" into best-case "one chip renders slightly plainer" — an asymmetric trade that strongly favors the guard in code living behind a slot error boundary.

---

## 4. The regression that would have caught this before release

A **render smoke that mounts the dock WITH an occurrence present** — the data-present path, not the empty state. This is essential because the empty dock returns `null` at `if (occurrences.length === 0) return null;` *before reaching the throwing line*; any empty-state-only test passes on both v0.2.10 and v0.2.11.

Shape of the test (host or jsdom/react-test-renderer style):

- Mount `AttachmentDock` (or `AttachmentChips`) with `props.input` containing at least one `occurrences` entry with `source === SOURCE` and a matching record in `records` (including an image-path item to exercise the new hover branch, and a locked phase to exercise the `disabled` guard).
- Assert the chip element actually renders: a `.chip` node exists with the expected `.name` text and an `.remove` button (and, for v0.2.11, the `.hover-card`/[`data-image`] attribute).
- Assert **no error-boundary capture**: spy on `console.error` (React logs boundary catches there) and/or mount under a test error boundary and assert it was never invoked; the component tree still contains the dock node.

Had this existed, v0.2.11 CI would have failed immediately with `ReferenceError: status is not defined` at the hoisted `imageItem` line — and a v0.2.10-era version with a record present and an unlocked phase would even have caught the masked `busy` landmine.

---

## 5. The release-process lesson

**Why `node --check` was insufficient.** `node --check` performs a *parse/syntax* pass only. A free identifier (`busy`, `record`, `status`) is perfectly legal syntax — it resolves at runtime as a variable lookup, and only throws `ReferenceError` when that line actually executes. This plugin is **lib-only plain JavaScript** (no TypeScript compiler, no bundler type pass), and the component is a Client slot renderer: its code runs only when the browser renders the slot **with data present**. So the entire shipped validation surface — syntax check, empty-state eyeballing, manual smoke without a paste — never executes line in question. The failure mode is also maximally quiet in production: the slot error boundary swallows the throw into the browser console, so no user report contains an error message, only "the chip is gone".

**Minimum viable pre-ship check for slot-rendering lib-only plugins:**

1. A **headless render smoke per registered slot component** (jsdom or react-test-renderer in CI) that mounts each one with **representative non-empty slot data** — at least one occurrence/record present, covering each new UI branch (here: an image item to hit the hover/onClick branch, plus a locked phase).
2. The smoke **fails on any console.error or error-boundary capture**, not just on a thrown exception propagating out — because in production the boundary is exactly what hides the throw.
3. A **static lint gate for free identifiers** (`no-undef` via ESLint, which a syntax check cannot do) — this single rule flags `busy`, `record`, and `status` in both versions at lint time, zero runtime needed.

That trio (lint for no-undef + data-present render smoke + boundary-capture assertion) converts this entire bug class from "user-reported vanishing UI after release" into a red CI line before the tag is cut.
