# S12 · Global Upgrade EBUSY + Downgrade Trap — Report

## 1. Attempt 1 root cause: why `koffi.node` is locked

`koffi.node` is a **native addon binary** (`@koromix/koffi`, a Win32/x64 FFI module). Windows loads `.node` files into a process exactly like a DLL: from the moment the module is required until the process exits, the OS keeps the file open with a share lock that forbids overwrite/rename. npm's global install copies the package tree into the prefix and hits `copyfile` on the in-use binary → `EBUSY`.

Who holds it (per `running-processes.txt`):

- **PID 42432 — the `dsh web` host.** It loaded koffi at startup for sandbox/filesystem operations. This is the lock holder that matters.
- PID 23768 — an agent session worker (child of the host; also keeps the host alive).
- PID 23920 — the `npm install -g` itself; it is the victim, not the holder.

**Why a browser-page refresh does not free the lock:** the Web GUI is only an SPA served by the host. Refreshing reloads page JavaScript in the browser; the Node host process (PID 42432) that actually loaded `koffi.node` keeps running, and native modules are never unloadable from a live Node process. The lock lives in the host OS process, not in the page.

**Correct stop-then-upgrade sequence:**

1. Finish/stop any running agent sessions, then fully exit the dsh host (`dsh web` / TUI) — and any other dsh-launched node processes (verify with `tasklist` that no `node.exe` dsh processes remain, or at least none holding koffi).
2. Run the global install while nothing holds the native files:
   ```
   npm install -g @deepseek-ai/dsh@0.1.2-alpha.5
   ```
3. Verify, then restart dsh and reinstall/re-enable plugins if needed.

## 2. Attempt 2 root cause: the downgrade to rc.2

The plugin README's "official combined command" was:

```
npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
```

`@deepseek-ai/dsh` is **unpinned**, so npm resolves it to a version via dist-tags, defaulting to the **`latest`** tag — not to "whatever is currently installed" and not to the newest published version overall. Per `npm-dist-tags.txt`:

- `latest: 0.1.1-rc.2` ← what npm resolved and installed
- `next: 0.1.1-rc.2`
- `alpha: 0.1.2-alpha.5` ← the version actually wanted

`0.1.2-alpha.5` exists only under the `alpha` dist-tag, so an unpinned install "downgraded" the global install from alpha.4 to rc.2. Pre-release versions are also semver-excluded from bare-range resolution, so even range matching would never pick alpha.5 without an explicit tag or exact version.

## 3. Exact safe upgrade commands (want alpha.5 + TUI plugin)

```
# 1. stop dsh completely (web host + sessions), confirm no dsh node.exe remains
# 2. install exact versions/tags:
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui
# 3. verify:
dsh --version   # must print 0.1.2-alpha.5
```

Key rules: always **pin the exact version or dist-tag** (`@0.1.2-alpha.5` or `@alpha`) for `@deepseek-ai/dsh` — never the bare package name — and never run the install while any dsh process is alive (EBUSY on `koffi.node`). If the TUI plugin declares a peer dependency range, make sure the pinned dsh satisfies it; alpha lineages may need the plugin's matching alpha.

## 4. Prevention for plugin README authors

- **Never publish an unpinned combined install command** like `npm install -g @deepseek-ai/dsh <plugin>`. The bare name follows `latest` and can silently downgrade users on `next`/`alpha` channels. Either:
  - omit dsh from the command entirely (install the plugin only: `npm install -g <plugin>`), or
  - pin an exact known-compatible version: `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 <plugin>`.
- **State the required stop-first step**: "fully exit dsh (web host and TUI) before upgrading, or the install fails with EBUSY on native modules (`koffi.node`)". A browser refresh does not count.
- Document the dist-tag the command assumes (`latest` vs `next` vs `alpha`) and publish per-channel install lines when the plugin supports pre-release channels.
- Show a verification step (`dsh --version`) after install so a silent downgrade is caught immediately.

## Summary

- Attempt 1: `EBUSY` because the running `dsh web` host process (PID 42432) had the native addon `koffi.node` loaded; only fully exiting the host (not a page refresh) releases the OS lock.
- Attempt 2: the unpinned `@deepseek-ai/dsh` resolved via the `latest` dist-tag to `0.1.1-rc.2`, silently downgrading from the alpha channel.
- Fix: stop all dsh processes, then `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui`, then verify `dsh --version`.
