# S22 · The Duplicate Insert That Crashed the Boot — Analysis Report

## 1. Root cause

**The two colliding declarations** are two `insert` loader entries with the same entry id `workspace-files`, both mapping to `@deepseek-ai/dsh-api-workspace-files`:

1. The **web-app bundle's** `cordis.patch.yml` (installed npm tree of 0.1.5-alpha.2, `packages/bundle/web-app/cordis.patch.yml`, L110–111) — shown in `web-app-patch-excerpt.txt`.
2. The **profile's** `cordis.patch.yml` (`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`) — the manual insert block shown in `profile-patch-excerpt.txt`, added by the maintainer after seeing the "文件资源服务不可用" error in the right-Sidebar document tab.

**Where the collision is detected:** at the **Cordis plugin-loader layer**, before any plugin code runs. The stack trace shows the failure inside `@deepseek-ai/cordis-plugin-loader`'s `EntryGroup.update` (`duplicate loader entry id: workspace-files`), reached through `Include._apply` — i.e. while the loader is applying the `cordis:include` entry groups assembled from the bundle patch plus the profile patch. It surfaces through `dsh-app-boot`'s `boot()` as `dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include)`. No plugin `apply()` was ever invoked.

**Why the loader refuses the whole boot instead of accepting the later row:** loader entry ids are unique keys within an entry group — the loader merges patches by id (that is how config overrides, `disabled` flags, etc. are addressed), so a duplicate id is structurally ambiguous, not a precedence question. `EntryGroup.update` throws `TypeError: duplicate loader entry id` on the second registration rather than overwriting or appending. Because composition happens before boot, this single throw aborts the entire `dsh web` startup — the harness deliberately fails loud at load time on self-contained misconfiguration rather than silently picking one row.

## 2. Layering rules

For a profile patch acting on a **bundle-provided** plugin:

| Operation | Verdict |
|---|---|
| Changing the plugin's **config by id** (e.g. a `config:` / `disabled` overlay keyed to the existing id) | **Safe** — this is what profile patches are for; the loader merges it onto the bundle's entry. |
| Adding an insert row for an id **no bundle ships** (a genuinely external plugin, like `dsh-file-trace` or `dsh-profiles`) | **Safe** — a new unique id, no collision. |
| Adding an insert row for an id **a bundle already ships** | **Fatal** — duplicate loader entry id; boot crash. |

**The maintainer's action is the third case.** The proving evidence rows are the identical pairs in the two excerpts: the bundle's `- id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'` (`web-app-patch-excerpt.txt`) versus the profile patch's identical insert block (`profile-patch-excerpt.txt`). Note the profile block even carries a comment admitting the doubt ("如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏") — the "redundant, keep it just in case" assumption is exactly wrong: in this loader a redundant insert is not idempotent, it is a crash. Contrast with the adjacent bundle rows (`session-controller`, `settings-controller`) which were never duplicated in the profile patch and caused no trouble.

(The original "文件资源服务不可用" symptom after the 0.1.2/0.1.3 → 0.1.5-alpha.2 in-place upgrade was a separate problem — most plausibly a stale profile composition that no longer matched the new bundle — and adding the insert row was a misdiagnosis of it as a missing-plugin problem.)

## 3. Fix

**Delete the manual `workspace-files` insert block** (the three lines `- insert:` / `- id: workspace-files` / `name: '@deepseek-ai/dsh-api-workspace-files'`, plus its comment) from:

`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`

Nothing else in the profile patch needs to change; the bundle's own row stays. Then re-run `dsh web`.

**The plugin's own code is not at fault.** `@deepseek-ai/dsh-api-workspace-files` never loaded — the crash happens during loader composition, before any plugin module resolves or `apply()` runs. **No plugin-side change can resolve this boot failure**; the defect is purely in the profile's patch YAML declaring a duplicate entry id.

If the underlying "文件资源服务不可用" symptom reappears after the row is removed, it must be diagnosed separately (e.g. verify the 0.1.5-alpha.2 bundle tree is complete and the profile's include of the web-app bundle patch is current) — not by re-inserting the plugin into the profile.

## 4. Prevention

**Maintainer-side, before adding such a row by hand:**
- Inspect the installed bundle's `cordis.patch.yml` (e.g. `…\node_modules\@deepseek-ai\dsh\…\packages\bundle\web-app\cordis.patch.yml`, or the bundle patch location the profile includes) and **grep for the entry id** (`workspace-files`) before inserting it. If the id already appears there, the bundle provides it; the profile must not.
- Remember the rule: profile patches may *overlay config* on a bundle-provided id or *insert genuinely new* ids, but must never *re-insert* a bundle-provided id.
- Treat "this row might be redundant, keep it anyway" as a red flag — redundancy here is fatal, not harmless.

**Host-side, to make the failure actionable:** the boot error should name the collision so the fix is mechanical, e.g.:

`dsh: plugin tree failed to load: duplicate loader entry id 'workspace-files' — this entry is already provided by the web-app bundle patch (packages/bundle/web-app/cordis.patch.yml). Remove the duplicate '- insert:' block for id 'workspace-files' from the profile patch C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml.`

Concretely, `EntryGroup.update` / the include-apply error path could carry the existing entry's source file and the offending entry's source file (both patches are known at composition time), and `dsh-app-boot` could print: the colliding id, which file each declaration came from, whom to blame (the profile patch, i.e. the user-editable layer, when one source is a bundle and the other a profile), and exactly which block to delete. Additionally, a `dsh` doctor/verify step (like the existing `verify-cordis-config` pattern) could pre-validate the profile patch against the bundle's entry ids and report the duplicate *before* boot is attempted.
