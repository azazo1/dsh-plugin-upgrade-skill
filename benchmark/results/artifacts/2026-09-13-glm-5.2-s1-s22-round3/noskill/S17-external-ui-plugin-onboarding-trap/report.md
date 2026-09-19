# S17 · External UI Plugin Onboarding Trap — Analysis Report

Task: S17-external-ui-plugin-onboarding-trap (read-only incident analysis)
Evidence: `environment/fixture/` (browser-error.txt, plugin/lib/client.js, profile/cordis.patch.yml,
plugin-apply-error.txt, working-plugin-excerpt.txt, host-boot-log.txt, restart-notes.txt).
Source grounding: shipped `@deepseek-ai/dsh-client-modules` (README + lib), `dsh-client-ui-settings-general`,
`dsh-client-ui-settings-plugins`, `dsh-typert-registry` bundles from the installed DSH web profile.

---

## 1. Failure 1 — why ONE bad client bundle took down EVERY plugin, and why the error named `dsh-typert-registry`

### What the host assembles and what reaches the browser

At host boot the node half of `dsh-client-modules` (`ctx.clientModules` / `ClientModuleRegistry`):

1. scans every enabled Loader entry (all `insert` rows resolved through the cordis patch layer — the boot log
   shows `3 insert rows resolved (dsh-brand-version, dsh-file-trace, dsh-profiles)` plus the ~50 stock rows);
2. snapshots each plugin's **built** client bundle (`lib/client.js`) and its source map into memory;
3. groups the bundles into **combo classic-script URLs** of the form `/plugins/??<ids>&rev=...` — one bootstrap
   combo for the modules row and one or more application combos for the rest, partitioned before a URL exceeds
   3 KiB (`client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)`);
4. injects into `<head>`: the `window.__ModuleLoader__` queue facade, advisory preloads, the parser-blocking
   combo scripts, and the boot graph (`window.__DSH_BOOT__`).

Each individual bundle is required to be a **loader-wrapped classic script**, not ESM:

```js
window.__ModuleLoader__.load({
  id: "<package name>",
  factory: (require) => { /* factory-form CJS; returns module.exports */ },
});
```

Executing the combo only *registers factories*; module bodies run lazily at first import/materialization.

### The failure mechanism

The user's `@lhh010/dsh-profiles/lib/client.js` begins with a top-level ESM statement
(`import React from 'react'`, plus `import { createPortal } from 'react-dom'`). Combo scripts are served and
executed as **classic scripts** (`<script>`, no `type="module"`), and all bundled plugins that share a combo
URL are **concatenated into one script**. A top-level `import`/`export` is a *parse-time* syntax error in a
classic script — `compile error (position 1:1)` is exactly the `import` keyword at line 1, column 1.

Because the whole combo is one script, one syntax error means the script **never parses or executes**: zero
`__ModuleLoader__.load()` calls run, zero factories register, and the browser-side module system has no entries
at all. That is why the Plugin list was EMPTY and even the previously-working stock plugins
(dsh-brand-version, dsh-file-trace) vanished — their bytes are in the same failed script.

### Why the error named `@deepseek-ai/dsh-typert-registry`

The browser half boots the plugin tree through the vendored Loader's `EntryTree.import`, which awaits entries
in tree order. `dsh-typert-registry` (entry `0c013085`) is simply the **first awaited entry whose import chain
touches the failed combo**; the rejection is reported as `failed to import loader entry 0c013085
(@deepseek-ai/dsh-typert-registry)` with the underlying cause attached
(`client-modules: bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)`).
The named entry is innocent — it is the messenger (first awaited import), not the culprit (the failing bytes,
which the cause string does identify). This ordering/attribution gap is the "misleading error" trap.

## 2. Diagnosis discipline and the correct client-bundle format

### Locating the culprit from the misleading error

- **Read the cause chain, not the headline entry.** The error's innermost cause names the exact failing bundle
  (`/plugins/@lhh010/dsh-profiles/lib/client.js`) and position (`1:1`). Any entry name in the outer message is
  just the first awaited import.
- **Change-one-variable bisect when the cause is unclear:** comment out the new `insert` row in
  `cordis.patch.yml` → restart → plugins come back → re-add → fails. That alone proves the new plugin owns the
  bytes. For multiple suspects, halve the inserted set.
- **Cheap static check that flags the offending bundle:** for every served `lib/client.js`, verify
  (a) it starts with the wrapper `window.__ModuleLoader__.load(` (or contains exactly one such top-level call),
  and (b) it contains **no top-level ESM `import`/`export` statements** — a regex/line scan for
  `^s*(import|export)s` outside the factory, or a `new Function()`/`node --check`-style classic-script parse.
  Both checks are static, run in milliseconds, and would have flagged this bundle before it ever reached the
  browser.

### The format an external plugin must ship (instead of bare ESM)

Per `dsh-client-modules` (README "Declaring a client plugin" / "Sharing modules" / "Build requirements") and
the working-plugin excerpt:

- **Wrapper:** the whole client half is one `window.__ModuleLoader__.load({ id, factory })` call; the factory is
  factory-form CJS (`var module = { exports: {} } ...`), returns `module.exports`, and all side effects
  (including CSS injection) live inside the factory closure.
- **React is obtained via `require`, never `import`:** the shell seeds a **frozen platform module table**
  (`PLATFORM_MODULES`: React, `react/jsx-runtime`, Cordis, static UI libraries); every bundle resolves its
  externals against exactly that baseline through the factory's `require("react")` /
  `require("react/jsx-runtime")`. Non-baseline shared modules must be declared in `package.json` under
  `dsh.client.external` (exact requests, answered by the dynamic package row they name). Bundling React into the
  plugin or importing it as ESM are both contract violations.
- **The wrapper/factory must export:** `apply(ctx)` (the Cordis client plugin body) and, when hard services are
  needed, `inject` (the service-name array) — see the excerpt's `const inject = ["slots"]; function apply(ctx){...}`.
- **Package declaration:** `dsh.client` in `package.json` with `platform: 'web'`, an exported `./client`
  bundle, and the built artifact must exist (`pnpm run build` produces `lib/client.js`) before launch — a
  missing bundle fails activation loudly.
- **No module-scope DOM work:** the user's top-level `document.body.appendChild` / `createPortal` must move
  into the React component rendered by a slot; UI appears through slot registration, not imperative portals.

## 3. Failure 2 — `slot "settings.section" is not declared (a parent entry's children table must declare it)`

### Who declares slots

Slots are *declared* by the registering entry that owns them, via the `children` table of its own slot
registration. Concretely, in the stock profile `dsh-client-ui-settings-general` registers `sidebar.settings`
and declares the whole settings surface as its children:

```js
ctx.slots.inject("sidebar.settings", () => ctx.slots.register({
  name: "sidebar.settings",
  children: {
    "settings.trigger":    { kind: "single", scope: "root" },
    "settings.header":     { kind: "single", scope: "root" },
    "settings.action":     { kind: "list",   scope: "root" },
    "settings.close":      { kind: "single", scope: "root" },
    "settings.section":    { kind: "list",   scope: "root" },  // ← the declaration
    "settings.onboarding": { kind: "list",   scope: "root" },
  },
  inject: shellInjected,
}, SettingsRoot));
```

(`dsh-client-ui-settings` owns the settingsScope/schema machinery; its README states "A settings surface
registers into the slot types this package declares … feature pages register `settings.section` contributions.")

### Why the bare cross-entry registration failed at apply time

Loader-entry activation order between two independent entries is **not constrained** — the declaring entry
(`ui-settings-general`) may apply before or after `@lhh010/dsh-profiles`. The user's code called

```js
ctx.slots.register(
  { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
  ProfilesSection,
)
```

directly (bare) inside `apply`. A bare `register` against a slot that no entry has declared yet — or with
 `kind`/`scope` fields, which only the declaring parent's `children` table may set — is rejected by SlotCore at
apply time with exactly this message. Note the failure is now correctly attributed (`failed to apply loader entry
(@lhh010/dsh-profiles)`) and contained: all other plugins load and render, because this error happens per-entry
at apply, not at combo parse.

### The exact wrapping form the registration must use

Every cross-entry registration goes through the **`ctx.slots.inject(slotName, register)` deferred wrapper**,
which waits for (and re-runs after) the slot's declaration, exactly as the stock Plugins section does:

```js
const inject = ["slots"];                      // service injection list, exported
function apply(ctx) {
  ctx.slots.inject("settings.section", () => ctx.slots.register({
    name: "settings.section",                  // target slot (declared elsewhere)
    id: "profiles-manager",
    order: 5,
    label: () => t("nav"),                     // locale-owned label
    locale: NS,
    inject: () => ({ /* props face for the component */ }),
    // children: { ... } only for slots THIS entry declares (e.g. its own sub-lists)
  }, ProfilesSection));
}
```

Field ownership:

- **A registrant may pass:** `name` (must equal the target slot), `id`, `order`, `key` (keyed slots),
  `label`, `locale`, `inject` (the props face), and `children` — but only to declare **new** slots it itself
  owns (as ui-settings-plugins declares `settings.plugins.tab` under its own section registration).
- **A registrant must NOT pass:** `kind` and `scope` for the target slot — those are declaration metadata that
  belong exclusively to the parent entry's `children` table (`kind: 'section', scope: 'settings'` in the user's
  code was both wrong values and an illegal field for a consumer). It must also not register bare — the
  `slots.inject(...)` wrapper is what orders the registration after the declaration and survives fiber restarts.

## 4. Dev-loop discipline — boot-assembled combos and the Windows EADDRINUSE restart

### Why edits do nothing until the host restarts

The combo is assembled **once per host boot**: the node half snapshots every client bundle into memory before
publication and serves immutable, content-addressed responses (unknown combination or revision → 404). Per the
package's own contract, *"Bundle content changes reach the graph only through `rebuilt()` (the HMR hook)"* —
i.e. the client-HMR driver invalidating one row. An externally installed community plugin linked into
`node_modules` has no dev watcher driving `rebuilt()` (client-plugin HMR reload-without-refresh applies only
while the repo's `pnpm run dev:web` watcher builds the bundles), so editing `lib/client.js` on disk changes
nothing in the browser — even after a hard refresh — because the served bytes are the boot snapshot.

**Correct restart procedure:**

1. fully stop the host process (see below), not just the terminal window;
2. start the host again — the boot log must show a fresh `client-modules: composed N loader entries…` line;
3. hard-refresh the browser (combo URLs are revisioned, but the index rows carrying them are read at load);
4. verify Settings → Plugins → Plugin list is non-empty — an empty list means the combo failed to parse again.

### Why the Windows restart died with EADDRINUSE

Closing the launching terminal on Windows does not reliably terminate the host's child process tree: an orphaned
`node` process kept the listening port open, so the next host boot could not bind and failed with EADDRINUSE.
Only killing the whole tree freed the port: `taskkill /PID <pid> /T /F` (`/T` = tree, `/F` = force). After
that the next boot bound normally. The dev-loop rule on Windows is therefore: stop by killing the process tree
(or via the host's own shutdown path), verify the port is free, then start.

## 5. Prevention

### Host side

- **Validate bundles at boot (fail loud at the boundary):** during combo assembly, run the cheap static checks of
  §2 on every snapshot — wrapper presence, no top-level ESM `import`/`export`, classic-script parse. Reject at
  host startup with one instruction and the offending **package + path list** (mirroring the existing
  missing-bundle behavior), instead of shipping an unparseable combo to the browser.
- **Attribute combo failures to the owning entry:** when a combo script fails to compile/execute, report the
  entries whose bundles share that combo URL — and especially the bundle whose byte range contains the error
  position — rather than the first awaited `EntryTree.import` entry. Even a minimal fix (append "shared combo
  also contains: <ids>" to the rejection) would have stopped the user from suspecting `dsh-typert-registry`.
- **Surface combo health in the UI:** the empty Plugin list already signals total failure; a browser-visible
  banner naming the failed combo and its member entries would make failure 1 self-diagnosing.
- Optionally, a `dsh` doctor/verify command that runs the same static bundle checks and the
  `verify-cordis-config`-style manifest checks (`dsh.client`, `dsh.client.external` suppliers exist) for
  externally installed plugins before boot.

### Authoring side — external client-plugin template/checklist

1. **Package:** `package.json` with `dsh.client: { platform: 'web' }`, `exports["./client"]`, and any
   non-baseline shared modules under `dsh.client.external` (exact request strings; suppliers must be installed).
2. **Build:** a build step that emits `lib/client.js` as ONE `window.__ModuleLoader__.load({ id, factory })`
   classic script; factory-form CJS; no top-level `import`/`export` anywhere outside the factory.
3. **Dependencies:** React/react-dom/Cordis/UI libraries come from the frozen platform table via
   `require("react")`, `require("react/jsx-runtime")` — never bundled, never ESM-imported.
4. **Exports:** `apply(ctx)` plus `inject` (e.g. `["slots", "locale"]`); every registration/effect goes through
   `ctx.effect()` or an API returning a disposer so the plugin is reversible.
5. **Slots:** register into existing slots ONLY via `ctx.slots.inject("<slot>", () => ctx.slots.register({ name,
   id, order, label, locale, inject }, Component))`; never pass `kind`/`scope` for a slot another entry
   declares; declare own child slots under `children` of your own registration.
6. **UI:** render through slot components; no module-scope DOM mutation, portals, or imperative mounting.
7. **Copy:** route all user-visible text through locale dictionaries (`ctx.locale.register` + `t`), never
   hardcoded strings.
8. **Install/dev loop:** link into the profile's `node_modules` + one `insert` row in `cordis.patch.yml`;
   remember every edit requires a full host restart (kill the process tree on Windows) + browser hard refresh;
   check the Plugin list after each boot.

---

## Summary of the three failures

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | All plugins fail to load; error names `dsh-typert-registry` | New plugin's bundle used top-level ESM `import`; classic-script combo (all plugins concatenated) fails to parse at 1:1; first awaited entry reported | Ship loader-wrapped factory-CJS bundle; React via `require` from platform table; export `apply`/`inject` |
| 2 | `slot "settings.section" is not declared (a parent entry's children table must declare it)` | Bare `ctx.slots.register` with `kind`/`scope` against a slot declared by another entry, unordered activation | Wrap in `ctx.slots.inject("settings.section", () => ctx.slots.register({name,id,order,label,locale,inject}, C))`; `kind`/`scope` belong to the declaring parent's `children` table |
| 3 | Edits invisible until restart; EADDRINUSE on restart | Combo snapshot assembled once per boot; changes reach the graph only via HMR `rebuilt()`; orphaned node process held the port | Full host restart per edit (`taskkill /T /F` on Windows) + hard refresh + verify Plugin list |

No blockers: the fixture was read-only and untouched; the output file is the only artifact written.
