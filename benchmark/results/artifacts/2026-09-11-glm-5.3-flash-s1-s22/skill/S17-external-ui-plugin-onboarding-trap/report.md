# S17 · External UI Plugin Onboarding Trap — Diagnostic Report

Subject: onboarding of the hand-written external web UI plugin `@lhh010/dsh-profiles` into the web profile, installed the community way (directory linked into the profile's `node_modules` plus one `insert` row in `cordis.patch.yml`). Three chained failures analyzed from the read-only evidence pack.

## 1 · Failure 1 root cause — one bad bundle took down EVERY plugin's registration, and the error named an innocent stock entry

**Evidence (browser-error.txt):**
`Failed to load plugins: failed to import loader entry 0c013085 (@deepseek-ai/dsh-typert-registry): client-modules: bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)` — and the plugin list was EMPTY; both previously working stock plugins (brand version, file tracking) vanished from the header.

**What the host assembles and in what form (host-boot-log.txt):**
`[boot] client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)`. At host boot the host reads every installed plugin's client bundle and **concatenates them into one classic (non-module) `<script>`** — the "client bundle combo". All plugin registrations share that single script.

**Why one plugin killed everything:** the culprit's bundle (`plugin/lib/client.js`) begins with top-level ESM:

```js
import React from 'react'
import { createPortal } from 'react-dom'
```

A top-level `import` is not valid syntax inside a classic script. The browser's parser hit `import` at **position 1:1** of that bundle segment, so the ENTIRE combo script failed at compile time. Because all 53 entries ride in that one script, a compile error anywhere in it prevents `window.__ModuleLoader__.load(...)` from ever executing for any entry — hence zero registrations, not just the offender's.

**Why the error named `dsh-typert-registry`:** that package is a stock host entry the user never touched. It was simply the **first awaited loader entry** in the combo: when the combo script throws at compile/evaluation time, the loader reports the failure against the first entry it was awaiting, not against the bundle whose text is syntactically invalid. The discriminating clue is in the error's own detail text — it names the real file: `bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)`.

**Corroborating card:** skill reference v0.1.5-alpha.1, card A1-20 — "one dropped module fails every client plugin's registration"; troubleshooting.md row: "Browser: `Failed to load plugins: failed to import loader entry <id>`, then **zero** plugins register — the named `<id>` is only the first awaited entry (e.g. `dsh-typert-registry`, innocent); some plugin's client bundle contains raw ESM".

## 2 · Diagnosis discipline and the correct external client-bundle format

**Locating the culprit from the misleading error:**
1. Read past the named entry — treat `@deepseek-ai/dsh-typert-registry` as innocent (it ships with the host; the user never modified it).
2. Bisect the patch layer's `insert` rows (profile/cordis.patch.yml): the new row in this incident is `id: dsh-profiles / name: '@lhh010/dsh-profiles'`. Comment out the newly added insert row, restart, reload — if plugins register again, the newest row's bundle is the culprit.
3. Cheap static check that flags the offending bundle without any runtime: **grep the candidate bundle for top-level ESM tokens** — `^import ` / `^export ` / `import(` at file top level — or simply read the first line: `position 1:1` in the compile error points exactly at line 1 of `client.js`, which is `import React from 'react'`.
4. Confirm against a working peer: `working-plugin-excerpt.txt` shows what a valid bundle looks like — no import/export statements, dependencies obtained via `require(...)` inside the factory.

**The packaging contract an external plugin must ship instead of bare ESM** (matching the working excerpt verbatim):
- The bundle's entire code is wrapped in a **`window.__ModuleLoader__.load({ id, factory })`** registration call — a classic-script IIFE-style wrapper, no ESM syntax anywhere.
- `id` must equal the package name (`"@lhh010/dsh-profiles"`; the excerpt shows `"@local/dsh-brand-version"`), i.e. matching `package.json` `name` and the patch row's `name`.
- **React is obtained by CommonJS `require` inside the factory**, e.g. `require("react/jsx-runtime")`, `require("@deepseek-ai/dsh-client-ui-primitives")` — never a top-level `import`; the host provides the modules to the factory's `require`.
- Inside the factory: `var module = { exports: {} }; var exports = module.exports;`, and the factory must **`return module.exports`** — that returned value is the plugin's client module (containing `apply` and `inject`).
- The excerpt also declares `const inject = ["slots"]` and its `apply(ctx)` performs the slot registrations — inject must declare what `apply` reads.

## 3 · Failure 2 — `slot "settings.section" is not declared (a parent entry's children table must declare it)`

**Evidence (plugin-apply-error.txt):** after repackaging (fixing failure 1), the second boot loads all other plugins normally but fails this one: `failed to apply loader entry (@lhh010/dsh-profiles): slot "settings.section" is not declared (a parent entry's children table must declare it)`.

**What it means:** slots are **declared by their owning (parent) entry** in a children table. `settings.section` is a slot owned by another entry (the settings UI host entry). Apply order across loader entries is **undefined** — the new plugin's registration can execute before the owner has declared the slot, so a bare `ctx.slots.register({ name: 'settings.section', ... })` (exactly what `plugin/lib/client.js` does) fails at apply time when the declaration does not exist yet.

**The offending code (plugin/lib/client.js):**
```js
ctx.slots.register(
  { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
  ProfilesSection,
)
```

**The exact wrapping form required:** a cross-entry registration must be **deferred via `ctx.slots.inject`**, which registers a contribution that attaches once the parent entry's declaration exists (troubleshooting.md, cards DSH-0.1.2-A1-25 / A1-26):

```js
ctx.slots.inject('settings.section', () => ctx.slots.register(
  { name: 'settings.section', id: 'profiles-manager', order: 5 },
  ProfilesSection,
))
```

**Which fields a registrant may pass and which it must not:** the registrant may pass only **`name`, `id`, `order`** (plus display fields such as `label`); it must **not** pass `kind` or `scope` — those belong to the parent entry's slot declaration, not to a child registration. The offending call passes both `kind: 'section'` and `scope: 'settings'`, which is outside the registrant's authority even after the ordering fix.

## 4 · Dev-loop discipline — the boot-assembled combo and the Windows restart trap

**Why plugin edits have no effect (host-boot-log.txt, restart-notes.txt):** the combo line — `client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)` — appears **once per boot**. At boot the host reads every plugin's client bundle from disk, concatenates them into one classic script, and serves that static combo; the browser only ever fetches that boot-time artifact. Editing a plugin file on disk afterwards changes nothing in the browser, even after a hard refresh, until the **host process itself** is stopped and restarted. (Same class of asymmetry as the S19 stale-host incident: the client plane refreshes per page load, but the artifact it fetches is frozen at boot.)

**Correct restart procedure (restart-notes.txt):**
1. Stop the host **fully** — verify the node process is actually gone (closing the launching terminal window is not a stop on Windows; a browser refresh is never a host stop).
2. If an orphan survives, kill the entire process tree: `taskkill /PID <pid> /T /F`.
3. Start the host again, **hard-refresh the browser**, then check Settings → Plugins → Plugin list — an empty list means the combo failed again.

**Why EADDRINUSE happened (restart-notes.txt item 2):** closing the launching terminal on Windows left the previous host's node process **alive and orphaned, still holding the listening port**. The next boot tried to bind the same port and died with `EADDRINUSE`. Only killing the whole process tree (`/T /F`) released the port; the subsequent boot bound normally. The skill's global-upgrade discipline states the same invariant: "a running host holds native-module file locks → EBUSY … a browser refresh is not a host stop" — here the analogous resource is the TCP listener.

## 5 · Prevention

**Host-side — name the offender instead of the first awaited entry:**
- At combo-assembly time, statically validate each entry's bundle text **before concatenation**: reject any bundle containing top-level ESM syntax (`import`/`export` statements) with a per-plugin error, e.g. `plugin @lhh010/dsh-profiles: bundle lib/client.js uses ESM `import` at line 1 — classic-script combo requires __ModuleLoader__.load wrapper`. Position 1:1 of the culprit is already known at assembly time, so the host can attribute precisely; today it defers to the browser and the first awaited entry takes the blame.
- Alternatively assemble each entry as a separately attributed segment (per-entry `new Function` compile or per-entry script tags under a single loader) so a compile failure is caught per-entry with the entry id, and a single bad bundle degrades to skipping that one plugin instead of zero plugins registering.
- At apply time, on the undeclared-slot error, include both the registrant's id and the declaring entry's id, and hint at the `ctx.slots.inject(name, ...)` wrapper.
- Optionally emit a startup roster line ("combo N entries; entries failing compile: [ids]") so the Plugin list being empty is immediately attributable.

**Authoring-side — external-plugin template / checklist (would have prevented all three failures):**
1. **Bundle format:** ship a classic-script bundle wrapped in `window.__ModuleLoader__.load({ id, factory })`; `id` === `package.json` `name` === the patch row's `name`; the factory ends with `return module.exports`. No `import`/`export` anywhere. CI/local check: `grep -nE '^\s*(import|export)\s' lib/client.js` must return nothing.
2. **Dependencies:** obtain React and host packages via `require("react/jsx-runtime")`-style calls inside the factory; declare `const inject = [...]` for every `ctx.*` surface `apply` touches (`inject = ["slots"]` here).
3. **Cross-entry slots:** never bare-`register` a slot owned by another entry (`settings.section`, `conversation.*`, …). Always wrap: `ctx.slots.inject('<slot>', () => ctx.slots.register(...))`; pass only `name`/`id`/`order`(/`label`) — never `kind`/`scope`.
4. **Dev loop:** after any plugin-file edit, fully stop the host (confirm the node process exited; on Windows use `taskkill /PID <pid> /T /F` for orphans), restart, hard-refresh, and verify the Plugin list is non-empty before judging the change. Never conclude an edit "did nothing" without a host restart.
5. **First-mount validation:** per the skill's validation layer 4, do not accept a bare page load — verify registration/mount from Settings → Plugins, and compare against a known-working plugin's bundle shell (as done with the `@local/dsh-brand-version` excerpt).

## Evidence index
- `browser-error.txt` — first-boot combo compile failure naming `@deepseek-ai/dsh-typert-registry`, empty plugin list.
- `plugin/lib/client.js` — top-level `import React`/`import { createPortal }`, bare `ctx.slots.register` with `kind`/`scope`, no `__ModuleLoader__` wrapper.
- `profile/cordis.patch.yml` — the `dsh-profiles` insert row (`@lhh010/dsh-profiles`).
- `plugin-apply-error.txt` — second-boot undeclared-slot failure for `settings.section`.
- `host-boot-log.txt` — 53-entry classic-script combo composed once per boot.
- `restart-notes.txt` — combo frozen at boot; orphaned node process → EADDRINUSE; `taskkill /T /F` recovery.
- `working-plugin-excerpt.txt` — the correct `window.__ModuleLoader__.load({ id, factory })` shell with `require` and `return module.exports`.
