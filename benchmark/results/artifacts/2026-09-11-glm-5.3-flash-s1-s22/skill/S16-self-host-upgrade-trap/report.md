# S16 · The Self-Host Upgrade Trap — Diagnostic Report

Evidence pack: fixture/README.md, agent-session-log.txt, env-state.txt, repair-notes.md (read-only). Skill applied: plugin-upgrade, "Global DSH host upgrades (agent discipline)" section.

## 1. Structural root cause

The agent session was not a bystander to the upgrade — it **was** the upgrade target:

- env-state.txt (BEFORE): "dsh web host -> running, GUI at http://127.0.0.1:3080"; "agent session -> active, executing INSIDE that host process". agent-session-log.txt confirms the tool call ran "inside the host's own worker process".
- The command `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` replaces the npm global package tree that the running host process is executing from. npm's own log shows the fatal step: "[16:41:05] npm info remove @deepseek-ai/dsh" — npm removed the package content out from under the live process, then "[16:41:31] npm info linkStuff @deepseek-ai/dsh@0.1.2-rc.1" — and "at this point the web GUI session DIED (browser tab: connection lost)".

What dies first: the host process itself, when the files backing its loaded/loaded-on-demand modules and its own worker tree are removed mid-execution. Because the tool worker is a child of that host, the worker dies with it, so "[tool result] <no result recorded — the tool call was interrupted after it was recorded, but no result was durably recorded. Its outcome is unknown.>" — the tool call could never return a result because the process responsible for producing and recording the result no longer existed.

This fails **by construction, not by accident**: any session-on-the-host attempting this replaces its own execution substrate mid-call. There is no timeout, retry, or error-handling path that helps; the failure is deterministic whenever the install actually touches the running tree. The plugin-upgrade skill states it exactly: "the session IS the host process, npm removes/replaces the very package tree it executes from, the host dies mid-install (the tool call never returns)".

## 2. The broken state afterwards

From env-state.txt (AFTER) and the post-mortem shell transcript in agent-session-log.txt:

- The **package content survived**: "node_modules\@deepseek-ai\dsh\ <present, partially replaced>" — npm had already fetched and linked much of rc.1 ("npm info fetch", "npm info linkStuff") before the host died.
- The **command vanished** because the CLI entry points are not part of the package directory — they are the npm-generated global **shims** in %APPDATA%\npm: `dsh`, `dsh.cmd`, `dsh.ps1`. The transcript shows `dsh.cmd` MISSING, and `dsh.ps1` "<stale, points into the old tree>"; both PATH lookups fail ("dsh : The term 'dsh' is not recognized..."). An interrupted install regenerates neither shims nor links, so content-present ≠ command-present.
- The tree is additionally **non-standard**: env-state.txt notes "some placed by hand during a partial manual repair attempt by the user... but NOT a standard install", plus a leftover dsh-old-0.1.1-rc.1 backup directory.

Why hand-swapping/patching directories makes it worse:

- A dropped-in directory has no regenerated shims, bin links, or lifecycle-script effects, so it cannot restore the command — exactly what the repair notes found ("the directory had been replaced/manually swapped, and the dsh / dsh.cmd shims were never generated").
- It leaves npm's bookkeeping (the global package database) pointing at a state that no longer matches disk, so the next real install starts from a corrupted, unknown baseline.
- Stale shims pointing into a dead tree produce confusing half-failures (the command resolves on some shells and not others).
- Skill rule: "never hand-copy package directories or hand-write shims" — the only owner of shim generation and install bookkeeping is the package manager performing a formal install.

## 3. The repair that was applied

repair-notes.md records the actual repair, performed by "a different agent CLI, run outside dsh":

1. **Re-ran the formal registry install from an external shell**: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`. This is the decisive step: it re-runs npm's complete install path — regenerating all three shims ("dsh / dsh.cmd / dsh.ps1 all regenerated") and restoring consistent install bookkeeping — instead of patching symptoms. It works where the in-session attempt could not because it ran from a shell that was **not itself a child of the package being replaced**; even if npm had removed the tree again, nothing executing from that tree would die mid-install, and the install would run to completion.
2. Aligned the source checkout from the alpha.5 tag to the dsh-v0.1.2-rc.1 tag (host-source reference workspace), with no local-modification conflicts.

Verification of the result:

- Immediate: `dsh --version -> 0.1.2-rc.1` (all shims regenerated).
- Left for the user as real-machine verification (repair-notes.md "Left for the user"): "start dsh --profile web, hard-refresh the browser, confirm plugins load (whale / progress / etc.)" — version marker alone is not acceptance; runtime composition and plugin activation must be observed, per the skill's validation layers (runtime cold-start, behavior path).
- Optional cleanup of dsh-old-* backups only "once rc.1 is confirmed".

## 4. The protocol the agent should have followed

**Self-recognition.** The agent should have recognized, before any command, that it runs *inside* the dsh host process it was asked to upgrade — the upgrade target and its own execution substrate are the same thing. The plugin-upgrade skill classifies a global host upgrade as **not Mode B/C plugin work at all**, and imposes the agent-discipline rule: "Never execute the global host upgrade from inside a session on that host". So the answer to "should it execute the global install?" is **no — unconditionally, not even with user confirmation**, because the failure is structural, not permission-gated. The correct deliverable is a hand-off procedure.

**Exact external procedure (order matters):**

1. **Before npm runs — fully stop every dsh process.** A running host holds native-module file locks (EBUSY risk) and would die mid-install again; the skill warns "a browser refresh is not a host stop" — closing the browser tab leaves the host alive.
2. From an **external terminal** (not a dsh tool call), run the **pinned install**: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — the exact version must be embedded in the command. A bare `npm install -g @deepseek-ai/dsh` resolves the `latest` dist-tag and "can silently downgrade to an older line".
3. Restart `dsh web`, **hard-refresh** the browser, and verify version markers and plugins.

Because the host is fully stopped before npm runs, "a crash during the upgrade is a signature of doing it wrong, not a risk to tolerate."

**Known rules vs. new for this incident:**

- Already follows from known upgrade rules (skill): pinned exact-version install (no bare dist-tag resolution), external execution context, stop-processes-first ordering, no hand-copied directories/shims, post-install verification of version markers and plugin activation.
- New for this incident: the **self-host discipline boundary itself** — that an agent running inside the host must never execute the global host upgrade, must not attempt directory-swap repairs on the broken install, and instead hands the user (or an external agent CLI) a procedure it deliberately cannot and must not run itself. Also incident-specific: recognizing the interrupted-install signature (content present, shims missing, no tool result recorded) as requiring the re-install repair rather than any in-place fix.

## 5. Prevention

**Agent-side guard.** A structural guard in the session/host layer:

- **Block the pattern at tool dispatch**, not by prompt: when a tool call originates from a session whose host is the npm-global `@deepseek-ai/dsh` install, and the command mutates that package (any `npm install -g @deepseek-ai/dsh…`, `npm uninstall -g`, `npm update -g` matching it, or pnpm/bun equivalents), refuse it with an explanatory message and emit the external procedure from §4 instead. (When DSH is launched from source rather than npm-global, the mutation target differs, so the guard keys off the resolved installation identity of the running host — consistent with the skill's rule to record source vs. installation identity separately.)
- **Self-reference detection**: the guard generalizes to "a process must not replace its own execution substrate" — flag any install/replace of the package that owns the currently running entry module.
- **Broken-state classifier**: on boot failure or missing-command reports, detect the interrupted-install signature (package directory present, shims absent/stale, npm bookkeeping inconsistent) and prescribe the external pinned re-install — never directory swaps or hand-written shims. The skill's ghost-host-check script is the analogous pre-flight classifier pattern.

**Post-upgrade checklist for this machine** (given the alpha.5→rc.1 findings):

- The corridor check is already answered by repair-notes.md's key finding: "Diff dsh-v0.1.2-alpha.5..dsh-v0.1.2-rc.1: 252 files, ALL of them package.json version bumps. Zero API/feature changes. Plugins migrated for 0.1.2-alpha.x need no re-migration" — consistent with the v0.1.2-rc.1 corridor card (zero plugin-facing cards, pure version bump). So no plugin source migration is on the checklist.
- Verify the install is standard, not the residue of the interrupted one: `dsh --version` reports 0.1.2-rc.1, and `dsh`, `dsh.cmd`, `dsh.ps1` all exist, are npm-generated (not hand-edited), and point at the rc.1 tree.
- Runtime acceptance: start `dsh --profile web`, **hard-refresh** the browser (the old page may hold a stale combo), confirm the GUI reconnects and **plugins actually load** (whale / progress / etc. from the repair notes) — install success is not enablement (skill Mode B step 5).
- Confirm the source-reference checkout is on the dsh-v0.1.2-rc.1 tag as the repair did, so future reference work reads rc.1 not alpha.5.
- Only after rc.1 is confirmed working: clean up the `dsh-old-*` backup directories (dsh-old-0.1.1-rc.1) left by the incident and the partial manual repair, and confirm no stray hand-placed files remain in the global tree.
- Record the incident protocol going forward: all future host upgrades follow the §4 external procedure, executed by the user or an external agent CLI, never from inside a dsh session.
