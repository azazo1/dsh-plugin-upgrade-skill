# S22 · The Duplicate Insert That Crashed the Boot — Report

Task: S22-duplicate-insert-boot-crash-trap (read-only analysis). Evidence: `boot-crash-log.txt`, `profile-patch-excerpt.txt`, `web-app-patch-excerpt.txt`, `README.md` under the fixture directory.

## 1. Root cause

**Colliding declarations** — two `insert` rows with the same loader entry id `workspace-files`, both naming `@deepseek-ai/dsh-api-workspace-files`:

1. The **web-app bundle's** `cordis.patch.yml` (installed 0.1.5-alpha.2 tree, `packages/bundle/web-app/cordis.patch.yml`, shown in `web-app-patch-excerpt.txt` L110-111) already ships the row.
2. The **profile's** `cordis.patch.yml` (`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`) gained a manually added, byte-for-byte equivalent insert block (last block of `profile-patch-excerpt.txt`) after the maintainer misdiagnosed the Sidebar "文件资源服务不可用" error as a missing plugin.

**Layer of detection** — the collision is caught in the **Cordis plugin-loader layer**, before any plugin code runs: `EntryGroup.update` in `@deepseek-ai/cordis-plugin-loader/lib/index.js:91` throws `duplicate loader entry id: workspace-files`, propagated through `Include._apply` ("failed to apply loader entry include (cordis:include)") and wrapped by `dsh-app-boot` as "plugin tree failed to load". The stack shows it happens while assembling the loader entry tree at boot (`runProfile` → `boot`), i.e. at configuration/include-resolution time, not at plugin instantiation.

**Why the whole boot is refused** — loader entry ids must be **unique across the merged tree**: the bundle patch and the profile patch are merged (the profile patch layers on top of the bundle's composition), and the loader enforces id uniqueness as a hard invariant when an `include` group is applied. There is no "later row wins" override semantics for `insert`: two rows claiming the same id would create two competing loader entries (ambiguous plugin identity, config targeting, and dependency ordering), so the loader treats it as a malformed configuration and fails loud — the entire plugin tree is rejected rather than silently picking one row. This matches the repo convention "misconfiguration fails loud at load when self-contained": a duplicate id is fully detectable at load time.

## 2. Layering rules for a profile patch acting on a bundle-provided plugin

| Operation | Verdict |
|---|---|
| Change the plugin's **config by id** (e.g. a config/overlay entry keyed on the existing `workspace-files` id) | **Safe** — it targets the already-registered entry; ids stay unique. |
| Add an insert row for an id **no bundle ships** (a genuinely new plugin) | **Safe** — a new unique id; the row adds an entry the merged tree lacks. |
| Add an insert row for an id a **bundle already ships** | **Fatal** — duplicate loader entry id; whole boot crashes. |

**The maintainer's action is the third case.** The proving evidence rows are the identical pair:

- `profile-patch-excerpt.txt`, final block: `- insert:` → `id: workspace-files`, `name: '@deepseek-ai/dsh-api-workspace-files'` (with the comment admitting "如果 web-app bundle 已包含此行则此条为冗余" — it is not redundant, it is fatal).
- `web-app-patch-excerpt.txt`: the same id/name row already present in the installed 0.1.5-alpha.2 bundle patch (L110-111), adjacent to `session-controller` and `settings-controller` which were never manually duplicated.

## 3. Fix

**Delete the manually added workspace-files insert block** (the last block: comment lines plus the `- insert:` → `id: workspace-files` / `name: '@deepseek-ai/dsh-api-workspace-files'` rows) from **`C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml`** — the profile patch, not the bundle. No other change: the bundle already provides the plugin, so after deletion the entry resolves once and boot succeeds.

**Is the plugin's own code at fault?** No. `@deepseek-ai/dsh-api-workspace-files` was never loaded — the crash happens in loader/include resolution before any plugin module executes. **Could a plugin-side change resolve it?** No. The duplicate id is a configuration-layer error spanning two patch files; no change to the plugin's source, name, or code can make the loader accept two rows with the same entry id. The fix is necessarily in the profile's `cordis.patch.yml`. (The original "文件资源服务不可用" symptom that prompted the insert is a separate issue — if it persists after the fix, it must be diagnosed on its own, e.g. service availability at runtime, not by re-adding the row.)

## 4. Prevention

**Maintainer-side, before hand-adding an insert row:**
- Inspect the installed bundle's composition for the target id first — e.g. read the installed `packages/bundle/web-app/cordis.patch.yml` under the npm tree (`C:\Users\lhh\AppData\Roaming\npm\node_modules\@deepseek-ai\dsh\...`), or the bundle's resolver manifest/dependency list, and grep for the id (`workspace-files`) and package name. If either appears, the plugin is already composed: adjust its **config by id** instead of inserting a row.
- Treat "service unavailable" runtime errors as runtime symptoms to diagnose (service present? provider error?), never as evidence that a plugin row is missing from the composition.
- Never write a "keep it just in case" duplicate row; a redundant insert is not harmless — it is boot-fatal.

**Host-side, to make the failure actionable:** at boot, when `EntryGroup.update` raises a duplicate id, the host could catch it and print a targeted diagnostic, for example:

- the duplicate id (`workspace-files`) and **both source locations** — the file and line of each colliding `insert` row (bundle patch path vs profile patch path), so the blame is explicit: "row already provided by bundle `<bundle path>:L110`; duplicate added in profile `<profile path>`";
- a one-line remediation: "delete the duplicate insert row for id `workspace-files` from the profile patch `C:\Users\lhh\.dsh\profiles\web\cordis.patch.yml` — bundle-provided plugins are configured by id, not re-inserted";
- optionally, a boot-time pre-check that diffs the profile patch's insert ids against the bundle patch's ids and warns before the loader throws, and/or documentation in the profile patch template listing bundle-provided ids that must never be inserted.

---
*Summary: root cause = duplicate `insert` row for loader entry id `workspace-files` (profile patch vs web-app bundle patch), detected in the Cordis plugin-loader `EntryGroup.update` during include application; loader rejects the whole tree because entry-id uniqueness is a load-time invariant with no last-row-wins semantics. Fix = delete the manual block from the profile's cordis.patch.yml; the plugin code is blameless and no plugin-side change can fix it. Prevention = check the installed bundle patch/manifest for the id before inserting, and have the host print both colliding file:line sources plus a delete instruction on duplicate-id errors.*
