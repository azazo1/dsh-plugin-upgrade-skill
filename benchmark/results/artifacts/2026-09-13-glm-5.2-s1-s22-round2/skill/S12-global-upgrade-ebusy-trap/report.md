# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnosis Report

**Mode:** A · inspect (read-only). No files, installs, or migrations were executed; the fixture was only read.
**Evidence pack:** `environment/fixture/` — `attempt1-ebusy.log`, `running-processes.txt`, `attempt2-downgrade.log`, `npm-dist-tags.txt`.

## Context

- Host: Windows, global npm install of `@deepseek-ai/dsh`, currently running `0.1.2-alpha.4`.
- Goal: upgrade to `0.1.2-alpha.5` (dist-tag `alpha`).
- Registry state at the time (`npm-dist-tags.txt`):
  - `latest: 0.1.1-rc.2`
  - `next: 0.1.1-rc.2`
  - `alpha: 0.1.2-alpha.5`

## 1. Attempt 1 root cause — why `koffi.node` is EBUSY

**What happened:** `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5` fails with `EBUSY` on `copyfile` of
`@koromix/koffi-win32-x64/win32_x64/koffi.node` (source) into npm's temp dir (`.dsh-TMPDIR`) as destination.

**Who holds the lock:** `running-processes.txt` shows the `dsh web` **host** process (PID 42432) is still
running. That host loaded the native FFI addon `@koromix/koffi` at startup (used for sandbox/filesystem
operations). `koffi.node` is a native `.node` PE binary; on Windows, once a process loads a native DLL into
its address space, the OS keeps the file locked (you cannot overwrite/rename a loaded module image) until the
process exits. npm's upgrade path must replace that file, hence `EBUSY` on `copyfile`.

**Why a browser refresh does not help:** refreshing the page only reloads the browser SPA. The Web GUI is a
client of the host process; the host node.exe that actually loaded `koffi.node` keeps running regardless of
what the browser does. Only terminating every dsh node process (host, agent session workers — e.g. PID 23768,
any terminal/subprocess children) releases the lock.

**Additional structural hazard (per the plugin-upgrade skill):** the upgrade was attempted from *inside* a dsh
session on that same host — the session IS the host process. npm would remove/replace the very package tree the
process executes from; even without EBUSY the host can die mid-install, leaving package content present without
regenerated shims (the `dsh` command gone). Global host upgrades must be run from an **external terminal**, never
from a tool call inside a session on that host.

**Correct stop-then-upgrade sequence:**
1. Fully stop every dsh process — the `dsh web` host and all worker/session children. Verify with the process
   listing that no `node.exe` dsh processes remain. A browser refresh/close is not a host stop.
2. From an **external terminal** (not from inside a dsh session), run the **pinned** install:
   `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5`.
3. Restart `dsh web`, hard-refresh the browser, and verify the version marker and plugins.

Because the host is fully stopped before npm runs, nothing crashes mid-install; a crash during the upgrade is a
signature of doing it wrong, not a risk to tolerate. If an install was already interrupted: repair externally by
re-running the pinned formal install — never hand-copy package directories or hand-write shims.

## 2. Attempt 2 root cause — why `dsh --version` printed `0.1.1-rc.2`

**What happened:** the combined command from a plugin README, `npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui`,
succeeded (EBUSY was gone because dsh was stopped), but `dsh --version` reports `0.1.1-rc.2` — a **downgrade**
from the installed alpha.4, not alpha.5.

**Why:** `@deepseek-ai/dsh` with **no version specifier** is not "keep or advance what's installed" — npm resolves
an unpinned package name to a **dist-tag**, specifically `latest`. Per `npm-dist-tags.txt`, at that moment
`latest` pointed to `0.1.1-rc.2` (the alpha.5 release was published only under the `alpha` tag). So npm
happily "upgraded" to the older rc.2 because that is what `latest` names. An unpinned install follows the
`latest` dist-tag and can silently downgrade a prerelease line — it neither preserves the installed version
nor advances to the newest published release.

## 3. Exact safe upgrade commands for this situation

Goal: dsh `0.1.2-alpha.5` plus the TUI plugin (`@deepseek-harness-tui/dsh-tui`).

From an **external terminal** (PowerShell/cmd), after stopping all dsh processes:

```powershell
# 1. stop every dsh host/worker process first (verify none remain):
#    e.g. stop the dsh web host and session workers; confirm via tasklist / node process listing

# 2. pinned host install — never a bare package name:
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5

# 3. the plugin (separately, after the host):
npm install -g @deepseek-harness-tui/dsh-tui

# 4. verify:
dsh --version          # must print 0.1.2-alpha.5
npm view @deepseek-ai/dsh dist-tags   # sanity-check which tag carries which version
```

Then restart `dsh web`, hard-refresh the browser, and verify the version marker and that the six community Web
plugins (and the TUI plugin) still load. Notes:

- Keep host and plugin installs as separate pinned commands rather than one combined line, so a plugin failure
  cannot take the host upgrade with it.
- If the exact plugin version matters, pin it too (`@deepseek-harness-tui/dsh-tui@<version>`).
- If an earlier interrupted install left the `dsh` shim missing, the same pinned external re-install repairs it.

## 4. Prevention — guidance for plugin README authors

The trap came from a README's copy-pasted combined command containing an **unpinned** `@deepseek-ai/dsh`. README
authors should:

1. **Never publish `npm install -g @deepseek-ai/dsh` (bare name).** A bare name resolves to the `latest`
   dist-tag, which may be older than the release the README documents (prerelease channels like `alpha`/`next`
   never become `latest` until finalized). Always pin: `npm install -g @deepseek-ai/dsh@<exact-version>`.
2. **Precondition the command on a full host stop.** State explicitly: quit every dsh process (host + workers)
   before installing, because native addons (`koffi.node`) stay file-locked until process exit; a browser refresh
   does not release them. Include the EBUSY symptom in a troubleshooting note so users can self-diagnose.
3. **Prefer a documented "install plugin only" command** (`npm install -g <plugin>`) and link to the host's own
   upgrade guide, instead of embedding an implicit host upgrade inside a plugin install line. If the plugin needs
   a minimum host version, state it as a requirement (`requires dsh >= 0.1.2-alpha.5`) rather than re-installing
   the host unpinned on the user's behalf.
4. **If a combined command is unavoidable**, pin BOTH packages to exact versions and label the required
   pre-step ("stop all dsh processes first; run from an external terminal, not from inside a dsh session").
5. Add a post-install verification step to the README: `dsh --version` should print the expected pinned version;
   if it prints something older, the `latest` tag / an unpinned reinstall downgraded the host.

## Report per skill structure

- **pre-existing (baseline):** not collected — read-only Mode A diagnosis; no builds/tests run.
- **Completed:** root-cause analysis of both attempts from the fixture evidence; safe pinned external upgrade
  procedure; README-author prevention guidance.
- **Skipped:** Mode B/C implementation steps — out of scope for a read-only diagnosis; registry state taken from
  `npm-dist-tags.txt` (no live registry access per the no-external-services rule).
- **Pending/residual risk:** none identified for the diagnosis; the six community Web plugins' compatibility with
  0.1.2-alpha.5 was not assessed (no plugin inventory provided; separate Mode A review recommended before upgrading).
- **Rollback:** no changes were made; nothing to roll back.
- **Recommendations:** after upgrading, run a plugin-by-plugin compatibility check of the six Web plugins against
  the 0.1.2-alpha.4 → alpha.5 corridor (see the skill's `references/v0.1.2-alpha.5.md` cards) before relying on them.
