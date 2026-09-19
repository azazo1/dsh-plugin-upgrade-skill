# S16 · The Self-Host Upgrade Trap — Report

## 1. Structural root cause

The failure is structural, not flaky. The agent session and its `pwsh` tool worker are
*parts of the thing npm was replacing*:

- The dsh web host is `node .../node_modules/@deepseek-ai/dsh/...` — a process whose
  loaded code lives inside the npm global package tree that the upgrade targets.
- The agent session, its GUI (http://127.0.0.1:3080), and the tool worker executing the
  `npm install -g` are all children of that host process.
- npm's install sequence removes the old package first (log: `npm warn cleaning
  node_modules/@deepseek-ai/dsh` → `npm info remove @deepseek-ai/dsh`) before fetching
  and linking the new one (`fetch` → `linkStuff`). On Windows, replacing a directory
  that backs a running process breaks the process. The host — and therefore the web GUI,
  the session, and the in-flight tool call — died between fetch and link completing.
- Because the tool worker itself was killed mid-call, no result could be recorded
  durably: the log shows the call was recorded as started but "<no result recorded …
  outcome is unknown>". The interruption is on the *caller's* side, so the callee's exit
  status can never come back.

By construction: the upgrade removes its own executor's runtime before the upgrade can
finish, so an in-session global self-upgrade can never complete from inside the host it
is upgrading.

## 2. The broken state afterwards

Evidence (env-state.txt, session log):

- The install died mid-sequence, after the old tree was removed/cleaned but before
  bin-linking completed. npm generates the global shims (`dsh`, `dsh.cmd`, `dsh.ps1`)
  as part of the link step; that step never ran to completion.
- Result: `dsh.cmd` and the extensionless `dsh` shim are **missing**, and `dsh.ps1`
  is **stale** (still pointing into the old alpha.5 tree, which npm had renamed to
  `dsh-old-0.1.1-rc.1`/backups). Windows resolves commands via PATHEXT, so with both
  resolvable shims gone, `dsh` is "command not found" even though rc.1 *package content*
  sits in `node_modules\@deepseek-ai\dsh`.
- The user's partial manual repair (hand-swapping directory content) made it worse in a
  specific way: it produced a **non-standard install** — content present, but no registry
  metadata/layout npm can reason about and no generated shims. Hand-patching cannot
  regenerate shims correctly (paths, ps1/cmd wrappers are npm-owned artifacts), and
  hand-swapped trees mask the true state, so later npm operations may mis-detect or
  double-mangle the tree. Directory swapping also risks mixing alpha.5 and rc.1 files.

## 3. The repair actually applied

Per repair-notes.md:

1. **Re-run the formal install from the registry**:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — executed by an *external* agent CLI
   outside dsh. This regenerated `dsh`, `dsh.cmd`, `dsh.ps1` and restored a standard
   install layout; `dsh --version` → `0.1.2-rc.1`.
2. Aligned the source checkout from the alpha.5 tag to `dsh-v0.1.2-rc.1` (no conflicts).

Why this works where the in-session attempt could not: the repairing process has no
dependency on the package being replaced, so it survives the remove/replace phase and
lets npm run to completion, including the bin-linking step whose absence caused the
breakage. It also normalizes the non-standard hand-swapped tree back to something npm
owns end-to-end.

**Verification:** `dsh --version` → 0.1.2-rc.1; all three shims present; and (left for
the user on the real machine) start `dsh --profile web`, hard-refresh the browser,
confirm plugins (whale / progress / etc.) load. The alpha.5→rc.1 diff (252 files, all
version bumps, zero API changes) means no re-migration of plugins is needed — plugin
loading success is the functional check.

## 4. The protocol the agent should have followed

**Self-recognition:** the agent runs *inside* the dsh host — it is a component of the
upgrade target. Any command that replaces the global `@deepseek-ai/dsh` tree kills its
own host, session, and tool worker mid-call. Therefore the agent must **not** execute the
global install itself — this is the "hand the user a procedure you must not execute
yourself" boundary. It should also have finished its turn cleanly (no in-flight tool
call) before the host is stopped.

**External procedure to hand the user (order matters):**

1. *Before npm runs:* close the dsh web GUI in the browser and **stop the running dsh
   host** (and any dsh sessions/workers) so nothing holds the package tree — this is the
   step that prevents exactly this incident and is **new for this incident** relative to
   known upgrade rules.
2. Then run the formal registry install in a fresh external shell:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — a plain, unmodified global install
   (no directory swapping, no hand patching), so npm owns remove → fetch → link →
   shim-generation atomically.
3. Verify: `dsh --version` → 0.1.2-rc.1; then `dsh --profile web` (or `dsh web`),
   hard-refresh the browser, confirm plugins load.

**Which parts follow from known rules vs. new:** running the standard global install
from a normal shell and verifying the version afterwards follow from ordinary upgrade
rules. The *new* part for this incident is the precondition — the agent recognizing its
in-host position and requiring the host (its own process) to be stopped *before* npm
runs, and declining to run the install itself.

## 5. Prevention

**Agent-side guard:** the shell/tool layer (or a pre-tool policy check) should match
commands that mutate the global `@deepseek-ai/dsh` installation — e.g. `npm
install/-g/uninstall` targeting `@deepseek-ai/dsh`, or writes into the npm global
`node_modules\@deepseek-ai\dsh` tree or its shims — and refuse them when the session
runs inside a dsh host, with a message explaining the self-upgrade conflict and emitting
the external procedure above (stop host first, then install from an external shell).
Detecting "am I inside the host I'd be replacing" (host process path under the npm global
dsh tree) makes the guard precise rather than a blanket npm ban.

**Post-upgrade checklist for this machine (given the alpha.5→rc.1 findings):**

- `dsh --version` reports 0.1.2-rc.1; `dsh`, `dsh.cmd`, `dsh.ps1` all present and
  consistent (no stale ps1 pointing at `dsh-old-*`).
- Standard install state: no hand-swapped content in
  `%APPDATA%\npm\node_modules\@deepseek-ai\dsh`.
- Start `dsh --profile web`, hard-refresh the browser at the GUI URL, confirm plugins
  (whale / progress / etc.) load — the diff was version bumps only, so *no plugin
  re-migration* is needed; loading success is sufficient.
- Source checkout aligned to `dsh-v0.1.2-rc.1` (done in repair).
- Optional: delete the `dsh-old-*` backup directories once rc.1 is confirmed working.
