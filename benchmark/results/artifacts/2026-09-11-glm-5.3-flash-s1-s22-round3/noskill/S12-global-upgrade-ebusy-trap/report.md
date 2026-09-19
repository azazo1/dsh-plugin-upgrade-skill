# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnostic Report

Environment: Windows, dsh `0.1.2-alpha.4` currently running, six community Web plugins across three GitHub mirrors. Target release: `@deepseek-ai/dsh@0.1.2-alpha.5`. Evidence: `attempt1-ebusy.log`, `attempt2-downgrade.log`, `npm-dist-tags.txt`, `running-processes.txt` (fixture, read-only).

## 1. Attempt 1 root cause — why `koffi.node` is locked

**What the evidence shows.** `attempt1-ebusy.log`:

```
$ npm install -g @deepseek-ai/dsh@0.1.2-alpha.5
npm error code EBUSY
npm error syscall copyfile
npm error path C:\...\@koromix\koffi-win32-x64\win32_x64\koffi.node
npm error dest C:\...\@deepseek-ai\.dsh-TMPDIR\...\koffi.node
```

npm is trying to copy the installed native FFI addon `@koromix/koffi-win32-x64`'s `koffi.node` into its staging directory, and Windows refuses the copyfile because the source file is open.

**Who holds the lock.** `running-processes.txt` gives the process listing at the time:

```
node.exe  42432  <- dsh web host (holds koffi.node)
node.exe  23768  <- agent session worker
node.exe  23920  <- npm install -g (attempting the copy)
```

The **dsh web host process (PID 42432)** holds the lock. The fixture's own annotation explains the mechanism: the dsh web host loaded `@koromix/koffi` (the native FFI addon for sandbox/filesystem operations) at startup. `koffi.node` is a native `.node` binary — once loaded into a process, the OS holds a file lock on it **until the process exits**. A running dsh instance therefore keeps every native addon it has loaded locked for the whole lifetime of the process.

**Why a browser-page refresh does not free the lock.** The DSH web GUI is an SPA served by the dsh web host. Refreshing the browser page only tears down and reloads the **client-side SPA**; the **host process that loaded koffi** (PID 42432) stays alive and keeps the module mapped. The lock is held by the OS on behalf of the *server* process, not the browser, so refreshing the page, closing tabs, or even restarting the browser cannot release it. The agent session worker (PID 23768) likewise belongs to the still-running dsh instance.

**Correct stop-then-upgrade sequence.**

1. Exit the running dsh instance completely — quit the CLI/session and stop the web host (PID 42432) and all agent session workers (PID 23768); **all** dsh-owned `node.exe` processes must be gone. Verify with `tasklist /FI "IMAGENAME eq node.exe"`.
2. Run the versioned install: `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5`.
3. Restart dsh afterwards (it re-launches against the newly copied `koffi.node`).

Principle: on Windows, a global npm upgrade of a package containing native `.node` addons can only succeed while **no process has those addons loaded** — stop the app first, upgrade second.

## 2. Attempt 2 root cause — why `dsh --version` showed `0.1.1-rc.2`

**What the evidence shows.** `attempt2-downgrade.log`:

```
$ npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
(installs fine, but...)
$ dsh --version
0.1.1-rc.2
```

The install command **omitted the version specifier** — `@deepseek-ai/dsh` appears bare, with no `@0.1.2-alpha.5`. The user wanted alpha.5 but got `0.1.1-rc.2`, an actual **downgrade**: semver orders `0.1.2-alpha.4` (a prerelease of 0.1.2) *above* `0.1.1-rc.2`.

**What the unpinned name resolves to and why.** An unpinned `npm install -g <pkg>` resolves to the version pointed to by npm's default dist-tag, which is **`latest`** — not "whatever you currently have installed", and not "the newest version that exists". Prereleases (`alpha`, `rc`) do not automatically become `latest`; the publisher must explicitly move the tag.

**Which dist-tag it follows — registry proof.** `npm-dist-tags.txt`:

```
$ npm view @deepseek-ai/dsh dist-tags
{
  next: '0.1.1-rc.2',
  latest: '0.1.1-rc.2',
  alpha: '0.1.2-alpha.5'
}
```

At that moment `latest` → `0.1.1-rc.2` (and `next` coincidentally also points at `0.1.1-rc.2`), while the wanted `0.1.2-alpha.5` is reachable only via the `alpha` dist-tag. The unpinned install followed `latest` → `0.1.1-rc.2`, overwriting the installed `0.1.2-alpha.4` — exactly why `dsh --version` printed `0.1.1-rc.2`.

The trap: the "official combined command from a plugin README" bundles the TUI plugin install (`@deepseek-harness-tui/dsh-tui`, fine) with an unpinned `@deepseek-ai/dsh` operand that silently *downgrades* any user running an alpha or otherwise newer-than-latest build.

## 3. Exact safe upgrade commands for this situation

Stop all dsh processes first (per §1 — otherwise the EBUSY returns), then pin both packages explicitly:

```powershell
# 1. Exit dsh (web host + session workers). Verify nothing dsh-owned remains:
tasklist /FI "IMAGENAME eq node.exe"

# 2. Install the exact target dsh version AND the TUI plugin in one command, dsh pinned:
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui

# 3. Verify:
dsh --version   # must print 0.1.2-alpha.5
```

Notes:

- Pinning `@0.1.2-alpha.5` is mandatory: bare `@deepseek-ai/dsh` follows `latest` (`0.1.1-rc.2`). `npm install -g @deepseek-ai/dsh@alpha` would also work via the `alpha` tag, but the explicit version is safest. `next` does not help — it also points at `0.1.1-rc.2`.
- Alternatively install the TUI plugin in a separate command; whichever command touches `@deepseek-ai/dsh` must carry the pinned version.
- Restart dsh after the upgrade and re-verify the six community plugins load under the new host version.

## 4. Prevention — guidance for plugin README authors

The Attempt 2 trap is an **unpinned package operand in a copy-pasted install command**. README authors should:

1. **Never write a bare package name for the host in install commands.** `npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui` downgrades anyone on a build newer than `latest`. Either document only the plugin install (`npm install -g @deepseek-harness-tui/dsh-tui`) and leave host upgrades to a separate, explicit step, or pin the host version the plugin was validated against: `npm install -g @deepseek-ai/dsh@<version> @deepseek-harness-tui/dsh-tui`.
2. **Never assume `latest` means "newest" or "what the user has".** `latest` is a mutable dist-tag that trails prereleases; document that alpha/rc users must pin explicitly (or use `@alpha`), and state which dist-tag (`latest`, `next`, `alpha`) each documented command targets.
3. **Warn about the Windows stop-before-upgrade requirement.** Every upgrade section should say: exit all running dsh processes (web host and session workers) before `npm install -g`, because native addons (`koffi.node`) stay file-locked while any dsh process is alive and a browser refresh does not release them.
4. **Include a post-install verification step** (`dsh --version`, checked against the intended version) so a silent downgrade is caught immediately rather than at the next session.
5. Prefer one canonical, versioned, copy-paste-safe command block per release over a generic combined command whose operands silently resolve by dist-tag.