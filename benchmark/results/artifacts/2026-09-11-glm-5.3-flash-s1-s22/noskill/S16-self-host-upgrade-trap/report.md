# S16 Diagnostic Report · The Self-Host Upgrade Trap

Evidence pack: fixture/README.md, fixture/agent-session-log.txt, fixture/env-state.txt, fixture/repair-notes.md (read-only).

## 1. Structural root cause

The agent session runs *inside* the thing the upgrade replaces. The session log states it explicitly: "the AGENT (running inside a dsh web session, GUI at http://127.0.0.1:3080, host process = node .../node_modules/@deepseek-ai/dsh/...)". The session's tool worker (the pwsh tool call) is a child of that same host process, whose executable code lives in the npm global tree `node_modules/@deepseek-ai/dsh` — exactly the directory `npm install -g` tears down and rewrites.

So the failure is by construction, not flakiness:

- npm began removing the running host's own code at 16:41:02–16:41:05 ("npm warn cleaning node_modules/@deepseek-ai/dsh", "npm info remove @deepseek-ai/dsh"). Removing or replacing the files of a running Node process pulls the ground out from under it; the host died mid-install ("at this point the web GUI session DIED (browser tab: connection lost)").
- Because the tool worker is a child of that host, killing the host also killed the pending npm install and the worker that would have reported its outcome. The log records "[tool result] <no result recorded — the tool call was interrupted after it was recorded, but no result was durably recorded. Its outcome is unknown.>" — the caller was destroyed before the callee could finish, so a result could never be delivered.

## 2. Broken state afterwards

env-state.txt AFTER: "dsh web host -> dead", "dsh --version -> command not found", "dsh web -> command not found". Yet "npm global tree -> @deepseek-ai/dsh package CONTENT present (rc.1 files, some placed by hand during a partial manual repair attempt by the user), but NOT a standard install".

The command vanished because a global npm package is usable only through its bin shims. The new-shell check shows "dsh.ps1 <stale, points into the old tree>", "dsh.cmd <MISSING>", and `dsh` gone; env-state confirms "shims -> dsh.cmd and dsh MISSING; dsh.ps1 stale". npm generates the shims as a step of a formal install (linkStuff/bin linking) — the interrupted install died around "npm info linkStuff @deepseek-ai/dsh@0.1.2-rc.1" and never generated them, so package content without shims is dead weight.

Why hand-swapping makes it worse (repair-notes.md, "What we found"): "the directory had been replaced/manually swapped, and the dsh / dsh.cmd shims were never generated — so the dsh command was actually dead". A directory swap leaves a non-standard tree: stale shims pointing into an old tree, no bin links, no npm bookkeeping (a later formal install/npm update cannot reason about a tree it did not create), and — as this incident shows — the user's manual attempt still left the CLI unusable. It also risks re-running the same trap if attempted from anything that depends on dsh.

## 3. The repair that was applied

repair-notes.md, "What we did": an *external* agent CLI (outside dsh) "Repaired the shims by RE-RUNNING the formal install from the registry: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` -> dsh / dsh.cmd / dsh.ps1 all regenerated; dsh --version -> 0.1.2-rc.1".

This works where the in-session attempt could not because the installer process was no longer a child of the host it was replacing — nothing destroyed the installer mid-flight, so npm could complete removal, fetch, and bin-link generation, producing a standard install (real shims, real npm bookkeeping) instead of a hand-made tree. It also "Aligned the source checkout ... from the alpha.5 tag to the dsh-v0.1.2-rc.1 tag; no local-modification conflicts."

Verification: `dsh --version` returns 0.1.2-rc.1; the remaining checks are explicitly "Left for the user": "start dsh --profile web, hard-refresh the browser, confirm plugins load (whale / progress / etc.)", then "Optional cleanup of the dsh-old-* backup directories once rc.1 is confirmed".

## 4. The protocol the agent should have followed

Recognition first: the agent IS the host process's in-process session; its tool calls execute under the same node .../node_modules/@deepseek-ai/dsh install that a global upgrade deletes. Any in-session global install of @deepseek-ai/dsh is a self-replacement of the running host — it must not be executed by the agent, regardless of how it is launched (pwsh, bash, etc.).

Therefore: the agent should NOT run the global install at all. It should stop at analysis (release notes, target version, migration impact) and hand the user an external procedure to run from a shell with no dsh process running:

1. Before npm runs: stop all dsh processes — quit the web GUI session/host (close the GUI, kill the host process) so nothing executes code from the tree npm is about to replace. (env-state BEFORE shows "dsh web host -> running" with the "agent session -> active, executing INSIDE that host process"; that is precisely the state that must not exist during install.)
2. From an ordinary shell: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — a formal registry install, never a directory swap or shim hand-edit, because only the formal install regenerates dsh/dsh.cmd/dsh.ps1 and records the tree with npm.
3. After: `dsh --version` -> 0.1.2-rc.1, then start `dsh --profile web` and verify the GUI.

Which parts are known vs new: the upgrade discipline of reading release notes and checking migration impact before upgrading is a known upgrade rule, and repair-notes' key finding confirms its result here — "Diff dsh-v0.1.2-alpha.5..dsh-v0.1.2-rc.1: 252 files, ALL of them package.json version bumps. Zero API/feature changes. Plugins migrated for 0.1.2-alpha.x need no re-migration" — so no plugin re-migration was needed. What is NEW for this incident is the self-host boundary itself: the agent must classify the target as *the host it runs inside*, refuse to execute the install, and insert the "shut dsh down before npm runs" step as a hard precondition.

## 5. Prevention

Agent-side guard: before executing any install/upgrade command, the agent should resolve the target package and ask "is this package the dsh host I am currently running inside (matching the @deepseek-ai/dsh install path of my host process)?" If yes — refuse execution, emit the external procedure above (stop dsh first, then formal `npm install -g`), and never attempt directory swaps or shim patching. More broadly: any mutation of the runtime a tool call depends on (the host's own package, its node_modules, its shims) is a self-destructive operation and belongs to out-of-band execution by the user or an external tool.

Post-upgrade checklist for this machine (from repair-notes):

- Confirm the install is standard: `dsh --version` -> 0.1.2-rc.1; all three shims (dsh, dsh.cmd, dsh.ps1) present and consistent, no stale shims pointing into old trees.
- Runtime verification: start `dsh --profile web`, hard-refresh the browser at http://127.0.0.1:3080, confirm plugins load (whale / progress / etc.).
- Given the alpha.5→rc.1 finding (252 files, all version bumps, zero API changes): no plugin re-migration needed for anything migrated during 0.1.2-alpha.x — verify plugins load rather than re-running migrations.
- Only after rc.1 is confirmed: clean up the dsh-old-* backup directories (currently present in the npm global tree, per env-state and the session log).
- Verify the source checkout is aligned to the dsh-v0.1.2-rc.1 tag with no local-modification conflicts, as the repair notes did.
