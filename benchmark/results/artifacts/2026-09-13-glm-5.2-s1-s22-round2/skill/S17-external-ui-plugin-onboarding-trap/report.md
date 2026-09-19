# S17 · External UI Plugin Onboarding Trap — Analysis Report

Task: S17-external-ui-plugin-onboarding-trap (read-only diagnosis)
Method: plugin-upgrade skill, Mode A (inspect) — no files outside the designated output
directory were written; the fixture directory was only read.
Evidence: `environment/fixture/` (browser-error.txt, host-boot-log.txt, plugin-apply-error.txt,
plugin/lib/client.js, profile/cordis.patch.yml, restart-notes.txt, working-plugin-excerpt.txt),
cross-checked against the installed host's shipped source
(`@deepseek-ai/dsh-client-modules`, `@deepseek-ai/dsh-client-ui-renderer`) and the skill's
troubleshooting/pre-flight references.

## 1. Failure 1 — why one bare-ESM client bundle killed EVERY plugin's registration

**Root cause.** At boot the host-side `dsh-client-modules` service scans every Loader entry
whose package declares a client half, reads each plugin's client bundle from disk, and
**concatenates all of them into one combo served as a single classic `<script>`** — the boot
log records exactly this: `client-modules: composed 53 loader entries into client bundle combo
(4.5 MB, classic script)`. The shipped source confirms the transport: the default bundle-load
hook is a "same-origin external classic script", and the combo is stamped with an indexed
source map and served as `text/javascript`.

A classic script is parsed as a whole. The user's `lib/client.js` begins with a top-level ESM
`import React from 'react'`, which is a *syntax* error anywhere in a classic script — so the
entire 53-entry combo fails to **compile**, not just the offending plugin. Nothing in the combo
executes, so `window.__ModuleLoader__` registers zero factories, the module table stays empty,
and every plugin — including the two stock ones that rendered fine before the insert —
disappears. The browser error itself carries the proof: the parenthetical names the real
culprit, `bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)`
(position 1:1 = the top-level `import` token at the very first character).

**Why the error names `@deepseek-ai/dsh-typert-registry`.** After the combo fails, the
browser-side plugin loader tries to import the entry graph and reports the **first awaited
loader entry** it failed on. `dsh-typert-registry` is simply the entry that happened to be
awaited first; it is a stock host package the user never touched. The error names *where the
loader gave up*, not *which bundle broke the combo* — a classic misleading-first-frame
attribution (the same symptom family the skill's troubleshooting table records for
`Failed to load plugins: failed to import loader entry <id>` with zero registrations; see also
card DSH-0.1.2-A1-20 for the related "one dropped client module fails every client plugin's
registration" mechanism).

## 2. Diagnosis discipline and the required client-bundle format

**Locating the culprit from the misleading error:**

1. Read the *whole* error chain, not the first line — the parenthetical
   `bundle <path> compile error (position 1:1)` names the offending bundle and position
   directly.
2. If the chain were truncated: **bisect the patch layer's `insert` rows** — the profile has
   exactly three (`dsh-brand-version`, `dsh-file-trace`, `dsh-profiles`); remove the newest
   insert, restart, confirm the combo compiles, re-add. Two reboots bound the culprit.
3. **Cheap static check** that flags the offending bundle without any boot: scan every shipped
   client bundle for top-level ESM tokens, e.g.
   `rg -n "^(import |export )" <plugin>/lib/client.js` (plus `import.meta` / bare `export {}`).
   Position 1:1 hits = bare ESM. Symmetrically, a *valid* bundle's first token is
   `window.__ModuleLoader__.load(`.

**The packaging contract an external plugin must ship** (visible verbatim in
`working-plugin-excerpt.txt` and in `dsh-client-modules`'s documented "lazy CJS table" model):

- The code is wrapped in a registration call:
  `window.__ModuleLoader__.load({ id: "<package name>", factory: (require) => { ... } })`.
  Executing the bundle only *registers* the factory; all side effects live inside the factory
  closure and run at materialization.
- **React is not imported and not bundled.** It is obtained through the factory's `require`
  argument from the shared in-browser module table: `require("react")`,
  `require("react/jsx-runtime")`, `require("@deepseek-ai/dsh-client-ui-primitives")`, etc.
- The wrapper must **return `module.exports` carrying the Cordis plugin object** — `apply(ctx)`
  and optionally `inject: [...]` — and the registration `id` must equal the package's
  `package.json` `name` (a mismatch trips the `loaded without registering "<id>"` assertion).

The user's bundle violated all of this: bare ESM imports, a hand-rolled DOM portal executed at
module top level (`document.body.appendChild` / `createPortal` outside any lifecycle), and an
ESM `export function apply` instead of the loader-wrapper export.

## 3. Failure 2 — `slot "settings.section" is not declared (a parent entry's children table must declare it)`

**Who declares slots.** In the Web Client's slot system, a slot like `settings.section` is
*owned* by the entry that renders the settings surface: that parent entry declares the slot in
its **children table** (`entry.children[key]` — confirmed in the shipped
`dsh-client-ui-renderer` source, which throws `SlotOwnershipError` exactly when
`entry.children?.[key] === undefined`). The declarer owns the slot's structural metadata
(`kind`, `scope`); other plugins only *contribute children* to it.

**Why the bare registration failed at apply time.** Cross-entry apply order is undefined. The
repackaged plugin now loaded, but its `apply` ran `ctx.slots.register({ name:
'settings.section', kind: 'section', scope: 'settings', ... })` directly. When that lands
before the owning settings entry has declared the slot in its children table, the registry
finds no declaration for `settings.section` and throws at apply time — which is why *only*
this plugin failed on the second boot while everything else loaded normally.

**The correct wrapping form** (per the skill's troubleshooting row for this exact message):
defer the registration until the declaration exists —

```js
function apply(ctx) {
  ctx.slots.inject('settings.section', () =>
    ctx.slots.register(
      { name: 'settings.section', id: 'profiles-manager', order: 5 },
      ProfilesSection,
    ),
  )
}
```

**Field ownership:** a cross-entry registrant may pass `name`, `id`, `order` (and a `label`
where the slot renders one). It must **not** pass `kind` or `scope` — those belong to the
declaring entry's children table and re-specifying them is both redundant and part of what
makes the bare form invalid. (The component itself should be rendered by the host's slot
machinery, not by the plugin's own `createPortal` into `document.body`.)

## 4. Dev-loop discipline — boot-assembled combo and the Windows EADDRINUSE restart

**Why edits don't appear.** The combo is assembled **once per host boot**: the host reads every
installed plugin's client bundle from disk, concatenates, and serves the result. There is no
watcher over plugin files; the shipped `dsh-client-modules` source states bundle *content*
changes reach the graph only through an explicit registry `rebuilt` notification — i.e. a
host-side rebuild/restart. Editing `lib/client.js` on disk afterwards changes nothing in the
browser, even after a hard refresh, because the browser keeps fetching the same boot-time combo
artifact. (Note the asymmetry the fixture hints at: client-half artifacts are re-fetched per
refresh, but the *combo bytes* are fixed at boot; host-half routes likewise register once at
apply — see the S19 stale-host family for the matching symptom.)

**Correct restart procedure** (from restart-notes.txt, and it is the right discipline):

1. Fully stop the host **process tree** (not just the terminal window).
2. Start the host; verify the boot log shows the combo line composed once.
3. Hard-refresh the browser.
4. Verify Settings → Plugins → Plugin list is non-empty — an empty list means the combo failed
   to compile again (go back to step 1 and the static ESM check).

**Why Windows died with EADDRINUSE.** Closing the launching terminal does not reliably kill
the node process tree on Windows: an orphaned node process kept the listening port bound, so
the next host boot could not bind and died with `EADDRINUSE`. Only killing the entire tree —
`taskkill /PID <pid> /T /F` — released the port; the following boot bound normally. So the
dev loop's "stop" step must terminate the tree explicitly (or use the host's own shutdown
path), never assume the terminal close did it.

## 5. Prevention

**Host-side (what DSH could do):**

- **At combo-compile failure, attribute per bundle.** Compile each entry's bundle bytes
  independently (e.g. `new Function` parse or per-bundle syntax check) before concatenating,
  so the failure surfaces as `package @lhh010/dsh-profiles: bundle compile error at 1:1 —
  top-level ESM in a classic-script combo` instead of a whole-combo abort named after the
  first awaited entry.
- **Startup bundle validation gate:** reject any client bundle whose first token is not
  `window.__ModuleLoader__.load(`, or that contains top-level `import`/`export` tokens, and
  check the registration `id` equals the package name — fail loud at boot with the package
  named (mirrors the existing build-time "bundle purity gate" the runtime already documents).
- **Browser error rewrite:** when the module table is empty after a combo compile failure,
  report "client bundle combo failed to compile; offending bundle: <path>" rather than
  `failed to import loader entry <first-awaited-id>`.
- **Port diagnostic:** on `EADDRINUSE`, print the PID/process holding the port and the
  `taskkill /PID <pid> /T /F` recovery command.

**Authoring-side template / onboarding checklist for an external Web-Client plugin:**

1. `package.json` with `name` used verbatim as the bundle registration id; declare the client
   half per the `dsh.client` manifest convention.
2. Client bundle shipped as the loader wrapper: `window.__ModuleLoader__.load({ id, factory:
   (require) => { ...; return module.exports } })` — no top-level `import`/`export`, no
   top-level DOM side effects (everything inside `apply`/factory).
3. React and host UI packages via `require("react")` / `require("react/jsx-runtime")` from the
   shared table — never bundled, never ESM-imported.
4. Foreign slots (`settings.section`, `conversation.*`, …) registered only via
   `ctx.slots.inject(name, () => ctx.slots.register(...))`, passing `name`/`id`/`order`
   (± `label`) and never `kind`/`scope`.
5. Pre-flight static gate before every install/upgrade:
   `rg -n "^(import |export )" lib/client.js` must be empty, and the first token must be the
   loader wrapper (the skill's pre-flight class #5 `__ModuleLoader__|PLUGIN_ID` patterns).
6. Dev loop: edit → stop the whole host process tree (`taskkill /T /F` on Windows) → start →
   hard refresh → check the plugin list is non-empty; treat an empty list as "combo compile
   failed again", not as "my plugin is broken alone".
7. Installation: link into the profile's `node_modules` + exactly one `insert` row in
   `cordis.patch.yml` (no duplicate ids — duplicates are a fatal Cordis composition error).

## Report per the skill's structure

- **pre-existing / baseline**: not collected (read-only Mode A diagnosis; no builds or tests
  were run, per the task's no-execution boundary).
- **Completed**: full root-cause attribution for all three failures, grounded in the fixture
  evidence, the installed host's shipped `dsh-client-modules` / `dsh-client-ui-renderer`
  source, and the skill's troubleshooting table; corrective registration snippet and
  prevention recommendations delivered above.
- **Skipped**: no migration/installation/validation executions (task is read-only analysis);
  fixture files untouched.
- **Pending/residual risk**: field ownership of slot fields beyond `name`/`id`/`order`/`label`
  is stated from the skill's troubleshooting guidance plus fixture comparison, not verified
  against a live host run (execution forbidden by the brief).
- **Rollback**: nothing to roll back — no writes outside the report directory.
- **Recommendations**: adopt the host-side and authoring-side prevention items in §5; consider
  an official external-plugin template repository exposing the wrapper scaffold.
