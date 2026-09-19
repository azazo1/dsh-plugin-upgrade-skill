# S22 · The Duplicate Insert That Crashed the Boot — Read-Only Diagnosis

**Task**: S22-duplicate-insert-boot-crash-trap · **Mode**: plugin-upgrade Mode A (inspect, read-only)
**Fixture**: real 2026-09-09 in-place upgrade of dsh to 0.1.5-alpha.2 (npm global, Windows 11, Node 24.14.1), profile created under 0.1.2/0.1.3.

## 1. Root cause

**Which two declarations collide.**

1. **Profile layer** — the maintainer's manual block at the end of `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml` (profile-patch-excerpt.txt):
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```
2. **Bundle layer** — the web-app bundle's own `cordis.patch.yml` in the installed 0.1.5-alpha.2 npm tree (`packages/bundle/web-app/cordis.patch.yml`, shown in web-app-patch-excerpt.txt L110–111) already contains the byte-identical row:
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```

Both rows reach the loader with the entry id `workspace-files`; Cordis entry ids must be unique across the fully composed tree.

**Where the collision is detected (Cordis layer).** The crash log's stack names the exact layers:

```
failed to apply loader entry include (cordis:include):
duplicate loader entry id: workspace-files
TypeError: duplicate loader entry id: workspace-files
    at EntryGroup.update (.../@deepseek-ai/cordis-plugin-loader/lib/index.js:91:28)
    at Include._apply (.../@deepseek-ai/dsh-app-boot/lib/index.js:240:19)
    at boot (.../@deepseek-ai/dsh-app-boot/lib/index.js:1534:3)
    at async runProfile (.../profile-boot-Dk-7KqJc.js:311:14)
```

The composition pipeline is: profile patch + bundle patches → `dsh-app-boot` → **`cordis:include` directive application** (`Include._apply`) → **`cordis-plugin-loader`'s `EntryGroup.update`**, which enforces unique entry ids. So the duplicate is detected in the **plugin-loader composition layer (EntryGroup, while applying include directives)** — before any plugin code is resolved, imported, or executed. Nothing in `@deepseek-ai/dsh-api-workspace-files` itself ever ran.

**Why the whole boot is refused instead of "later row wins".** Cordis composition treats entry ids as the stable identity keys the whole tree is keyed on (dependency resolution, inject wiring, patch-by-id `config`/`disabled` targeting). A duplicate id would make those lookups ambiguous, so duplicate insert is a **fatal, fail-loud configuration error**, not a last-write-wins override. This matches the repo's misconfiguration policy ("misconfiguration fails loud at load when self-contained") and the skill's troubleshooting row for this exact signature: *Cordis treats duplicate insert as a fatal error (no silent override); delete the duplicate insert block in the profile patch to restore boot* (plugin-upgrade skill, troubleshooting.md, sourced from discussion #5999). The fail-closed behavior is deliberate: the alternative (silently picking one row) would hide a profile/bundle drift that the user needs to see.

## 2. Layering rules for a profile patch acting on a bundle-provided plugin

| Operation | Verdict | Why |
|---|---|---|
| Change the plugin's **config by id** (`config: {workspace-files: {...}}`) or toggle `disabled` | ✅ **Safe** | Patch-by-id merges into the existing bundle entry; no new entry id is created |
| `insert` a row for an id **no bundle ships** (e.g. the profile's own `dsh-file-trace`, `dsh-profiles` rows) | ✅ **Safe** | The insert introduces the only entry with that id |
| `insert` a row for an id **a bundle already ships** | ❌ **Fatal** | Two entries claim the same id → `duplicate loader entry id` at `EntryGroup.update`; the entire `dsh web` boot aborts |

**The maintainer's action is the fatal third case.** The proving evidence row is in `web-app-patch-excerpt.txt`:

```yaml
# The workspace-files row is already here (L110-111 in the installed tree):
- insert:
    - id: workspace-files
      name: '@deepseek-ai/dsh-api-workspace-files'
```

i.e. the web-app bundle of the freshly installed 0.1.5-alpha.2 already provides `workspace-files` — exactly as the adjacent bundle rows `session-controller` / `settings-controller` show the normal pattern (bundle-provided, never manually inserted into the profile patch). Ironically, the maintainer's own comment in the profile patch anticipated this ("如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏" — "redundant if the bundle already has it; kept to be safe") but guessed wrong about the consequence: it is not redundant-but-harmless, it is boot-fatal.

## 3. Fix

**Exact change**: delete the manually added block (comment lines included) from `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`:

```yaml
# workspace-files: 右侧 Sidebar 文件预览所需的宿主服务（0.1.5 系列新增）
# 如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏
- insert:
    - id: workspace-files
      name: '@deepseek-ai/dsh-api-workspace-files'
```

No other file changes. The bundle's own copy (web-app `cordis.patch.yml`) stays untouched — it is inside the installed npm tree and is the row that actually provides the service. After deletion, `dsh web` boots again with `workspace-files` provided by the bundle.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` never loaded — the crash happens in composition, before plugin resolution. **Could any plugin-side change resolve the boot failure?** No. The error is in the profile's composition file; no amount of plugin source, manifest, or dependency change can prevent two composition rows with the same entry id from colliding. The only resolution is on the composition side: remove the duplicate row.

**What about the original symptom (文件资源服务不可用 / file-resource service unavailable) that motivated the insert?** That symptom preceded the manual edit and must have a different root cause — the service is composition-provided by the bundle, so if the tab still fails *after* removing the duplicate row and rebooting, the cause is a compose/artifact gap (e.g. the in-place-upgrade client/bundle roster mismatch pattern) or a runtime service-registration failure, and should be diagnosed separately (per the skill's troubleshooting row: "如插件确实不可用，根因是 compose/artifact 缺口而非缺少 insert" — discussion #5999). It is never fixable by inserting a duplicate row.

## 4. Prevention

**Maintainer-side, before adding any row by hand:**

1. Inspect the **installed bundle's** `cordis.patch.yml` (for the web profile: the npm-installed tree's `packages/bundle/web-app/cordis.patch.yml` — i.e. `C:\Users\lhh\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\...\packages\bundle\web-app\cordis.patch.yml`) and grep it for the entry id (`workspace-files`) before writing an `insert`. If the id already appears there, the bundle provides it — do not insert.
2. Remember what each layer is for: bundle patch = what the shipped product composes; profile patch = *additions* (ids no bundle ships) and *adjustments by id* (`config`, `disabled`). An `insert` of a bundle-shipped id is always wrong.
3. On DSH upgrades that add new bundle modules, the correct posture is: change nothing in the profile — new bundle rows come with the bundle. Only touch the profile when adding genuinely external plugins (as the profile's own `dsh-file-trace` / `dsh-profiles` rows correctly do).

**Host-side, to make the failure actionable.** The current message (`duplicate loader entry id: workspace-files`) names the id but not which two sources collided. The host/boot layer could improve it to blame-and-instruct, e.g.:

```
Error: dsh: plugin tree failed to load:
  duplicate loader entry id: workspace-files
    declared by: profile patch C:Userslhh.dshprofileswebcordis.patch.yml (insert)
    already provided by: web-app bundle cordis.patch.yml (insert)
  Fix: delete the duplicate "- insert: [{id: workspace-files, ...}]" block from the
  profile patch; bundle-provided plugins must be configured by id (config/disabled),
  never re-inserted.
```

That requires `EntryGroup.update`/`Include._apply` to carry source attribution (file + directive) per entry id and print both owners — turning a cryptic loader TypeError into a one-step remediation. (Author-side corollary from the troubleshooting table: 0.1.5-series additions like `workspace-files` and `ui-sidebar-*` are bundle-automatic; plugin authors should document "do not insert" for bundle-provided ids in upgrade notes.)

## Skill-process notes

- Mode A (inspect) read-only: fixture, instruction, and skill references were only read; nothing under the benchmark repository was modified; no installs, migrations, or lifecycle scripts were run.
- Reference cross-check: plugin-upgrade skill `references/troubleshooting.md` carries this exact symptom row ("重启后宿主启动即崩： duplicate loader entry id", sourced from discussion #5999), which independently corroborates the diagnosis from the fixture evidence.

## Summary

- **Completed**: full root-cause attribution (profile insert × bundle insert of `workspace-files`, detected in `cordis-plugin-loader` `EntryGroup.update` while applying `cordis:include`); layering-rule matrix (config-by-id safe, insert-of-unshipped-id safe, insert-of-shipped-id fatal — the maintainer's case, proven by web-app-patch-excerpt.txt L110–111); minimal fix (delete the manual insert block from the profile's cordis.patch.yml; plugin code is not at fault and cannot fix it); prevention guidance for both maintainer and host.
- **Skipped**: none of the four questions; no version-corridor cards apply (this is a cross-version Cordis composition rule, not an API change — no version card exists, per troubleshooting.md).
- **Pending/residual risk**: the original "文件资源服务不可用" symptom is explained only negatively (it is not a missing composition row); if it persists after the fix, it needs separate runtime diagnosis (possible in-place-upgrade bundle/client roster drift).
- **Rollback**: n/a — read-only task; the only remediation belongs to the maintainer (delete one block in their profile patch).
