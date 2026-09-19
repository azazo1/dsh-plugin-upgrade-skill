# S17 · The External UI Plugin Onboarding Trap — Incident Analysis

Read-only analysis of the evidence pack in `environment/fixture/`. All file references point at
fixture files. No fixture file was modified.

## Incident timeline

1. User hand-writes `@lhh010/dsh-profiles` (directory linked into the web profile's
   `node_modules`) and adds one `insert` row to `profile/cordis.patch.yml`
   (`- id: dsh-profiles, name: '@lhh010/dsh-profiles'`).
2. **First boot**: browser refuses to load plugins AT ALL — `browser-error.txt` shows
   `failed to import loader entry 0c013085 (@deepseek-ai/dsh-typert-registry):
   client-modules: bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)`.
   Plugin list is EMPTY; even the two previously-working stock header plugins are gone.
3. User repackages the plugin into the ModuleLoader form; **second boot** loads all other
   plugins but `plugin-apply-error.txt` records
   `failed to apply loader entry (@lhh010/dsh-profiles): slot "settings.section" is not declared
   (a parent entry's children table must declare it)`.
4. Throughout, every edit requires a full host restart, and one Windows restart died with
   EADDRINUSE until the old process tree was force-killed (`restart-notes.txt`,
   `host-boot-log.txt`).

---

## 1. Failure 1 root cause: one raw-ESM bundle killed the whole combo

**What the host assembles.** Per `host-boot-log.txt`, at boot the host's client-modules
composer reads every installed plugin's client bundle and **concatenates all 53 loader
entries into ONE classic script** ("composed 53 loader entries into client bundle combo
(4.5 MB, classic script)") and serves that single classic (non-module) script to the
browser. There is no per-plugin `<script type="module">`; every entry shares one parse
unit.

**Why one bundle kills every registration.** `plugin/lib/client.js` as the user wrote it
is bare ESM: it begins with top-level `import React from 'react'` /
`import { createPortal } from 'react-dom'` and uses `export function apply(ctx)`.
An `import` statement is a syntax error at position 1:1 **when parsed as a classic
script** — which is exactly what the combo is. Because the combo is one concatenated
classic script, a single syntax error makes the WHOLE combo fail to compile, so the
ModuleLoader registers **zero** entries: the plugin list is empty and even the untouched
stock plugins (brand version, file trace) disappear from the header. The failure is
all-or-nothing by construction of the combo, not by any defect in the other 52 entries.

**Why the error names `@deepseek-ai/dsh-typert-registry`.** The browser-side loader
awaits its entries in order; `0c013085 (@deepseek-ai/dsh-typert-registry)` is simply the
**first awaited entry** whose import promise rejects when the combo fails to compile. The
error message attaches the compile-error detail (which does name the real bundle path
`/plugins/@lhh010/dsh-profiles/lib/client.js` and position 1:1), but the headline entry
name is the first victim, not the culprit. The typert-registry package is a stock host
entry the user never touched — it is innocent; it just happened to be first in the await
order when the shared combo blew up.

Scope note: raw ESM is not "invalid JavaScript" universally — in an ESM/module context
these imports parse fine (`node --check` will even accept the file). It is invalid
**in this host's classic-script combo**, which is the only context that matters for a web
profile client bundle here.

## 2. Diagnosis discipline and the required client-bundle format

**Locating the culprit despite the misleading headline.**

- Read past the entry name to the parenthesized detail: it names the exact bundle path and
  position — `/plugins/@lhh010/dsh-profiles/lib/client.js` at 1:1. That is the culprit.
- **Cheap bisect**: the only change before the failure was one `insert` row in
  `cordis.patch.yml`. Temporarily remove (or comment out) the `dsh-profiles` insert row,
  restart the host, hard-refresh: if the plugin list comes back, the isolated row's bundle
  is the culprit. Re-add to confirm. One restart per probe because the combo is built once
  per boot (see §4).
- **Cheap static check that flags the offending bundle**: parse each plugin's
  `lib/client.js` **as a classic script**, e.g. `new vm.Script(source)` (Node
  `vm`) or equivalent per-bundle classic-mode parse. `vm.Script` rejects top-level
  `import`/`export` with a SyntaxError at 1:1 — exactly the browser's failure — while
  accepting the valid loader-wrapper bundles. Note that `node --check client.js` is
  **insufficient**: modern Node auto-detects module syntax and will accept the ESM file,
  hiding the failure mode that matters. (A scan for top-level `^s*import` /
  `^s*export` is a useful first-order grep, but the classic-script parse is the
  authoritative check.)

**The packaging contract an external plugin must ship** (from
`working-plugin-excerpt.txt`): NOT bare ESM, but a ModuleLoader registration:

```js
window.__ModuleLoader__.load({
  id: "@lhh010/dsh-profiles",          // package-name identity — must match the entry
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });

    // React and other shared libraries come from the HOST via require inside the
    // factory — never from a top-level ESM import:
    const React = require("react");
    const { createPortal } = require("react-dom");   // if actually needed

    function ProfilesSection() {
      return React.createElement(/* ... */);
    }

    const inject = ["slots"];           // services this client half needs
    function apply(ctx) {
      // slot registration goes here — see §3 for the deferred form
    }

    module.exports = { inject, apply };  // the wrapper must export apply (+ inject)
    return module.exports;
  },
});
```

Key points:

- **What wraps the code**: a single `window.__ModuleLoader__.load({ id, factory })` call;
  the factory is a classic-script function body that builds a CommonJS-style
  `module`/`exports` and returns it. No top-level `import`/`export` anywhere.
- **How React is obtained**: via the `require` argument the host passes into the factory
  (`require("react")", `require("react/jsx-runtime")",
  `require("@deepseek-ai/dsh-client-ui-primitives")`, etc.), resolving to host-provided
  shared instances — one React, no bundling, no CDN, no globals.
- **What the wrapper must export**: `apply(ctx)` (the client-half Cordis plugin entry)
  and optionally `inject` (the array of services the client half depends on, e.g.
  `["slots"]`). The user's original bundle also had a second defect hidden behind the
  syntax error: it mounted a DOM portal at module scope. In the loader form, all side
  effects belong inside `apply` (or the component lifecycle), not at factory top level.

## 3. Failure 2: `slot "settings.section" is not declared`

**Who declares slots.** Slots in this client runtime are **declared by their owning
(parent) entry** — a parent entry's children table declares each slot it hosts. The
`settings.section` slot is declared by the stock settings UI entry (another loader
entry), not by `@lhh010/dsh-profiles`.

**Why the bare registration fails at apply time.** The combo registers/loads entries and
applies them in an order that is **not guaranteed** to run the declaring parent entry
before this plugin's `apply`. The user's repackaged bundle called, inside `apply`:

```js
ctx.slots.register(
  { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
  ProfilesSection,
)
```

i.e. an **immediate** registration of another entry's slot. If the declaring entry has not
run yet, the slot does not exist in the registry, so the registration is rejected with
`slot "settings.section" is not declared (a parent entry's children table must declare
it)` — and only this entry fails (`plugin-apply-error.txt` notes all other plugins load
and render normally). This is an apply-time ordering failure, not a packaging failure this
time.

**The correct wrapping form: deferred registration via `slots.inject`.** The registrant
must not register immediately; it must wait for the declaration:

```js
function apply(ctx) {
  ctx.slots.inject("settings.section", () =>
    ctx.slots.register(
      { name: "settings.section", id: "profiles-manager", order: 5 },
      ProfilesSection,
    ),
  );
}
```

`ctx.slots.inject(slotName, callback)` defers the callback until the named slot is
declared (a block callback returning the registration, or an equivalent supported deferred
form). `slots.inject` is the required mechanism — mentioning it is not enough; the
registration call itself must move inside the deferred callback.

**Field ownership:**

- **Registrant supplies**: `name` (the declared slot name), `id` (this registration's
  id), `order` (relative ordering), and optionally a display `label`.
- **Registrant must NOT supply**: `kind` and `scope` — these are **declaration-owned**
  fields set once by the parent entry's children table when it declares the slot. The
  user's `kind: 'section', scope: 'settings'` on the register call duplicates/contends
  with the declaring entry's data and is not the registrant's to set.

## 4. Dev-loop discipline: boot-assembled combo and the Windows restart

**Why edits don't rebuild.** The host builds the client bundle combo **exactly once per
boot**: at startup it reads every installed plugin's client bundle from disk,
concatenates them into the classic-script combo, and serves that snapshot
(`host-boot-log.txt`: the combo line appears ONCE per boot). There is no file watcher
and no per-request re-composition on this host, so editing `lib/client.js` on disk
afterwards — even with a browser hard refresh — changes nothing. The browser re-fetches
the same pre-built combo.

**Correct restart procedure per iteration:**

1. Fully **stop the host process** (not just close the terminal window).
2. On Windows, verify the old node process is actually gone; if the port is still held,
   kill the entire process tree: `taskkill /PID <pid> /T /F` (`/T` = tree, `/F` =
   force). Then start the host again.
3. **Hard-refresh the browser**, then verify registration via
   Settings → Plugins → Plugin list — an empty list means the combo failed to compile
   again (`restart-notes.txt` step 3).

**Why EADDRINUSE, and why the tree kill was needed.** Closing the launching terminal on
Windows does not reliably terminate the node process tree it spawned: the host's node
process (and any children) survived, still holding the listening port. The next host boot
then failed to bind with EADDRINUSE — an orphaned old process retaining the port, **not**
a defect in the new plugin packaging. `taskkill /PID <pid> /T /F` kills the process AND
its whole child tree, freeing the port; the next boot bound normally. (Equivalents like
stopping via the host's own shutdown path, or killing each PID in the tree, work too;
the essential parts are: kill the tree, not just the shell, and confirm the port is free
before rebooting.)

## 5. Prevention

### Host-side

1. **Per-plugin classic-script validation at startup.** Before or while composing the
   combo, the host should parse each plugin's client bundle individually as a classic
   script (`new vm.Script(bundleSource)` or equivalent). A bundle that fails gets
   excluded from the combo (or the boot fails loudly) **with the offending plugin's id and
   bundle path in the error** — never silently concatenated into a shared parse unit.
2. **Culprit attribution at combo-failure time.** When the browser-side loader reports
   "failed to import loader entry X", the message should not stop at the first awaited
   entry. Since the compile error already carries the bundle path, the host/loader should
   surface `combo compile failed; offending bundle: <plugin id>/<path> (<line:column>)`
   — attributing the failing bundle's owning plugin, and stating that the named entry is
   merely the first awaited victim. Aggregating per-entry registration results (e.g.
   "52/53 entries registered; 1 bundle rejected") would make the blast radius obvious.
3. Optionally: a dev-mode re-composition trigger (rebuild combo on file change) and/or a
   friendly diagnostic when binding fails with EADDRINUSE ("port still held by PID <pid>,
   likely a previous host instance — kill the process tree"), plus a shutdown path that
   reliably terminates the child process tree on Windows.

### Authoring-side: external-plugin template / checklist

A `dsh external web UI plugin` template should generate exactly this shape and the
checklist should verify it before every insert:

- [ ] **Client bundle is a ModuleLoader classic script**: one
      `window.__ModuleLoader__.load({ id, factory })` wrapper; factory returns
      `module.exports`. No top-level `import`/`export` anywhere in `lib/client.js`.
      Verify with `new vm.Script(fs.readFileSync('lib/client.js','utf8'))` — it must
      parse. (Do not trust `node --check`, which accepts ESM.)
- [ ] **`id` equals the package name** used in the `cordis.patch.yml` insert row.
- [ ] **React and shared libs via the factory's `require`** (`require("react")`, …);
      never bundler imports, CDN loads, or global reach-ins.
- [ ] **Exports**: `apply(ctx)` and, when services are needed, `inject` (e.g.
      `["slots"]`). No DOM mutation at factory top level — side effects live in
      `apply` or component lifecycle.
- [ ] **Cross-entry slots are deferred**: any slot declared by another entry (e.g.
      `settings.section`) is registered via
      `ctx.slots.inject("settings.section", () => ctx.slots.register({ name, id, order
      [, label] }, Component))`. Registrant passes name/id/order (+ optional label)
      only; declaration-owned fields (`kind`, `scope`) are left to the declaring
      parent entry.
- [ ] **Dev loop**: after every file edit, fully stop and restart the host (the combo is
      built once at boot; a browser refresh alone changes nothing); then hard-refresh and
      check Settings → Plugins (empty list = combo compile failure).
- [ ] **Windows restart hygiene**: close the host via its real shutdown path or kill the
      process tree (`taskkill /PID <pid> /T /F`); if the next boot hits EADDRINUSE, an
      orphaned previous host still holds the port — kill the tree, don't debug the plugin.
- [ ] **Bisect rule**: when the plugin list goes empty after an insert, suspect the newly
      inserted row's bundle first; remove that one insert row, restart, confirm, re-add.

## Summary

| Failure | Root cause | Fix |
|---|---|---|
| Whole plugin list empty; error names `dsh-typert-registry` | One raw-ESM bundle (top-level `import`) broke the single concatenated classic-script combo; typert-registry was just the first awaited entry | Ship a `window.__ModuleLoader__.load({id, factory})` classic-script bundle |
| `slot "settings.section" is not declared` | Immediate registration of another entry's slot before its declaring parent ran; apply order is not guaranteed; registrant also set declaration-owned `kind`/`scope` | `ctx.slots.inject("settings.section", () => ctx.slots.register({name,id,order[,label]}, C))`; drop `kind`/`scope` |
| Edits invisible; EADDRINUSE on restart | Combo assembled once per host boot; orphaned old Windows process tree still held the port | Full host stop + restart per edit; `taskkill /PID <pid> /T /F`; hard refresh; verify plugin list |
