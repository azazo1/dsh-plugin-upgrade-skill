# S12 Diagnostic Report — Global Upgrade EBUSY + Downgrade Trap

Mode A (read-only inspection) per the dsh-plugin-upgrade skill. Evidence: fixture pack
(attempt1-ebusy.log, attempt2-downgrade.log, npm-dist-tags.txt, running-processes.txt).
Current dsh: 0.1.2-alpha.4; target: 0.1.2-alpha.5. Skill alignment: the SKILL.md "Global DSH
host upgrades (agent discipline)" section covers exactly this scenario — never run a global
host upgrade from inside a session, always pinned install from an external terminal.

## 1. Attempt 1 root cause — why koffi.node is locked

**Evidence.** attempt1-ebusy.log:

    npm error code EBUSY
    npm error syscall copyfile
    npm error path C:\...\@koromix\koffi-win32-x64\win32_x64\koffi.node

running-processes.txt shows three node.exe processes at that moment:

- PID 42432 — the `dsh web` host, annotated as "holds koffi.node"
- PID 23768 — an agent session worker
- PID 23920 — the `npm install -g` itself (attempting the copy)

**Diagnosis.** `koffi.node` is a native FFI addon (@koromix/koffi-win32-x64) that the dsh web
host loaded at startup for sandbox/filesystem operations. On Windows, a loaded native `.node`
binary is memory-mapped into the process; the OS holds the file locked until the owning process
exits. `npm install -g` must replace files inside the same global package tree the running host
executes from, so its `copyfile` of `koffi.node` fails with EBUSY.

**Why a browser refresh does not help.** Refreshing the page only reloads the browser SPA. The
native module lives in the host process (PID 42432), which stays alive across page reloads —
the lock is on the host's in-process mapping, not on any browser state. Only process exit
releases it.

**Correct stop-then-upgrade sequence.**
1. Fully stop every dsh process — the host AND its session workers (PIDs 42432, 23768). The
   skill is explicit: "a running host holds native-module file locks → EBUSY; a browser refresh
   is not a host stop".
2. From an EXTERNAL terminal (never from inside a dsh session — the session IS the host process,
   and a mid-install host death leaves the `dsh` command broken until an external pinned
   reinstall repairs it), run the pinned install (see §3).
3. Restart `dsh web`, hard-refresh the browser, verify `dsh --version` and plugin activation.

If an install was already interrupted, repair only by re-running the pinned formal install from
an external shell — never hand-copy package directories or hand-write shims.

## 2. Attempt 2 root cause — the downgrade to 0.1.1-rc.2

**Evidence.** attempt2-downgrade.log:

    $ npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
    (installs fine, but...)
    $ dsh --version
    0.1.1-rc.2

npm-dist-tags.txt at that time:

    latest: '0.1.1-rc.2',
    next:   '0.1.1-rc.2',
    alpha:  '0.1.2-alpha.5'

**Diagnosis.** The README's combined command installs `@deepseek-ai/dsh` with **no version
specifier**. An unpinned `npm install -g <pkg>` resolves to the package's `latest` dist-tag.
Here `latest` is `0.1.1-rc.2` — an OLDER release line than the currently installed
0.1.2-alpha.4, because the 0.1.2 alphas are published only under the `alpha` dist-tag, not
`latest`. So the "upgrade" silently performed a cross-line downgrade to 0.1.1-rc.2. It follows
the `latest` dist-tag; it neither preserves the installed version nor advances to alpha.5.
(The TUI half of the command is unaffected — only the unpinned dsh spec mis-resolves.)

## 3. Exact safe upgrade commands

From an external terminal, with every dsh process (host + session workers) confirmed exited:

    npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui

- Pin dsh to the exact target version — never a bare package name. If the TUI plugin documents a
  compatible version, pin that too (e.g. `@deepseek-harness-tui/dsh-tui@<exact>`); installing
  both in one command is fine once dsh carries its explicit `@0.1.2-alpha.5`.
- Then restart and verify:

      dsh --version        # must print 0.1.2-alpha.5
      dsh web              # restart host, hard-refresh the browser, verify plugins activate

- Rollback if needed: `npm install -g @deepseek-ai/dsh@0.1.2-alpha.4` (pinned likewise).
- Corridor note: alpha.4 → alpha.5 is a supported skill corridor (references/v0.1.2-alpha.5.md:
  storage domains gain optional `compatibleVersions` read tolerance and
  `invalidRecords: 'backup-and-skip'` salvage), so no intermediate steps are required.

## 4. Prevention for plugin README authors

- **Always pin exact versions in install commands**: write
  `npm install -g @deepseek-ai/dsh@<exact-version> @deepseek-harness-tui/dsh-tui@<exact-version>`,
  never a bare `@deepseek-ai/dsh`. A bare name silently resolves to the `latest` dist-tag,
  which can be older than the user's installed prerelease (exactly the rc.2 downgrade here).
- **Never publish dist-tag-dependent examples**: prerelease lines live on `alpha`/`next`
  tags, not `latest`; any README command that relies on `latest` pointing at the prerelease
  will downgrade prerelease users.
- **State the precondition**: "stop all dsh processes first (host and session workers); a
  browser refresh is not a stop; run npm from a terminal outside any dsh session."
- **State the verification step**: after install, `dsh --version` must print the exact pinned
  version before restarting the host.
