# S16 · The Self-Host Upgrade Trap — Diagnostic Report

Evidence pack (read-only): `fixture/README.md`, `fixture/agent-session-log.txt`, `fixture/env-state.txt`, `fixture/repair-notes.md`.

## 1. Structural root cause: the agent replaced its own foundation while standing on it

The session log header states the setup explicitly: the agent session was 'running inside a dsh web session, GUI at http://127.0.0.1:3080, host process = node .../node_modules/@deepseek-ai/dsh/...'. The session and its tool worker are not adjacent to the upgrade target — they ARE processes loaded from the exact package tree that `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` was replacing.

Sequence from `agent-session-log.txt`:

- `[16:41:02] npm warn cleaning node_modules/@deepseek-ai/dsh` — npm begins deleting the running host's own code from underneath it.
- `[16:41:05] npm info remove @deepseek-ai/dsh`, `[16:41:09] npm info fetch @deepseek-ai/dsh@0.1.2-rc.1`, `[16:41:31] npm info linkStuff ...` — removal proceeds; then the log records: 'at this point the web GUI session DIED (browser tab: connection lost)'.

What dies first: the running dsh host process. As npm removes and rewrites files in its own node_modules directory, the host — and with it the web GUI, the agent session, and the tool worker executing the install — is destroyed or fatally disrupted. The tool call never returned a result because the component that would produce and durably record the result, the host's tool worker, was itself the casualty: the log records `[tool result] <no result recorded — the tool call was interrupted after it was recorded, but no result was durably recorded. Its outcome is unknown.>`.

This fails by construction, not by accident: a global npm install of the package that hosts the executing agent necessarily deletes the agent's own runtime mid-execution. No retry, timeout tuning, or extra care inside the session changes the outcome — the agent cannot survive replacement of the process it lives in. It is a self-reference trap whose collateral is the host process itself.

## 2. The broken state: content present, install non-standard, command dead

From `env-state.txt` (AFTER) and the shell checks at the bottom of the session log:

- `dsh --version` and `dsh web` return 'The term \'dsh\' is not recognized as the name of a cmdlet, function, script file, or operable program file.' — the command entry points are gone.
- Shims in `$env:APPDATA\npm`: `dsh.ps1` present but 'stale, points into the old tree'; `dsh.cmd` MISSING; `dsh` MISSING.
- Package tree: `node_modules\@deepseek-ai\dsh\` is 'present, partially replaced'; `env-state.txt` says rc.1 package CONTENT is present but 'NOT a standard install — the directory had been replaced/manually swapped ... during a partial manual repair attempt by the user'. A `dsh-old-0.1.1-rc.1` backup directory also sits in the tree.

Why the command vanished though content remains: the shell-visible 'dsh command' is not the package directory — it is the set of bin shims that npm generates only at the link stage. The install was killed around `linkStuff`, so the shims were removed or never regenerated; `dsh.ps1` survives only as a stale pointer into the old, half-deleted tree. A directory full of package files with no bin links is inert to the shell.

Why hand-swapping/patching makes it worse: the user's manual directory swap already produced a non-standard tree (per `repair-notes.md`: 'the directory had been replaced/manually swapped, and the dsh / dsh.cmd shims were never generated') that no longer matches what a registry install lays down — unknown file provenance, no shims, leftover `dsh-old-*` siblings. Hand-patching cannot correctly regenerate npm's bin links or guarantee file integrity; it deepens divergence from a canonical install and leaves a tree that npm may not cleanly upgrade or uninstall.

## 3. The repair: re-run the formal registry install from outside dsh

`repair-notes.md` records what the external repair session (a different agent CLI, run outside dsh) actually did:

1. **Repaired the shims by RE-RUNNING the formal install from the registry**: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` → 'dsh / dsh.cmd / dsh.ps1 all regenerated; dsh --version -> 0.1.2-rc.1'. This works where the in-session attempt could not because it runs in a process outside the dsh host — nothing being replaced is executing it, so npm completes removal, reinstall, and bin-link generation uninterrupted. It also supersedes the hand-swapped directory with a canonical registry install instead of trusting the user's manually placed files.
2. **Aligned the source checkout** (used for host-source reference) from the alpha.5 tag to the `dsh-v0.1.2-rc.1` tag, with 'no local-modification conflicts'.

Key finding in the notes: diff `dsh-v0.1.2-alpha.5..dsh-v0.1.2-rc.1` = 252 files, ALL package.json version bumps, zero API/feature changes — plugins migrated for 0.1.2-alpha.x need no re-migration.

Verification: immediate verification was `dsh --version` → `0.1.2-rc.1` plus all three shims regenerated. The notes explicitly leave real-machine verification to the user: start `dsh --profile web`, hard-refresh the browser, confirm plugins load (whale / progress / etc.), then optionally clean up the `dsh-old-*` backups.

## 4. The protocol the agent should have followed

**Recognition:** from its own runtime context, the agent should have recognized it was a dsh web session running INSIDE the dsh host process, and that the upgrade target `@deepseek-ai/dsh` in the global npm tree is exactly the package its host runs from. Self-upgrading the running host is structurally impossible from inside; the conclusion 'I must not execute this install' comes before any command is attempted.

**Should it execute the global install? No.** The discipline boundary is: hand the user a procedure, do not run it yourself. The exact external procedure (order matters):

1. **Before npm runs:** stop the running dsh host and close the web GUI sessions, so nothing is executing from the tree npm will replace (in-flight session work ends with it). Note the target version, 0.1.2-rc.1.
2. **The install command:** from a normal shell OUTSIDE any dsh process, run the plain formal registry install: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`. It must be the registry install — not a directory swap or hand-patched shims — because only npm's link stage regenerates the `dsh`, `dsh.cmd`, and `dsh.ps1` shims that make the command exist; those were exactly what the interrupted install left missing.
3. **After:** verify `dsh --version` → `0.1.2-rc.1`; start `dsh --profile web`, hard-refresh the browser, confirm plugins load; then optionally remove `dsh-old-*` backups.

Known rules vs. new: using the formal registry install rather than hand swaps, and verifying the version afterward, are standard upgrade discipline (the repair notes apply exactly these). What is new in this incident is the self-host boundary itself: when the upgrade target contains the running agent's own host process, the agent must not execute the install at all, and the procedure it hands over must begin with shutting the host down before npm runs.

## 5. Prevention

**Agent-side guard:** a pre-flight check before any package-manager operation that mutates `@deepseek-ai/dsh` (or the global npm prefix generally): compare the install target with the package the current host process is loaded from (host process path contains `node_modules/@deepseek-ai/dsh/...`, per the session-log header). On match, refuse to run the install, explain the structural self-replacement hazard, and emit the §4 external procedure for the user. More generally: any operation whose target tree contains the current process's own executable/module path is a self-mutation and must be delegated to the user, never executed in-session.

**Post-upgrade checklist for this machine:**

- `dsh --version` reports `0.1.2-rc.1`.
- All three shims (`dsh`, `dsh.cmd`, `dsh.ps1`) exist and none is stale — the incident's signature failure was missing `dsh`/`dsh.cmd` plus a stale `dsh.ps1` pointing into the old tree.
- `dsh --profile web` starts; the GUI at http://127.0.0.1:3080 loads after a hard refresh; plugins load (whale / progress / etc.).
- No re-migration needed: per the repair notes, alpha.5→rc.1 is 252 files, all version bumps — plugins already migrated for 0.1.2-alpha.x carry over unchanged.
- The global tree is a standard registry install (no hand-swapped directories); clean up the `dsh-old-*` backup directories only after rc.1 is confirmed working.
- Source checkout (if used as host-source reference) aligned to the `dsh-v0.1.2-rc.1` tag.