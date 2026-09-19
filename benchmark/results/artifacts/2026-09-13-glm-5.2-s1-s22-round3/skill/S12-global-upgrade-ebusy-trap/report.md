# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnostic Report

Task: S12-global-upgrade-ebusy-trap (read-only analysis; Mode A inspect per the plugin-upgrade skill's
"Global DSH host upgrades (agent discipline)" section). No files in the fixture were touched; no installs
or migrations were executed.

Evidence base: `attempt1-ebusy.log`, `running-processes.txt`, `attempt2-downgrade.log`, `npm-dist-tags.txt`.

---

## 1. Attempt 1 root cause — why `koffi.node` is EBUSY

**What is holding it:** the running **dsh web host process** (PID 42432 in `running-processes.txt`). The host
loads `@koromix/koffi` — a native FFI addon used for sandbox/filesystem operations — at startup, which maps
`@koromix\koffi-win32-x64\win32_x64\koffi.node` into the process. On Windows, a loaded native `.node`
PE image is held with a mandatory share lock by the OS: **no other process may write/copy over it until every
process that loaded it has exited**. `npm install -g` (PID 23920) tries to `copyfile` a fresh
`koffi.node` into the dsh package tree and fails with `EBUSY`. Note this is file-content locking, not a
permission problem — it would fail identically for any account.

A second holder worth noting: PID 23768, the **agent session worker**, is also a dsh-spawned node process and
just as capable of holding native-module locks (the skill warns generally: "a running host holds native-module
file locks → EBUSY"). Any dsh-derived node process can keep the lock alive.

**Why a browser-page refresh does not free the lock:** the browser page is only a client of the host. The Web
GUI is an SPA served by the `dsh web` host process; refreshing it drops the WebSocket and reloads JavaScript
in the *browser*, but the host process (PID 42432) keeps running in the console session with `koffi.node`
still mapped. A refresh is not a host stop.

**Correct stop-then-upgrade sequence:**

1. Fully stop every dsh process — the `dsh web` host *and* all agent session workers it spawned. On Windows,
   verify with e.g. `tasklist /FI "IMAGENAME eq node.exe"` (or `Get-Process node`) that the host/worker PIDs
   are gone; kill lingering dsh node processes if a clean shutdown left any. A browser refresh does not count.
2. From an **external terminal** (not from inside a dsh session — see below), run the **pinned** install
   `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5`.
3. Restart `dsh web`, hard-refresh the browser, and verify `dsh --version` reports `0.1.2-alpha.5`.

Per the skill: never run the global host upgrade from *inside* a dsh session running on that host — the session
IS the host process; npm replaces the package tree the host executes from, the tool call never returns, and the
interrupted install can leave package content without regenerated shims (the `dsh` command itself disappears
until an external pinned re-install repairs it).

## 2. Attempt 2 root cause — why `dsh --version` printed `0.1.1-rc.2`

Attempt 2 ran the "official combined command" from a plugin README:

```
npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui
```

The `@deepseek-ai/dsh` token is **unpinned**, so npm resolves it to a **dist-tag**, not to "whatever is
installed" and not to the newest published version. Per `npm-dist-tags.txt`:

| dist-tag | version |
|---|---|
| `latest` | `0.1.1-rc.2` |
| `next` | `0.1.1-rc.2` |
| `alpha` | `0.1.2-alpha.5` |

A bare package name defaults to the **`latest` dist-tag**, which at that moment pointed at `0.1.1-rc.2`. So
the install *succeeded* — and silently **downgraded** the host from 0.1.2-alpha.4 to 0.1.1-rc.2, an older line
entirely. Alpha.5 exists only under the `alpha` tag; it is not reachable without an explicit pin or
`@alpha`. This is exactly the trap the skill names: "a bare package name resolves to the `latest` dist-tag
and can silently downgrade to an older line." Npm never compares against the currently installed version; an
unpinned global install is "install whatever `latest` says," full stop.

## 3. Exact safe upgrade commands for this situation (want alpha.5 + the TUI plugin)

From an **external terminal**, after **all dsh processes are stopped**:

```pwsh
# 0. verify nothing is holding native-module locks
tasklist /FI "IMAGENAME eq node.exe"

# 1. pinned host install — never the bare package name
npm install -g @deepseek-ai/dsh@0.1.2-alpha.5
# (equivalently: npm install -g @deepseek-ai/dsh@alpha — but the exact pin is safer/reproducible)

# 2. TUI plugin, pinned to a version whose DSH peer-dependency corridor covers 0.1.2-alpha.5
npm view @deepseek-harness-tui/dsh-tui versions           # pick the exact version
npm view @deepseek-harness-tui/dsh-tui@<version> peerDependencies
npm install -g @deepseek-harness-tui/dsh-tui@<exact-version>

# 3. verify before restarting
dsh --version        # must print 0.1.2-alpha.5
```

Then restart `dsh web`, hard-refresh the browser, and confirm the TUI plugin is actually enabled in the
resolved profile composition (a successful install does not mean DSH enabled it — Mode B step 5 of the skill).
Before installing the TUI plugin, check its release notes for the corridor it targets: a plugin built for the
0.1.1 line may not be compatible with 0.1.2-alpha.5 (the skill's reference cards cover 0.1.1-rc.2 →
0.1.2-alpha.x breaking changes); if its peer range does not include `0.1.2-alpha.5`, wait for or request an
alpha-corridor release rather than forcing the install. Do not hand-copy package directories or hand-write
shims if anything was interrupted — re-run the pinned formal install.

## 4. Prevention — what plugin README authors should do differently

1. **Never publish a bare `npm install -g @deepseek-ai/dsh …` as an install command.** A bare name follows the
   `latest` dist-tag and can silently downgrade users on alpha/next lines. Always pin
   `@deepseek-ai/dsh@<exact-version>` (or at minimum the intended dist-tag `@alpha`/`@next`, stated as
   such), and update the README pin at each release.
2. **State the peer corridor explicitly**: the README should name the DSH version(s) the plugin version was
   built and tested against, so users can match host and plugin lines instead of mixing them blindly in one
   combined command.
3. **Put the stop-host step in the command block, not in prose (or nowhere)**: e.g.
   "stop all dsh processes first (a browser refresh is not a stop), then from an external terminal run …".
   Combined one-liners that begin with `npm install -g` invite exactly the EBUSY of attempt 1.
4. **Prefer separate, individually pinned commands** for host and plugin, or a single command where *every*
   package is version-pinned — never a mixed command where the host is unpinned and the plugin is pinned.
5. **Never suggest running the global upgrade from inside a running dsh session** (an agent/CLI launched by dsh
   is the host process; the install kills itself mid-flight).

---

## Skill-conformance notes

- Mode A (read-only inspect): no configuration, dependency, or source writes were performed; the fixture was
  only read. The normally-required user confirmation before writes is covered by the BENCHMARK-AUTH-v1
  authorization in the task brief, but no write beyond the report was needed.
- The diagnoses follow the skill's "Global DSH host upgrades (agent discipline)" section verbatim: EBUSY from a
  live host's native-module lock; browser refresh ≠ host stop; bare package name → `latest` dist-tag → silent
  downgrade; repair/upgrade only via an external, pinned install.

## Skipped / not applicable

- Corridor card analysis (Mode C) — this task is a host-install diagnosis, not a plugin source migration.
- Runtime verification layers — the brief forbids executing installs; the recommended commands are documented
  for the user to run externally.

## Residual risk

- The exact compatible `@deepseek-harness-tui/dsh-tui` version for the 0.1.2-alpha.5 corridor could not be
  confirmed from the fixture (no registry access allowed); step 3 therefore includes the
  `npm view … peerDependencies` check the user must perform before installing the plugin.
