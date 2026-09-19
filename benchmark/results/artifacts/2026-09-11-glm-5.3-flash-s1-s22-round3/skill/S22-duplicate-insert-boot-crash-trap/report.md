# S22 · The Duplicate Insert That Crashed the Boot — Diagnostic Report

Evidence pack read from `environment/fixture/`: `boot-crash-log.txt`, `profile-patch-excerpt.txt`, `web-app-patch-excerpt.txt`, `README.md`.

## 1. Root cause

**The two colliding declarations** are two `insert:` rows with the same id `workspace-files`, both resolving to `@deepseek-ai/dsh-api-workspace-files`:

1. The **bundle-provided row** in the web-app bundle's `packages/bundle/web-app/cordis.patch.yml` (L110–111 in the installed 0.1.5-alpha.2 tree, per `web-app-patch-excerpt.txt`):

    - insert:
      - id: workspace-files
        name: '@deepseek-ai/dsh-api-workspace-files'

2. The **manually added row** in the profile patch `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml` (last block of `profile-patch-excerpt.txt`), added by the maintainer after seeing 文件资源服务不可用:

    - insert:
      - id: workspace-files
        name: '@deepseek-ai/dsh-api-workspace-files'

  The block even carries the maintainer's own warning: "如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏".

**Layer where the collision is detected**: the plugin-loader include stage of boot. The stack trace in `boot-crash-log.txt` shows:

- `EntryGroup.update` at `@deepseek-ai/cordis-plugin-loader/lib/index.js:91:28` throws `TypeError: duplicate loader entry id: workspace-files`;
- it propagates through `Include._apply` (`dsh-app-boot/lib/index.js:240:19`) into `boot` (`dsh-app-boot/lib/index.js:1534:3`) → `runProfile` → `runCli`, surfacing as `Error: dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include): duplicate loader entry id: workspace-files`.

So the collision is caught at the **loader entry-group merge layer** (`cordis:include` application inside `dsh web` boot), not at plugin initialization and not at config resolution.

**Why the loader refuses the whole boot instead of accepting the later row**: loader entry ids are identity keys for the plugin tree. A duplicate id is an ambiguous composition — which row's `name`/`config` would win is undefined, so silently taking the later row would make composition order semantically significant and hide a mis-authored patch. `EntryGroup.update` therefore treats the duplicate as a hard invariant violation and throws during `cordis:include` application, before any plugin is instantiated; since the plugin tree cannot be assembled, the entire boot aborts (fail loud at the earliest resolvable point).

## 2. Layering rules — safe vs. fatal operations for a profile patch on a bundle-provided plugin

- **Safe: changing an existing plugin's config by id** — a profile patch tuning the `config` of a plugin the bundle ships overlays one entry; no new loader identity is created.
- **Safe: adding a row for an id no bundle ships** — the profile genuinely contributes a new loader entry. This is what the pre-existing profile rows do: `dsh-file-trace` → `@dsh-external/dsh-file-trace` and `dsh-profiles` → `@lhh010/dsh-profiles` (external client plugins no bundle provides).
- **Fatal: adding a row for an id a bundle already ships** — the bundle's include already registers that entry id; the profile's second `insert` row produces `duplicate loader entry id` and aborts boot. To customize a bundle plugin, patch its config by id, never re-insert it.

**The maintainer's case is the fatal one**: 0.1.5-alpha.2's web-app bundle already provides `workspace-files`, and the maintainer manually inserted a second row for the same id into the profile's `cordis.patch.yml`.

**Proving evidence row**: `web-app-patch-excerpt.txt` states "The workspace-files row is already here (L110-111 in the installed tree)" and shows the identical `id: workspace-files` / `name: '@deepseek-ai/dsh-api-workspace-files'` insert row — byte-for-byte matching the profile's manual block. The crash log's `duplicate loader entry id: workspace-files` is the runtime confirmation. The excerpt also notes `session-controller` / `settings-controller` are likewise bundle-provided and were never manually inserted, showing the correct layering convention the manual row broke.

## 3. Fix

**Exact change and file**: delete the manual `workspace-files` insert block (the two trailing comment lines plus the `insert:` row for `id: workspace-files`) from the profile patch `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`:

    # workspace-files: 右侧 Sidebar 文件预览所需的宿主服务（0.1.5 系列新增）
    # 如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏
    - insert:
        - id: workspace-files
          name: '@deepseek-ai/dsh-api-workspace-files'

Nothing else changes: the bundle's own row (web-app bundle `cordis.patch.yml` L110–111) already inserts the plugin in 0.1.5-alpha.2, so composition is complete without the profile row. After the clean boot, re-diagnose the original 文件资源服务不可用 symptom separately — if content reads still fail, the cause lies in the service runtime, not in missing profile composition.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` never instantiated; the crash happens in the loader (`EntryGroup.update` → `Include._apply`) before any plugin code runs. The plugin is not misbehaving.

**Could any plugin-side change resolve the boot failure?** No. The duplicate identity exists purely between two composition files (profile patch vs. bundle patch). Only removing one of the two `insert` declarations — in practice the profile's manual row — clears the failure. No change to plugin code, defaults, or package metadata can deduplicate two loader entries sharing one id.

## 4. Prevention

**Author-side check before hand-inserting a row**: inspect the installed bundle's patch before editing the profile patch — `packages/bundle/web-app/cordis.patch.yml` under the npm-installed tree (proven reachable via the `node_modules` path in the crash log), and grep it for the target `id` first. The excerpts show the check is cheap: `workspace-files`, `session-controller`, and `settings-controller` are all bundle-provided in 0.1.5 and none should ever be manually inserted into a profile patch. If the id exists there, the profile may only tune that entry's `config` — never add a second `insert` row. After any in-place version upgrade, re-read the bundle patch: rows legitimately manual under 0.1.2/0.1.3 can become bundle-provided under 0.1.5, exactly what the maintainer's own "冗余" comment anticipated but did not act on.

**Host-side improvements at boot**: on a duplicate id, the host should fail with a message that blames both sources and names the deletion target, e.g.:

    duplicate loader entry id: workspace-files
      first inserted by bundle packages/bundle/web-app/cordis.patch.yml (L110-111)
      duplicate insert in profile patch C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml
      → delete the workspace-files insert block from the profile patch; to override a bundle plugin, patch its config by id instead of inserting a new row

Concretely it should report (a) which file/line supplied the first registration, (b) which file supplied the duplicate, and (c) which row to delete — and ideally print a non-fatal advisory at boot listing profile insert ids that shadow bundle-provided ids, before they hard-fail. The current crash output names only the id (`workspace-files`), leaving the maintainer to diff the two patch files by hand.
