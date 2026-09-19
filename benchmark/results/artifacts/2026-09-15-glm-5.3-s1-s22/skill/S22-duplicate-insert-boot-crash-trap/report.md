# S22 · The Duplicate Insert That Crashed the Boot (Read-Only)

Task: analyze a `dsh web` boot crash after an in-place dsh 0.1.5-alpha.2 upgrade on Windows, where the maintainer manually inserted a `workspace-files` row into the profile's `cordis.patch.yml` after the right-Sidebar document tab failed its content read (文件资源服务不可用).

Evidence used (fixture, read-only):

- `boot-crash-log.txt` — full crash: `dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include): duplicate loader entry id: workspace-files`, thrown from `EntryGroup.update` in `@deepseek-ai/cordis-plugin-loader/lib/index.js:91`, wrapped by `Include._apply` / `boot` in `@deepseek-ai/dsh-app-boot`.
- `profile-patch-excerpt.txt` — `C:\\Users\\lhh\\.dsh\\profiles\\web\\cordis.patch.yml` with the manually added `- insert: [{ id: workspace-files, name: '@deepseek-ai/dsh-api-workspace-files' }]` block, under a comment claiming the row is 冗余 ("redundant") if the bundle already has it.
- `web-app-patch-excerpt.txt` — the web-app bundle's own `cordis.patch.yml` (npm-installed 0.1.5-alpha.2 tree, L110-111) already ships an identical `insert` row for `id: workspace-files` / `@deepseek-ai/dsh-api-workspace-files`.

Mode: Mode A inspect (read-only diagnosis). No file, dependency, or composition was changed; only this report was written.

## 1. Root cause

**Colliding declarations.** Two `insert` entries with the same loader entry id `workspace-files` resolve to the same package `@deepseek-ai/dsh-api-workspace-files`:

1. the bundle-provided row in the web-app bundle's `cordis.patch.yml` (shipped by the npm-installed 0.1.5-alpha.2 tree — `web-app-patch-excerpt.txt` lines 6–8), and
2. the maintainer's manual `- insert:` block appended to the profile's `cordis.patch.yml` (`profile-patch-excerpt.txt` lines 18–20).

**Where the collision is detected.** At the Cordis plugin-loader layer, not in plugin code: `EntryGroup.update` in `@deepseek-ai/cordis-plugin-loader` maintains an id-keyed entry group and throws `duplicate loader entry id: workspace-files` when a second entry with an existing id is applied. The host's boot glue (`@deepseek-ai/dsh-app-boot`, `Include._apply`) wraps that throw as `failed to apply loader entry include (cordis:include)` and the profile runner surfaces it as `dsh: plugin tree failed to load` before any plugin module loads. The stack in `boot-crash-log.txt` (loader → app-boot → profile-boot → bin.js) confirms the failure is in loader-entry application, prior to plugin activation.

**Why the whole boot is refused rather than "later row wins".** Loader entry ids are unique keys of the plugin tree, not an overwrite surface: Cordis applies patch operations by entry id, and an `insert` semantically *creates* a new entry. Two inserts for one id leave the tree ambiguous (two entries competing to define the same plugin node), so the loader treats it as a malformed composition and fails closed at load time. This matches the skill's "Misconfiguration fails loud at load when self-contained" convention: the composition is self-contained and contradictory, so the loader aborts the entire boot instead of silently preferring one row — accepting the later row would hide a composition bug and could load the wrong copy (bundle vs. profile-resolved) nondeterministically from the user's viewpoint.

## 2. Layering rules for a profile patch acting on a bundle-provided plugin

| Operation | Verdict | Why |
|---|---|---|
| Change the plugin's **config by id** (e.g. an overlay/patch entry that targets `workspace-files` and sets `config` or `disabled`) | **Safe** | It keys off the existing bundle entry's id; no new entry id is created, so no duplicate can arise. |
| **Add a row for an id no bundle ships** (a genuinely new/external plugin, like the `dsh-file-trace` / `dsh-profiles` rows above it in the profile patch) | **Safe** | The id is novel in the merged tree; `insert` creates the only entry for it. |
| **Add an `insert` row for an id a bundle already ships** (`workspace-files`) | **Fatal** | The bundle's `cordis.patch.yml` already inserted that id; the second insert collides and the loader fails the whole boot with `duplicate loader entry id`. |

**The maintainer's action is the third (fatal) case.** The proving evidence row is the identical `- insert: - id: workspace-files / name: '@deepseek-ai/dsh-api-workspace-files'` block in `web-app-patch-excerpt.txt` (lines 6–8, "already here (L110-111 in the installed tree)"), which the manual block in `profile-patch-excerpt.txt` (lines 18–20) duplicates. The adjacent `session-controller` / `settings-controller` rows underline the rule: those bundle-provided ids were never manually inserted into the profile patch, and boot worked.

The maintainer's own comment in the profile patch ("如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏") records the exact mistaken assumption: "redundant but keep it just in case". In this loader, a duplicate insert is not redundant — it is a hard boot failure.

## 3. Fix

**Exact change:** delete the entire manually added block from `C:\\Users\\lhh\\.dsh\\profiles\\web\\cordis.patch.yml` — the three-line `- insert:` entry (id `workspace-files`, name `@deepseek-ai/dsh-api-workspace-files`) and its two comment lines (lines 16–20 of `profile-patch-excerpt.txt`). Change nothing else: the web-app bundle's own row remains the single source of that entry, and the next `dsh web` boot resolves it normally.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` never executed — the crash happens in the Cordis plugin-loader entry-application stage, before any plugin module is loaded. The fault is purely in profile composition (a duplicate `insert` row across patch layers).

**Could any plugin-side change resolve it?** No. No change to the workspace-files plugin (or any plugin) can fix a duplicate loader entry id: the collision exists between two composition rows in the patch files, and the loader aborts before plugin code runs. The only resolution is on the composition side — removing one of the two rows (here, the profile's manual one).

Note: this fix reverts the boot to the pre-insert state; it does not by itself address the original "文件资源服务不可用" symptom that motivated the insert. That symptom has a different cause and needs separate diagnosis (per the v0.1.5-alpha.1/A1-20 record, an in-place npm-global upgrade can serve a stale client combo missing newly-added bundle modules — one dropped module fails client plugin registration and a clean host restart/reinstall self-heals the roster/combo mismatch; also recall `workspaceFiles` API changes across 0.1.5-alpha.1/alpha.2). That follow-up is out of scope for this read-only report but should be tracked; the wrong fix (duplicate insert) must not be retried.

## 4. Prevention

**Maintainer-side, before adding such a row by hand:**

- Inspect the installed bundle's `cordis.patch.yml` under the npm global tree (here `C:\\Users\\lhh\\AppData\\Roaming\\npm\\node_modules\\@deepseek-ai\\dsh\\...\\packages\\bundle\\web-app\\cordis.patch.yml` equivalent in the installed layout) and grep it for the entry id and package name before inserting. If either appears, the bundle already provides the plugin: do not insert; if configuration is needed, target the existing id with a config change instead of a new row.
- Prefer asking "why is the service unavailable?" before "which row is missing?": a freshly upgraded 0.1.5-alpha.2 bundle ships `workspace-files`; a missing-service symptom right after an in-place upgrade points at stale bundle/client state or an incomplete install (see the A1-20 restart/self-heal record), not at an absent composition row. Re-verify after a clean restart before touching the patch file.
- Never keep a "possibly redundant" row "just to be safe" — in this loader, redundancy of an insert is fatal, not harmless. Delete-or-verify, don't hedge.

**Host-side, to make the failure actionable:**

- Print both collision sources in the error: for `duplicate loader entry id: X`, name each contributing patch file and line — e.g. `duplicate loader entry id: workspace-files: first inserted by <bundle cordis.patch.yml (web-app bundle) L110>, second by <profile cordis.patch.yml C:\\Users\\lhh\\.dsh\\profiles\\web\\cordis.patch.yml L18>`. The current message names only the id; the user must guess which of several patch layers to edit.
- Add a remediation hint that assigns blame and the action: `remove the profile-level insert (bundle already provides this plugin); to customize, patch config by id instead of inserting a new row`. Since the collision is fully self-contained at load time, the loader has both file paths available and can emit this deterministically.
- Optionally, fail even earlier with a dedicated pre-boot composition check (before plugin tree application) that detects profile-insert ids that shadow bundle-provided ids and reports them as a distinct "profile patch duplicates bundle entry" diagnostic, so users never see the raw loader TypeError.

## Skill-process notes

- Mode A (inspect, read-only) — no configuration, dependency, or source writes; the fixture was not modified.
- Corridor context applied: 0.1.2/0.1.3 profile → 0.1.5-alpha.2 host (version-jump edge covered by the v0.1.5-alpha.1/alpha.2 cards; the A1-20 in-place-upgrade client-combo record is directly relevant background to the original symptom).
- Baseline (Mode C exemption list): not collected — no migration/build was run; this task is read-only diagnosis.

**Completed:** root cause, layering-rule classification, minimal fix, and prevention analysis above, from the three evidence files.

**Skipped:** runtime verification layers (cold-start, behavior flows) — impossible without modifying the profile, which the read-only scope forbids.

**Pending/residual risk:** the underlying 文件资源服务不可用 symptom is diagnosed only tentatively (likely stale in-place-upgrade client/bundle state per A1-20); it needs a separate verification once the duplicate insert is removed.

**Rollback:** none required — nothing was changed; the recommended change itself (deleting the manual block) restores the pre-incident profile state.

**Recommendations:** host-side duplicate-id diagnostics with source file/line attribution; a doc note in the profile-patch guide that profile patches must not re-insert bundle-provided ids (config-by-id is the supported override), mirroring the layering table in §2.
