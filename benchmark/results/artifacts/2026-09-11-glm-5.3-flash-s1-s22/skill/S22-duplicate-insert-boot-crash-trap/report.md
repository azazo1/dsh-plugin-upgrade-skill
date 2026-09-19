# S22 - The Duplicate Insert That Crashed the Boot: Diagnostic Report

Read-only diagnosis of a dsh 0.1.5-alpha.2 in-place upgrade (Windows 11, npm global) whose next dsh web boot crashed with: duplicate loader entry id: workspace-files. Evidence: boot-crash-log.txt, profile-patch-excerpt.txt, web-app-patch-excerpt.txt, README.md from the fixture pack. Diagnosis follows the plugin-upgrade skill (Mode A - inspect: read-only analysis, no configuration or code changes).

## 1. Root cause - which two declarations collide, and at which layer

The colliding pair:

- Profile layer: C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml, the manually added block:

    - insert:
        - id: workspace-files
          name: '@deepseek-ai/dsh-api-workspace-files'

- Bundle layer: the installed web-app bundle's cordis.patch.yml (packages/bundle/web-app/cordis.patch.yml, cited at L110-111 in the installed tree) already ships the identical row:

    - insert:
        - id: workspace-files
          name: '@deepseek-ai/dsh-api-workspace-files'

Both declare a loader entry with id workspace-files, so the profile patch adds a SECOND entry for an id the bundle already inserted.

Detection layer: the Cordis plugin LOADER / boot composition layer, not any plugin's code and not a service container. The stack trace pins it exactly:

    TypeError: duplicate loader entry id: workspace-files
        at EntryGroup.update (...@deepseek-ai/cordis-plugin-loader/lib/index.js:91:28)
        at Include._apply (...@deepseek-ai/dsh-app-boot/lib/index.js:240:19)
        at boot (...@deepseek-ai/dsh-app-boot/lib/index.js:1534:3)

The loader is applying the profile's cordis:include-merged entry set into an EntryGroup, which keeps a unique-id registry (EntryGroup.update); a second registration under an existing id throws immediately.

Why the whole boot refuses instead of accepting the later row: loader entry ids are identity keys for the plugin tree - two entries under one id is an ambiguous composition (which config, which package name wins?). The loader treats that as fail-loud misconfiguration, consistent with the DSH convention that misconfiguration fails loud at load. It is deliberately a hard, immediate throw at boot (plugin tree failed to load), not a warning with last-wins: silently accepting the duplicate would mask a profile/bundle composition mistake, which is exactly what the maintainer needed to see.

Also note: the manual insert was motivated by a misread of the original symptom (document tab opened, read failed with the message 文件资源服务不可用). The bundle already provides the host service row, so the insert was unnecessary; the original read failure is a separate post-upgrade symptom (the 0.1.5-alpha.2 workspace-files surface change), not evidence of a missing composition row.

## 2. Layering rules - safe vs. fatal operations for a profile patch on a bundle plugin

1. Changing a bundle-shipped plugin's config by id (override/modify its settings under the existing id): SAFE. The id already exists; the profile layer adjusts configuration without adding a second entry, so no duplicate id.
2. Adding a row for an id no bundle ships (a genuinely external plugin, e.g. dsh-file-trace and dsh-profiles in the same profile patch): SAFE. Unique id, no bundle conflict; the loader registers one entry.
3. Adding a row for an id a bundle already ships: FATAL - duplicate loader entry id, boot refuses. Two insert entries collide on the unique id key in EntryGroup; the loader throws and the boot dies.

The maintainer's action is the fatal third case: a manual insert for workspace-files, an id the web-app bundle already provides. The evidence row that proves it is web-app-patch-excerpt.txt (bundle tree, L110-111):

    - insert:
        - id: workspace-files
          name: '@deepseek-ai/dsh-api-workspace-files'

matched against the identical id in profile-patch-excerpt.txt. Ironically the profile patch's own comment anticipated this: 如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏 - the keep-it-just-in-case hedge is what turned a redundant row into a boot crash.

The adjacent bundle rows for session-controller and settings-controller confirm the convention: bundle-provided ids are never manually inserted into the profile patch, while the pre-existing external rows (dsh-file-trace, dsh-profiles) are exactly the safe second case.

## 3. Fix - the minimal correct change

Change exactly one file: delete the manually added workspace-files insert block from the PROFILE's cordis.patch.yml (C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml) - the final insert block of the excerpt plus its two comment lines. Change nothing else; the bundle's own row remains the single provider of the service.

- The plugin's own code is not at fault. @deepseek-ai/dsh-api-workspace-files is bundle-shipped and unchanged; nothing about its code caused the throw - the crash happens in the loader before any plugin is activated.
- No plugin-side change can resolve it. The duplicate id lives entirely in profile/bundle composition metadata; a plugin cannot deregister a profile-level row, and editing or moving plugin code would not remove the extra loader entry. Only removing the profile-side duplicate row fixes the boot.

After the deletion, restart dsh web and verify boot completes cleanly. The original symptom (文件资源服务不可用 on document-tab content read) must then be diagnosed on its own merits against the 0.1.5-alpha.2 workspace-files surface changes (per the skill's alpha.2 cards: workspaceFiles drops the Agent first parameter, gains a Typert workspaceFileScope client resource, absolute-scope authorization, and a maxFileBytes cap) - likely a plugin/config upgrade issue, never an excuse to re-add this row.

## 4. Prevention - what to check first, and what the host could print

Author/maintainer-side (before hand-adding any row):

1. Grep the installed bundle tree for the id before writing any insert: e.g. search the installed bundle's cordis.patch.yml (packages/bundle/web-app/cordis.patch.yml in the installed node_modules path) for workspace-files. The row was present at L110-111 - a five-second read would have prevented the crash.
2. Treat the adjacent bundle rows (session-controller, settings-controller) as the reference pattern: everything they resemble is bundle-owned; never copy a bundle row into a profile patch.
3. Update the obsolete profile comment (保留以确保升级 profile 不遗漏) so the next reader does not re-introduce the hedge.
4. Do not infer a missing host service from a UI feature failure (文件资源服务不可用); check the boot manifest / service registry first - a row the bundle ships is by definition not missing from composition.

Host-side (actionable boot output):

- On detecting a duplicate id, the host should print an attribution + remediation message, e.g.: duplicate loader entry id: workspace-files - declared in profile 'C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml' (trailing insert block) AND bundle '@deepseek-ai/dsh-bundle-web-app' cordis.patch.yml:110 - remove the profile-side row; profile patches may not insert an id a bundle provides. That names whom to blame (the hand-edited profile) and what to delete (the trailing insert block), instead of only the id.
- Companion aid: print the already-declared source of the id on conflict, and/or a startup summary line listing bundle-provided ids so maintainers can diff profile rows against it; a non-fatal pre-flight check in a diagnose command could flag profile rows duplicating bundle rows before boot.
- Per the fail-loud principle, the boot refusal itself is correct; only the diagnostic quality needs to improve.

---

### Summary

A redundant insert row for the bundle-provided id workspace-files in the profile's cordis.patch.yml collided with the web-app bundle's own row at the Cordis plugin-loader layer (EntryGroup.update, fail-loud on duplicate entry ids) and refused the boot. Fix: delete the profile-side row. Prevention: check the installed bundle patch before hand-inserting, and have the host attribute the duplicate to its declaring files with a delete-this-row instruction.
