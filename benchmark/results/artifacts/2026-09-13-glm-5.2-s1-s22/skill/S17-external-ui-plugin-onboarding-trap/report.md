# S17 · External UI Plugin Onboarding Trap — Analysis Report

Task: S17-external-ui-plugin-onboarding-trap (read-only diagnosis)
Mode: A · inspect (plugin-upgrade skill). No files outside the designated output directory were written; the fixture is untouched.

Evidence used (read-only): `fixture/browser-error.txt`, `fixture/plugin/lib/client.js`, `fixture/profile/cordis.patch.yml`, `fixture/plugin-apply-error.txt`, `fixture/working-plugin-excerpt.txt`, `fixture/host-boot-log.txt`, `fixture/restart-notes.txt`, plus the plugin-upgrade skill's `references/troubleshooting.md`, `references/v0.1.2-alpha.1.md` (cards DSH-0.1.2-A1-25/A1-26) and `references/v0.1.5-alpha.1.md` (card DSH-0.1.5-A1-20).

Incident identity: hand-written external Web Client plugin `@lhh010/dsh-profiles`, installed the community way — directory linked into the web profile's `node_modules` plus one `insert` row in `profile/cordis.patch.yml` (`- insert: - id: dsh-profiles / name: '@lhh010/dsh-profiles'`, alongside the two pre-existing rows `dsh-brand-version` and `dsh-file-trace`).

---

## 1. Failure 1 — why ONE bad client bundle killed EVERY plugin's registration, and why the error named `dsh-typert-registry`

**What the host assembles and serves.** At boot, the host's client-modules layer resolves the profile's patch rows (host log: `[boot] cordis patch layer: 3 insert rows resolved`), reads every installed plugin's client bundle (`lib/client.js`), and concatenates them into ONE classic-script combo (`[boot] client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)`). That single combo is what reaches the browser — served over the combo route (`/plugins/??<name>/client.js&rev=...`, cf. card DSH-0.1.2-A1-26) and advertised through the boot manifest. There is no per-plugin isolation: all client halves execute inside one `<script>` and register through `window.__ModuleLoader__.load({ id, factory })`.

**Why one ESM `import` fails everything.** The plugin as written (`plugin/lib/client.js`) begins with top-level ESM statements:

```js
import React from 'react'
import { createPortal } from 'react-dom'
...
export function apply(ctx) { ... }
```

A classic `<script>` (non-module) is parsed and compiled as a whole. `import`/`export` are only legal at the top level of a module; inside a classic script they are a SyntaxError at **compile time**, before ANY byte of the combo executes. Because all 53 loader entries share one script, one illegal token aborts the entire combo — hence zero plugins register, the Plugin list is EMPTY, and even the previously-fine stock plugins (`dsh-brand-version`, `dsh-file-trace`) vanish. The browser error confirms both halves: `bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)` — the offending bundle and the exact position of the first `import` — wrapped in `failed to import loader entry 0c013085 (@deepseek-ai/dsh-typert-registry)`.

**Why the error names `dsh-typert-registry`.** After the combo's failure, the loader's import/activation step awaits its entries in order and surfaces the **first awaited entry** — `@deepseek-ai/dsh-typert-registry`, a stock host package early in the roster. It is innocent: it never executed because nothing in the combo executed. The named id is a reporting artifact of the await order, not the culprit (same attribution trap as card DSH-0.1.5-A1-20, where the first *unregistered* entry — also innocent — got named while every client plugin failed). The real culprit is stated one clause later in the same message: the `compile error` bundle path `@lhh010/dsh-profiles`.

## 2. Diagnosis discipline and the required client-bundle format

**Locating the culprit from the misleading error.**
1. Read the whole error, not the first id: the parenthetical `bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)` names the offending bundle and the offset of the offending token. When only `failed to import loader entry <id>` is available, treat `<id>` as "first awaited entry", not as guilt.
2. Cheap static check that flags the offending bundle: scan every assembled bundle for top-level ESM tokens, e.g. `rg -n "^\s*(import|export)\b" <profile>/node_modules/*/lib/client.js` — or per the skill's pre-flight pattern, `rg -n "__ModuleLoader__|PLUGIN_ID" .`: a bundle that does NOT contain a `window.__ModuleLoader__.load({...})` wrapper is suspect; a hit of a bare top-level `import`/`export` is conclusive.
3. If still ambiguous, bisect the patch layer's `insert` rows: boot with only stock rows, then add the user rows one at a time (`dsh-brand-version`, `dsh-file-trace`, `dsh-profiles`). The failure returns exactly when `dsh-profiles` re-enters — pinning the culprit without touching the stock packages.
4. Cross-check against a known-good bundle from the same profile (`working-plugin-excerpt.txt`) — the diff immediately shows the missing `__ModuleLoader__.load` shell.

**The packaging contract an external plugin must ship** (from the working excerpt):
- The bundle must be a **classic script** wrapped in `window.__ModuleLoader__.load({ id, factory })` — NOT bare ESM.
- `id` must equal the package.json `name` exactly (`@lhh010/dsh-profiles`); otherwise the boot assertion `loaded without registering "<id>"` fires (card DSH-0.1.2-A1-26).
- The `factory: (require) => {...}` closure receives a CommonJS-style `require`; **React is obtained inside the factory** via `let react_jsx_runtime = require("react/jsx-runtime")` (or `require("react")`) — never via a top-level `import`, and never bundled as a second React copy. Host-provided client packages (e.g. `@deepseek-ai/dsh-client-ui-primitives`) are required the same way, backed by `dsh.client.inject` declarations in package.json.
- The factory builds `var module = { exports: {} };`, marks it with `Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" })`, defines the plugin (`const inject = ["slots"]` and `function apply(ctx) {...}`), and returns `module.exports`. The wrapper must export the Cordis plugin face: at minimum an `apply(ctx)` (plus its `inject` list, e.g. `["slots"]`).
- Side effects like mounting a DOM host (`document.createElement('div')` + `createPortal`) belong inside the component/apply flow, not at bundle top level; rendering happens through slot registration, not by self-mounting on load.

## 3. Failure 2 — `slot "settings.section" is not declared (a parent entry's children table must declare it)`

**Who declares slots.** Slots are *declared* by the entry that owns the parent surface: the settings entry's own manifest/children table declares `settings.section` (and each child's `kind`/`scope`). Apply order across loader entries is undefined, so when a foreign plugin executes `ctx.slots.register({ name: 'settings.section', id: ..., kind: 'section', scope: 'settings' }, Component)` as a **bare registration at apply time**, that call can land *before* the owning entry has declared the slot — the registry rejects it with exactly this error. The plugin is registering a slot another entry owns, not one it owns.

**The exact wrapping form.** Per the skill's troubleshooting table (citing DSH-0.1.2-A1-25/A1-26), the registration must be wrapped so it runs only once the parent's declaration exists:

```js
ctx.slots.inject('settings.section', () =>
  ctx.slots.register({ name: 'settings.section', id: 'profiles-manager', order: 5 }, ProfilesSection)
)
```

The `inject(name, callback)` form defers the `register` call until the slot is declared, removing the ordering dependency. That is also what the working excerpt shows (`const inject = ["slots"]` + `ctx.slots.inject(...)` calls inside `apply`).

**Field ownership at the registration site.** The registrant (a child adding itself into an existing parent slot) may pass only:
- `name` (the declared slot path, e.g. `settings.section`),
- `id` (its own child id),
- `order` (and a `label` where the slot's contract takes one).

It must **not** pass `kind` or `scope` — those belong to the declaring parent's children table; a child re-stating them is at best redundant and at worst a conflicting re-declaration. In the user's code, `kind: 'section', scope: 'settings'` must be dropped along with adding the `inject` wrapper. (The user's code also had the argument shape of a slot *renderer* registration combined with self-mounting `createPortal` — the component itself, not a portal mount, is what `register` receives.)

## 4. Dev-loop discipline — boot-assembled combo, restart procedure, and the Windows EADDRINUSE

**Why edits don't appear.** The client bundle combo is assembled exactly ONCE per host boot (host log prints the combo line once; restart-notes point 1). After boot, the host serves that frozen combo; editing any plugin file on disk changes nothing in the browser — a hard refresh re-fetches the same assembled artifact. There is no watch/HMR for external plugin bundles in this dev loop (the harness's client-plugin HMR receiver only reloads without refresh while the repo's `pnpm run dev:web` watcher rebuilds bundles — not applicable to a hand-installed external plugin).

**Correct restart procedure** (per restart-notes and the skill's global-upgrade discipline):
1. Fully STOP the host process — not just close the launching terminal.
2. Confirm the old node process is actually gone (check the port / process list) before starting again.
3. Start the host; verify the fresh combo line in the boot log.
4. Hard-refresh the browser, then check Settings → Plugins → Plugin list — an empty list means the combo failed again (repeat diagnosis); a populated list plus the plugin's DOM/slot output proves registration and mount, not just an HTTP 200 on the bundle.

**Why the Windows restart died with EADDRINUSE.** On Windows, closing the launching console can leave the node host process alive (the listening socket is inherited/held by a surviving child of the original tree). The next boot cannot bind the still-held port → `EADDRINUSE`. Because the orphan is a *process tree* (launcher → node → children), ending just one PID may not release the port; the user had to kill the whole tree: `taskkill /PID <pid> /T /F`. This mirrors the skill's global rule that a running dsh host holds native-module/file/port locks and must be fully stopped before any install/restart — a browser refresh is never a host stop.

## 5. Prevention

**Host-side (attribute instead of implicating the first awaited entry):**
- At combo-assembly time (boot), statically validate each contributed bundle before concatenation: reject/flag any bundle containing top-level `import`/`export` outside a `__ModuleLoader__.load` factory, or lacking the `__ModuleLoader__.load` wrapper entirely, and **name that plugin** in the boot log — this converts the browser-side whole-combo compile error into a per-plugin boot-time diagnosis.
- At combo-failure time in the browser, report the failing bundle path/id from the compile error as the primary diagnosis (it is already known: `bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error`) and demote "first awaited loader entry" to context, so an innocent stock entry (`dsh-typert-registry`) is never the headline.
- On Windows shutdown, ensure child processes are terminated with the host (job object / tree kill), or at boot detect the port-held condition and report the holding PID with the `taskkill /PID <pid> /T /F` remedy instead of a bare EADDRINUSE.

**Authoring-side (external-plugin template / onboarding checklist):**
1. **Client bundle format**: ship a classic script wrapped in `window.__ModuleLoader__.load({ id, factory: (require) => {...} })`; the `id` equals package.json `name`; no top-level ESM; React and host client packages obtained via `require(...)` inside the factory; factory returns `module.exports` carrying `apply` (and `inject`).
2. **Manifest**: package.json declares the client half (`dsh.client`, with `inject` listing only real service packages) and the assembly row in `cordis.patch.yml` uses the bare package name.
3. **Slots**: never bare-register another entry's slot; wrap with `ctx.slots.inject(parentSlot, () => ctx.slots.register(...))`; pass only `name`/`id`/`order`(`label`); never `kind`/`scope` (owned by the parent's children table).
4. **No self-mounting**: render via the slot's component contract; no top-level DOM creation or `createPortal` at module scope.
5. **Dev loop**: host restart (full process-tree stop → start → verify boot combo line) + browser hard refresh after every plugin edit; empty Plugin list = re-diagnose. On Windows, verify the old process tree is dead (`taskkill /PID <pid> /T /F`) before rebooting the host.

---

## Skill report structure

- **pre-existing (baseline)**: not collected — read-only Mode A inspection of a static evidence pack; no build/test baseline applies.
- **Completed**: full root-cause chain for all three failures (whole-combo classic-script compile failure with misleading first-awaited-entry attribution; cross-entry slot declaration ordering and the `slots.inject` wrapper with correct field ownership; boot-assembled combo dev loop and Windows process-tree EADDRINUSE), the required external client-bundle packaging contract, diagnosis procedure (error-parenthetical reading, static ESM/`__ModuleLoader__` scan, insert-row bisection), and host-side + authoring-side prevention. Report written to the designated output directory only.
- **Skipped**: no runtime verification (verify-runtime / token-URL client mount per validation layer 4) — the fixture is static and read-only by task rule; no installations or migrations executed (explicitly disallowed). Card adoption beyond the cited ones not needed — no corridor migration is involved.
- **Pending/residual risk**: line numbers/behavior are inferred from the evidence pack and skill cards (troubleshooting.md rows for the two exact error strings; DSH-0.1.2-A1-25/A1-26; DSH-0.1.5-A1-20), not from a live host repro; exact host-side prevention UX is a recommendation, not a verified patch.
- **Rollback**: nothing to roll back — no files outside `benchmark-runs/glml-5.2-r1/.../report.md` were created or modified; the fixture and skill tree are unchanged.
- **Recommendations**: adopt the host-side boot-time bundle validation and error-attribution improvements upstream; publish an official external-plugin client template implementing checklist items 1–5; consider per-plugin bundle serving or combo isolation so one malformed plugin cannot take down the whole roster.
