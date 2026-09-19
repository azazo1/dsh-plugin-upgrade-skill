# S12 · Global Upgrade EBUSY + Downgrade Trap — Report

## 1. Attempt 1 root cause: why `koffi.node` is locked

- `koffi.node` is a **native addon binary** (@koromix/koffi, a FFI library used by dsh for sandbox/filesystem operations). On Windows, loading a native `.node` DLL into a process takes an OS-level file lock on the file that persists **until the process exits**.
- `running-processes.txt` shows the holder: `node.exe` **PID 42432 — the dsh web host** — loaded koffi at startup. (The agent session worker, PID 23768, may equally hold it if it loaded the addon.)
- `npm install -g` fails with `EBUSY` on `copyfile` because npm tries to replace the file while the OS lock is held — the lock is on the **source-plane copy inside the global node_modules**, not on anything npm can rename around.
- **A browser-page refresh does not help**: refreshing only reloads the SPA JavaScript in the browser. The koffi lock lives in the **host Node process**, which keeps running across page refreshes. Only terminating the host (and any worker processes that loaded the addon) releases the lock.

**Correct stop-then-upgrade sequence:**

1. Close/stop all dsh processes: shut down the web host (`dsh web` / the GUI host) and any running agent sessions/workers.
2. Verify nothing is holding the addon: `tasklist /FI "IMAGENAME eq node.exe"` (or `handle.exe koffi.node` if available) — no dsh-related node.exe should remain.
3. Run the global install (see §3).
4. Restart dsh.

## 2. Attempt 2 root cause: the silent downgrade

- The plugin README's combined command used an **unpinned** `@deepseek-ai/dsh`.
- An unpinned npm spec resolves to the **`latest` dist-tag**, not "whatever is newer than what I have" and not `next`/`alpha`. npm knows nothing about the currently installed version; it just installs whatever `latest` points at.
- `npm-dist-tags.txt` shows the registry state: `latest: 0.1.1-rc.2`, `next: 0.1.1-rc.2`, `alpha: 0.1.2-alpha.5`.
- So `npm install -g @deepseek-ai/dsh` installed **0.1.1-rc.2** — a **downgrade** from the running 0.1.2-alpha.4, and two prereleases behind alpha.5. `dsh --version` correctly reported `0.1.1-rc.2`.

## 3. Exact safe upgrade commands (target: alpha.5 + the TUI plugin)

```powershell
# 1. Stop dsh completely (web host + all sessions), then confirm:
tasklist /FI "IMAGENAME eq node.exe"   # no dsh host/worker processes left

# 2. Install with the version EXPLICITLY pinned (or use the dist-tag explicitly):
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui
# (equivalent tag form for dsh: @deepseek-ai/dsh@alpha — pinning the exact
#  version is safer because tags move)

# 3. Verify before restarting anything:
dsh --version   # must print 0.1.2-alpha.5

# 4. Restart dsh / the web host.
```

Rules embedded here: never combine an unpinned `@deepseek-ai/dsh` with plugin installs; always stop dsh first on Windows because of the koffi native-addon lock.

## 4. Prevention for plugin README authors

- **Pin the dsh dependency explicitly** in install commands (`@deepseek-ai/dsh@<version>` or at least a named dist-tag like `@alpha`). Never ship `npm install -g @deepseek-ai/dsh <my-plugin>` — unpinned `dsh` follows `latest` and will silently downgrade users on prerelease channels.
- **State the prerequisite**: stop all running dsh processes before `npm install -g` on Windows (native addons like koffi are locked while any host/worker process lives). Mention that refreshing the browser page does not release the lock.
- Show a **verify step** after install (`dsh --version`) so a mismatch is caught immediately.
- Prefer a **separate upgrade command** from the plugin-install command, so installing a plugin never re-resolves the harness version as a side effect.
