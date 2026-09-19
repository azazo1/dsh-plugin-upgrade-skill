# S22 · The Duplicate Insert That Crashed the Boot — Analysis Report

Task: S22-duplicate-insert-boot-crash-trap (read-only analysis; no fixture or repo files were modified).

## 1. Root cause

**The two colliding declarations are two `insert` rows with the same loader entry id `workspace-files`:**

1. **Profile patch** — `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`, the manually added block at the end:
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```
2. **Web-app bundle patch** — the installed 0.1.5-alpha.2 tree's `packages/bundle/web-app/cordis.patch.yml` (L110–111), which already ships the *identical* row:
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```

**Where the collision is detected:** in the Cordis **plugin loader layer**, not in the plugin itself. The crash stack shows `cordis-plugin-loader`'s `EntryGroup.update` throwing `duplicate loader entry id: workspace-files`, reached via `Include._apply` (`failed to apply loader entry include (cordis:include)`) while `dsh-app-boot` builds the plugin tree at boot. Entry ids in a loader group are a set, not a list: a second registration of the same id is an inconsistency, not an override.

**Why the whole boot is refused instead of "later row wins":** the `cordis:include` directive applies patch entries as an atomic tree construction step. Loader entry ids must be unique per group because downstream Cordis resolution (config lookup, dependency ordering, lifecycle ownership) keys plugins by id; silently keeping one of two rows would make it ambiguous which declaration owns the entry. Cordis therefore fails loud at load time — the profile composition is invalid, so `dsh web` aborts before any plugin (including the unrelated ones) starts. This matches the repo convention "misconfiguration fails loud at load when self-contained".

Note the original symptom (文件资源服务不可用, the Sidebar document tab failing to read) was **not** caused by a missing insert row: the bundle already provides `workspace-files`, so adding it could never be the right fix. The maintainer misdiagnosed the 0.1.2/0.1.3 → 0.1.5-alpha.2 in-place upgrade symptom and the "fix" converted a runtime service failure into a boot crash.

## 2. Layering rules for a profile patch acting on a bundle-provided plugin

| Operation | Verdict |
|---|---|
| Changing the plugin's **config by id** (e.g. a `config:` block keyed to `workspace-files`) | **Safe.** Config overlays target an existing entry; they do not create a second loader entry. |
| Adding an insert row for an id **no bundle ships** (a genuinely new plugin, like `dsh-file-trace` or `dsh-profiles` above it) | **Safe.** New id, no collision; this is exactly what profile patches are for. |
| Adding an insert row for an id a **bundle already ships** | **Fatal.** Produces `duplicate loader entry id` and crashes the entire boot at load time. |

**The maintainer's action is the third (fatal) case.** The proving evidence row is the bundle's `web-app-patch-excerpt.txt` L110–111: `- id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'` — identical to the profile's manual insert. The profile excerpt's own comment even hedges ("如果 web-app bundle 已包含此行则此条为冗余") — it guessed redundancy instead of verifying, and "redundant" is wrong: in this loader a duplicate is not redundant, it is invalid.

## 3. Fix

**Delete the entire manual `workspace-files` insert block (both the comment lines and the three `- insert:` YAML lines) from `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`.** No other file changes; the bundle's own row continues to provide the plugin.

**Is the plugin's own code at fault? No.** `@deepseek-ai/dsh-api-workspace-files` was never loaded — the failure happens in the loader before plugin apply. **No plugin-side change can resolve this boot failure**, because the error is in the composition (profile patch + bundle patch), not in any plugin's implementation. (Separately, the *original* pre-crash symptom — 文件资源服务不可用 — may warrant its own investigation, e.g. service availability in the upgraded bundle, but that is unrelated to this crash and cannot be fixed by patch inserts.)

## 4. Prevention

**Author/maintainer side — before hand-adding any insert row:**
- Inspect the **installed bundle's `cordis.patch.yml`** (here `…\node_modules\@deepseek-ai\dsh\node_modules\…\packages/bundle/web-app/cordis.patch.yml`, or the bundle patch inside the installed 0.1.5-alpha.2 tree) and grep it for the intended entry id. If the id already appears, do not insert; adjust `config:` by id instead if per-profile settings are needed.
- Compare against sibling bundle-provided rows (`session-controller`, `settings-controller`) as the model: those were never manually inserted into the profile patch, and the profile boots fine with them.
- Treat an upgrade symptom like "service unavailable" as a runtime/service issue to diagnose (versions, service start errors), not as "row missing from my patch" — the bundle, not the profile, owns composition of shipped plugins.

**Host side — making the failure actionable at boot:** when `EntryGroup.update` raises `duplicate loader entry id: X`, the boot error should print:
- **both source locations** of the duplicate id — the bundle patch path (with line number) and the profile patch path (with line number) — so the blame is unambiguous: the *user-editable profile patch* row is the one to delete;
- a remediation line, e.g. `remove the duplicate "- insert: id: workspace-files" block from C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml (already provided by the web-app bundle patch)`;
- optionally, `dsh` could pre-validate the merged patch (profile ∪ bundles) before boot and warn on ids present in both, or `dsh profile` tooling could reject/flag a profile insert whose id already resolves to a bundle-shipped entry — turning a stack-trace crash into a one-line actionable message.
