# S15 · Vanishing Dock Chips — the Silent Slot Crash

**Task:** S15-slot-error-boundary-crash (read-only diagnosis)
**Plugin:** `@org/dsh-attach-input` v0.2.10 → v0.2.11 (community Web plugin, lib-only, no build/test infra)
**Evidence:** fixture pack (`plugin-dock-chips.js`, `feature.diff`, `user-thread.md`) — inspected read-only; nothing in the fixture or benchmark repo was modified.
**Mode:** plugin-upgrade skill, Mode A (inspect/diagnose) — no configuration, dependency, or source writes performed.

---

## 1. Exact root cause

### The throwing expression

```js
// AttachmentChips, shipped in v0.2.10 (hardening pass):
disabled: (props.input?.phase ?? 'plain') !== 'plain' || busy,   // <-- ???
```

`busy` is **not in scope in `AttachmentChips`**. It is a `useState` declared inside the
sibling component `AttachButton` (the fixture marks it: `// <-- busy lives HERE`). State
variables of one function component are locals of that function's render closure; they are
not module-scope and not props. So inside `AttachmentChips`, `busy` is a **free
identifier**. The moment JavaScript evaluates that right operand it throws:

```
ReferenceError: busy is not defined
```

thrown synchronously during `AttachmentChips`'s render, inside `AttachmentDock`'s render,
inside the InputZone slot entry.

A second, related scope defect ships in the v0.2.11 diff itself:

```js
const imageItem = status !== 'missing'
  ? record?.items.find(item => isImagePath(item.path))
  : undefined;
```

This line was hoisted **above** the `occurrences.map(...)` callback, but `status` and
`record` are `const`s declared **inside** that callback. At the hoisted position they are
free identifiers too, so this line can also throw `ReferenceError: status is not defined`.
Both are out-of-scope identifier errors in the same component; whichever line executes
first takes the slot down. The maintained narrative (and the maintainer's own note) points
at the **pre-existing `busy` line** as the root cause; the hoisted `imageItem` line is at
minimum a second landmine that must be fixed in the same pass.

### Why it throws only when a chip renders

The first statement of `AttachmentChips` is:

```js
if (occurrences.length === 0) return null;
```

With no pending attachments (the vast majority of renders — the dock sits above the input
on every turn), the component returns `null` **before reaching any throwing line**. The
crash requires at least one occurrence with `source === SOURCE` — i.e., exactly the
"paste a screenshot" path the user reported. That is also why the empty dock, the attach
button, and the paste pipeline all kept working.

### Why the `||` short-circuit kept it latent through v0.2.10

`A || busy` evaluates `busy` **only when `A` is falsy** — i.e., only when the composer's
phase is exactly `'plain'`. The hardening pass added the phase guard precisely because
pending chips render while the input is in a **non-plain (locked/attaching)** phase; in
every v0.2.10 render that shipped to users, the left operand was `true`, the `||`
short-circuited, and the right operand was dead code. A free identifier only throws when
*evaluated*, so `busy` sat latent like an unpulled pin. v0.2.11 first shipped a flow that
reaches the throwing code with occurrences present in a context that evaluates the full
expression (and additionally hoisted the preview computation out of the guard of the map
callback), so the pin was finally pulled on real user data.

### Why the symptom is "the whole dock vanished", not "the remove button is broken"

The dock registers through the **InputZone slot**. A slot entry that throws during render
is caught by the framework's **slot-level error boundary**, which **unmounts the entire
entry** — there is no per-button degradation; React error boundaries discard the whole
subtree that threw. So the user sees no chip, no filename, no dock at all: the entry is
simply gone. The error itself surfaces **only in the browser console** (which users never
open), and no in-UI error banner appears — hence "silent". The attach button (`+`) is a
**separate slot entry** (`input.left`) with its own boundary, and it never throws, so it
survives untouched. The paste itself is handled host-side by the attach pipeline, not by
this component, so the image still attaches and sends.

## 2. Why blaming the v0.2.11 diff is the wrong first conclusion

The diff *looks* guilty: it touched the same component, in the same release, right before
the regression report. But two facts break that inference:

1. **The diff's context line contradicts the shipped v0.2.10 source.** The diff's `-` line
   shows `disabled: (props.input?.phase ?? 'plain') !== 'plain',` (no `busy`), while the
   shipped v0.2.10 `lib/client.js` — confirmed by the maintainer's own note — already
   contained `... !== 'plain' || busy` from the v0.2.10 hardening pass. The diff was
   generated against a **stale base** (a branch that had lost/dropped the hardening
   commit), so it visually "re-adds" a line that already existed. Reading the diff as
   "v0.2.11 introduced `busy`" is an artifact of the bad base, not history.
2. **A single console stack trace decides it.** `ReferenceError: busy is not defined` at
   the `disabled` line reproduces from the v0.2.10 source alone; a hover-preview crash
   would instead point at `imageItem`, `objectUrlOf`, or the hover-card and would occur
   only on hover / image interactions.

### Correct bisection

- **Rollback/re-add bisect:** take the shipped v0.2.11 tree, revert *only* the
  hover-preview hunks, mount the composer, paste an image → it still crashes → the feature
  hunks are exonerated. Conversely, cherry-pick the hover-preview hunks onto a tree that
  provably matches shipped v0.2.10 → the crash predates the diff.
- **Minimal render mount:** render `AttachmentChips` (or `AttachmentDock`) directly, in
  isolation, with one seeded occurrence and `input.phase = 'plain'` → the **v0.2.10**
  source throws the same ReferenceError. A bug that reproduces on the old version is by
  definition not introduced by the new diff.

### "New feature crashed the slot" vs "old latent bug first exercised now"

| Signal | New-feature crash | Old latent bug |
|---|---|---|
| Stack trace | points at diff-added code (`imageItem`, `objectUrlOf`, hover-card) | `ReferenceError: busy is not defined` at the pre-existing `disabled` line |
| Trigger | only image attachments / hover interactions | any occurrence present when the expression is evaluated (phase `'plain'`) |
| Reproduces on v0.2.10? | no | **yes** (with data present) |
| Diff base sanity | context lines match shipped v0.2.10 | context lines mismatch → stale-base diff |

Here the evidence (maintainer note + shipped file + the short-circuit latency story) lands
in the right-hand column. (Honest caveat: the hoisted `imageItem` line, as written in the
diff, also references free `status`/`record` and would throw even earlier — so the first
console check must identify *which* ReferenceError actually fired before assigning blame;
both are out-of-scope identifier defects in the same component and both get fixed.)

## 3. The fix

**Remove the dangling reference** (primary): delete `|| busy` from `AttachmentChips`'s
`disabled` — the chips component has no legitimate `busy`. **Or scope it properly**: if
the remove button genuinely must be locked while an attach is in flight, lift that state
to the shared parent (or a context) and pass it down explicitly, e.g.
`disabled: phaseGuard || props.attachBusy`. Also fix the hoisted line: move the
`imageItem` computation back **inside** the map callback where `record`/`status` are
declared (or compute from `occurrence` directly).

**Hardening the diff should also get:**

- `record?.items ?? []` before `.find(...)` — `record` may be `undefined` (status
  `'missing'`) or carry no `items`; a bare `.find` on `undefined` is a TypeError that
  takes the whole slot down.
- `event.target.closest?.('.remove')` — `event.target` is not guaranteed to be an Element
  exposing `closest` in every retargeting edge (e.g. SVG/text-adjacent targets); the
  optional chain degrades to "don't suppress" instead of throwing.

**Why this is cheap insurance in slot components:** a slot entry has **no partial-failure
mode** — any single throw unmounts the *entire* entry silently (console-only). So the
blast radius of one careless read is total disappearance of the UI, while the cost of
`??`/`?. ` is a few characters and no behavioral change on the happy path. Defensive
reads at slot boundaries are asymmetrical insurance: nearly free, catastrophically
valuable.

## 4. The regression that would have caught this before release

A **render smoke that mounts the dock WITH an occurrence present**:

1. Seed the `records` map with one record and pass `props.input = { phase: 'plain',
   occurrences: [{ source: SOURCE, ref, occurrenceId, label }] }` — **phase `'plain'`
   specifically**, because that is the arm of the `||` that evaluates `busy`.
2. Render `AttachmentDock` (or `AttachmentChips`) under a test renderer / jsdom.
3. Assert the chip element renders (`[data-status]` / `.chip` exists, label text present).
4. Assert **no error-boundary capture fired**: wrap in a failing test boundary (its
   `componentDidCatch`/`getDerivedStateFromError` calls `expect.fail`), or spy
   `console.error` for the React error-boundary signature.

The empty-state mount that likely existed (or the "syntax check only" habit) is worthless
here: with `occurrences = []` the component returns `null` **before reaching the throwing
line**, so an empty-dock smoke passes forever while the chip path is dead. The regression
must exercise the data-present, plain-phase path — precisely the state the first real
pasted screenshot produced.

## 5. The release-process lesson

`node --check` **only parses** the file. It proves the syntax is well-formed; it says
nothing about identifiers resolving, props existing, or render succeeding. A free
identifier like `busy` is grammatically perfect — it fails only at *evaluation* time, and
only with *data present* (empty state early-returns first). For a **lib-only plugin** with
no build step there is also no typecheck and no test runner in the loop, so nothing ever
executed the component: the defect class "component only fails at render time with data
present" is structurally invisible to the entire shipping pipeline.

**Minimum viable pre-ship check for slot-rendering lib-only plugins:** a headless **render
smoke** — a ~20-line script (`node --test`, vitest, or plain jsdom + the plugin's own
React/`h`) that mounts **every registered slot component** with realistic **non-empty**
props and asserts it renders without throwing and without an error-boundary capture. That
single smoke would have caught this bug in v0.2.10's hardening pass, one release early.
If any TypeScript can be retrofitted, `tsc --noEmit` additionally flags `busy` as an
unresolved name statically — but the render smoke is the non-negotiable minimum.

---

## Report per skill structure

- **pre-existing (baseline):** not collected — read-only diagnosis task; no repository of the plugin beyond the fixture pack was run.
- **Completed:** full root-cause analysis of the free-identifier render crash (`busy` out of scope in `AttachmentChips`; plus the diff's hoisted `status`/`record` scope defect), short-circuit latency, slot error-boundary unmount semantics, diff-blame refutation with a concrete bisection, fix + two hardening patterns, data-present render regression design, and the `node --check` release-process gap.
- **Skipped:** no version-corridor card consultation — this is a same-version render-crash diagnosis, not a DSH host migration; no touchpoint classes beyond UI/slot were implicated by the evidence.
- **Pending/residual risk:** the shipped plugin source itself (full `lib/client.js`, `records` map, slot registration code) was not available beyond the excerpt — the exact first-throwing line (`busy` vs hoisted `imageItem`) should be confirmed from one real browser-console stack trace; the fix is described, not applied (Mode A read-only).
- **Rollback:** nothing was changed; no rollback needed.
- **Recommendations:** adopt the per-slot data-present render smoke as a release gate; add `tsc --noEmit` (or a minimal eslint no-undef pass) to the plugin's ship script; when generating changelog diffs, verify diff context lines against the actually-shipped previous tag to avoid stale-base blame.
