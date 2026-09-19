# S16 · The Self-Host Upgrade Trap — Analysis Report

Task: read-only incident analysis of an in-session `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`
that killed the dsh host running the very agent that issued it. Evidence:
`agent-session-log.txt`, `env-state.txt`, `repair-notes.md` (read-only fixture). Methodology:
`plugin-upgrade` skill (the "Global DSH host upgrades (agent discipline)" section and the
`v0.1.2-rc.1` corridor card). Mode: this is Mode-A-style read-only diagnosis; no writes,
installs, or migrations were performed.

## 1. Structural root cause — why the in-session global upgrade fails by construction

The requesting agent did not run "on" the machine next to dsh; it ran **as part of the dsh
host process**. Every layer of the call chain is owned by the artifact npm was replacing:

- The web session, its GUI (http://127.0.0.1:3080), and the conversation state live inside
  the host process `node .../node_modules/@deepseek-ai/dsh/...`.
- The `pwsh` tool call that ran `npm install -g` executed in the host's own tool worker —
  a child of the process whose package tree was the install target.

npm's global upgrade sequence is destructive-in-place: the log shows
`npm warn cleaning node_modules/@deepseek-ai/dsh` (16:41:02) and
`npm info remove @deepseek-ai/dsh` (16:41:05) **before** the new tarball is even fetched
(16:41:09). The moment the old tree is removed, the running host — including the session,
the tool worker, and the code that would have recorded the tool result — loses the modules
it executes from, and the process dies mid-install. That is why:

- the GUI connection was lost at ~16:41 (host dead), and
- the tool call **never returned a result**: the recorder that would persist the tool
  outcome was itself inside the dying process, so the session log shows "no result
  durably recorded — outcome unknown".

This is not flakiness or a race to retry: any in-session attempt to `npm install -g` over
the host's own package is fatal by construction, deterministically, at the
`cleaning`/`remove` step. Per the skill: a crash during the upgrade is a *signature of
doing it wrong*, not a risk to tolerate.

## 2. The broken state afterwards — and why hand-repair makes it worse

Machine state before/after (env-state.txt):

| | Before (0.1.2-alpha.5) | After |
|---|---|---|
| host | running, GUI live | dead mid-install |
| `dsh --version` | `0.1.2-alpha.5` | command not found |
| package content | standard alpha.5 install | rc.1 content present but NON-STANDARD (hand-swapped during a partial manual repair) |
| shims | `dsh`, `dsh.cmd`, `dsh.ps1` present | `dsh` and `dsh.cmd` MISSING; `dsh.ps1` stale, pointing into the old tree |
| leftovers | — | `dsh-old-0.1.1-rc.1` backup dir |

Why the command vanished while content survived: on npm/Windows, the `dsh` **command** is
not the package directory — it is the generated shim files (`dsh`, `dsh.cmd`, `dsh.ps1`)
in `%APPDATA%\npm`. The install died in the window after the old tree was removed but
before npm's `linkStuff`/bin step regenerated the shims, so the CLI entry points were
never recreated. Content-present-but-shim-missing is the exact interrupted-install
signature.

Why hand-swapping directories is the wrong repair:

- npm global installs are not "a directory of files": the standard layout includes the
  generated shims, the npm metadata (`.package-lock.json` / install record) tying the
  global tree to a resolved version, and native-module layout on Windows. A manually
  swapped directory is invisible to that bookkeeping, so later `npm install -g` /
  `npm ls -g` behavior is unpredictable.
- Hand-writing shims reproduces npm's generation step by guesswork (paths, node invocation,
  PowerShell/CMD shim dialects); a wrong shim fails later in confusing ways.
- A stale `dsh.ps1` pointing into the old tree alongside missing `dsh`/`dsh.cmd` already
  shows the half-repaired state diverging per shell (PowerShell finds the stale ps1; cmd
  finds nothing).
- The skill states it flatly: never hand-copy package directories or hand-write shims;
  repair by re-running the pinned formal install.

## 3. The repair actually applied, and why it works

The external repair notes record:

1. **Re-ran the formal install from an external shell**:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` → `dsh`/`dsh.cmd`/`dsh.ps1` all
   regenerated, `dsh --version` → `0.1.2-rc.1`. This works precisely where the in-session
   attempt could not: executed from outside dsh, no process depends on the tree being
   replaced, so npm can run to completion, regenerate the shims, and normalize the
   hand-damaged layout back to a standard install. (The notes' step 2 — aligning the
   *source checkout* to the `dsh-v0.1.2-rc.1` tag — is workspace hygiene for the reference
   checkout, separate from the global install repair.)
2. **Verification**: shim presence + `dsh --version → 0.1.2-rc.1` is the static layer.
   The notes leave the runtime/behavior layers to the user (start `dsh --profile web`,
   hard-refresh the browser, confirm plugins load) — consistent with the skill's layered
   validation (wrapper/static then runtime cold-start then behavior), with the caveat that
   those runtime steps had **not yet been executed** at the time of the notes.

## 4. The protocol the agent should have followed

What the agent should have recognized: the upgrade target (`@deepseek-ai/dsh` global
install) is the runtime of the agent itself — the session, the tool worker, and the code
executing the command all live inside the artifact being replaced. An agent must therefore
**never execute the global host install from inside a session on that host** — this is not
a Mode B/C plugin operation at all, and no amount of retry, timeout tuning, or sequencing
inside the session fixes it. The correct output is not an action but a **hand-off: an
external procedure for the user**, in this order:

1. **Before npm runs — fully stop every dsh process** (host/`dsh web`, any CLI sessions).
   A running host holds native-module file locks on Windows (EBUSY) and, as this incident
   proves, is destroyed by the in-place removal. A browser tab refresh is *not* a host
   stop — the host process must exit.
2. **From an external terminal, run the pinned install**:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — the exact version matters: a bare
   package name resolves to the `latest` dist-tag, which can silently land on an older or
   different line than the requested rc.
3. **Restart `dsh web`, hard-refresh the browser**, verify version markers and that
   plugins load.

Which parts follow from known rules vs. what is new for this incident:

- **Already established by the skill's upgrade rules**: (a) the agent-discipline boundary —
  never self-upgrade the host from inside a session, hand the user the external procedure;
  (b) stop all dsh processes before npm (file locks); (c) the pinned
  `@<exact-version>` install form versus dist-tag drift; (d) restart + hard-refresh +
  version/plugin verification afterwards; (e) if an install was already interrupted,
  repair only by re-running the pinned formal install, never by directory swapping or
  shim hand-writing.
- **New / incident-specific**: the *interrupted-install forensics* — recognizing
  content-present-without-shims (`dsh.cmd`/`dsh` missing, stale `dsh.ps1`) plus a dead
  GUI and an unrecorded tool result as the deterministic signature of an in-session
  self-upgrade, and the fact that the user's partial manual repair had further degraded
  the tree to a non-standard state the formal re-install had to normalize. Additionally,
  for this specific version hop the rc.1 corridor card shows alpha.5→rc.1 is a pure
  version bump (see §5), so the procedure needed no plugin re-migration step — an
  incident-specific fact, not a general rule.

## 5. Prevention

**Agent-side guard.** Before executing any tool call, the agent (or the host's tool
executor) should match the command against "self-host mutation": a global
install/uninstall/update whose target resolves to the package the current process runs
from — concretely, `npm/-g @deepseek-ai/dsh` (any version, including uninstall and
`npm update -g`) when the session's own host is that package. On hit, the guard must
(hard-)refuse execution and instead emit the external procedure of §4 as the reply.
Cheap detection: compare the resolved global package path against the running
process's own module origin (`import.meta.url` / `process.argv[1]` ancestor
`node_modules/@deepseek-ai/dsh`). Softer companions: refuse *any*`-g` lifecycle
operation touching the host package, and surface a "you are inside the upgrade target"
notice whenever release-notes checks mention a dsh host version. Related known
failure mode worth including in the guard's tests: the alpha.1 corridor card
`ghost-host-check` class and the v0.1.5-alpha.1 in-place-upgrade client/bundle roster
mismatch — self-referential host mutations fail in several distinct ways, all of which
the "don't do it from inside" boundary covers.

**Post-upgrade checklist for this machine** (given the alpha.5→rc.1 findings):

1. Static: `dsh --version` → `0.1.2-rc.1`; all three shims (`dsh`, `dsh.cmd`, `dsh.ps1`)
   present and consistent; `npm ls -g @deepseek-ai/dsh` reports a standard resolved
   install (no hand-swapped residue).
2. Runtime: start `dsh --profile web` (a cold start, not a reconnect), hard-refresh the
   browser, confirm the GUI loads and the session list is intact.
3. Behavior: confirm plugins load (whale / progress / etc. per the repair notes) and run
   one message → tool → response flow through the Web Client.
4. Migration scope: alpha.5→rc.1 diff = 252 files, **all package.json version bumps,
   zero API/feature changes** — plugins already migrated for 0.1.2-alpha.x need **no
   re-migration**; do not invent migration work for this hop.
5. Cleanup: after rc.1 is confirmed working, optionally remove the `dsh-old-*` backup
   directories (deferred until verification passes, per the repair notes).

## Summary judgment

The incident was a structural self-upgrade failure, deterministic at npm's
clean/remove step; the correct response at every stage was already encoded in the
plugin-upgrade skill's host-upgrade discipline — the agent should have refused to execute
and handed over the stop-first, pinned, external install procedure; the repair correctly
re-ran that formal install from outside; and prevention is an agent-side self-host
mutation guard plus the layered post-upgrade checklist above.

*No files inside the fixture or benchmark repository were modified; the only write is this
report in the designated output directory.*
