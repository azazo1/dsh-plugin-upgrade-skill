# S22 · The Duplicate Insert That Crashed the Boot — Diagnostic Report

Evidence pack (read-only): `boot-crash-log.txt`, `profile-patch-excerpt.txt`, `web-app-patch-excerpt.txt`, `README.md` under the fixture directory.

## 1. Root cause

**Which two declarations collide.** The loader entry id `workspace-files` is declared twice as an `insert` row:

1. The web-app bundle's own `cordis.patch.yml` (`packages/bundle/web-app/cordis.patch.yml`, lines 110–111 in the installed 0.1.5-alpha.2 tree) already ships:
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```
2. The maintainer manually appended the identical id to the profile patch `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`:
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```

During boot, the profile's `cordis:include` of the web-app bundle's patch and the profile's own rows are merged into one entry group; the second `insert` with id `workspace-files` collides with the first.

**At which layer the collision is detected.** It is detected inside the Cordis plugin loader's entry-group bookkeeping, not inside any plugin. The stack trace pins it precisely:

```
TypeError: duplicate loader entry id: workspace-files
    at EntryGroup.update (.../@deepseek-ai/cordis-plugin-loader/lib/index.js:91:28)
    at Include._apply (.../@deepseek-ai/dsh-app-boot/lib/index.js:240:19)
    at boot (.../@deepseek-ai/dsh-app-boot/lib/index.js:1534:3)
```

So the failure surfaces while `dsh-app-boot` applies a loader entry include (`failed to apply loader entry include (cordis:include)`), and the actual duplicate check throws from `EntryGroup.update` in `@deepseek-ai/cordis-plugin-loader` — the loader layer that owns unique entry ids across the composed patch tree. No plugin code ever runs.

**Why the loader refuses the whole boot instead of accepting the later row.** Loader entry ids are the identity key for every entry in the composed tree (config resolution, effect ownership, disposer identity). Silently accepting a later duplicate row would make boot composition order-dependent and ambiguous: two rows claiming the same id could carry different `name`s or configs, and "last one wins" would hide a real composition mistake — exactly the class of misconfiguration the repo's "misconfiguration fails loud" rule targets. The loader therefore treats a duplicate id as a hard, unrecoverable error at load time and aborts the whole plugin-tree load, which the boot wrapper rethrows as `Error: dsh: plugin tree failed to load`. The boot ends before any service is provided — hence the immediate crash rather than a degraded web app.

## 2. Layering rules for profile patches acting on bundle-provided plugins

- **Safe: changing the plugin's config by id.** A profile patch may reference an entry id the bundle already ships in order to override/adjust its `config`. Reconciling config for an existing id is the intended layering mechanism (profile refines bundle defaults); it does not create a second entry, so no duplicate-id collision occurs.
- **Safe: adding a row for an id no bundle ships.** If neither the bundle nor any included patch declares the id, a profile `insert` is the correct way to contribute a genuinely external plugin (this is what the profile's pre-existing rows do, e.g. `id: dsh-file-trace` → `@dsh-external/dsh-file-trace` and `id: dsh-profiles` → `@lhh010/dsh-profiles` — external packages the web-app bundle does not provide).
- **Fatal: adding an `insert` row for an id a bundle already ships.** The bundle already inserts that id; a second `insert` with the same id makes the entry-group id non-unique and the loader aborts the boot with `duplicate loader entry id`.

**Which case is the maintainer's action.** The fatal third case: the maintainer hand-added an `insert` row for `workspace-files` into the profile patch even though the web-app bundle of 0.1.5-alpha.2 already ships it.

**Which evidence row proves it.** `web-app-patch-excerpt.txt`, quoting the installed tree (`packages/bundle/web-app/cordis.patch.yml`, L110–111):

```yaml
- insert:
    - id: workspace-files
      name: '@deepseek-ai/dsh-api-workspace-files'
```

together with the profile excerpt's own warning comment — "如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏" — which acknowledges the redundancy risk and the crash log confirms the loader rejects it. The adjacent bundle rows for `session-controller` and `settings-controller` are likewise bundle-provided and were never hand-inserted, which is why they cause no crash.

## 3. Fix

**What to change and in which file.** Delete the manually added `workspace-files` `insert` block (the three lines `- insert:` / `- id: workspace-files` / `- name: '@deepseek-ai/dsh-api-workspace-files'` plus its two comment lines) from the profile patch:

`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`

That is the whole fix. The bundle already inserts `workspace-files`, so after removing the duplicate row the composed entry group is unique again and `dsh web` boots. No config override is needed either — the profile row carried no `config` keys, only the same `id`/`name` the bundle already provides, so it was pure duplication with zero added behavior.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` never gets a chance to load — the stack trace shows the failure in `cordis-plugin-loader`'s `EntryGroup.update` during patch composition, before any plugin `apply` runs. The plugin is entirely uninvolved.

**Could any plugin-side change resolve the boot failure?** No. The collision is between two *declarations of the same entry id* in two patch files; it exists at the loader layer before plugin identity is even resolved. No change inside the plugin (renaming its service, changing its code, altering exports) can de-duplicate two rows that both ask the loader to insert id `workspace-files`. Only removing one of the two declarations — the profile-side one, since the bundle-provided one is the authoritative shipped copy — resolves it.

(Note on the original symptom: the "文件资源服务不可用" read failure that motivated the insert was a separate 0.1.2→0.1.5 upgrade issue; since 0.1.5's web-app bundle already inserts `workspace-files`, that insert would have been redundant anyway — the sidebar fix must lie elsewhere, not in this row.)

## 4. Prevention

**What to check in the installed bundle before hand-adding a row.** Before inserting an id manually, grep the installed package's bundle patches — under the npm global tree, e.g. `C:\Users\lhh\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\node_modules\@deepseek-ai\dsh-web-app\**/cordis.patch.yml` (source: `packages/bundle/web-app/cordis.patch.yml`) — for the id:

```
grep -n "workspace-files" .../node_modules/@deepseek-ai/dsh-web-app/cordis.patch.yml
```

If the id appears in any shipped `cordis.patch.yml` / `cordis.yml`, the bundle already owns that entry: never `insert` it from the profile; only add a profile-side `config` override keyed by that id if customization is actually needed. A general rule: the profile patch should only contain ids that exist nowhere in the installed bundle tree (like the profile's `dsh-external/dsh-file-trace` and `@lhh010/dsh-profiles` rows), and its comment should record the check ("verified absent from web-app bundle 0.1.5-alpha.2") rather than an unverified "保留以确保升级 profile 不遗漏" hope. Additionally, the original symptom should be diagnosed against the new version's actual composition (e.g. inspect the running plugin tree / session log to see whether `workspace-files` is provided) before concluding the row is "missing".

**What the host could print at boot to make the failure actionable.** The current error `duplicate loader entry id: workspace-files` names the id but not the culprits. The loader/boot layer could emit a diagnostic that blames both sources and prescribes the deletion:

- the two declaration sites — which file supplied each row (the bundled `packages/bundle/web-app/cordis.patch.yml` vs. the profile's `~/.dsh/profiles/web/cordis.patch.yml`), with line numbers;
- an explicit remediation line, e.g.:
  `duplicate loader entry id: workspace-files — already inserted by bundle @deepseek-ai/dsh-web-app (cordis.patch.yml:110); remove the insert row from profile patch C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml (or change it to a config override for id workspace-files)`;
- and, ideally, a one-line inventory at boot ("bundle-provided ids: workspace-files, session-controller, settings-controller, …") or a warning (not a crash) when a profile insert shadows a bundle-shipped id, so the redundancy is visible before it hard-fails.

That turns the crash from "which of my many patch rows is duplicated?" into "delete this exact block in this exact file".
