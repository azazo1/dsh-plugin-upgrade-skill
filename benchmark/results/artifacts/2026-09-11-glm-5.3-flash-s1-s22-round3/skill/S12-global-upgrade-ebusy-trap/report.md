# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnostic Report

Evidence pack inspected (read-only): `environment/fixture/` — `attempt1-ebusy.log`, `attempt2-downgrade.log`, `npm-dist-tags.txt`, `running-processes.txt`, `README.md`. Running dsh: `0.1.2-alpha.4`; target: `0.1.2-alpha.5`.

## 1. Attempt 1 root cause — EBUSY copying `koffi.node`

**Symptom.** `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5` fails with:

```
npm error code EBUSY
npm error syscall copyfile
npm error path C:\...\@koromix\koffi-win32-x64\win32_x64\koffi.node
npm error dest C:\...\@deepseek-ai\.dsh-TMPDIR\...\koffi.node
```

**Who holds the lock.** `running-processes.txt` shows three `node.exe` processes; the annotation identifies PID 42432 as the **dsh web host**, with the note "dsh web host (holds koffi.node)", plus PID 23768 (agent session worker) and PID 23920 (the npm install itself). The dsh web host loaded `@koromix/koffi` — a native FFI addon used for sandbox/filesystem operations — at startup. `koffi.node` is a native `.node` binary: on Windows, once a process loads a native DLL/addon via `LoadLibrary`, the OS holds a file lock on it **until the owning process exits**. npm's `copyfile` into the install destination therefore hits EBUSY because the file is memory-mapped/locked by the live host process.

**Why a browser refresh does not help.** Refreshing the page only reloads the SPA in the browser. The `koffi.node` lock lives in the **host** `node.exe` process (PID 42432), which stays alive across page reloads; the browser never had the file open. The only thing that releases the lock is terminating the process that loaded the addon — the same principle documented in DSH's defensive-patterns guidance on subprocess/teardown (native modules must be released by process exit, not by client disconnects). The agent session worker (PID 23768) should also be stopped, since any `node.exe` child of the running dsh instance can hold addon files open.

**Correct stop-then-upgrade sequence.**

1. Stop all dsh processes (quit the web host and its session workers — verify with `tasklist /FI "IMAGENAME eq node.exe"` that no dsh-owned `node.exe` remains; do not kill unrelated node processes).
2. Run the pinned install: `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5`.
3. Restart dsh and verify with `dsh --version` that it prints `0.1.2-alpha.5`.

## 2. Attempt 2 root cause — unpinned install resolved to rc.2, not alpha.5

**Symptom.** `attempt2-downgrade.log`:

```
$ npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
(installs fine, but...)
$ dsh --version
0.1.1-rc.2
```

**Why.** The command names `@deepseek-ai/dsh` **without a version specifier**. An unpinned argument to `npm install -g` resolves to the dist-tag `latest` — not to the currently installed version, and not to the newest version ever published. `npm-dist-tags.txt` shows the registry state at that moment:

```
{
  next: '0.1.1-rc.2',
  latest: '0.1.1-rc.2',
  alpha: '0.1.2-alpha.5'
}
```

`latest` points at `0.1.1-rc.2`; `0.1.2-alpha.5` is only reachable via the `alpha` dist-tag. So the "combined" command actually **downgraded** the global install from `0.1.2-alpha.4` to `0.1.1-rc.2`. (An unpinned install does not "keep" the existing version either — npm always installs what the tag resolves to, replacing what was there.)

## 3. Exact safe upgrade commands

```sh
# 1. Stop dsh completely (web host + session workers); confirm no dsh node.exe remains:
tasklist /FI "IMAGENAME eq node.exe"

# 2. Pinned install of the target version, plus the TUI plugin:
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui

# 3. Restart dsh and verify:
dsh --version   # must print 0.1.2-alpha.5
```

Equivalently, pin the TUI plugin too if a specific version is wanted. Do **not** use `@deepseek-ai/dsh@alpha` — dist-tags are mutable pointers and would silently change what a future reinstall gets; always pin the exact semver for reproducibility. (For a durable alpha channel, `npm install -g @deepseek-ai/dsh@alpha` works today but must be re-checked after each release, since `latest` still points at `0.1.1-rc.2`.)

## 4. Prevention — guidance for plugin README authors

1. **Always pin exact versions in install commands.** Write `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5`, never a bare `@deepseek-ai/dsh`. An unpinned name silently installs `latest`, which may be older than what the user already runs (this exact downgrade) or newer/breaking than the plugin was tested against.
2. **Never use mutable dist-tags (`latest`, `next`, `alpha`) in documented commands** unless the doc explicitly explains the drift risk; `latest` pointed at `0.1.1-rc.2` while alpha users were on `0.1.2-alpha.4` — "upgrade" docs that resolve through `latest` can downgrade users.
3. **State the stop-first requirement.** Any README install/upgrade instruction for a package shipping native addons (`.node` files such as `koffi.node`) must begin with "stop all running dsh processes first", with a verification step (`tasklist`/process check) — otherwise Windows users hit EBUSY.
4. **Include a post-install version check** (`dsh --version` must print the exact documented version) so a resolution surprise is caught immediately instead of after the user's next session.
5. When a combined install (dsh + plugin) is documented, pin **both** packages; a combined line invites copy-paste, and the unpinned component is invisible to readers focused on the plugin name.
