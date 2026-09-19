# S22 · The Duplicate Insert That Crashed the Boot — Report

## 1. Root cause

**The two colliding declarations** are two `insert` rows with the same loader entry id `workspace-files`:

1. The **web-app bundle's** `cordis.patch.yml` (installed with npm 0.1.5-alpha.2, `packages/bundle/web-app/cordis.patch.yml`):
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```
2. The **profile's** `cordis.patch.yml` (`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`), the block the maintainer added manually:
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```

**Detection layer.** The collision is detected in the **Cordis plugin loader**, during `boot`'s plugin-tree assembly — specifically in `EntryGroup.update` of `@deepseek-ai/cordis-plugin-loader` (stack: `failed to apply loader entry include (cordis:include)` → `EntryGroup.update` → `Include._apply` → `boot` in `dsh-app-boot`). When the profile patch is layered on top of the bundle's composition, applying the second `include` for entry id `workspace-files` finds the id already present in the entry group and throws `duplicate loader entry id: workspace-files`, which `dsh-app-boot` rethrows as `dsh: plugin tree failed to load: …`.

**Why the whole boot fails instead of accepting the later row.** Loader entry ids are unique keys in the entry group: an id maps to exactly one plugin entry (id → name/config), so composition is a keyed merge, not a last-wins list. `insert` semantically means "add a new entry"; it is not an upsert. Because a duplicate `insert` means the composed configuration is ambiguous/self-contradictory, the loader treats it as a fatal configuration error and refuses to build the plugin tree at all rather than silently picking a winner. This is the standard "misconfiguration fails loud at load" behavior — a half-loaded plugin tree (e.g. loading one copy, dropping the other) could produce two plugin instances of the same service and worse downstream failures.

## 2. Layering rules for a profile patch acting on a bundle-provided plugin

| Operation | Safe? |
|---|---|
| **Changing the plugin's config by id** (e.g. an overlay entry keyed on `workspace-files` that sets `config`, or `disabled: true`) | ✅ Safe — it targets an existing entry; the loader merges config onto the existing id. |
| **Adding an insert row for an id no bundle ships** | ✅ Safe — genuinely new entry, no collision (e.g. the profile's `dsh-file-trace` and `dsh-profiles` rows, which boot fine). |
| **Adding an insert row for an id a bundle already ships** | ❌ **Fatal** — `insert` for an existing id is a duplicate loader entry and aborts the entire boot. |

**The maintainer's action is the third case**: manually inserting `workspace-files` into the profile patch while the bundle already ships that exact row.

**Evidence row that proves it:** `web-app-patch-excerpt.txt` shows the identical `- insert: - id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'` row already present in the installed 0.1.5-alpha.2 web-app bundle patch (L110–111), and the excerpt itself notes the adjacent `session-controller` / `settings-controller` bundle rows were never manually inserted into the profile patch — those did not collide; only `workspace-files` did.

## 3. Fix

**Minimal correct change:** delete the manually added `workspace-files` insert block (the three lines of `- insert:` plus the two comment lines above it, including the incorrect "如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏" rationale) from:

`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`

No other file changes. The bundle's `cordis.patch.yml` already provides `workspace-files`, so after deleting the duplicate row `dsh web` boots with the plugin loaded exactly once.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` (the plugin) never even loaded — the failure happens in loader composition, before any plugin code runs. Neither the plugin's implementation nor its package is implicated by this crash; it is purely a profile-configuration error.

**Could any plugin-side change resolve it?** No. No change to the plugin's source, exports, or its own manifest can help, because the collision is between two loader *entry declarations* in two different `cordis.patch.yml` files. The only resolution is at the composition layer: remove one of the two duplicate declarations (the profile's, per the minimal fix above). (Guarding inside the plugin's `apply()` would be useless for the same reason — `apply` never runs.)

Note also: the manual insert was based on a wrong diagnosis. The "文件资源服务不可用" read failure after upgrade has some other cause (service registration/availability at runtime); the profile was *not* missing the plugin, since the bundle already shipped it. After removing the duplicate row, that original symptom should be re-investigated separately rather than papered over with inserts.

## 4. Prevention

**Maintainer-side (before adding a row by hand):**
- Inspect the installed bundle's composition first: the `cordis.patch.yml` inside the installed web-app bundle under the npm tree (e.g. `…\node_modules\@deepseek-ai\dsh\…\packages/bundle/web-app/cordis.patch.yml` — reachable from the paths printed in any boot stack) and grep it for the entry id before inserting (e.g. `workspace-files`).
- Equivalently, list the loader entries the bundle composes (any `dsh` command/printout that dumps the resolved plugin tree, or the bundle's resolver manifest `dependencies`) and check whether the id already exists.
- Rule of thumb: a profile patch may *configure/disable* a bundle-provided plugin by id, and may *insert* only ids the bundle does not ship. Never `insert` an id that already exists anywhere in the composed tree.
- Treat comment rationalizations like "保留以确保升级 profile 不遗漏" as a smell: on an in-place bundle upgrade, new rows come from the *new bundle's* patch file automatically; the profile does not need to re-declare them.

**Host-side (making the failure actionable at boot):**
When `EntryGroup.update` raises `duplicate loader entry id: X`, the host boot error should:
- name both declaring sources — e.g. `duplicate loader entry id 'workspace-files': declared in profile patch (C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml) and in bundle patch (…/web-app/cordis.patch.yml)`;
- blame the user-editable side explicitly ("the profile patch row is the duplicate; the bundle row is authoritative for bundle-provided plugins");
- tell the user exactly what to delete ("remove the `- insert:` block for id 'workspace-files' from your profile's cordis.patch.yml");
- ideally distinguish the three layering cases so users learn that config-by-id is the supported way to adjust bundle plugins.

That converts an opaque `TypeError: duplicate loader entry id` stack into a one-line, self-diagnosing instruction.
