# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnosis Report

**Mode:** A · inspect (read-only diagnosis; no install/migration executed — per benchmark authorization, this brief is the confirmation to analyze and report only).
**Evidence:** fixture pack read in full: `attempt1-ebusy.log`, `running-processes.txt`, `attempt2-downgrade.log`, `npm-dist-tags.txt`.
**Environment (from evidence):** Windows, dsh `0.1.2-alpha.4` currently installed and running; six community Web plugins across three GitHub mirrors; registry state: `latest: 0.1.1-rc.2`, `next: 0.1.1-rc.2`, `alpha: 0.1.2-alpha.5`.

---

## 1. Attempt 1 root cause: why `koffi.node` is EBUSY

**Who holds the lock:** the running **dsh web host process** (PID 42432, `node.exe`, per `running-processes.txt`). At startup the host loaded `@koromix/koffi` — a native FFI addon — which maps the binary `koffi-win32-x64/win32_x64/koffi.node` into the process. Windows locks a loaded native `.node` DLL image file: it cannot be renamed, deleted, or copied over while any process has it mapped. The global `npm install -g` (PID 23920) tries to `copyfile` a fresh `koffi.node` into the global package tree (via the `.dsh-TMPDIR` staging path) and the OS rejects it with `EBUSY`. The agent session worker (PID 23768) is a second live dsh-owned node process; any such process holding the mapped file keeps the lock.

**Why a browser refresh does not help:** refreshing the page only reloads the Web SPA in the browser. The browser talks to the host over HTTP; the page is not the host. The host node process — the one that mapped `koffi.node` — keeps running after a refresh, so the lock persists. Only terminating the node processes releases it.

**Correct stop-then-upgrade sequence** (from the skill's global-host-upgrade discipline):

1. Fully stop every dsh process: end the `dsh web` host and all session workers (check with `tasklist` that no `node.exe` dsh processes remain). A browser refresh or closing the tab is **not** a host stop.
2. From an **external terminal** (not a tool call inside a dsh session running on this same host — the session IS the host process, and upgrading it from inside is structurally fatal: npm removes/replaces the package tree the process executes from, the tool call never returns, and the interrupted install can leave package content without regenerated shims, i.e. a dead `dsh` command), run the **pinned** install (see §3).
3. Restart `dsh web`, hard-refresh the browser, verify `dsh --version` and that the six plugins load.

Because the host is stopped before npm runs, nothing crashes mid-install — a crash during upgrade is a signature of doing it wrong.

## 2. Attempt 2 root cause: the silent downgrade

The plugin README's "official combined command" used the **unpinned** package name: `npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui`. A bare `@deepseek-ai/dsh` with no version spec resolves to the registry's **`latest` dist-tag**, not to "keep or advance my current version". At the time of the attempt (`npm-dist-tags.txt`):

- `latest` → `0.1.1-rc.2`
- `next` → `0.1.1-rc.2`
- `alpha` → `0.1.2-alpha.5`

So the install succeeded — installing `0.1.1-rc.2`, a **downgrade** from the running `0.1.2-alpha.4` and nowhere near the wanted alpha.5. `dsh --version` printed `0.1.1-rc.2` exactly because that is what `latest` pointed to. The alpha line lives behind the `alpha` dist-tag and is never picked by an unpinned name. This is a classic pre-release trap: npm never resolves a bare name to a prerelease unless that prerelease is tagged `latest`.

(Note: attempt 2's successful install also implies the EBUSY was gone by then — dsh had been stopped — so attempt 2 did the stop correctly and failed only on the missing version pin.)

## 3. Exact safe upgrade commands for this situation

Target: `dsh 0.1.2-alpha.5` plus the TUI plugin.

```powershell
# 1) Stop the host and all session workers, then verify nothing is left:
tasklist /FI "IMAGENAME eq node.exe"     # no dsh host/worker processes should remain

# 2) From an EXTERNAL terminal (not inside a dsh session), pinned install:
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui

# 3) Restart and verify:
dsh --version        # must print 0.1.2-alpha.5
dsh web              # then hard-refresh the browser; confirm the six plugins load
```

Key points: pin the **exact version** (`@0.1.2-alpha.5`) — never the bare name, and don't rely on `@alpha` either since a moving tag can silently shift; pinning the exact version also gives a reproducible rollback (`npm install -g @deepseek-ai/dsh@0.1.2-alpha.4` from an external shell with dsh stopped). The three GitHub mirrors hosting the six plugins are irrelevant to the host upgrade itself; afterwards, verify each mirror-served plugin still mounts, and consult the corridor `0.1.2-alpha.4 → 0.1.2-alpha.5` (skill reference `v0.1.2-alpha.5.md`: storage-domain `compatibleVersions` / `invalidRecords` tolerance plus a host fix for rc.2/alpha.3-era homes) — plugin-side changes may be needed for any of the six.

## 4. Prevention: guidance for plugin README authors

- **Never publish an unpinned `npm install -g @deepseek-ai/dsh ...` command.** A bare name follows `latest` and can silently downgrade users on pre-release lines. Always pin: `npm install -g @deepseek-ai/dsh@<exact-version> <plugin-package>@<exact-version>`.
- **State the stop-first precondition explicitly** next to any install command: "stop all dsh processes first; a browser refresh is not a host stop" — and that the command must be run from an external terminal, not from inside a dsh session.
- Prefer offering a copy-paste block that includes the verification step (`dsh --version`) so a wrong resolution is caught immediately rather than discovered later.
- Document which dist-tag (`latest` / `next` / `alpha`) the plugin's required host line lives on, and prefer exact versions over moving dist-tags in install instructions.

---

## Report per skill structure

- **pre-existing**: not collected (Mode A, static read-only evidence pack).
- **Completed**: root causes for both attempts traced to primary evidence (process list + dist-tags listing); safe ordered upgrade procedure; README-author prevention guidance.
- **Skipped**: no runtime verification, no install/migration (explicitly out of scope for this read-only task; the fixture is static).
- **Pending/residual risk**: actual plugin compatibility of the six community plugins with alpha.5 is unverified until the upgrade runs; the storage-domain compatibility fix in alpha.5 is the relevant corridor card to re-check for rc.2/alpha.3-era homes.
- **Rollback**: baseline recorded from evidence — `0.1.2-alpha.4` installed, registry tags as listed; recoverable via external pinned re-install of `@0.1.2-alpha.4`. Never hand-copy package directories or hand-write shims after an interrupted install.
- **Recommendations**: adopt pinned-version install snippets repo-wide; consider a version-marker check after upgrade in plugin "getting started" docs.
