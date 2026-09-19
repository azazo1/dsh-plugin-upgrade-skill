# S17 · The External UI Plugin Onboarding Trap — Analysis Report

Scope: read-only analysis of the evidence pack in
`environment/fixture/` (browser-error.txt, host-boot-log.txt, plugin-apply-error.txt,
plugin/lib/client.js, profile/cordis.patch.yml, restart-notes.txt, working-plugin-excerpt.txt),
cross-checked against the installed DeepSeek Harness packages
(`@deepseek-ai/dsh-client-modules`, `@deepseek-ai/cordis-plugin-loader`,
`@deepseek-ai/dsh-client-ui-agent-preset`).

---

## 1. Failure 1 — why ONE bad client bundle took down EVERY plugin, and why the error named `dsh-typert-registry`

### What the host assembles and how it reaches the browser

At host boot, the client-modules host half (`ctx.clientModules`) scans every enabled Loader
entry, resolves each plugin package's `dsh.client` declaration, and snapshots the built client
bundle (`lib/client.js`) plus source map. It then **concatenates bundles into combo classic
scripts** — per the host boot log: *"client-modules: composed 53 loader entries into client
bundle combo (4.5 MB, classic script)"* — and publishes them under `/plugins/??...` combo URLs.
The browser receives this not as ES modules but as **one or a few classic `<script>` payloads**
described by `WebBootEntry` rows injected as `window.__DSH_BOOT__`. Each bundle in the combo is
a factory registration of the form `window.__ModuleLoader__.load({ id, factory: (require) => {...} })`;
executing the combo only registers factories — module bodies run lazily at materialization.

### Why one ESM `import` killed all 53 entries

A classic script is parsed in its entirety before anything executes. The user's
`plugin/lib/client.js` begins with a top-level ESM statement:

```js
import React from 'react'
```

`import` at the very first byte of the bundle's chunk inside the classic-script combo is a
**syntax error at parse time** — hence `compile error (position 1:1)`. Because the combo is a
single script, a parse failure aborts evaluation of the WHOLE script: not one factory registers,
`EntryTree.import` cannot proceed for any entry in that combo, and the browser reports
"Failed to load plugins" with an EMPTY plugin list — including the two stock plugins
(`dsh-brand-version`, `dsh-file-trace`) that rendered fine before the insert. The blast radius
of one malformed bundle is every entry sharing its combo, which at boot is effectively all of them.

### Why the error named `@deepseek-ai/dsh-typert-registry`

The failure surfaced while the browser awaited the import of loader entry `0c013085`
(`@deepseek-ai/dsh-typert-registry`). That entry is simply the **first entry whose import
pulled in the combo that happened to contain the broken bundle** — the loader imports entries in
boot-graph order, so the first awaited entry on the failing combo gets named in the headline.
`dsh-typert-registry` is completely innocent; it is an attribution artifact of combo-level
sharing. The real culprit is in the error's inner detail: `bundle
/plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)` — the message did
contain the answer, just not in the first line the user read.

---

## 2. Diagnosis discipline and the correct client-bundle format

### Locating the culprit from the misleading error

1. **Read the whole error chain, not the headline.** The outer frame names the first awaited
   entry; the inner `client-modules: bundle <path> compile error` clause names the exact file.
   Attribute to the bundle path, never to the loader entry.
2. **Bisect by recency, not by the error.** Only one thing changed: the `insert` row
   `dsh-profiles` in `profile/cordis.patch.yml`. Remove that one row and reboot — if plugins
   load, the culprit is confirmed. Never start editing stock packages the error names.
3. **Cheap static check:** scan each served `lib/client.js` for top-level `import ` /
   `export ` statements (a one-line grep: `rg -n "^(import|export)\\b" lib/client.js`), or
   parse each bundle as a *classic script* (e.g. `new Function(source)` / acorn with
   `sourceType: 'script'`). Any bare ESM statement fails the check; the position will match
   the reported `1:1`.

### The packaging contract an external client plugin must ship

The bundle must be a **factory-wrapped CommonJS-flavored classic script**, exactly like the
working excerpt:

```js
window.__ModuleLoader__.load({
  id: "@lhh010/dsh-profiles",
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");            // or require("react/jsx-runtime")
    // ... component definitions ...
    const inject = ["slots"];
    function apply(ctx) { /* ctx.slots.inject(...) ... */ }
    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  },
});
```

- **What wraps the code:** `window.__ModuleLoader__.load({ id, factory })`. Executing the
  bundle only registers the factory; side effects live inside the factory closure and run at
  materialization.
- **How React is obtained:** via the factory's synchronous `require` (`require("react")`,
  `require("react/jsx-runtime")`, `@deepseek-ai/dsh-client-ui-primitives`, ...). These resolve
  against the shell's **frozen platform module table** (`PLATFORM_MODULES`: React, Cordis,
  static UI libraries); non-baseline requests must be declared in `package.json` under
  `dsh.client.external`. Never an ESM `import` — the combo is a classic script.
- **What the wrapper must export:** the Cordis plugin object — `apply(ctx)` (required) and
  optionally `inject` (e.g. `["slots"]`). The factory returns `module.exports`.
- Additionally, the user's bundle had a **top-level DOM side effect**
  (`document.body.appendChild(host)` + `createPortal` at module scope). In the factory model,
  side effects run at materialization; mounting UI belongs inside the registered slot
  component / `apply`, not at module top level. The package must also declare `dsh.client`
  (`platform: 'web'`, `exports: './client'`) in `package.json`, and `lib/client.js` must be a
  built artifact that exists before launch.

---

## 3. Failure 2 — `slot "settings.section" is not declared (a parent entry's children table must declare it)`

### Who declares slots

In the vendored Cordis loader, a slot belongs to the **entry whose `slots`/children table
declares it** (`dsh-client-ui-settings` declares `settings.section` in its entry config). The
slot registry enforces ownership: an entry may only `register` a slot that its own entry (or an
owning parent entry's children table) declares. `@lhh010/dsh-profiles` declared nothing, so its
bare `ctx.slots.register({ name: 'settings.section', ... })` failed **at apply time** with the
ownership error. Note this failure is per-plugin and late (all other plugins rendered normally on
that boot) — unlike failure 1, which was combo-wide and at parse time.

### The exact wrapping form the registration must use

Use `ctx.slots.inject(slotName, callback)` so the registration **defers until the declaring
entry exists**, then register inside the callback. This is exactly what the stock
`dsh-client-ui-agent-preset` plugin ships:

```js
ctx.slots.inject("settings.section", () => ctx.slots.register({
  name: "settings.section",
  id: "agent-presets",
  order: 20,
  label: () => ctx.locale.bind("settings.agentPreset")("nav"),
  locale: "settings.agentPreset",
  inject: sectionInjected,
}, AgentPresetSection));
```

For the profiles plugin:

```js
ctx.slots.inject("settings.section", () => ctx.slots.register(
  { name: "settings.section", id: "profiles-manager", order: 5 },
  ProfilesSection,
));
```

### Which fields a registrant may pass and which it must not

- **May pass — child fields:** `name` (must match the declared slot), `id` (this plugin's child
  id), `order`, presentation fields like `label`/`locale`, and the component.
- **Must not pass — slot-defining/ownership metadata:** `kind`, `scope` (and any other
  declaration-time slot configuration). Those belong to the declaring entry
  (`dsh-client-ui-settings`); a registrant re-declaring them is exactly the cross-entry
  ownership violation the error describes. The plugin must also declare `inject: ["slots"]`
  on the plugin object (per the cordis-client-runner guard, using `ctx.slots` requires
  declaring the service in `inject`).

---

## 4. Dev-loop discipline

### Why edits don't reach the browser

Per `dsh-client-modules`: the host half snapshots each client bundle **once at boot** and
concatenates the combo; the combo line appears once per boot. Bundle content changes reach the
graph only through `rebuilt()` (the HMR hook used by the repo's own `pnpm run dev:web`
watcher for its built artifacts) — an **external** plugin's `lib/client.js` on disk is not
watched, so editing it changes nothing in the browser, even after a hard refresh, until the host
process restarts and recomposes.

### The correct restart procedure

1. Stop the host process **and its whole child process tree** (see below); verify the port is
   actually free (`Get-NetTCPConnection -LocalPort <port>` / `netstat -ano`).
2. Start the host again; confirm the boot log shows the
   `client-modules: composed N loader entries ...` combo line.
3. Hard-refresh the browser, then check **Settings → Plugins → Plugin list** — an empty list
   means the combo failed to parse again (bisect per §2 before touching anything else).

### Why the Windows restart died with EADDRINUSE

Closing the launching terminal does not reliably kill the node process tree on Windows: the host
server process survived as an orphan and kept the listening socket bound, so the next boot's
`listen()` failed with `EADDRINUSE`. Killing only the visible process was insufficient; the
fix was killing the entire tree — `taskkill /PID <pid> /T /F` — after which the port freed and
the next boot bound normally. The takeaway: stop the host through a mechanism that reaps the
whole tree (managed job / explicit tree kill), and check the port before concluding anything
about the plugin.

---

## 5. Prevention

### Host-side

1. **Per-bundle parse validation at composition time.** Before concatenating, parse each
   snapshot as a classic script (acorn `sourceType: 'script'` or `new Function`). On failure,
   fail loudly at boot naming the owning plugin package and bundle path
   (`@lhh010/dsh-profiles lib/client.js: top-level import at 1:1 — client bundles must use the
   window.__ModuleLoader__.load factory form`) instead of serving a combo that will fail
   wholesale in the browser.
2. **Accurate combo-failure attribution.** When an entry import fails, the runtime knows which
   combo URL it belongs to and which bundles were concatenated into it; the error should list
   every member bundle (or the parsed culprit) rather than naming only the first awaited entry.
   Bundling an Indexed Source Map with authored sections (already done) plus an owning-plugin
   prologue comment per chunk would let the browser-side error name the plugin directly.
3. Optional: a boot-time self-test that materializes each registered factory once after combo
   evaluation, converting late apply-time failures (like failure 2) into boot diagnostics.

### Authoring-side template / checklist for external UI plugins

- `package.json`: `dsh.client` declaration with `platform: 'web'`, `"exports": "./client"`;
  any non-baseline module requests listed in `dsh.client.external`; build step produces
  `lib/client.js` before launch.
- `lib/client.js`: wrapped as `window.__ModuleLoader__.load({ id, factory: (require) => {...} })`;
  **no top-level `import`/`export`**; React and UI primitives via `require(...)` against the
  platform baseline; **no top-level DOM side effects**; factory returns `module.exports`
  containing `apply(ctx)` and `inject` (e.g. `["slots"]`).
- Slot usage: for slots owned by other entries, always `ctx.slots.inject("<slot>", () =>
  ctx.slots.register(...))`; pass only child fields (`name`, `id`, `order`, `label`, component);
  never re-declare `kind`/`scope` owned by the declaring entry.
- Install: link the package into the web profile's `node_modules` and add one `insert` row in
  `cordis.patch.yml`.
- Verification loop after each edit: rebuild → stop host **process tree**
  (`taskkill /PID <pid> /T /F` or managed stop) → confirm port free → start host → confirm
  combo line in boot log → hard refresh browser → **Settings → Plugins → Plugin list must be
  non-empty** → check the host log for per-entry apply errors.
- When a load error names a stock package you never touched: read the inner bundle path in the
  error, and bisect by removing your newest `insert` row first.
