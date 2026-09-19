# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnostic Report

## 1. Attempt 1 root cause: why `koffi.node` is locked (EBUSY)

**Error evidence** (`attempt1-ebusy.log`):

    $ npm install -g @deepseek-ai/dsh@0.1.2-alpha.5
    npm error code EBUSY
    npm error syscall copyfile
    npm error path C:\...\@koromix\koffi-win32-x64\win32_x64\koffi.node
    npm error dest C:\...\@deepseek-ai\.dsh-TMPDIR\...\koffi.node

npm's `copyfile` syscall on the installed native addon `koffi.node` fails with EBUSY — the file is
locked by the OS because a running process has it loaded.

**Who holds it** (`running-processes.txt`): at the time of attempt 1, three node.exe processes were running:

    node.exe  42432  <- dsh web host (holds koffi.node)
    node.exe  23768  <- agent session worker
    node.exe  23920  <- npm install -g (attempting the copy)

The annotation in `running-processes.txt` states it directly: the **dsh web host (PID 42432)** loaded
`@koromix/koffi` (a native FFI addon used for sandbox/filesystem operations) at startup. `koffi.node`
is a native `.node` binary — once loaded into a process, Windows holds a file lock on it **until that
process exits**. npm cannot overwrite/copy a DLL-like mapped image file while the host process is alive,
hence EBUSY. (The agent session worker PID 23768 is also part of the running dsh; the lock is attributed
to the web host because it is the process that loaded koffi.)

**Why a browser-page refresh does not free the lock**: refreshing the browser page only reloads the SPA
in the browser. The server-side host process that actually loaded `koffi.node` (PID 42432) stays alive;
the lock belongs to that OS process, not to any browser page. Only terminating the process releases the
file lock.

**Correct stop-then-upgrade sequence**: exit dsh completely — quit the web host (and any agent session
workers/child processes it spawned, e.g. PID 23768) so every process holding `koffi.node` is gone —
then run the global install, then restart dsh. Verify no `node.exe` dsh processes remain
(`tasklist /FI "IMAGENAME eq node.exe"`) before installing.

## 2. Attempt 2 root cause: why `dsh --version` printed `0.1.1-rc.2` instead of `0.1.2-alpha.5`

**Evidence** (`attempt2-downgrade.log`):

    $ npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
    (installs fine, but...)
    $ dsh --version
    0.1.1-rc.2

The combined command came from a plugin README and installs **`@deepseek-ai/dsh` without any version
specifier** (no `@0.1.2-alpha.5`). An unpinned `npm install -g pkg` resolves to the version pointed at
by the **`latest` dist-tag**.

**Registry state** (`npm-dist-tags.txt`):

    $ npm view @deepseek-ai/dsh dist-tags
    {
      next: '0.1.1-rc.2',
      latest: '0.1.1-rc.2',
      alpha: '0.1.2-alpha.5'
    }

So the unpinned install resolves to **`latest` = `0.1.1-rc.2`**, not alpha.5. The wanted
`0.1.2-alpha.5` is only reachable through the dedicated `alpha` dist-tag, and it is a prerelease —
npm never advances `latest` to a prerelease automatically, so `latest` still points at the older
stable `0.1.1-rc.2`. The result is effectively a **downgrade**: attempt 1's pinned alpha.5 install had
failed, so the machine still had an older install, and attempt 2 explicitly installed `0.1.1-rc.2` over it.

## 3. Exact safe upgrade commands

1. **Stop dsh completely** — quit the running dsh web host and its session workers (e.g. PIDs 42432 and
   23768) and confirm with `tasklist /FI "IMAGENAME eq node.exe"` that no dsh node.exe processes remain.
2. **Install the pinned alpha plus the TUI plugin in one command** (pin the version explicitly; never rely
   on `latest` for a prerelease):

       npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui

   (Equivalently: `npm install -g @deepseek-ai/dsh@alpha @deepseek-harness-tui/dsh-tui` — the `alpha`
   dist-tag currently maps to `0.1.2-alpha.5`. Pinning the exact version is safer since tags move.)
3. **Verify** the result before restarting anything:

       dsh --version   # must print 0.1.2-alpha.5

4. Restart dsh.

## 4. Prevention: what plugin README authors should do differently

- **Never publish bare `npm install -g @deepseek-ai/dsh` in install instructions.** It resolves to the
  `latest` dist-tag, which for a prerelease ecosystem points at an older stable — exactly the downgrade
  seen in `attempt2-downgrade.log`. Always pin the version that matches the plugin's tested dsh release,
  e.g. `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5` (or `@alpha` when alpha is intended, with a
  note that tag targets move over time).
- **State the stop-dsh-first requirement.** Any instruction that upgrades dsh itself must begin with
  "exit dsh completely (web host and session workers) before installing" — otherwise users hit the
  attempt-1 EBUSY on locked native addons like `koffi.node`.
- **Warn that refreshing the browser does not release file locks** — the lock is held by the host process,
  so the app must actually be exited.
- **Add a post-install verification step** (`dsh --version` prints the expected version) so a silent
  resolution to an unwanted version is caught immediately instead of discovered later.
