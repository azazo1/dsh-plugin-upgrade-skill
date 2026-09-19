# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnosis Report

Evidence reviewed (read-only): `attempt1-ebusy.log`, `running-processes.txt`, `attempt2-downgrade.log`, `npm-dist-tags.txt` from the fixture pack.

## 1. Attempt 1 root cause — why `koffi.node` is locked

**What is holding it:** the still-running **dsh web host process** (node.exe, PID 42432 in `running-processes.txt`). `@koromix/koffi` is a native FFI addon (used by dsh for sandbox/filesystem operations) that the host loads at startup. On Windows, once a process loads a native `.node` PE binary, the OS keeps the file locked (it is a loaded module, mapped into the process) until that process exits. `npm install -g` therefore cannot `copyfile` over/through `koffi.node` into its temp dir (`@deepseek-ai/.dsh-TMPDIR/...`) and fails with `EBUSY`.

**Why a browser-page refresh does not help:** the Web GUI is just a SPA served by the host. Refreshing reloads the page in the browser; the **host node.exe process — the process that actually mapped `koffi.node` — keeps running** and keeps the lock. The lock lives in the OS per-process, not per browser tab. (The agent session worker, PID 23768, is a child and should also be gone before upgrading, but it is not the lock holder named in the evidence.)

**Correct stop-then-upgrade sequence:**

1. Finish/stop any running agent sessions (children of the host).
2. Fully exit the dsh web host process so it unloads `koffi.node` (close the dsh command/terminal that started it, or stop the dsh service; verify with `tasklist` that the host node.exe PID is gone).
3. Only then run the pinned global install (commands in §3).
4. Restart dsh and verify with `dsh --version`.

## 2. Attempt 2 root cause — the silent downgrade to rc.2

Attempt 2 stopped the host first (good), so the install succeeded — but the command copied from the plugin README was:

```
npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
``}

The `@deepseek-ai/dsh` specifier is **unpinned**, so npm resolves it to the registry's **`latest` dist-tag**, exactly as if you had typed `@deepseek-ai/dsh@latest`. Per `npm-dist-tags.txt` at that moment:

- `latest` → `0.1.1-rc.2`
- `next` → `0.1.1-rc.2`
- `alpha` → `0.1.2-alpha.5`

The installed `0.1.2-alpha.4` is an **alpha-channel** build, but npm global installs never "advance from" or even look at the currently installed version: an unpinned name simply follows `latest`, which still pointed at the older `0.1.1-rc.2`. So the "upgrade" command silently **downgraded** the global install from alpha.4 to rc.2, which `dsh --version` then reported. To get alpha.5 you must explicitly use `@alpha` or the exact version.

## 3. Exact safe upgrade commands (want alpha.5 + the TUI plugin)

```pwsh
# 1. Stop all dsh host/agent processes (releases the koffi.node lock)
#    verify nothing is holding it:
tasklist /FI "IMAGENAME eq node.exe"

# 2. Pin BOTH packages to the exact target version / channel:
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui@<matching-version>
#    (or channel-pinned: npm install -g @deepseek-ai/dsh@alpha)

# 3. Verify — must print 0.1.2-alpha.5:
dsh --version
```

Notes:
- Pin the TUI plugin explicitly too (`@<version>` or its matching tag); an unpinned third-party global package follows **its own** `latest`, which can equally mismatch your alpha-channel dsh.
- Never use the README's combined unpinned command when you are not on the `latest` channel.

## 4. Prevention — what plugin README authors should do

- **Never publish unpinned global install commands.** `npm install -g @deepseek-ai/dsh <my-plugin>` hijacks the *core* package's version and follows dsh's `latest` dist-tag, silently downgrading users on `next`/`alpha` channels. This is the trap that caught this user.
- Install **only the plugin** in the README command (`npm install -g <my-plugin>@x.y.z`); tell users to install/upgrade dsh separately, pinned to the version/channel they already use (`npm install -g @deepseek-ai/dsh@<their-version>`).
- Always **pin exact versions** (or at least a dist-tag) in copy-paste commands, and keep them updated per release.
- Document the **stop-before-upgrade** requirement on Windows: native addons like `koffi.node` stay locked until the host process exits; state that a browser refresh does not release it.
- Suggest a post-install verification step (`dsh --version`) so a silent downgrade is caught immediately.

## Summary

| Attempt | Failure | Root cause |
|---|---|---|
| 1 | EBUSY copying `koffi.node` | Running dsh web host (PID 42432) has the native addon loaded; Windows locks loaded `.node` modules until process exit; page refresh doesn't touch the host process |
| 2 | `dsh --version` → `0.1.1-rc.2` | Unpinned `@deepseek-ai/dsh` resolves to the `latest` dist-tag (= 0.1.1-rc.2), which is *older* than the installed alpha.4 — an unpinned global install follows the registry tag, not the installed version |

Fix: stop dsh completely, install with explicit pins (`@deepseek-ai/dsh@0.1.2-alpha.5` + pinned TUI plugin), verify `dsh --version`, and pressure plugin READMEs to stop shipping unpinned combined global-install commands.
