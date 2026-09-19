# S12 · Global Upgrade EBUSY + Downgrade Trap — Report

## 1. Attempt 1 root cause — why `koffi.node` is locked

`koffi.node` is a **native Node addon binary** (`@koromix/koffi`, used by dsh for FFI-based sandbox/filesystem operations). On Windows, when a process loads a native `.node` DLL, the OS keeps the file locked until **every process that loaded it exits**.

From `running-processes.txt`:

- PID **42432** — `dsh web` host: loaded koffi at startup → **this is the lock holder**
- PID 23768 — agent session worker (child of the host; likely also holds a reference)
- PID 23920 — the `npm install -g` itself, failing on `copyfile`

npm's global install must replace files under the global prefix; because the source-of-truth copy of `koffi.node` (and the staging copy in `@deepseek-ai/.dsh-TMPDIR`) is mapped into a live process, `copyfile` fails with **EBUSY**.

**Why a browser-page refresh does not help:** the Web GUI is only a client-side SPA. Refreshing reloads the page in the browser; the **host Node process (42432) keeps running** with koffi still mapped. The lock is owned by the OS on behalf of that process, not by the browser tab, so nothing page-side can release it.

**Correct stop-then-upgrade sequence:**

1. Finish/stop agent sessions so no dsh work is in flight.
2. Fully **exit the dsh host process** (stop `dsh web` / close the harness — verify with `tasklist` that no `node.exe` dsh host/worker processes remain).
3. Only then run the `npm install -g`.
4. Restart dsh and verify with `dsh --version`.

## 2. Attempt 2 root cause — the version "downgrade"

The plugin README's combined command was:

```
npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
```

The `@deepseek-ai/dsh` specifier is **unpinned**, so npm resolves it to the dist-tag `latest`. Per `npm-dist-tags.txt`:

- `latest` → **0.1.1-rc.2**
- `next` → 0.1.1-rc.2
- `alpha` → 0.1.2-alpha.5

So the install succeeded but installed rc.2, and since the user already had 0.1.2-alpha.4, this effectively **downgraded** the installation. An unpinned global install never "preserves or advances" the installed version — it always follows the registry's `latest` tag, which currently points *behind* the alpha line. `dsh --version` printing `0.1.1-rc.2` is exactly consistent with this.

## 3. Exact safe upgrade commands for this situation

(with dsh fully stopped, per §1)

```powershell
# verify nothing is holding the addon
tasklist /FI "IMAGENAME eq node.exe"

# install the exact prerelease version + the TUI plugin, both pinned by tag/version
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui

# verify
dsh --version   # expect 0.1.2-alpha.5
```

Notes:

- Pin the **exact version** (`@0.1.2-alpha.5`) rather than `@alpha` for reproducibility; `@alpha` also works and tracks the alpha tag, but pinning the concrete version guarantees no surprise movement.
- If the TUI plugin must match the dsh release line, verify its compatibility after install; upgrade it in the same command so both move together.
- If any plugin came from one of the three GitHub mirrors rather than npm, upgrade it through that mirror's own procedure — a global npm upgrade does not touch mirror-installed plugins.

## 4. Prevention — guidance for plugin README authors

1. **Never publish an unpinned `npm install -g @deepseek-ai/dsh ...` in plugin install instructions.** An unpinned global dsh specifier resolves to `latest`, which can silently downgrade users on prerelease lines. Either:
   - omit the dsh package entirely (install only the plugin, assuming dsh is present), or
   - pin it (`@<exact-version>`) or use an explicit dist-tag (`@alpha`), stating which.
2. **Document the stop-first requirement.** Install commands for/alongside dsh must be preceded by "fully stop all dsh processes (host and session workers)" — native addons like koffi stay locked until process exit, and a browser refresh does not release them.
3. **Show verification.** Include `dsh --version` after install so users catch a wrong-channel resolution immediately.
4. **Explain channel semantics.** Note that `latest` does not track prereleases; users on alpha lines must pin or use `@alpha`.

## What this task tested

- Diagnosing an OS-level file lock from process-listing evidence (native addon mapped into a live host process; page refresh cannot release it).
- Tracing an unpinned global install to its actual registry resolution (`latest` tag → rc.2) rather than assuming version preservation.
- Producing a safe, ordered stop → pin → install → verify procedure and preventive README guidance.
