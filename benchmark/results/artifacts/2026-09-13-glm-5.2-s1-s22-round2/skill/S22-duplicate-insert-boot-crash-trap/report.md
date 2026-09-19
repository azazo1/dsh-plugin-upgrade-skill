# S22 · The Duplicate Insert That Crashed the Boot — Read-Only Diagnosis

**Mode:** A · inspect (read-only). Skill: `plugin-upgrade`. No files outside the designated output directory were written; the fixture was not modified.

Evidence: `boot-crash-log.txt`, `profile-patch-excerpt.txt`, `web-app-patch-excerpt.txt`, `README.md` (fixture pack, 2026-09-09, dsh 0.1.5-alpha.2 in-place npm-global upgrade on Windows 11, Node v24.14.1).

## 1. Root cause

**The two colliding declarations** — both are `insert` rows creating a loader entry with the same entry id, `workspace-files`:

1. **Bundle-provided row** — the web-app bundle's `cordis.patch.yml` in the installed 0.1.5-alpha.2 tree (`packages/bundle/web-app/cordis.patch.yml`, L110–111):
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```
2. **Manual profile row** — the block the maintainer appended to `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml` after seeing the 文件资源服务不可用 read failure:
   ```yaml
   # workspace-files: 右侧 Sidebar 文件预览所需的宿主服务（0.1.5 系列新增）
   # 如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```

**Where the collision is detected — the Cordis layer.** Not in the plugin's code and not in the dsh profile layer: it is the **Cordis plugin loader's entry-group bookkeeping**. The stack in the crash log names it exactly:

- `EntryGroup.update` in `@deepseek-ai/cordis-plugin-loader/lib/index.js:91` throws `TypeError: duplicate loader entry id: workspace-files`;
- the throw crosses into `Include._apply` (`dsh-app-boot`, applying the `cordis:include` patch operation) and surfaces as `dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include)` from `boot` → `runProfile` → `runCli`.

So the profile patch is applied as a `cordis:include` overlay onto the already-loaded bundle composition; within one entry group, loader entry ids must be unique, and `EntryGroup.update` enforces that as a hard precondition.

**Why the whole boot is refused instead of accepting the later row.** Loader entry ids are the stable identity used to address an entry for later config/patch/disable operations — accepting a second row with the same id would make that addressing ambiguous (two entries, one `@deepseek-ai/dsh-api-workspace-files` package instance each, plus undefined config-target semantics). The composition step therefore fails loud and aborts the plugin-tree load before any plugin runs: a config-level error at load time is not recoverable by continuing with an arbitrary winner. This matches the documented "misconfiguration fails loud at load when self-contained" rule; the cost is that one duplicate YAML block takes down the entire `dsh web` boot.

## 2. Layering rules for a profile patch acting on a bundle-provided plugin

| Operation on id `X` already shipped by the bundle | Verdict |
|---|---|
| Change the plugin's **config by id** (config entry keyed by `id: X`, or a patch that targets the existing entry) | **Safe** — it addresses the single existing bundle entry; no second entry is created |
| Add an `insert` row for an id **no bundle ships** | **Safe** — genuinely new entry, no collision (this is what the neighboring `dsh-file-trace` / `dsh-profiles` external-plugin rows correctly do) |
| Add an `insert` row for an id a **bundle already ships** | **Fatal** — `duplicate loader entry id` at `EntryGroup.update`; the whole boot aborts |

**Which case the maintainer hit:** the third one — a redundant duplicate `insert` of `workspace-files`, an id the web-app bundle already provides.

**The evidence row that proves it:** `web-app-patch-excerpt.txt` L110–111 (the bundle's own `- insert: - id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'`), which is byte-identical in id and package to the manual block in `profile-patch-excerpt.txt`. The adjacent `session-controller` / `settings-controller` rows confirm the pattern: bundle-provided ids are never manually inserted into the profile patch. The maintainer's own comment ("如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏") shows the doubt was already there but resolved the wrong way — "redundant" is not benign here, it is the crash.

## 3. Fix

**Minimal correct change:** delete the manually added block — the comment lines and the `- insert:` entry for `workspace-files` — from **`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`**. Nothing else in the profile patch or the bundle needs to change; after removal, the bundle's own row is the single provider of `workspace-files` and the boot proceeds.

If the maintainer later needs to adjust the plugin's behavior, the layering-correct operation is a **config entry keyed by `id: workspace-files`** in the profile patch, not a second insert.

**Is the plugin's code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` never loaded — the failure occurs in the composition stage before plugin instantiation. **Could any plugin-side change resolve it?** No; the duplicate is a property of the profile configuration versus the bundle composition, and the loader rejects it before plugin code can participate. (Conversely, this also means the crash is fully fixed on the config side alone.)

**Note on the original symptom:** removing the duplicate fixes the crash but does not, by itself, explain the earlier 文件资源服务不可用 read failure. Given the in-place 0.1.2/0.1.3 → 0.1.5-alpha.2 upgrade path, the likely cause is the known in-place-upgrade client/bundle mismatch (skill card DSH-0.1.5-A1-20: an in-place npm-global upgrade can serve a stale client combo that omits newly-added bundle modules; a full host restart self-heals the roster/combo mismatch). That symptom should be re-checked after the profile fix with a clean host restart before any further composition edits.

## 4. Prevention

**Maintainer-side, before hand-adding any row:**
- Look at the **installed bundle's `cordis.patch.yml`** in the npm-global tree (here `C:\Users\lhh\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\...\packages\bundle\web-app\cordis.patch.yml`) and search it for the entry id (e.g. `workspace-files`). If the id is already there, the bundle provides the plugin; the profile may only layer **config by id**, never a second `insert`.
- Treat "redundant, kept just in case" as a red flag in a patch file: in the Cordis loader, id-uniqueness within a group is a hard precondition, not a de-duplication hint.
- For a missing-service symptom, first rule out non-composition causes (stale client combo after in-place upgrade, host restart needed) before concluding the composition is missing a row.

**Host-side, to make the failure actionable:** the loader/boot error currently names only the id. It could print:
- **both source locations** — the file (and line) of each colliding declaration: the bundle's `cordis.patch.yml:110` and the profile's `cordis.patch.yml` block — so the collision is visible without archaeology;
- an explicit **whom-to-blame / what-to-delete** line, e.g.: `duplicate loader entry id 'workspace-files': entry already provided by bundle web-app (cordis.patch.yml:110); remove the duplicate - insert row for this id from C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml, or use a config entry keyed by this id to override settings`;
- optionally, a distinction between same-id-with-same-package (a pure duplicate — safe to point at the profile) and same-id-with-different-package (a genuine conflict needing a human decision), since the remediation message differs.

## Report structure per skill

- **pre-existing:** not collected (Mode A read-only inspection; no baseline suite run).
- **Completed:** root cause, layering-rule table, minimal fix, prevention — from the three fixture files and the crash stack; no writes outside this report.
- **Skipped:** no dependency/lockfile/registry inspection (config-layer failure, package identity identical on both rows); no runtime verification (unattended read-only task; also the fixture environment is not the live host).
- **Pending/residual risk:** the original 文件资源服务不可用 symptom is attributed by inference (DSH-0.1.5-A1-20 stale client combo) but not reproduced/verified; confirm after a clean host restart post-fix.
- **Rollback:** N/A — no changes were made; the fix itself (deleting the manual block) is its own rollback (the block's exact content is preserved in `profile-patch-excerpt.txt` if ever needed).
- **Recommendations:** host-side duplicate-id diagnostics with source locations and a targeted removal hint (§4); profile-side lint that flags insert ids already present in the resolved bundle composition before boot.
