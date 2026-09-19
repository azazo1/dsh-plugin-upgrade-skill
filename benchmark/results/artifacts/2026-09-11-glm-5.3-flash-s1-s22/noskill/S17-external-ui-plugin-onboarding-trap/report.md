# S17 · The External UI Plugin Onboarding Trap — Diagnostic Report

Evidence pack: fixture/ (README.md, browser-error.txt, host-boot-log.txt, plugin-apply-error.txt, plugin/lib/client.js, profile/cordis.patch.yml, restart-notes.txt, working-plugin-excerpt.txt). Cross-checked against the shipped client module system (`@deepseek-ai/dsh-client-modules/lib/client.js`) and slot renderer (`@deepseek-ai/dsh-client-ui-renderer/lib/client.js`).

## 1. Failure 1 root cause — one bad bundle killed every plugin, and the error named an innocent stock entry

**What the host assembles at boot.** `host-boot-log.txt` shows the mechanism:

> `[boot] client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)`

At boot the host reads every installed plugin's `lib/client.js`, **concatenates all of them into ONE classic script combo**, and serves that single resource (one combo URL shared by every entry — see `pendingArrival` in dsh-client-modules: "every row in one batch shares it"). The combo is loaded by `<script src>` (defaultLoadBundle: `document.createElement("script")`), i.e. as a **classic script, not an ES module**. A bundle only *registers* its factory by executing `window.__ModuleLoader__.load({id, factory})`; nothing else in the browser parses plugin sources again.

**Why everything died.** The user's bundle (`plugin/lib/client.js`) starts with:

```js
import React from 'react'
import { createPortal } from 'react-dom'
...
export function apply(ctx) { ... }
```

Top-level `import`/`export` is a **syntax error in a classic script**. Because the culprit was concatenated into the shared combo, the browser's parse of the *entire combo* failed at the first illegal token ("compile error (position 1:1)" — the very first characters of the user's file, `import`). When a classic script fails to parse, **none of its top-level statements run**, so all 52 other `__ModuleLoader__.load({...})` registrations in that combo never executed. Result, per `browser-error.txt`: "Failed to load plugins … Settings → Plugins → Plugin list: EMPTY. Zero entries registered", and even the two previously working stock plugins vanished from the header.

**Why the error named `@deepseek-ai/dsh-typert-registry`.** The loader materializes entries lazily: `ClientModuleSystem.import(specifier)` → `arriveGraphRow(row)` loads the row's bundle URL, then checks `if (!this.factories.has(id)) throw …`. The outer wrapper of the error is "failed to import loader entry **0c013085 (@deepseek-ai/dsh-typert-registry)**" — that is simply **the first entry whose import was awaited** when the shared combo failed; the graph walk reached the typert-registry row first, awaited its `initialUrl` (the shared combo), and the transport rejected. The *inner* message actually names the true culprit file:

> `client-modules: bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)`

So `dsh-typert-registry` is innocent — it is a bystander whose import happened to be the await point; the named bundle path in the inner error is the real offender. The user never touched that stock entry.

## 2. Diagnosis discipline and the correct client-bundle format

**Bisecting from the misleading error.** Never trust the outer entry name (it is the first awaiter, not the culprit). Bisect the *bundle set*, not the entry:

1. The combo is one resource, so comment-out/remove the newly inserted profile row (`profile/cordis.patch.yml` — the `dsh-profiles` insert is the only change) and reboot. If plugins return, the new plugin's bundle is the culprit — confirmed by the inner error already pointing at `/plugins/@lhh010/dsh-profiles/lib/client.js`.
2. Bisect further by removing one plugin at a time (or diffing against the last-known-good boot) whenever the culprit is not obvious.

**Cheap static check.** A classic-script combo must contain no top-level ESM syntax. One grep flags it instantly:

```
grep -nE "^\s*(import|export)[\s{'"*]" plugin/lib/client.js
```

Any hit at top level = the bundle will kill the whole combo. This is exactly the "bundle purity" the module system mirrors at runtime ("the runtime mirror of the build-time bundle purity gate" in its require error text).

**The required format** — see `working-plugin-excerpt.txt`, the packaging shell of a *working* plugin:

```js
window.__ModuleLoader__.load({
  id: "@local/dsh-brand-version",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    let react_jsx_runtime = require("react/jsx-runtime");
    let primitives = require("@deepseek-ai/dsh-client-ui-primitives");
    const inject = ["slots"];
    function apply(ctx) { /* ctx.slots.inject(...) calls */ }
    return module.exports;
  },
});
```

- **What wraps the code:** `window.__ModuleLoader__.load({ id, factory(require) })` — the lazy-CJS registration form. The factory body is the module; it returns `module.exports`. Everything (including CSS injection) lives inside the factory closure and runs at materialization, not at script execution.
- **How React is obtained:** via `require(...)` from the platform seed/module table — `require("react/jsx-runtime")` (or `react`), `require("react-dom")` as available seeds, and host primitives from `@deepseek-ai/dsh-client-ui-primitives`. **No `import` of React**; externals are seed words resolved by `makeRequire`.
- **What the wrapper must export:** the plugin's `apply(ctx)` (and the `inject` array for hard Service dependencies) inside `module.exports` — so the vendored Cordis loader can call `apply` with fiber lifecycle, inject-waiting, and disposal. The host boot manifest's `inject` rows feed this.

## 3. Failure 2 — `slot "settings.section" is not declared (a parent entry's children table must declare it)`

**Who declares slots.** Slots are *declared* by the parent entry that renders the hole — here the settings shell entry owns the `settings.section` children table. A registrant cannot create the hole; it can only contribute into a hole another entry declared.

**Why the user's bare register failed.** In `plugin/lib/client.js` the user wrote, directly inside `apply`:

```js
ctx.slots.register(
  { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
  ProfilesSection,
);
```

At apply time the slot controller checks the registration key against the declaring entry's children table and throws `SlotOwnershipError` ("slot '…' is not declared by this entry's children" in dsh-client-ui-renderer). A foreign entry registering `settings.section` without a declaration in its own children table fails — and since the slot had not been declared *yet* (declaration ordering: the settings shell's declaration is not guaranteed to precede an external plugin's apply), a bare synchronous register cannot wait for it either.

**The exact wrapping form.** Wrap the registration in `ctx.slots.inject(slotKey, callback)`, which installs an effect that runs the callback only once the declaration exists (synchronously if already declared, otherwise inside the declaring `register()`; the controller belongs to the caller's fiber, so unload disposes it). This is exactly what every shipped plugin does — e.g. `@deepseek-ai/dsh-client-ui-agent-preset/lib/client.js`: `ctx.slots.inject("settings.section", () => ctx.slots.register({...}))` — and what the redacted working excerpt elides as "ctx.slots.inject(...) calls":

```js
function apply(ctx) {
  ctx.slots.inject("settings.section", () =>
    ctx.slots.register({ id: "profiles-manager", order: 5, element: ProfilesSection }),
  );
}
```

**Allowed vs forbidden fields.** The registrant passes only its *contribution* spec: its own `id`, ordering (`order`), and the element/render payload. It must **not** pass the *declaration*-owned fields of the slot spec: the slot `name`/key as a spec property, `kind`, or `scope` — those belong to the parent entry's children-table declaration. The user's object mixed all of them in (`name`, `kind: 'section'`, `scope: 'settings'`), which is both the ownership error and declaration-field leakage into a contribution.

Two more defects in the same file worth noting: top-level DOM side effects (`document.createElement('div') … document.body.appendChild`) run at script execution instead of inside the factory/apply fiber, and `createPortal(...)` at module top level renders outside any React root and any fiber-owned lifecycle.

## 4. Dev-loop discipline

**Why edits do nothing until restart.** `host-boot-log.txt`: "The combo line appears ONCE per boot" — the host composes the 53-entry client bundle combo (4.5 MB, classic script) once at boot and serves that static resource. Editing a plugin file on disk afterwards changes nothing in the browser, "even after a hard refresh, until the host process is stopped and started again" (`restart-notes.txt`). The browser only re-executes the served combo; there is no per-plugin rebuild of the combo from disk on request.

**Correct restart procedure.** Stop the host *properly* (not by closing the terminal window), verify the old node process is gone, start again, then per `restart-notes.txt` item 3: browser hard refresh, then check Settings → Plugins → Plugin list — "empty list = the combo failed again". That plugin list is the fast health probe for the combo.

**Why EADDRINUSE.** On Windows, closing the launching terminal does not deliver a signal to the child process tree the way POSIX process groups do; the host's node process survived as an orphan and still held the listening port. The next boot could not bind: EADDRINUSE. Only killing the entire tree freed the port:

```
taskkill /PID <pid> /T /F
```

(`/T` = tree, `/F` = force; per `restart-notes.txt` item 2, after that the next boot bound normally.) Practical discipline: find the holder before starting (`Get-NetTCPConnection -LocalPort <port>` / `netstat -ano | findstr <port>`) and kill the tree, not just the window.

## 5. Prevention

**Host-side (name the culprit, not the first awaiter).**
- **At combo composition (boot):** before concatenating, syntax-check each bundle under the classic-script goal it will actually run under (a parse/scan for top-level `import`/`export` per bundle), and fail loud with the offending *bundle path and package id* — refusing to serve a combo that is known-bad, so one plugin cannot blank out all client UI. The error already computes the bundle path; surface it as the primary message, demoting the awaiting entry id to a detail.
- **At combo-failure time:** when the served script fails to parse or a batch transport rejects, report which entries' factories are missing vs registered — the loader already knows (`factories` map, `arrive`'s "loaded without registering" check). "Bundle X compiled, entries [a,b,c] never registered" pinpoints the culprit directly. Serving per-entry script URLs (or at least isolating the failing transport to one URL) would stop one bundle from taking down registration of all 53.
- **At apply time:** the second failure already names the entry ("failed to apply loader entry (@lhh010/dsh-profiles)") — keep that, and extend it with a hint: "slot 'settings.section' is declared by another entry; use ctx.slots.inject('<slot>', …)".

**External-plugin authoring template/checklist (covers all three failures).**
1. Bundle shape: everything inside `window.__ModuleLoader__.load({ id, factory(require) { …; return module.exports; } })`; **no top-level `import`/`export` anywhere** (grep `^\s*(import|export)` before shipping).
2. React and host primitives come from `require("react/jsx-runtime")`, `require("@deepseek-ai/dsh-client-ui-primitives")`, etc. — never imported.
3. No top-level DOM or render side effects; components mount through slot registrations inside `apply`; all effects go through `ctx.effect`/`ctx.slots.inject` so unload disposes them.
4. Export `apply(ctx)` and declare hard dependencies via `inject` (e.g. `inject: ["slots"]`).
5. Another entry's slot is contributed **only** via `ctx.slots.inject("<slotName>", () => ctx.slots.register({...}))`; pass only contribution fields (`id`, `order`, element payload), never declaration fields (`name`/`kind`/`scope`).
6. Dev loop: every plugin-file edit requires a full host restart before the browser sees anything; restart properly, kill orphans with `taskkill /PID <pid> /T /F` on Windows, hard-refresh, and verify Settings → Plugins → Plugin list is non-empty (empty = combo still failing).
