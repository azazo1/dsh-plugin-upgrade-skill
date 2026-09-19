# S17 · The External UI Plugin Onboarding Trap — Diagnosis Report

**Mode**: A-style read-only diagnosis (plugin-upgrade skill; no writes, installs, or migrations performed).
**Evidence**: static fixture pack under `environment/fixture/` (browser-error.txt, host-boot-log.txt, plugin/lib/client.js, profile/cordis.patch.yml, plugin-apply-error.txt, restart-notes.txt, working-plugin-excerpt.txt), cross-checked against the skill's reference cards (troubleshooting.md, DSH-0.1.2-A1-25/A1-26, DSH-0.1.5-A1-20).
**Baseline**: not collected — this is incident diagnosis, not a migration; no code was built or changed.

---

## 1. Failure 1 — why one bad bundle took down EVERY plugin, and why the error named `dsh-typert-registry`

### What the host assembles and ships

From `host-boot-log.txt`:

> `[boot] client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)`

At host boot, the client-modules assembly walks every installed plugin that declares a client half (`dsh.client`), reads each one's client bundle file, and **concatenates all of them into a single classic `<script>`** served from the combo route (`/plugins/??…`). Each contributing bundle is expected to be a *classic script* that registers itself by calling `window.__ModuleLoader__.load({ id, factory })` — the form visible in `working-plugin-excerpt.txt`. The browser then imports the loader entries from that single script.

### The failure mechanism

`plugin/lib/client.js` as the user wrote it begins with:

```js
import React from 'react'
import { createPortal } from 'react-dom'
```

A top-level ESM `import` is a **SyntaxError in a classic script**. Because all 53 entries share ONE script, one ESM token anywhere fails the **compile (parse) of the whole combo** — the script never evaluates, so `__ModuleLoader__.load` is never called for *any* entry. Result: zero plugins register, the plugin list is empty, and even the previously-working stock plugins (brand version, file trace) vanish. That matches the browser-error.txt observation exactly ("Plugin list: EMPTY. Zero entries registered").

`(position 1:1)` in the error is the tell: the parser choked on the very first token of the offending bundle — the `import` keyword.

### Why the error names `@deepseek-ai/dsh-typert-registry`

The error headline is `failed to import loader entry 0c013085 (@deepseek-ai/dsh-typert-registry)`. That entry is merely **the first loader entry the client awaits** during plugin import. The combo-level compile error surfaces through the first awaited entry's import promise, so the innocent stock entry's name becomes the headline. The actual culprit is named in the error's cause text — `bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error` — which the user read past. `dsh-typert-registry` never touched anything; it is a victim of attribution order, not a cause. (Same attribution trap as DSH-0.1.5-A1-20, where a combo gap also surfaced under `failed to import loader entry <id>`.)

---

## 2. Diagnosis discipline and the correct client-bundle format

### Locating the culprit from the misleading error

1. **Read the whole error, not the headline.** The segment after the colon carries the real coordinate: `bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)`. The named loader entry is only the first awaited entry; the bundle path is the culprit.
2. **Bisect the patch layer.** With a whole-combo failure and no path in the message, binary-search the profile's `cordis.patch.yml` `insert` rows: comment out the newest row(s) → boot → if plugins come back, the removed row's package owns the offending bundle. Here the newest insert (`dsh-profiles`) is the obvious first candidate; removing it restores the two stock plugins.
3. **Cheap static check that flags the offending bundle.** Every legitimate bundle is a classic script wrapped in `window.__ModuleLoader__.load(`. So:
   - `rg -n "__ModuleLoader__|PLUGIN_ID" <profile-node-modules>` (the skill's pre-flight #5 command) — a bundle that does NOT match `window.__ModuleLoader__.load(` at (or near) the top is suspect;
   - `rg -n "^import |^export " <bundle>.js` — any top-level ESM token in a classic-script combo is the compile error. `plugin/lib/client.js` fails both probes: no `__ModuleLoader__` wrapper, and lines 1–2 are bare `import`s.
   - `node --check <bundle>.js` parses it as CommonJS/classic script and reproduces the SyntaxError locally in seconds, without booting the host.

### The client-bundle contract an external plugin must ship

From `working-plugin-excerpt.txt` (the working plugin in the same profile):

```js
window.__ModuleLoader__.load({
  id: "@local/dsh-brand-version",      // MUST equal package.json "name" (A1-26)
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    let react_jsx_runtime = require("react/jsx-runtime");           // React as an external
    let _primitives = require("@deepseek-ai/dsh-client-ui-primitives"); // host UI as externals
    /* component definitions */
    const inject = ["slots"];
    function apply(ctx) { /* ctx.slots... */ }
    return module.exports;
  },
});
```

- **Wrapper**: a self-executing classic script calling `window.__ModuleLoader__.load({ id, factory })`. No top-level `import`/`export`; no ESM module syntax at all. (Bundlers like tsdown produce this via an IIFE/global-output format with a `PLUGIN_ID` banner.)
- **React**: obtained **inside the factory via the injected `require`** (`require("react")`, `require("react/jsx-runtime")`, `require("react-dom")`, host `@deepseek-ai/*` client packages) from the loader's shared module registry — never bundled, never statically imported.
- **Exports**: the factory must populate and return `module.exports` exposing the Cordis client plugin object: an `apply(ctx)` function (the plugin body) and optionally `inject: [...]` for hard service dependencies.
- **Registration id**: the `load({ id })` string must equal the package.json `name` — for this plugin `@lhh010/dsh-profiles`, matching the `insert` row (`name: '@lhh010/dsh-profiles'`).
- **Bonus defect in the user's original**: the top-level `document.createElement`/`createPortal` DOM side effect runs at module-evaluation time, outside any mount context. DOM work belongs inside the component or `apply` lifecycle, not at bundle top level.

---

## 3. Failure 2 — `slot "settings.section" is not declared`

### What the error means and who declares slots

`plugin-apply-error.txt` (second boot, after repackaging fixed the bundle format):

> `failed to apply loader entry (@lhh010/dsh-profiles): slot "settings.section" is not declared (a parent entry's children table must declare it)`

In the Web Client, a slot like `settings.section` is **owned and declared by its parent entry** — the settings page's own bundle declares its children table (the set of slots it will host). An external plugin is a *consumer* of that slot, not its declarer. The plugin's code did:

```js
ctx.slots.register(
  { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
  ProfilesSection,
)
```

This is a **bare `register` of another entry's slot**. Loader-entry apply order across entries is undefined, so this registration can land **before the owning entry has declared the slot** — and when it does, the registrar rejects the unknown slot name at apply time and the whole entry fails. (Notably, this failure is correctly scoped: only `@lhh010/dsh-profiles` fails; "all other plugins load and render normally", unlike failure 1's whole-combo blast radius.)

### The correct wrapping form

Wrap the registration in `ctx.slots.inject`, which defers the `register` until the slot's owner has declared it:

```js
function apply(ctx) {
  ctx.slots.inject('settings.section', () =>
    ctx.slots.register({ id: 'profiles-manager', order: 5 }, ProfilesSection),
  )
}
```

(and declare `inject: ["slots"]` on the plugin object if `slots` is treated as a hard dependency, as the working excerpt does).

### Field ownership

- **Registrant MAY pass**: its own registration identity within the slot — `id`, `order` (and `label` where the slot takes one), plus the component.
- **Registrant MUST NOT pass**: `name`, `kind`, `scope` — those describe the slot itself and belong exclusively to the parent entry's children table that declares the slot. The user's `{ name, kind: 'section', scope: 'settings' }` extras were attempting to (re)declare a slot owned by the settings entry.

---

## 4. Dev-loop discipline — boot-assembled combo and the Windows EADDRINUSE

### Why edits don't appear without a host restart

From `host-boot-log.txt` and `restart-notes.txt`: the combo line (`composed 53 loader entries…`) appears **once per boot**. The host reads each plugin's client bundle from disk and concatenates the combo at process startup; afterwards it serves that assembled artifact. Editing a plugin file on disk changes nothing in the browser — even after a hard refresh — because the refresh re-fetches the *same pre-assembled* combo, not the changed files. (The host half has a symmetric constraint: routes/services register once at apply.) So the edit-verify loop is:

1. edit the plugin file(s);
2. **stop the host process** and start it again (combo is re-assembled at boot);
3. **hard-refresh the browser**;
4. verify: Settings → Plugins → Plugin list — an empty list means the combo failed again (parse error in some bundle); a populated list with the plugin absent means its own entry failed at apply (e.g. the slot error).

### Why the Windows restart died with EADDRINUSE

The host is not a single node process; it supervises a **process tree** (launcher → node host, plus workers). Closing the launching terminal on Windows kills the shell but **orphans the node child**, which keeps running and keeps the listening port bound. The next boot's `listen()` then fails with `EADDRINUSE` — not a plugin problem at all. The orphaned process only released the port after killing the entire tree:

```powershell
taskkill /PID <pid> /T /F
```

(`/T` = tree, `/F` = force). Only then did the next boot bind normally. Correct Windows restart procedure: stop via the host's own shutdown path (or taskkill the tree), confirm the port is free, boot, hard-refresh, check the plugin list. Related Windows file-lock discipline (EBUSY on held native-module handles) is covered by the skill's S12 guidance — full host stop before file replacement.

---

## 5. Prevention

### Host-side

**At combo-assembly time (boot):**
- **Static pre-flight per bundle**: before concatenating, cheaply validate each bundle — it must contain a `window.__ModuleLoader__.load(` registration and must survive `node --check`-style classic-script parsing (equivalently: reject top-level `import`/`export` tokens). On violation, **fail with the offending plugin's id and bundle path**, not the first awaited loader entry, and optionally skip just that bundle (degraded, named) instead of shipping a combo that cannot parse.
- **Registration-id equality check**: verify each bundle's `load({ id })` equals its package.json `name` at assembly (extends A1-26 from a startup assertion to a boot-time, per-plugin-named report).

**At combo-failure time (browser):**
- When a combo-level compile/parse error occurs, the client knows which byte range / which concatenated segment failed. Map the failing position back to the contributing bundle and **report that plugin's id in the headline** (e.g. `client bundle @lhh010/dsh-profiles: top-level ESM import at 1:1 — bundles must be classic scripts registering via __ModuleLoader__.load`), keeping the first-awaited-entry name only as secondary context.
- Symmetrically for apply-time failures: when a slot registration is rejected as undeclared, suggest the inject-wrapper form in the message (name the missing slot and hint "wrap cross-entry registrations in ctx.slots.inject").

**Structural option (larger change):** wrap each contributed bundle in its own evaluation boundary (e.g. per-entry `new Function`/iframe-sandboxed factory, or per-entry script tags) so one bundle's parse error degrades to that plugin only — eliminating the whole-combo blast radius by construction. This trades the single-request combo for per-entry requests; the revision-keyed combo in `window.__DSH_BOOT__` (A1-20) would need a per-entry invalidation story.

### Authoring-side — external client-plugin template/checklist

**Template (the corrected `@lhh010/dsh-profiles` client bundle):**

```js
window.__ModuleLoader__.load({
  id: "@lhh010/dsh-profiles",            // === package.json name === insert row name
  factory: (require) => {
    var module = { exports: {} };
    var exports = module.exports;
    Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
    const React = require("react");       // React is an external, never bundled
    /* component definitions — DOM work only inside components/apply */
    function ProfilesSection() { /* ... */ }
    const inject = ["slots"];
    function apply(ctx) {
      ctx.slots.inject("settings.section", () =>        // inject, never bare register
        ctx.slots.register({ id: "profiles-manager", order: 5 }, ProfilesSection));
    }
    exports.inject = inject;
    exports.apply = apply;
    return module.exports;
  },
});
```

**Checklist:**
1. **Format**: classic script; first meaningful statement is `window.__ModuleLoader__.load({ id, factory })`. `node --check bundle.js` passes. No top-level `import`/`export`, no top-level DOM side effects.
2. **Identity**: `load` id == package.json `name` == profile `cordis.patch.yml` insert `name`.
3. **Externals**: `react`, `react-dom`, `@deepseek-ai/dsh-client-*` consumed via the factory's `require`; never bundled into the artifact.
4. **Exports**: `apply(ctx)` (required) and `inject` (only real hard dependencies) on `module.exports`.
5. **Slots**: only `ctx.slots.inject(<owner-declared slot>, () => register(...))` for slots owned by other entries; pass only `id`/`order`/`label` + component — never `name`/`kind`/`scope`. Declare own slots in your own entry's children table if you host children yourself.
6. **Dev loop**: edit → stop host (on Windows kill the process tree: `taskkill /PID <pid> /T /F`, or EADDRINUSE on next boot) → start host → browser hard refresh → verify Settings → Plugins list is non-empty and your entry is present; empty list ⇒ combo parse failure in *some* bundle — run the `__ModuleLoader__` / `^import` static probes over the profile's bundles.
7. **Install surface**: exactly what was done here is fine — package linked into the web profile's `node_modules` + one `insert` row with the bare package name; no duplicate inserts of bundle-provided ids (duplicate loader-entry ids are fatal at boot).

---

## Skill report skeleton

- **Completed**: full read-only root-cause attribution of all three failures (combo parse blast radius + misleading first-entry attribution; cross-entry slot declaration vs inject-wrapper; boot-assembled combo + orphaned process-tree port hold), the client-bundle packaging contract, diagnosis procedure, and host-side + authoring-side prevention. No files outside the report output were touched; fixture untouched.
- **Skipped**: no runtime verification (fixture is static evidence; brief forbids execution/installs); no corridor migration cards applied beyond citation (no source repository to migrate).
- **Pending / residual risk**: prevention items for the HOST are proposals only — implementing them would require DSH core changes, which this skill must not make to paper over plugin incompatibility. Per-bundle isolation (option in §5) changes the combo contract and would need its own design review.
- **Rollback**: nothing to roll back (read-only analysis; only this report file was written).
- **Recommendations**: adopt the boot-time bundle pre-flight and culprit-named combo errors host-side; publish the §5 checklist as the external client-plugin onboarding template (community-standard adjacent); consider the skill's `verify-runtime`-style client-layer check (token URL → boot manifest → combo artifact → registration proof, per A1-20's verification recipe) as the standard post-onboarding gate.
