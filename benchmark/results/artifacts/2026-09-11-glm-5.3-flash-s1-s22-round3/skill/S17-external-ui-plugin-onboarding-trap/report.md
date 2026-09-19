# S17 - The External UI Plugin Onboarding Trap - Diagnostic Report

Evidence pack inspected (read-only): README.md, browser-error.txt, host-boot-log.txt, plugin-apply-error.txt, plugin/lib/client.js, profile/cordis.patch.yml, restart-notes.txt, working-plugin-excerpt.txt.

## 1. Failure 1 root cause - one bad bundle takes down every plugin, and why the error names dsh-typert-registry

**What the host does at boot.** The host boot log states the mechanism explicitly:

> [boot] client-modules: composed 53 loader entries into client bundle combo (4.5 MB, classic script)

At boot the host reads every installed plugin's client bundle (the three profile patch rows resolved dsh-brand-version, dsh-file-trace, dsh-profiles), wraps each into a "loader entry", and concatenates all entries into one static, classic-script combo served to the browser. The new plugin was linked into the web profile's node_modules and added with one insert row in profile/cordis.patch.yml (- insert: - id: dsh-profiles, name: '@lhh010/dsh-profiles'), so its bundle was pulled into that combo like any stock plugin's.

**Why one plugin kills all plugins.** The combo is built and consumed as a single unit. The browser error shows a compile error at position 1:1 of /plugins/@lhh010/dsh-profiles/lib/client.js:

> Failed to load plugins: failed to import loader entry 0c013085 (@deepseek-ai/dsh-typert-registry): client-modules: bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)

The offending bundle - plugin/lib/client.js as the user wrote it - begins with:

    import React from 'react'
    import { createPortal } from 'react-dom'

and ends with "export function apply(ctx) {...}" - top-level ESM import/export syntax. That syntax is illegal inside a classic script. Because the host concatenates entries into one classic script and the browser evaluates the combo as a whole, a syntax-level compile failure aborts evaluation of the entire combo: zero loader entries get registered. This is exactly what the fixture records: "Settings -> Plugins -> Plugin list: EMPTY. Zero entries registered," and the two previously working plugins (brand version, file tracking) also disappeared from the header.

**Why the error names @deepseek-ai/dsh-typert-registry.** The named entry is a stock host package the user never modified. The error is misleading because of evaluation-order-plus-await semantics: the host awaits loader entries in combo order, and entry 0c013085 (dsh-typert-registry) is simply the first awaited entry, so the combo-level script compile/evaluation failure surfaces as that entry's import rejection. The parenthetical payload - "bundle /plugins/@lhh010/dsh-profiles/lib/client.js compile error (position 1:1)" - is the real culprit attribution, but the leading frame names the innocent first awaited entry. Position 1:1 is itself the clue: the failure is at the very first character of a bundle, i.e. a parse failure (top-level import in a classic script), not logic inside the named package.

## 2. Diagnosis discipline - locating the real culprit and the correct bundle format

**How to bisect from the misleading error.** Never trust the entry named in the leading frame; trust the embedded bundle path.

1. Read the full error text: the innermost specific message already names the guilty file (/plugins/@lhh010/dsh-profiles/lib/client.js), and "compile error (position 1:1)" indicates syntax, not behavior.
2. Bisect the combo, not the package: remove plugin insert rows from the profile patch one at a time, starting with the newest insert (dsh-profiles). If the plugin list returns, the removed entry's bundle is the culprit - no debugging of dsh-typert-registry needed.
3. Cheap static check that flags the offending bundle: scan each plugin's lib/client.js for top-level ESM tokens at the start of the file - a leading "import " statement or "export " keyword. The working-plugin excerpt contains neither; the failing client.js starts with "import React from 'react'". A one-line grep (^import / ^export at file top) flags the bundle instantly.

**The required client-bundle format.** Compare the working plugin's excerpt with the failing one.

Working (working-plugin-excerpt.txt) - an IIFE-style classic-script wrapper registered on a host global:

    window.__ModuleLoader__.load({
      id: "@local/dsh-brand-version",
      factory: (require) => {
        var module = { exports: {} };
        var exports = module.exports;
        Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
        let react_jsx_runtime = require("react/jsx-runtime");
        let _deepseek_ai_dsh_client_ui_primitives = require("@deepseek-ai/dsh-client-ui-primitives");
        /* ... component definitions elided ... */
        const inject = ["slots"];
        function apply(ctx) { /* ... ctx.slots.inject(...) calls elided ... */ }
        return module.exports;
      },
    });

Failing (plugin/lib/client.js) - bare ESM with import/export.

The contract an external plugin must ship: the bundle is a **classic script (no top-level import/export syntax)** whose whole body is a window.__ModuleLoader__.load({ id, factory }) call; factory receives a require function; **React (and react/jsx-runtime) is obtained by calling require("react") / require("react/jsx-runtime") inside the factory** - never by a static ESM import and never from an assumed global. The factory constructs a fresh module/exports object and **must return module.exports**; that returned object carries the plugin's inject list and its apply(ctx) function, which the host invokes as the loader entry.

## 3. Failure 2 - slot "settings.section" is not declared (a parent entry's children table must declare it)

After repackaging, the browser loads plugins again, but apply fails only for the new plugin:

> failed to apply loader entry (@lhh010/dsh-profiles): slot "settings.section" is not declared (a parent entry's children table must declare it)

**Who declares slots.** Slots are declared by the parent entry that owns the subtree: the owner publishes a children table (the declaration of the slots that exist under it), and only names in that table are valid registration targets. Registration is not declaration.

**Why a bare registration fails at apply time.** The repackaged plugin still registers directly:

    ctx.slots.register(
      { name: 'settings.section', id: 'profiles-manager', order: 5, kind: 'section', scope: 'settings' },
      ProfilesSection,
    )

The host validates each register target against the parent entry's children table at apply time. "settings.section" belongs to the host's settings entry, not to @lhh010/dsh-profiles; the new plugin never declared it, so the host rejects the registration - loudly, but scoped to this entry only (all other plugins load and render normally on this boot). This is the fail-loud-at-earliest-resolvable-point rule working as designed.

**The exact wrapping form the registration must use.** Registration into another entry's slot must go through the injected slots service: the plugin declares "slots" in its inject list and calls ctx.slots.inject(...) inside apply - exactly the pattern visible in the working excerpt (const inject = ["slots"]; apply calls ctx.slots.inject(...)).

**Which fields the registrant may pass and which it must not.** When contributing to a parent-declared slot via inject, the registrant supplies only its own contribution/placement fields: the target slot name (settings.section), its own component id/label, and ordering (order) as the parent's contract permits. It must not pass ownership/declaration fields that belong to the parent's children table - kind and scope, and any attempt to create/declare the slot itself. Those are the parent's to declare; a child authoring them (kind: 'section', scope: 'settings' here) is precisely the violation the host refuses. Concretely: child passes { name, id, order } plus its component; it must not pass kind/scope or attempt to declare the slot.

## 4. Dev-loop discipline - boot-assembled combo, correct restart, and the Windows EADDRINUSE

**Why edits don't apply.** host-boot-log.txt: the combo line appears ONCE per boot. At boot the host reads every installed plugin bundle, concatenates them into the classic-script combo, and serves that artifact; it does not watch plugin files afterwards. restart-notes.txt confirms: "Editing a plugin file on disk afterwards has NO effect in the browser, even after a hard refresh, until the host process is stopped and started again." A hard refresh only re-fetches the same stale combo.

**Correct restart procedure.** The combo is rebuilt only at host boot, so every plugin edit requires:

1. Fully stop the host - on Windows, do not merely close the launching terminal; closing the terminal window can orphan the node child. Verify the port is released.
2. If the port is held: taskkill /PID <pid> /T /F - kill the whole process tree, not just the parent (per restart-notes.txt, the next boot "bound normally" only after the tree kill).
3. Start the host again (fresh combo assembly), then hard-refresh the browser.
4. Check Settings -> Plugins -> Plugin list: an empty list means the combo failed compile/evaluation again - the Failure 1 signature repeats.

**Why EADDRINUSE until the tree was force-killed.** On Windows, closing the terminal does not propagate a termination signal down to the child node process: the shell died, the node server survived, still holding the listening socket. The next host boot found the port occupied -> EADDRINUSE. Only killing the entire process tree (taskkill /PID <pid> /T /F) released the socket, after which the boot bound normally. Lesson: on Windows, treat restart as a tree-level kill and confirm the port is free before relaunching.

## 5. Prevention

**Host-side improvements (name the culprit, not the first awaited entry).**

1. Pre-serve per-entry compile validation: at combo assembly time (client-modules: composed N loader entries), parse/compile each plugin bundle individually before concatenation. A classic-script parse of @lhh010/dsh-profiles/lib/client.js fails at the import on line 1, letting the host refuse or skip with the exact plugin id and file named, instead of letting the browser discover it inside the merged artifact.
2. Attribute errors to the bundle path: the host already embeds the guilty path in the payload (bundle /plugins/.../client.js compile error (position 1:1)); it should surface that plugin's id as the primary subject ("failed to load plugin @lhh010/dsh-profiles: ..."), and map byte offsets in the combined combo back to the owning entry so runtime throws in a merged combo also name the responsible plugin.
3. Fail loud but scoped: a single entry's compile failure should degrade to "plugin X not registered" with a prominent warning, never a silently empty plugin list; print per-entry compile status at boot so manual bisecting is unnecessary.
4. Improve the slot error: extend "slot settings.section is not declared" with the declaring parent's entry id and the fix ("declare inject: ['slots'] and register via ctx.slots.inject()"), turning the fix into a one-read answer.
5. Dev-loop hint: log once that the combo is assembled at boot and plugin file changes require a host restart.

**External-plugin authoring template / checklist** (each item maps to one of the three failures):

1. Format: ship lib/client.js as a classic script wrapped in window.__ModuleLoader__.load({ id, factory }) where factory returns module.exports. No top-level import/export anywhere. (Failure 1.)
2. Dependencies: obtain React and shared modules via require(...) inside the factory (require("react"), require("react/jsx-runtime"), primitives), matching the working excerpt - never ESM import, never assumed globals.
3. apply/inject: define apply(ctx) inside the factory, export it on module.exports, and declare hard dependencies in inject (e.g. const inject = ["slots"]).
4. Slots: to place UI into an existing host slot use ctx.slots.inject(...) inside apply, passing only contribution fields (target slot name, own id/label, order); never ctx.slots.register a slot your plugin did not declare, and never pass parent-ownership fields (kind, scope). (Failure 2.)
5. No module-scope DOM side effects: the failing bundle appended a #dsh-profiles-root div at module top level; mount inside the slot/component lifecycle instead so apply stays declarative and idempotent.
6. Static self-check before install: grep the bundle for top-level ^import / ^export - any hit means the packaging step was skipped.
7. Dev loop (Windows): after every bundle edit, fully stop the host, ensure the port is free (taskkill /PID <pid> /T /F on an orphaned tree), reboot, hard-refresh, and verify Settings -> Plugins lists the plugin - an empty list is the combo-failure signature and the newest insert row is the first suspect. (Failure 3.)
8. Onboarding: add the plugin with a single insert row in the profile's cordis.patch.yml (as profile/cordis.patch.yml shows) only after items 1-7 pass.
