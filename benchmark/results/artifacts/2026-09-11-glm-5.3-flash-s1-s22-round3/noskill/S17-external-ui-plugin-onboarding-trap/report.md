# S17 · The External UI Plugin Onboarding Trap — Diagnostic Report

Evidence pack: environment/fixture/ (read-only): browser-error.txt, plugin/lib/client.js, profile/cordis.patch.yml, plugin-apply-error.txt, working-plugin-excerpt.txt, host-boot-log.txt, restart-notes.txt.

## 1. Failure 1 root cause — one bad bundle killed every plugin's registration

**Evidence.** browser-error.txt:

> Failed to load plugins: failed to import loader entry 0c013085 (@deepseek-ai/dsh-typert-registry): client-modules: bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)

and "Settings → Plugins → Plugin list: EMPTY. Zero entries registered," including the two stock plugins that previously rendered.

**Root cause — combo, not per-plugin loading.** host-boot-log.txt shows how the host serves client code:

> [boot] client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)

At boot the host reads every installed plugin's client bundle and concatenates all of them into one classic script (the "combo"). The browser imports the loader entries from this single combo; there is no per-plugin isolation. restart-notes.txt confirms the model: "the host reads every installed plugin's client bundle, concatenates them into one classic script, and serves that."

The user's plugin/lib/client.js begins with:

> import React from 'react'
> import { createPortal } from 'react-dom'

A bare ESM import statement is a syntax error inside a classic script. Position 1:1 is exactly the first character of the first import. When the combo fails to compile, the whole combo is rejected — the loader entry import fails, so zero entries get registered, taking down the two innocent stock plugins (brand version, file tracking) plus all 53 entries.

**Why the innocent dsh-typert-registry was named.** The error names the first awaited loader entry being imported when the combo compile error surfaced — @deepseek-ai/dsh-typert-registry is merely the first entry in registration order, not the culprit. The real culprit path is right there in the error body: bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1). The entry id (0c013085) and the failing bundle path are different things; misreading the entry id as the culprit is the trap.

## 2. Diagnosis discipline and the correct client-bundle packaging contract

**How to bisect from the misleading error.**

- Read the error to the end: the bundle path after "client-modules:" points at the offending file — /plugins/@lhh010/dsh-profiles/lib/client.js. The entry id before the parenthetical is a red herring.
- If the message were ambiguous, bisect the combo, not the browser: disable/remove insert rows in the profile's cordis.patch.yml one at a time (or diff against the last working patch — here the only new row is the dsh-profiles insert) and reboot. The boot that recovers the plugin list identifies the inserted plugin.
- Cheap static check that flags the bundle immediately: a top-level 'import ' / 'export ' statement in a lib/client.js bundle intended for a classic script. grep -n "^import\|^export" lib/client.js on the new bundle returns lines 1–2 — an instant fail. Also compare against a known-good bundle (next section).

**The required packaging form** (shown redacted in working-plugin-excerpt.txt for the working @local/dsh-brand-version):

- The bundle must be an IIFE-style CommonJS-flavored module registered on the host's global loader, not bare ESM:

    window.__ModuleLoader__.load({
      id: "<plugin id>",
      factory: (require) => {
        var module = { exports: {} };
        var exports = module.exports;
        Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
        /* components */
        const inject = ["slots"];
        function apply(ctx) { /* registrations */ }
        return module.exports;
      },
    });

- What wraps the code: the window.__ModuleLoader__.load({...}) call; the code lives inside factory: (require) => {...}, which builds and returns module.exports. No top-level import/export.
- How React is obtained: through the injected require — e.g. require("react/jsx-runtime") — plus host UI packages such as require("@deepseek-ai/dsh-client-ui-primitives"). React is a loader dependency, never bundled or imported as ESM.
- What the wrapper must export: a module.exports carrying apply(ctx) (and, when needed, an inject array of service names, as the working excerpt shows: const inject = ["slots"]). apply(ctx) is the entry the host invokes to register into slots.

Repackaged this way (which is what "the plugin was repackaged" means between failure 1 and failure 2), the bundle compiles inside the classic-script combo and the loader entries register — plugin-apply-error.txt confirms "All other plugins load and render normally on this boot."

## 3. Failure 2 — slot "settings.section" is not declared (a parent entry's children table must declare it)

**Evidence.** plugin-apply-error.txt: failed to apply loader entry (@lhh010/dsh-profiles): slot "settings.section" is not declared (a parent entry's children table must declare it).

**Who declares slots.** Slots are declared by the parent entry — the entry that owns the surface (here the settings entry) — in its children table, as part of its own registration. A plugin that merely wants to render into another entry's slot does not own the slot and cannot create it by registering into it; registration is an occupy operation, not a declaration operation.

**Why a bare registration fails at apply time.** The repackaged bundle registers directly (plugin/lib/client.js):

> ctx.slots.register(
>   { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
>   ProfilesSection,
> )

At apply time the host validates that the slot name exists in the declaring (parent) entry's children table. It does not — no parent declares settings.section — so the host fails loud ("misconfiguration fails loud … never silently skip a missing referent") and rejects the entry's apply. This is the cross-entry ownership trap: the child assumed the parent's declaration.

**The exact wrapping form the registration must use.** The cross-entry contribution must go through the inject wrapper for another entry's slot — the working plugin shows the pattern in its elided apply body: ctx.slots.inject(...) calls. Instead of ctx.slots.register(<full slot descriptor>, component), the registrant declares what it injects (module-level inject: ["slots"]) and calls ctx.slots.inject(...) naming the parent's slot and its own contribution. The slot identity remains owned by the parent's declaration, never re-declared by the child. (If no parent entry declares a settings.section slot at all, the fix is upstream: the declaring entry's children table must gain the slot; the plugin can never declare it.)

**Fields a registrant may pass vs must not.** The registrant may pass only its contribution's own identity: its id (e.g. profiles-manager), display ordering (order), and the component. It must not pass the ownership/declaration fields of the slot itself — the slot name as a fresh declaration, kind, scope — because those are defined by the parent's children-table declaration; re-declaring them in a bare register is exactly what the apply-time check rejects.

## 4. Dev-loop discipline — boot-assembled combo and the Windows restart

**Why edits don't take effect.** host-boot-log.txt / restart-notes.txt: "Combo assembly happens ONCE at host boot … Editing a plugin file on disk afterwards has NO effect in the browser, even after a hard refresh, until the host process is stopped and started again." The host reads every plugin's client bundle at boot, concatenates the combo (4.5 MB classic script), and serves that static artifact; there is no file watcher or per-request recomposition for the combo. A browser hard refresh only refetches the same stale combo.

**Correct restart procedure** (restart-notes.txt item 3):

1. Stop the host properly — verify the node process actually exited; do not just close the launching terminal, which on Windows orphans the process.
2. If the port is still held, kill the whole tree: taskkill /PID <pid> /T /F.
3. Start the host; wait for the boot line "client-modules: composed N loader entries into client bundle combo".
4. Hard refresh the browser, then check Settings → Plugins → Plugin list — "empty list = the combo failed again."

**Why EADDRINUSE until force-kill.** Closing the launching terminal does not deliver a kill to the child node process; the previous host's node process stayed alive still holding the listening port. The next boot failed with EADDRINUSE because the socket was bound by the orphan. Only taskkill /PID <pid> /T /F (tree kill) removed the orphan and freed the port; the next boot then bound normally.

## 5. Prevention

**Host-side (name the culprit, not the first awaited entry).**

- At combo composition time (boot), compile-check each plugin bundle individually before concatenation and report the failing bundle's plugin id/path in the headline: "combo rejected: bundle /plugins/@lhh010/dsh-profiles/lib/client.js (plugin dsh-profiles) failed to compile at 1:1: unexpected token 'import' (classic script; ESM import/export not allowed — use the __ModuleLoader__ wrapper)". The information already exists in the error body; it just is not promoted.
- Do not let one failing entry blank the combo: skip the failing entry, register the rest, and surface the excluded plugin id in Settings → Plugins so the damage is bounded and diagnosable.
- Validate slot registrations with a diagnostic that names both registrant and the expected declaring entry: "plugin dsh-profiles registers slot 'settings.section' but no parent entry declares it; the declaring entry's children table must declare it — registrants contribute via ctx.slots.inject, not register".
- On Windows shutdown, kill the listener with its process tree (job-object/tree kill) so closing a terminal cannot orphan a port holder and cause EADDRINUSE.

**Authoring template / checklist for external UI plugins.**

1. Bundle format: ship a classic-script IIFE registered via window.__ModuleLoader__.load({ id, factory: (require) => { ...; return module.exports; } }); never top-level import/export (static check: no line starting with 'import ' or 'export ').
2. Dependencies: obtain React (require("react/jsx-runtime")) and host UI packages through the injected require; do not bundle or ESM-import React or react-dom helpers such as createPortal.
3. Exports: module.exports must expose apply(ctx), plus inject: ["slots"] when contributing to slots.
4. Slots: never bare-register another entry's slot. The parent entry's children table must declare the slot; the plugin contributes with the ctx.slots.inject form, passing only its own contribution (id/order/component) — not the slot's declaration fields (name/kind/scope).
5. Copy the packaging shell from a known-good bundle in the same profile (as working-plugin-excerpt.txt provides) before first boot.
6. Dev loop: after every plugin-file edit, restart the host (verify process exit; tree-kill orphans), confirm the "composed N loader entries" boot line, hard-refresh, and confirm the plugin list is non-empty before iterating further.
7. When a load error names an entry id, check the bundle path in the same message and the rows last added to cordis.patch.yml first — the named entry is often just the first awaited victim of another plugin's bundle.
