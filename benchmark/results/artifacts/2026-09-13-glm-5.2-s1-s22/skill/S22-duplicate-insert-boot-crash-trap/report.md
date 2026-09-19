# S22 · The Duplicate Insert That Crashed the Boot — Analysis Report

Task: S22-duplicate-insert-boot-crash-trap (read-only diagnosis)
Skill mode: Mode A · inspect (read-only; no migration, installation, or file changes performed)
Evidence: `fixture/boot-crash-log.txt`, `fixture/profile-patch-excerpt.txt`, `fixture/web-app-patch-excerpt.txt`, `fixture/README.md` (all read-only, unchanged)

## Scenario recap

A Windows profile created under dsh 0.1.2/0.1.3 was upgraded in place to 0.1.5-alpha.2. After the upgrade the right-sidebar document tab opened but its content read failed (文件资源服务不可用 — "file resource service unavailable"). The maintainer diagnosed a missing `workspace-files` host service and manually appended an `insert` row for `id: workspace-files` to the profile's `cordis.patch.yml`. The next `dsh web` boot failed immediately with:

```
Error: dsh: plugin tree failed to load: failed to apply loader entry include (cordis:include):
duplicate loader entry id: workspace-files
```

## 1. Root cause

**The two colliding declarations** are two `insert` rows carrying the same loader entry id `workspace-files`:

1. The web-app bundle's patch (`packages/bundle/web-app/cordis.patch.yml` in the npm-installed 0.1.5-alpha.2 tree, L110–111 per `web-app-patch-excerpt.txt`):
   ```yaml
   - insert:
       - id: workspace-files
         name: '@deepseek-ai/dsh-api-workspace-files'
   ```
2. The profile's own patch (`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`), manually appended by the maintainer with identical `id`/`name` (`profile-patch-excerpt.txt`, final block under the comment "如果 web-app bundle 已包含此行则此条为冗余").

**Where the collision is detected:** at Cordis loader tree construction, not at plugin activation and not in plugin code. The stack trace in `boot-crash-log.txt` shows:

- `EntryGroup.update` in `@deepseek-ai/cordis-plugin-loader/lib/index.js:91` throws `duplicate loader entry id: workspace-files` — the entry-group registry enforces id uniqueness while merging entries;
- `Include._apply` (`dsh-app-boot/lib/index.js:240`) fails with `failed to apply loader entry include (cordis:include)` — the profile patch's `insert` include is being applied on top of the already-loaded bundle composition;
- `boot` → `runProfile` → `runCli` abort, so the process dies before any plugin's `apply()` ever runs.

**Why the loader refuses the whole boot instead of accepting the later row:** entry ids are the loader's identity keys for the whole plugin tree — they are how later patch operations (config overrides, `disabled` flags, dependency resolution) address entries unambiguously. Two live entries with one id would make every later reference ambiguous, so the loader treats duplicate ids as a structural integrity failure and fails closed at tree-load time (error stage `plugin tree failed to load`). It is a hard precondition, not a last-write-wins merge: there is no ordering semantics under which the "later" row could silently win, and the boot aborts deterministically before the host starts.

Note the misdiagnosis chain: the original "文件资源服务不可用" symptom was a runtime service-availability problem (per the 0.1.5-alpha.1 card A1-20, in-place npm upgrades can serve a stale client combo that omits newly added bundle modules; a host restart / browser refresh self-heals the roster-combo mismatch). It was not a missing composition row — the bundle already shipped `workspace-files`. The manual "fix" therefore attacked the wrong layer and converted a recoverable runtime mismatch into a fatal boot crash.

## 2. Layering rules for a profile patch acting on a bundle-provided plugin

| Operation | Verdict |
|---|---|
| Changing the plugin's **config by id** (e.g. an overlay entry keyed on the existing `workspace-files` id) | **Safe** — it addresses an entry the bundle already provides; no new id enters the tree. |
| Adding an insert row for an id **no bundle ships** (a genuinely absent plugin, like the profile's `dsh-file-trace` / `dsh-profiles` external rows) | **Safe** — the id is new; the loader accepts it. This is exactly what the other rows in `profile-patch-excerpt.txt` legitimately do. |
| Adding an insert row for an id **a bundle already ships** | **Fatal** — duplicate loader entry id; the whole boot aborts at tree load. |

**The maintainer's action is the third case.** The proving evidence pair:

- `web-app-patch-excerpt.txt` L110–111 — the 0.1.5-alpha.2 web-app bundle already inserts `id: workspace-files` (`@deepseek-ai/dsh-api-workspace-files`);
- `profile-patch-excerpt.txt` final block — the maintainer inserted the identical `id`/`name` row into the profile patch. Identical `id` is what collides; even identical `name` does not make it a no-op — the loader rejects on id alone.

The excerpt's own comment ("如果 web-app bundle 已包含此行则此条为冗余；保留以确保升级 profile 不遗漏") shows the maintainer suspected redundancy but assumed it would be harmless. In Cordis loader semantics "redundant" insert rows are not skipped — they are duplicate ids and fatal.

## 3. Fix

**The minimal, complete fix:** delete the manually added block from `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml` — i.e. remove

```yaml
- insert:
    - id: workspace-files
      name: '@deepseek-ai/dsh-api-workspace-files'
```

together with its comment, and change nothing else. No compensating row is needed: the bundle already provides the plugin, so after deletion the tree loads with exactly one `workspace-files` entry and `dsh web` boots again.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` never executed — the crash happens during loader tree construction, before any plugin code runs (`EntryGroup.update` / `Include._apply`, pre-`apply()`). **Could any plugin-side change resolve the boot failure?** No. The duplicate id exists purely in composition data (two YAML patches); no change to the plugin's source, manifest, or runtime code can remove a loader-entry id collision. The only resolution is on the composition side: delete the redundant profile row (or, hypothetically, the bundle row — but the bundle tree is npm-owned and must not be hand-edited, so the profile row is the only correct deletion target).

**Follow-up for the original symptom:** after the boot is restored, if 文件资源服务不可用 recurs, treat it as the runtime/client-combo issue (A1-20 pattern): fully restart the `dsh web` host and hard-refresh the browser so the client combo includes the newly-added bundle modules, rather than adding composition rows.

## 4. Prevention

**Maintainer-side, before hand-adding any insert row:**

- Inspect the installed bundle's composition first — the web-app bundle's `cordis.patch.yml` inside the installed npm tree (the file proven by `web-app-patch-excerpt.txt`), grep for the intended `id:` (here `workspace-files`). If the bundle already ships the row, do not insert it again; if config changes are needed, address the existing id via an overlay/config patch instead of a new insert.
- Equivalently, check the profile's resolved composition (the loader's merged view, used for verification only) to confirm the plugin is genuinely absent before assuming "missing from composition".
- Treat runtime service-unavailable errors and composition errors as separate layers: verify the plugin is absent from the resolved tree before concluding a composition row is missing, and prefer a host restart / client refresh first after an in-place upgrade.

**Host-side, to make the failure actionable at boot:** when `EntryGroup.update` rejects a duplicate id, the host could print a blame-bearing diagnostic, for example:

```
duplicate loader entry id: workspace-files
  already provided by: bundle patch <installed>/packages/bundle/web-app/cordis.patch.yml:110 (web-app bundle, dsh 0.1.5-alpha.2)
  conflicting insert:   profile patch C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml (cordis:include)
  fix: delete the profile's insert row for id "workspace-files"; the bundle already provides it. To change its settings, patch config by id instead of inserting a new entry.
```

i.e. name (a) the surviving first entry's source file and line, (b) the offending later include's source file, and (c) the exact remediation (delete this row / use config-by-id). Optionally the loader could also pre-validate a profile patch against the bundle composition and fail before boot with "profile inserts N ids already provided by the bundle: …" — turning a mid-boot stack trace into a one-line actionable message that blames the hand edit, not the plugin.

## Report structure per skill

- **pre-existing (baseline):** not collected — read-only inspection task; no builds/tests run.
- **Completed:** full root-cause, layering-rule, fix, and prevention analysis from the three evidence files; no files modified.
- **Skipped:** none of the evidence was irrelevant; no runtime reproduction attempted (evidence is conclusive and reproduction would require mutating a profile, which the brief forbids).
- **Pending/residual risk:** line numbers (bundle L110–111) are as cited in the excerpt; the original 文件资源服务不可用 root cause (stale client combo vs. other) is inferred from the corridor pattern, not independently reproduced.
- **Rollback:** nothing changed; no rollback needed. Fixture untouched.
- **Recommendations:** host-side duplicate-id diagnostics with source attribution (above); document in the community standard that profile patches must not re-insert bundle-provided ids and should use config-by-id overlays instead.
