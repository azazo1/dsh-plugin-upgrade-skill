# S17 · The External UI Plugin Onboarding Trap — Report

## Scenario summary

A user hand-wrote an external Web UI plugin (`@lhh010/dsh-profiles`), linked it into the
web profile's `node_modules`, and added one `insert` row in `cordis.patch.yml`. Three
distinct failures followed:

1. first boot: the browser refused to load **all** plugins, error naming
   `@deepseek-ai/dsh-typert-registry` (a stock, untouched entry);
2. after repackaging: an apply-time error — `slot "settings.section" is not declared
   (a parent entry's children table must declare it)`;
3. throughout: every plugin edit required a host restart, and one restart died with
   EADDRINUSE until the old process tree was force-killed.

---

## 1. Failure 1 root cause: one bad client bundle kills every registration

**What the host assembles.** At boot, the host's `client-modules` step reads **every
installed plugin's client bundle** (`lib/client.js`), concatenates them into a **single
classic `<script>` combo** (host log: *"composed 53 loader entries into client bundle
combo (4.5 MB, classic script)"*), and serves that one file to the browser. Each
individual bundle inside the combo is wrapped in the `window.__ModuleLoader__.load({ id,
factory })` registration form (see `working-plugin-excerpt.txt`).

**Why one bad bundle kills everything.** The user's `plugin/lib/client.js` is written as
bare ESM: top-level `import React from 'react'` and `export function apply(ctx)`. A
classic `<script>` tag executes in **non-module script mode**: top-level `import` /
export` statements are a **syntax error** at parse position 1:1 — exactly what the
error reports: *"bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error
(position 1:1)"*. Because all 53 entries share one concatenated script, a parse error in
one bundle aborts evaluation of the **whole combo**: the module loader registers
**nothing**, so the Settings → Plugins list is empty and even the previously working
stock plugins (brand version, file tracking) vanish.

**Why the error names `dsh-typert-registry`.** The host awaits loader entries in order;
the reported failure is attributed to the **first awaited entry** that failed — the stock
`@deepseek-ai/dsh-typert-registry` — even though the *detail* line of the same message
correctly points at the real culprit bundle (`@lhh010/dsh-profiles/lib/client.js`). The
stock entry is innocent: it merely happened to be the entry whose import was pending when
the combo-level compile failure surfaced. The error message's headline attribution and
its parenthetical detail disagree; the detail is the truth.

## 2. Diagnosis discipline and the correct client-bundle format

**Locating the culprit.**

- Read the full error, not the headline: the parenthetical names the exact file
  (`/plugins/@lhh010/dsh-profiles/lib/client.js`) — that is the culprit, not
  `dsh-typert-registry`.
- If the error were less specific: **bisect the `insert` rows** in `cordis.patch.yml`
  (remove the new third row → boot → works; restore → fails), or binary-search the
  installed plugin set.
- **Cheap static check** that flags the offending bundle in one pass: grep every
  `lib/client.js` for top-level ESM markers — `^import `, `^export `,
  `^import(` at position 1:1. Any hit means the bundle is not loadable as a classic
  script. (Bonus smells in this bundle: top-level DOM side effects —
  `document.body.appendChild(host)` at module scope — and a direct
  `react-dom` `createPortal` call, neither of which belongs in a loader factory.)

**The format an external plugin must ship.** A plain-JavaScript, self-contained wrapper
(see the working excerpt):

```js
window.__ModuleLoader__.load({
  id: "@lhh010/dsh-profiles",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    let react = require("react");              // React obtained via the loader's require,
    // let jsx = require("react/jsx-runtime"); // never via top-level ESM import
    function ProfilesSection() { /* React.createElement(...) */ }
    const inject = ["slots"];
    function apply(ctx) { /* ctx.slots.inject(...) */ }
    exports.apply = apply;                     // or module.exports = { inject, apply }
    return module.exports;
  },
});
```

- **What wraps the code:** a `window.__ModuleLoader__.load({ id, factory })` call whose
  `factory(require)` body provides CommonJS-style `module`/`exports` locals. No
  top-level `import`/`export`, no top-level DOM side effects.
- **How React is obtained:** inside the factory via the provided `require("react")` /
  `require("react/jsx-runtime")` / `require("@deepseek-ai/dsh-client-ui-primitives")`,
  resolved against the loader's module map inside the combo — never a bare ESM import and
  never a bundled copy of React (which would duplicate React instances and break hooks).
- **What the wrapper must export:** a plugin object with `apply(ctx)` (and `inject`
  when it depends on services), i.e. `exports.apply = apply` — the loader applies that
  exported plugin function, not an ESM-named export.

## 3. Failure 2: `slot "settings.section" is not declared`

**Who declares slots.** Slots are **declared by their owning (parent) entry** through a
children/declaration table published by the plugin that owns the settings page — the
settings entry declares `settings.section` as an injectable child slot. Declaration and
registration are separate steps with ordering guarantees: an entry may only contribute to
a slot that has been declared by its parent's table.

**Why the bare registration fails.** The repackaged plugin called, inside `apply`:

```js
ctx.slots.register(
  { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
  ProfilesSection,
)
```

`register` **creates/declares** a slot. A third-party entry attempting to re-declare
another entry's slot at apply time fails the declared-slot check — hence *"slot
settings.section is not declared (a parent entry's children table must declare it)"*:
from the registrant's perspective the slot's declaration is owned by the parent entry, and
a bare `register` from outside that ownership is rejected. Note the failure mode
changed from whole-combo death to a **single-entry apply failure**: all other plugins
load and render on this boot, confirming the combo now parses.

**The exact wrapping form the registration must use.** Follow the working excerpt:

```js
const inject = ["slots"];
function apply(ctx) {
  ctx.slots.inject(
    { name: "settings.section", id: "profiles-manager", order: 5 },  // contribution only
    ProfilesSection,                                                  // rendered React node/component
  );
}
```

- The plugin object carries `inject: ["slots"]` so Cordis reactivates it once the slots
  service (and the declaring parent entry) is available — this is what resolves the
  cross-entry ordering: the injectable waits for the declarer.
- The factory exports `apply` (as above).

**Field ownership.** The registrant (`inject`) may pass contribution-scoped fields:
`name` (which declared slot to contribute to), `id` (its own child identity),
`order`, props/component, and event handlers on its own contribution. It must **not**
pass declarer-owned fields: `kind`, `scope`, `children`/the children table, or any
structural slot metadata — those belong exclusively to the parent entry that declares the
slot.

## 4. Dev-loop discipline

**Why edits don't appear.** The combo is assembled **once per host boot**: the host reads
every installed plugin's client bundle, concatenates, and serves the frozen result
(*"The combo line appears ONCE per boot"*). Editing a plugin file on disk afterwards
changes nothing in the browser — even after a hard refresh — because the served artifact
is the boot-time snapshot, not a per-request read. (This is also why the
dev-mode HMR receiver only hot-reloads when the web dev watcher is rebuilding bundles;
an external plugin outside that pipeline gets no rebuild at all.)

**Correct restart procedure:**

1. stop the host process (fully — see below);
2. start the host again (watch for the one `client-modules: composed … loader entries`
   combo line);
3. hard-refresh the browser;
4. verify Settings → Plugins → Plugin list — an empty list means the combo failed to
   parse again (go back to the static ESM check).

**Why the Windows restart died with EADDRINUSE.** Closing the launching terminal does not
reliably terminate the node child process tree on Windows; the orphaned host process kept
the listening port bound, so the new host's `listen()` failed with `EADDRINUSE`. The
port only freed after killing the whole tree — `taskkill /PID <pid> /T /F` (`/T` kills
the tree, `/F` forces) — after which the next boot bound normally. Discipline: stop the
host via its own shutdown path (or explicit tree-kill), confirm the port is free, then
start; never assume a closed terminal means a dead server.

## 5. Prevention

**Host-side.**

- **Per-bundle compile validation at combo assembly.** When `client-modules` composes
  the combo, parse/compile each contributing bundle individually (e.g. `new
  Function`/`vm.compileFunction` dry-run) at boot; on failure, name the offending
  plugin id and file with position — not the first awaited loader entry. The current
  attribution logic surfaces the awaited entry (`dsh-typert-registry`) while the truth
  sits in the parenthetical; invert that priority.
- **Fail with a plugin-scoped entry, not a dead combo.** Ideally isolate syntax-failed
  bundles: register the remaining entries and report the failed plugin in the Plugin list
  / a boot warning, so one authoring mistake cannot blank the entire UI.
- **Cheap static gate:** at assembly, scan each bundle for top-level `import`/`export`
  (position 1:1) and for slot registrations naming slots the bundle's own entry did not
  declare, emitting an actionable message ("ship `window.__ModuleLoader__.load`
  factory form; use `ctx.slots.inject` for `settings.section`").
- **Port hygiene on Windows:** on EADDRINUSE at bind, report the PID holding the port and
  suggest `taskkill /PID <pid> /T /F`; consider a graceful-shutdown handler that kills
  the child tree so terminal close cannot orphan the listener.

**Authoring template / checklist for external UI plugins.**

1. Package `lib/client.js` as one classic-script-safe file:
   `window.__ModuleLoader__.load({ id: "<@scope/pkg>", factory: (require) => { … } })`
   with local `module`/`exports`; **no top-level `import`/`export`**.
2. Obtain React and primitives only via the factory's `require(`react`) /
   `require("react/jsx-runtime")` / `require("@deepseek-ai/dsh-client-ui-primitives")`.
3. Export `apply(ctx)` from the factory; declare `inject: ["slots"]` when consuming
   slots.
4. Register into existing slots with `ctx.slots.inject({ name, id, order }, Component)`;
   never `register` another entry's slot; never pass `kind`/`scope`/`children` —
   declarer-owned.
5. No top-level DOM side effects (`document.body.appendChild`) — render only from the
   slot the plugin injects into.
6. Dev loop: edit → fully stop host (tree-kill if orphaned) → start → hard refresh →
   verify Settings → Plugins list is non-empty; empty list ⇒ re-run the top-level-ESM grep.

## Evidence trail

| Fixture file | Fact it establishes |
| --- | --- |
| `browser-error.txt` | whole-combo failure; headline names `dsh-typert-registry`, detail names the real bundle |
| `plugin/lib/client.js` | bare ESM + top-level DOM side effects + `slots.register` misuse |
| `working-plugin-excerpt.txt` | correct `__ModuleLoader__.load` wrapper, `require` for React, `slots.inject` |
| `plugin-apply-error.txt` | apply-time declared-slot check failure after repackaging |
| `host-boot-log.txt` / `restart-notes.txt` | one combo per boot; orphaned node process → EADDRINUSE → `taskkill /T /F` |
| `profile/cordis.patch.yml` | the three `insert` rows; bisection surface |
