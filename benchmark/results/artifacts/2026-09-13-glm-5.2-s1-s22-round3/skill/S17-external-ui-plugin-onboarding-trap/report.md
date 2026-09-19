# S17 · External UI Plugin Onboarding Trap — Analysis Report

Task: attribute a whole-combo client-bundle failure, the external client-bundle packaging
contract, cross-entry slot declaration ordering, the boot-assembled dev loop, and
host/authoring-side prevention. Evidence: the read-only fixture pack under
`environment/fixture` plus primary sources (the installed host's
`@deepseek-ai/dsh-cordis-client-runner` slot ledger / module loader, and the
plugin-upgrade skill's corridor cards). Read-only analysis; nothing outside the designated
output directory was written.

---

## 1. Failure 1 root cause: one bare-ESM client bundle killed EVERY plugin

**What the host assembles.** At host boot, the client-modules layer reads every installed
plugin's client bundle, concatenates them into ONE classic `<script>` combo (host boot
log: `client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic
script)`), and serves that single script to the browser. It is not ES-module loading; the
combo is one shared script whose per-plugin units are `window.__ModuleLoader__.load({ id,
factory })` calls (visible in the working-plugin excerpt and in the shipped
`dsh-cordis-client-runner/lib/client.js`, which itself begins with
`window.__ModuleLoader__.load({`).

**Why one bad bundle kills all registrations.** The offending
`@lhh010/dsh-profiles/lib/client.js` begins with a top-level ESM `import React from
'react'` (position 1:1). In a classic script, `import` is a reserved token that fails at
*compile/parse* time — before ANY line of the concatenated combo executes. A parse error in
one concatenated unit aborts the whole script, so no `__ModuleLoader__.load` call in the
combo ever runs: zero plugins register, the plugin list is empty, and even the two stock
plugins that previously rendered disappear. The failure is all-or-nothing by construction,
not a per-plugin isolation bug.

**Why the error names `dsh-typert-registry`.** The browser-side loader imports/applies
entries in order and reports the *first entry it awaited*, which happens to be the stock
`@deepseek-ai/dsh-typert-registry` — an innocent entry the user never touched. The error
text even carries the real culprit if read carefully: `client-modules: bundle
/plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)`. The entry id in
the headline is attribution noise; the bundle path in the detail is the diagnosis.

## 2. Diagnosis discipline and the required bundle format

**Locating the culprit from the misleading error:**

- Read the whole error, not the headline: the parenthetical names the exact bundle file
  and position (`@lhh010/dsh-profiles/lib/client.js`, 1:1 — column 1 of line 1 is the
  classic signature of a top-level `import`/`export` token).
- Bisect the patch layer: the profile has exactly 3 `insert` rows
  (dsh-brand-version, dsh-file-trace, dsh-profiles); remove/comment the newest row →
  boot heals → re-add to confirm. The newest insert is the prior probability winner.
- Cheap static check that flags the offending bundle before any boot:
  `rg -n "^import |^export |__ModuleLoader__" <profile>/node_modules/*/lib/client.js`
  (the skill's pre-flight pattern). Any client bundle with a top-level
  `import`/`export` and no `window.__ModuleLoader__.load` wrapper is mis-packaged.
  Parsing each bundle with `new Function(...)`-equivalent tooling (node `--check` as
  classic script) achieves the same without a browser.

**The packaging contract an external client bundle must ship** (from the working excerpt
and the shipped runner):

- Wrapped in `window.__ModuleLoader__.load({ id, factory })` — never bare ESM.
- `id` MUST equal the package.json `name` (`@lhh010/dsh-profiles`); typically injected
  by the tsdown banner `PLUGIN_ID` (card DSH-0.1.2-A1-26).
- The `factory: (require) => { ...; return module.exports }` closes over a CommonJS-style
  `module`/`exports` pair; **React is obtained inside the factory via
  `require("react")`** (or `require("react/jsx-runtime")`), from the combo's module
  table — never via a top-level import and never bundled privately (that also avoids a
  second React instance).
- The factory must export the Cordis plugin: an `apply(ctx)` (and typically
  `const inject = ['slots', …]`), returned via `module.exports`.
- No top-level DOM side effects: the user's `document.createElement`/`createPortal`
  body-append at module scope is also wrong form — rendering belongs to the slot
  registration the shell mounts.

## 3. Failure 2: `slot "settings.section" is not declared (a parent entry's children table must declare it)`

**Who declares slots.** Slots are declared by their *owner* entry through the slot core's
children table — a parent entry (e.g. the settings shell occupant of
`sidebar.settings`, `client-ui-settings-general`) declares its children such as
`settings.section` when it mounts. Primary source (shipped runner's slot ledger for
`settings.section`): `declaredBy: "an entry in 'sidebar.settings'
(client-ui-settings-general), so it exists while that entry is mounted"`. The declaration
therefore exists only while the parent entry is applied and mounted.

**Why the bare registration failed at apply time.** The user's repackaged plugin called
`ctx.slots.register({ name: 'settings.section', id: 'profiles-manager', order: 5, kind:
'section', scope: 'settings' }, ProfilesSection)` directly from `apply`. Entry apply
order across combo entries is undefined, so the registration can land *before* the owning
parent has declared the slot — the register-time validation then rejects it with exactly
this message. Note the error correctly names the failing entry this time
(`failed to apply loader entry (@lhh010/dsh-profiles)`) and only that entry fails.

**The exact wrapping form** (the runner's own example for `settings.section`):

```js
return {
  inject: ['slots'],
  apply(ctx) {
    ctx.slots.inject('settings.section', () => ctx.slots.register(
      { name: 'settings.section', id: 'my-entry', order: 100, label: 'My entry' },
      () => React.createElement('div', null, 'hello'),
    ))
  },
}
```

`ctx.slots.inject(name, thunk)` defers the `register` until the owner's declaration
exists, decoupling cross-entry ordering.

**Fields the registrant may pass vs must not:** the registrant supplies only `name`,
`id` (its own cell key — a fresh id adds a new section beside the shipped ones; reusing
a shipped id replaces that cell), `order`, and `label` (string or thunk; locale-owned
display text). It must NOT pass `kind` or `scope` — those belong to the owner's
*declaration* of the slot (here `kind: 'list'`, `scope: 'root'`), not to a registrant;
the user's `kind: 'section'` / `scope: 'settings'` fields are owner metadata the
registrant is attempting to re-declare. The component is passed as the render body.

## 4. Dev-loop discipline: boot-assembled combo and the Windows EADDRINUSE

- **Why edits don't appear:** the combo is assembled ONCE per host boot from the bundles
  on disk and served as a static classic script; there is no per-request bundling or HMR
  for host-composed client plugins in this configuration (the host-boot log's combo line
  appears once per boot). Editing plugin files after boot changes nothing in the browser —
  even a hard refresh re-fetches the same pre-assembled combo.
- **Correct restart procedure:** stop the host *process*, start it again (combo
  re-assembles), then hard-refresh the browser and verify Settings → Plugins → Plugin
  list is non-empty (empty list = the combo failed again).
- **Why the Windows restart died with EADDRINUSE:** the host is a node process tree
  (launcher + server, plus possibly workers/children) that holds the listening port.
  Closing the launching terminal on Windows does not reliably terminate the whole tree —
  an orphaned node process kept the port bound, so the next boot's `listen` failed with
  EADDRINUSE. Only killing the entire tree (`taskkill /PID <pid> /T /F`) released the
  port; the following boot bound normally. Discipline: stop by terminating the process
  tree (or the launcher's own shutdown path), confirm the port is free, then start.

## 5. Prevention

**Host-side:**

- At combo-assembly time (boot), statically compile/parse each contributed bundle
  individually (`new Function` / `node --check` equivalent) and fail (or degrade to
  excluding) the *specific offending bundle*, naming its plugin id and file — instead of
  letting one parse error surface at first-import time under the first awaited entry's id.
- At combo-failure time, attribute the error to the failing bundle, not the first awaited
  entry: the parse error already carries a file path; the host should translate that path
  back to the owning loader entry/plugin id and surface that in the browser error and the
  host log.
- Same for apply-time slot errors: include the registrant entry id (already done for
  failure 2) and, for the "not declared" family, hint at the `ctx.slots.inject(name, () =>
  ctx.slots.register(...))` wrapper (the runner's ledger already carries these examples —
  surface them in the error).
- Optionally expose a boot-time validation flag/log line listing each bundle's packaging
  verdict (wrapped / bare ESM / wrong registration id vs package.json name), turning
  failure 1 into a pre-flight diagnostic.

**Authoring-side template/checklist for external web UI plugins:**

1. Client bundle is built with the official tsdown-style banner config producing
   `window.__ModuleLoader__.load({ id, factory })`; registration `id` == package.json
   `name`; assembly row `name` uses the bare package name.
2. No top-level `import`/`export`, no module-scope DOM access; all requires
   (`react`, `react/jsx-runtime`, host client packages) inside the factory; return the
   plugin (`inject` + `apply`) from `module.exports`.
3. `dsh.client.inject` lists only real service-providing packages (no phantom deps).
4. Any slot owned by another entry is registered via
   `ctx.slots.inject('<slot>', () => ctx.slots.register({ name, id, order, label }, body))`;
   registrant never passes `kind`/`scope`/owner metadata.
5. Install = link into profile `node_modules` + one `insert` row with the bare package
   name; verify no duplicate ids already provided by the base bundle.
6. Dev loop: edit → stop host process tree (Windows: verify the port is actually free) →
   start host → hard refresh → check the plugin list is non-empty; on
   `failed to import loader entry <id>` read the bundle path in the detail line and
   bisect the newest insert row first.

## Sources

- Fixture pack (read-only): browser-error.txt, host-boot-log.txt, plugin-apply-error.txt,
  plugin/lib/client.js, profile/cordis.patch.yml, restart-notes.txt,
  working-plugin-excerpt.txt.
- plugin-upgrade skill: references/troubleshooting.md (both symptom rows),
  references/v0.1.2-alpha.1.md cards DSH-0.1.2-A1-25/A1-26, references/pre-flight.md
  (`rg -n "__ModuleLoader__|PLUGIN_ID"`).
- Primary: installed host `@deepseek-ai/dsh-cordis-client-runner/lib/client.js` —
  module loader wrapper, `settings.section` slot ledger entry (declaredBy, register
  options `id`/`order`/`label`, canonical `ctx.slots.inject` example).

No blockers; the task is fully answerable from the fixture plus local primary sources.
