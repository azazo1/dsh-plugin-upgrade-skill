# S16 · The Self-Host Upgrade Trap — Report

## Incident summary

A user asked an agent running inside a `dsh web` session (host process =
`node .../node_modules/@deepseek-ai/dsh/...`, GUI at http://127.0.0.1:3080) to
"update dsh to v0.1.2-rc.1". The agent checked release notes, then ran
`npm install -g @deepseek-ai/dsh@0.1.2-rc.1` as a pwsh tool call from inside that
session. Mid-install (between `linkStuff` and completion) the web GUI lost connection,
the host process died, the tool call never returned a result, and afterwards the `dsh`
command itself was gone. An external repair session re-ran the formal install, which
regenerated the shims and restored the CLI.

## 1. Structural root cause — why this fails by construction

The failure is architectural, not flaky:

- **The session is the upgrade target.** The agent, its session, and the pwsh tool
  worker all live inside the running dsh host process, whose code is loaded from the
  very `node_modules/@deepseek-ai/dsh` directory the global npm install replaces.
  The session is not a bystander observing the upgrade; it is the running instance of
  the package being replaced.
- **The tool worker is a child of the victim.** The pwsh call executes as a worker
  spawned and supervised by the host process. npm's sequence makes the collision
  inevitable: `cleaning node_modules/@deepseek-ai/dsh` → `remove @deepseek-ai/dsh`
  (the log at 16:41:02–16:41:05) deletes/replaces the package content and the shims
  while the host process still has modules, the CLI entry, and its supervisor
  relationships rooted in that tree. On Windows, replacing files backing a running
  process and its global shims kills or breaks the host; here the host died mid-call
  (GUI "connection lost").
- **Why no tool result was recorded.** The result path — worker exits, host captures
  output, host writes a durable result event to the session log — runs through the host
  process that was the casualty. When the host died mid-call, the call had been recorded
  as started but its outcome could never be durably recorded, hence "<no result
  recorded … outcome unknown>". The interruption is a direct consequence of the actor
  destroying its own container, so retrying or waiting longer could never succeed.

## 2. The broken state afterwards

From `env-state.txt` and the post-mortem shell output:

- **Content present, command gone.** `node_modules\@deepseek-ai\dsh\` still exists
  (with rc.1 files), but `dsh.cmd` and the extensionless `dsh` shim are MISSING and
  `dsh.ps1` is stale, pointing into the old tree. On Windows, a global npm command is
  usable only through those shims in `%APPDATA%\npm` (which is on PATH); npm creates
  them in the `linkStuff`/bin-linking phase, which never completed because the install
  died after `linkStuff` started but before shim generation finished. Package content
  without shims = a `dsh` directory PowerShell cannot invoke → "command not found",
  even though the code is on disk.
- **Why hand-swapping directories makes it worse.** The evidence shows the user's
  partial manual repair (directory swapped by hand) left a **non-standard install**: rc.1
  content mixed with a `dsh-old-0.1.1-rc.1` backup and stale shims. A npm global
  install is more than a directory of files — it is a consistent tuple of (package
  content + version metadata + generated `dsh`/`dsh.cmd`/`dsh.ps1` shims + npm's own
  install bookkeeping). Hand-patching any one element desynchronizes the rest: stale
  `dsh.ps1` resolves into a tree that no longer matches, partial content may mix
  versions, and npm's metadata no longer describes what's on disk, so future
  installs/upgrades start from a corrupted baseline. The repair notes' verdict is
  explicit: only re-running the formal install from the registry produces a state npm
  itself considers valid.

## 3. The repair actually applied, and why it works

The external repair session (a different agent CLI, running **outside** dsh):

1. **Re-ran the formal install from the registry**:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`. Because it ran from a process with no
   dependency on the dsh tree, npm could complete its full lifecycle — remove/replace
   content, then generate all three shims (`dsh`, `dsh.cmd`, `dsh.ps1`). Verified:
   `dsh --version -> 0.1.2-rc.1`. This works precisely where the in-session attempt
   could not: the replacing process is not itself backed by the replaced files, so
   nothing dies mid-link.
2. **Aligned the source checkout** used for host-source reference from the alpha.5 tag
   to `dsh-v0.1.2-rc.1` (no local-modification conflicts).

Verification recorded: shim regeneration + `dsh --version` output; diff evidence
(alpha.5→rc.1 = 252 files, all `package.json` version bumps, zero API changes) that no
plugin re-migration is needed; real-machine checks (start `dsh --profile web`,
hard-refresh browser, confirm plugins load) left to the user, plus optional cleanup of
`dsh-old-*` backups once rc.1 is confirmed.

## 4. The protocol the agent should have followed

**Self-recognition.** The agent should have recognized that it was executing inside the
running dsh host process — i.e., that it *is* an instance of the upgrade target — and
that a global install of `@deepseek-ai/dsh` is a self-host replacement. No in-session
tool call can perform that replacement safely: the actor, its worker, and the result
recording all depend on the files being replaced.

**Should it execute the global install at all? No.** Self-upgrade of the host that is
running the agent is exactly the boundary between "do it for the user" and "hand the
user a procedure you must not execute yourself". The correct output is the external
procedure, not the command.

**The external procedure (order matters):**

1. **Stop the host first**: close the `dsh web` session/host process (and any other
   running dsh instances) so nothing on the machine is executing from the global
   `node_modules/@deepseek-ai/dsh` tree. This must happen *before* npm runs — a running
   host is what turns the install into a self-kill on Windows.
2. **From a fresh external shell** (plain PowerShell, not inside any dsh session), run
   the exact formal install:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`
   It must be the plain registry install — not directory swapping, not copying over the
   old tree — because only npm's full lifecycle regenerates the `dsh`/`dsh.cmd`/`dsh.ps1`
   shims and keeps content + shims + metadata consistent.
3. **Verify**: `dsh --version` → 0.1.2-rc.1, then `dsh --profile web` and a browser
   hard-refresh.
4. Optional cleanup of `dsh-old-*` backups after confirmation.

**Known vs. new.** The "use the formal `npm install -g` from the registry; don't patch
trees by hand" rule already follows from known upgrade rules (never hand-swap package
directories; repair by re-running the installer). The part that is **new for this
incident** is the ordering constraint *specific to self-hosting*: the dsh host running
the agent must be stopped **before** npm executes, and the agent must never be the one
to run the install — it must hand the procedure to the user and end its own session as
step 1, because running the install from inside the session is structurally
self-destructive.

## 5. Prevention

**Agent-side guard.** Before executing any install/upgrade command, the agent (or a
guard plugin wrapping shell/subprocess tools) should:

- Detect the **self-reference**: compare the install target (`@deepseek-ai/dsh`,
  global) against the running host's own package — e.g. the process's module paths or an
  exposed runtime identity (`dsh --version` / host package info). Match ⇒ refuse the
  in-session execution and emit the external procedure instead.
- More generally, refuse tool calls that modify the files backing the current host
  process (global npm tree of `@deepseek-ai/dsh`, its shims in `%APPDATA%\npm`)
  while that host is running.
- Since the tool result path also depends on the host, the guard belongs *before*
  execution — a mid-flight rescue is impossible by construction.

**Post-upgrade checklist for this machine (given the alpha.5→rc.1 findings):**

- `dsh --version` reports 0.1.2-rc.1 and all three shims (`dsh`, `dsh.cmd`, `dsh.ps1`)
  are present and non-stale in `%APPDATA%\npm`.
- Start `dsh --profile web`, hard-refresh the browser, confirm the GUI connects and
  plugins load (whale / progress / etc.).
- Because the alpha.5→rc.1 diff is 252 files of pure `package.json` version bumps and
  zero API changes: **no plugin re-migration** is needed — verify one or two migrated
  plugins load normally rather than re-running migration.
- Align any host-source-reference checkout to the `dsh-v0.1.2-rc.1` tag (done in
  repair; confirm no drift).
- Clean up the `dsh-old-*` backup directories once rc.1 is confirmed working.
- Confirm no half-swapped residue from the manual repair attempt remains (the tree
  matches a standard install).
