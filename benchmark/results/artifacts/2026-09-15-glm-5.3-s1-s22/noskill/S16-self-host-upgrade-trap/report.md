# S16 · The Self-Host Upgrade Trap — Report

## 1. Structural root cause: why the in-session upgrade fails by construction

The agent ran `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` from inside a dsh web session.
That session, its host process, and the pwsh tool worker executing the npm command are all
*part of the thing being replaced*:

- The dsh host process runs from `...
ode_modules@deepseek-aidsh...` in the npm
  global tree — the exact directory npm is about to remove and rewrite.
- The agent's tool worker is a child of that host process; the web GUI is served by the
  same process (http://127.0.0.1:3080).
- npm's upgrade sequence is destructive *before* it is constructive: the log shows
  `npm warn cleaning node_modules/@deepseek-ai/dsh` then `npm info remove` at
  16:41:02–16:41:05. Removing/relinking the package tree and its bin shims kills the
  files backing the running host process and the command shims it depends on.

So the failure is structural, not flaky: mid-install, npm deletes the live package and
shims; the host process (whose code lives in that tree) dies or becomes unloadable; the
GUI connection is lost at 16:41:09-ish; the npm child is killed with its parent/pipe
before it finishes `linkStuff`; the tool call never completes and never returns a
durable result to the agent or the session log. The interruption is the *expected*
outcome of upgrading the package that is currently executing the upgrade.

## 2. The broken state afterwards

From `env-state.txt` and the session log's shell output:

- The package *content* (rc.1 files) is present under
  `%APPDATA%\npm\node_modules\@deepseek-ai\dsh`, but `dsh.cmd` and the extensionless
  `dsh` shim are **missing** and `dsh.ps1` is **stale** (points into the old tree).
  On Windows, command resolution goes through those shims; with them gone/rotten,
  `dsh --version` and `dsh web` return "command not found" even though the package
  directory still exists. npm died between removing the old shims and generating the new
  ones (it never completed `linkStuff`).
- Hand-swapping or patching directories makes it worse: a manually assembled tree is a
  NON-STANDARD install (the user's partial attempt already mixed hand-placed rc.1 files
  into the tree). npm's install state (shims, bin links, metadata consistency) can't be
  reproduced by copying files; a stale `dsh.ps1` plus a hand-built package dir is a
  Frankenstein install that npm itself will mistrust on the next operation. The correct
  unit of repair is "re-run the formal install", not "fix individual files".

## 3. The repair actually applied, and why it works

Per `repair-notes.md`, the external repair session (a different agent CLI, running
outside any dsh process):

1. Re-ran the formal install from the registry:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — because *nothing dsh-owned was
   running*, npm could complete its full remove→fetch→link cycle and regenerate
   `dsh`, `dsh.cmd`, `dsh.ps1`. This works precisely where the in-session attempt
   could not: the upgrade target is not hosting the process performing the upgrade.
   Result: `dsh --version -> 0.1.2-rc.1`.
2. Aligned the source checkout (host-source reference workspace) from the alpha.5 tag
   to `dsh-v0.1.2-rc.1`; no local-modification conflicts.

Verification: `dsh --version` reports 0.1.2-rc.1 with all three shims regenerated;
remaining user-side verification is to start `dsh --profile web`, hard-refresh the
browser, and confirm plugins (whale / progress / etc.) load; then optionally clean up
the `dsh-old-*` backups once confirmed.

## 4. The protocol the agent should have followed

The agent should have recognized that **it was running inside the upgrade target**: its
host process, GUI, and tool worker all live in the global npm package being replaced.
An agent must never execute a global upgrade of its own harness from inside a session —
it is a guaranteed self-termination with an indeterminate outcome (the tool call cannot
return). This is the agent-discipline boundary: hand the user a procedure instead of
doing it. The correct external procedure, in order:

1. **Before npm runs:** stop dsh entirely — close the web GUI/browser tab and shut down
   the `dsh web` host process (and any other dsh sessions) so nothing is executing
   from the global tree. Use a plain external terminal (PowerShell/cmd), not a dsh
   session.
2. **The install:** `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` run from that
   external shell with no dsh process alive, letting npm complete its full
   remove/fetch/link cycle so all shims are regenerated atomically by npm itself.
3. **After:** `dsh --version` → 0.1.2-rc.1, restart `dsh --profile web`, hard-refresh
   the browser, confirm plugins load; optionally remove `dsh-old-*` backups.

Which parts are known vs new:
- Already following from known upgrade rules: run the global npm install from outside
  the affected sessions; align any host-source reference checkout to the matching tag;
  verify with `dsh --version` and a GUI/plugin check; clean up old backup dirs.
- **New for this incident:** the requirement that the *dsh host process itself* must be
  shut down *before* npm runs — the upgrade must not merely avoid running inside a dsh
  tool call, it must not run while any dsh process is alive on the machine, because the
  host process executes from the very tree npm replaces. Also new: on an interrupted
  install, repair by re-running the formal install rather than hand-patching
  directories/shims.

## 5. Prevention

Agent-side guard (class-level): before executing any tool call that mutates the global
install of the harness itself (npm/pnpm `install -g @deepseek-ai/dsh`, npm removal,
shim edits), the agent should detect that its own host process runs from that package
tree (e.g. compare its executable/module path against the npm global
`node_modules\@deepseek-ai\dsh`) and refuse to execute, instead emitting the external
procedure above for the user. The general rule: an agent must never replace a package
that is currently executing it — the call cannot return and the outcome is
indeterminate.

Post-upgrade checklist for this machine (given the alpha.5→rc.1 findings):
- Confirm all three shims exist and `dsh --version` → 0.1.2-rc.1.
- Restart `dsh --profile web`; hard-refresh the browser; confirm plugins
  (whale / progress / etc.) load.
- Source checkout alignment: already moved alpha.5 → `dsh-v0.1.2-rc.1` tag; nothing
  further needed — the alpha.5→rc.1 diff is **252 files, all version bumps, zero
  API/feature changes**, so plugins migrated for 0.1.2-alpha.x need **no re-migration**.
- Optionally delete the `dsh-old-*` backup directories once rc.1 is confirmed working.
