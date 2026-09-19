# S16 · The Self-Host Upgrade Trap — Report

Task: analyze (read-only) why an in-session `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`
killed the running dsh host, left the CLI unusable, and what the correct repair and
protocol are. Evidence: `environment/fixture/` (agent-session-log.txt, env-state.txt,
repair-notes.md). No files inside the fixture or benchmark repository were modified.

Methodology: `plugin-upgrade` skill, "Global DSH host upgrades (agent discipline)"
section — this incident is exactly the structural failure that section forbids. The task
is Mode A (read-only inspect/diagnose); no install, migration, or write was executed.

---

## 1. Structural root cause — failure by construction, not by accident

The requesting agent was a dsh web session, and **the session IS the host process**. The
conversation, the tool worker executing the `pwsh` tool call, and the HTTP server backing
the GUI at http://127.0.0.1:3080 all live inside `node .../node_modules/@deepseek-ai/dsh/...`
— the very package tree that `npm install -g` was replacing. Concretely:

- The tool worker (the pwsh subprocess spawned by the host) is a **child of the host
  process running from the package directory npm was removing**. npm's global install of
  an already-present package is destructive-in-place: the log shows
  `npm warn cleaning node_modules/@deepseek-ai/dsh` then `npm info remove @deepseek-ai/dsh`
  (16:41:02–16:41:05) — the running host's module tree was deleted out from under it
  before the new tarball was linked (`linkStuff` at 16:41:31).
- On Windows the host also holds **native-module file locks** inside that tree; removing
  locked content mid-execution kills or corrupts the process. The web GUI connection
  died at exactly this point — the host died mid-install, and the in-flight tool call
  never returned: its outcome could not be durably recorded because the recording layer
  (the host process itself) was the thing being destroyed. This is why the session log
  shows `<no result recorded — outcome unknown>`.

So the failure is not flaky and not retryable from inside: any retry would repeat the
same suicide. The skill states this as an absolute rule: never execute the global host
upgrade from inside a session on that host — a crash during the upgrade is a signature
of doing it wrong, not a risk to tolerate.

## 2. The broken state afterwards — interrupted-install signature

From env-state.txt, the AFTER state shows the classic interrupted npm global install:

- **Package content present, shims absent**: `node_modules\@deepseek-ai\dsh\` contains
  rc.1 files, but `dsh` and `dsh.cmd` shims are MISSING and `dsh.ps1` is stale (points
  into the old tree). npm writes package content early (fetch/copy/linkStuff) and
  (re)generates the bin shims at the END of the install; the host died before that final
  step, so `dsh --version` and `dsh web` both return "command not found" even though
  the package is "installed". A partial manual directory swap by the user made it a
  NON-STANDARD install: content present, no standard layout, no shims — the CLI is dead.
- **Why hand-swapping/patching directories makes it worse**: the npm global tree is only
  useful as a coherent install (package content + generated `dsh`/`dsh.cmd`/`dsh.ps1`
  shims + npm's own metadata). Hand-copying package directories or hand-writing shims
  produces a tree npm no longer recognizes, drifts from what the registry guarantees
  (lifecycle/bin generation, file completeness), and leaves stale backups
  (`dsh-old-0.1.1-rc.1`) and stale shims (`dsh.ps1`) that can silently resolve to the
  wrong version later. The skill's rule: never hand-copy package directories or
  hand-write shims — repair only by re-running the pinned formal install from outside.

## 3. The repair actually applied, and why it works

The external repair notes record:

1. **Re-run the formal install from an external agent (outside dsh)**:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` → regenerated
   `dsh` / `dsh.cmd` / `dsh.ps1`; `dsh --version → 0.1.2-rc.1`. This works where the
   in-session attempt could not because no dsh process was alive to be killed: with the
   host fully stopped, npm can clean, link, and generate shims to completion. Re-running
   the pinned install also *normalizes* the user's non-standard hand-patched tree back
   into a standard registry install.
2. Aligned the source-reference workspace from the alpha.5 tag to `dsh-v0.1.2-rc.1`
   (no local-modification conflicts).

Verification: `dsh --version` reports the pinned target; the remaining verification
(left for the user per the notes) is behavioral — start `dsh --profile web`,
hard-refresh the browser, confirm plugins (whale / progress / etc.) load, then
optionally clean up `dsh-old-*` backups once rc.1 is confirmed.

## 4. The protocol the agent should have followed

**Recognition**: the agent should have identified its own relationship to the upgrade
target — it ran *inside* the dsh host process that `npm install -g` would remove.
Upgrading the host is not plugin Mode B/C work at all; the skill's agent-discipline
section explicitly forbids executing it in-session. So: **no, it must never execute the
global install itself**, however benign the release notes look (and here the notes
confirmed alpha.5→rc.1 is 252 files of pure version bumps — the danger was structural,
not version-related). The correct behavior is to hand the user an external procedure:

1. **Before npm runs**: fully stop every dsh process — the host, the GUI server, all
   sessions. A running host holds native-module file locks (EBUSY on Windows) and is
   the process npm replaces. A browser tab refresh/close is NOT a host stop.
2. **The install command**, from an EXTERNAL terminal (not a dsh session/tool call):
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — the **exact pinned version** must be
   part of the command, because a bare `npm install -g @deepseek-ai/dsh` resolves to
   the `latest` dist-tag and can silently install/downgrade to an older line.
3. **Afterwards**: restart `dsh web`, hard-refresh the browser, verify version markers
   and that plugins load.

Which parts follow from known rules vs. new for this incident: the "never upgrade the
host from inside a session" boundary, the stop-first ordering, the pinned-version
command form, and the restart/hard-refresh/verify tail all follow directly from the
skill's global-host-upgrade discipline. What is incident-specific (new) is the
**interrupted-install recovery**: once an in-session attempt has already broken the
tree, the only sanctioned repair is re-running the pinned formal install from an
external shell — never hand-copying directories or hand-writing shims — and, in this
case, also re-aligning the source-reference checkout to the target tag and treating
the hand-swapped directory state as untrusted until normalized.

## 5. Prevention

**Agent-side guard** (class-level, not version-specific):

- A pre-execution check on destructive/global install commands: if the command targets
  the dsh host package (`@deepseek-ai/dsh`, or the package tree the current process
  executes from) via `npm/pnpm install -g`, `npm rm -g`, cache cleaning of that tree,
  or equivalent, and this agent runs inside that host — **refuse and respond with the
  external hand-off procedure** (steps above) instead of executing. Detection can be
  structural: compare the install target against the running process's own module
  origin (`node .../node_modules/@deepseek-ai/dsh/...`).
- Symmetrically, a recovery rule: if a previous in-session attempt left the shim-less
  signature (content present, `dsh`/`dsh.cmd` missing), the agent must not "help" by
  patching directories — it can only emit the external pinned re-install instruction.

**Post-upgrade checklist for this machine** (given the repair notes' alpha.5→rc.1
findings):

1. `dsh --version` → `0.1.2-rc.1`; all three shims (`dsh`, `dsh.cmd`, `dsh.ps1`) present
   and consistent — no stale `.ps1` pointing into an old tree.
2. Cold-start `dsh web` (or `dsh --profile web`), hard-refresh the browser, confirm the
   GUI loads and the session/plugins work: whale, progress, etc.
3. No re-migration needed: the alpha.5→rc.1 diff is 252 files, all `package.json`
   version bumps, zero API/feature changes — plugins already migrated for
   0.1.2-alpha.x are unaffected. Verification effort should go to the runtime mount,
   not to source changes.
4. Confirm the source-reference checkout sits on `dsh-v0.1.2-rc.1` with no
   local-modification conflicts.
5. After rc.1 is confirmed working, optionally remove the `dsh-old-*` backup
   directories (including `dsh-old-0.1.1-rc.1`) to prevent a stale shim/path from ever
   resolving into them.

---

## Summary answers (compressed)

| Question | Answer |
|---|---|
| Root cause | The session/tool worker ran inside the very host process whose package tree `npm install -g` deletes first; the host (and its result-recording layer) died mid-install — structural, not flaky |
| Why `dsh` vanished | npm writes content early and generates bin shims last; the interrupted (then hand-patched) install left content present with `dsh`/`dsh.cmd` missing and a stale `dsh.ps1` — a non-standard install; hand-swapping directories breaks npm's coherent install guarantees and is forbidden |
| Repair applied | External pinned re-install `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` (host stopped → npm completes, shims regenerate); verified via `dsh --version` + restart/hard-refresh/plugin check |
| Correct protocol | Recognize self-host relationship → never execute the global install in-session → hand the user: stop all dsh processes (not just close the tab) → external pinned install → restart, hard-refresh, verify |
| Prevention | Guard refusing global installs targeting the running host's own package; recovery rule mandating external pinned re-install; post-checklist: shims consistent, cold-start + plugin load, no re-migration (pure version bumps), tag-aligned checkout, cleanup of `dsh-old-*` |

No blockers: all evidence was available in the fixture; the analysis is complete and
read-only as required.
