# S22 Diagnostic Report — The Duplicate Insert That Crashed the Boot

## 1. Root cause

**Which two declarations collide.** The loader entry id `workspace-files` is declared twice as an `insert` row in two `cordis.patch.yml` files that are merged into the same plugin tree at boot:

1. The web-app **bundle** patch — `packages/bundle/web-app/cordis.patch.yml` in the installed 0.1.5-alpha.2 npm tree — already ships `- insert: - id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'` (shown at L110–111 in `web-app-patch-excerpt.txt`).
2. The **profile** patch — `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml` (`profile-patch-excerpt.txt`) — contains the maintainer's manually added block with the identical id `workspace-files` and the identical package name `@deepseek-ai/dsh-api-workspace-files`, under the comment "如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏".

**Where the collision is detected.** The stack trace in `boot-crash-log.txt` pinpoints the layer: `TypeError: duplicate loader entry id: workspace-files at EntryGroup.update (@deepseek-ai/cordis-plugin-loader/lib/index.js:91:28)`, wrapped by `Include._apply` (`@deepseek-ai/dsh-app-boot/lib/index.js:240:19`) during `boot`, and surfaced as `Error: dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include): duplicate loader entry id: workspace-files`. So the check lives in the **Cordis plugin loader's entry-group merge (`EntryGroup.update`)**, applied while the boot glue expands the `cordis:include` loader entry — i.e., at plugin-tree load time, before any plugin code runs.

**Why the whole boot is refused instead of accepting the later row.** Loader entry ids are unique keys in the plugin tree. When `EntryGroup.update` encounters an id that already exists, it cannot know which of the two declarations is authoritative — the two rows are textually identical here only by coincidence, and in general a duplicate could mean two conflicting configs for one plugin. Silently "accepting the later row" would make composition order-dependent and could mask a genuine misconfiguration, so it violates the repo's misconfiguration rule ("Misconfiguration fails loud at load when self-contained"). The conflict is self-contained at load time, so the loader throws a `TypeError` immediately and the boot fails fast rather than producing an ambiguously composed tree. The generic wrapper `throw new Error(${binName}: ${stage}: ${detail}${stack})` in `dsh-app-boot/lib/index.js:1545` reports the stage ("plugin tree failed to load") and detail without dropping the original cause.

## 2. Layering rules (profile patch acting on a bundle-provided plugin)

- **Safe — changing an existing plugin's config by id.** A profile patch may override or extend the `config` of a plugin that a bundle already ships, keyed by the same id. This refines behavior without changing the tree's plugin set, so the loader merges it as an update to the existing entry.
- **Safe — adding a row for an id no bundle ships.** Inserting a genuinely new loader entry id (like the pre-existing `dsh-file-trace` / `@dsh-external/dsh-file-trace` and `dsh-profiles` / `@lhh010/dsh-profiles` rows in `profile-patch-excerpt.txt`) extends the tree with a plugin the bundle does not provide. No id collision is possible.
- **Fatal — adding an insert row for an id a bundle already ships.** The bundle's `cordis.patch.yml` is applied via `cordis:include`, and the loader's `EntryGroup.update` rejects a second declaration of the same entry id outright. This is the fatal case.

**Which case is the maintainer's action.** The maintainer's manual insert of `workspace-files` is the **fatal third case**: 0.1.5-alpha.2's web-app bundle already ships that id (proven by `web-app-patch-excerpt.txt`, rows L110–111: `- insert: - id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'`), and the profile patch adds it a second time. The bundle row is the evidence row that proves the collision; the maintainer's own comment in `profile-patch-excerpt.txt` even concedes it ("如果 web-app bundle 已包含此行则此条为冗余") — the guess was wrong for 0.1.5-alpha.2.

## 3. Fix

**What to change and where.** Delete the entire manually added `workspace-files` insert block from the **profile patch**, `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`:

```yaml
# workspace-files: 右侧 Sidebar 文件预览所需的宿主服务（0.1.5 系列新增）
# 如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏
- insert:
    - id: workspace-files
      name: '@deepseek-ai/dsh-api-workspace-files'
```

The bundle already provides the same row (`web-app-patch-excerpt.txt`), so after deleting it the tree contains exactly one `workspace-files` declaration and the loader merges cleanly. This is the minimal correct change — nothing else in the profile patch (the `dsh-file-trace`, `dsh-profiles`, and external client plugin rows) collides with any bundle id.

This also addresses the original symptom correctly: since the bundle supplies `workspace-files`, the earlier "文件资源服务不可用" failure in the right-Sidebar tab was not caused by a missing profile row at all — that diagnosis was mistaken, and no profile-side addition was ever needed for this id.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` never gets a chance to load; the failure happens earlier, in the loader's entry-merge, purely from patch composition. **Could any plugin-side change resolve it?** No. The duplicate declaration exists only in the two `cordis.patch.yml` files; no change inside the plugin's source, exports, or config can remove the extra profile-side declaration. Only editing (here: deleting from) the profile's `cordis.patch.yml` resolves the boot failure.

## 4. Prevention

**Author-side (before hand-adding a row).** Before inserting any row into the profile's `cordis.patch.yml`, check the **installed bundle tree** for the same id — specifically the npm-installed `.../node_modules/@deepseek-ai/dsh/node_modules/@deepseek-ai/dsh-app-web...` / `packages/bundle/web-app/cordis.patch.yml` (the exact file captured in `web-app-patch-excerpt.txt`). Grep the installed bundle's patch files for the id:

```powershell
Select-String -Path "$env:APPDATA\npm\node_modules\@deepseek-ai\dsh\**\cordis.patch.yml" -Pattern "workspace-files"
```

If the id already appears in a bundle-provided patch, the profile must not insert it again (at most it may override that plugin's config by id, which is the safe layering operation). Also distrust "keep it just in case" comments like the one in `profile-patch-excerpt.txt` — after an in-place upgrade, a row that was needed under 0.1.2/0.1.3 may now be bundle-provided, and keeping it turns a stale comment into a boot crash. Verify the actual upgraded version's bundle contents, not the old version's behavior.

**Host-side (what boot could print to make this actionable).** The current message only names the id and the loader-internal stack. At boot, the host/loader could:

1. **Name the colliding sources** — print both file paths that declare the id, e.g. `duplicate loader entry id: workspace-files declared in C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml (profile insert) and ...\@deepseek-ai\dsh-app-web...\cordis.patch.yml (web-app bundle insert, L110)`. This directly tells the maintainer whom to blame (the profile patch — the later, hand-added declaration) and what to delete (the profile-side `- insert: - id: workspace-files` block).
2. **Suggest the remedy** — append a hint such as "remove the duplicate insert row from the profile patch, or use a config override (same id, config only) to customize a bundle-provided plugin".
3. **Distinguish fatal from safe duplicates** — if a later row is a pure config update for an existing id, merge it under the documented layering rules instead of failing; reserve the hard failure for a second `insert` of the same id, which is what happened here.
