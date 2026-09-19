# S16 · The Self-Host Upgrade Trap — Analysis Report

**Task:** S16-self-host-upgrade-trap (read-only incident analysis)  
**Skill applied:** `plugin-upgrade` (Mode A · inspect — read-only; the skill's "Global DSH host upgrades (agent discipline)" section is the governing rule set for this incident class)  
**Evidence:** `environment/fixture/` — `agent-session-log.txt`, `env-state.txt`, `repair-notes.md` (read-only, unchanged)  
**Corridor reference:** `references/v0.1.2-rc.1.md` (alpha.5 → rc.1, cardCount: 0)

---

## 1. Structural root cause: the failure is by construction, not by accident

The session, its agent, and the tool worker executing the `pwsh` call are all **parts of the thing npm was replacing**. The evidence records the topology explicitly: the host process is `node .../node_modules/@deepseek-ai/dsh/...`, the web GUI at `http://127.0.0.1:3080` is served by that process, and the agent session runs *inside* it — the `pwsh` tool call ran "inside the host's own worker process."

So when the agent invoked `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`:

- The install target and the install *executor* were the same file tree. npm's global install of an existing package first removes the old copy (log: `npm warn cleaning node_modules/@deepseek-ai/dsh` → `npm info remove @deepseek-ai/dsh`). The moment npm deletes/replaces the host's own `node_modules\@deepseek-ai\dsh` directory, it pulls the rug out from under the running `node` process: modules already loaded may survive in memory briefly, but the process's file backing, resolution root, and any lazily-required module are gone or half-replaced. The host (and with it the web GUI, the session, and the in-flight tool worker) dies mid-install — between `linkStuff` (16:41:31) and shim regeneration.
- The tool call never returned a result **because the thing that would have recorded the result no longer existed**. The session log's verdict is precise: the call was recorded as started, but "no result was durably recorded. Its outcome is unknown." The tool result has to travel worker → host process → session log; when the host process is the casualty of the command itself, there is no recorder left to durably log an outcome. This is not a timeout or a flaky kill — the observer was destroyed by the observation.
- This is why the skill calls an in-session global host upgrade "structurally fatal": there is no ordering, retry, or timeout that makes it work. The session *is* the host process; npm removes/replaces the very package tree it executes from. A crash during the upgrade is "a signature of doing it wrong, not a risk to tolerate."

## 2. The broken state afterwards: package content present, command gone

Reading the interrupted-install signature from `env-state.txt` and the log:

- **Why `dsh` vanished while package content remained:** a Windows npm global install is two phases — (a) fetch/unpack the package content into `%APPDATA%\npm\node_modules\@deepseek-ai\dsh`, then (b) generate the command shims (`dsh`, `dsh.cmd`, `dsh.ps1`) in `%APPDATA%\npm`. The log died at `linkStuff` — after content placement had begun but **before shim regeneration**. The after-state confirms the exact signature: `node_modules\@deepseek-ai\dsh\` present but "partially replaced", `dsh.cmd` **MISSING**, `dsh` missing, `dsh.ps1` **stale** (still pointing into the old tree, which npm had rotated out to `dsh-old-0.1.1-rc.1`). The CLI entry points are the shims, not the directory; with them absent or dangling, `dsh` is "not recognized" even though rc.1 files sit on disk.
- **The user's partial manual repair made it worse:** `env-state.txt` records "some placed by hand during a partial manual repair attempt", and the repair notes classify the result as a **NON-STANDARD install** — a hand-swapped directory is not a state npm or any package script produced, so its layout, bin bindings, and integrity are unverified; copying files creates no shims, and the stale `dsh.ps1` pointing into a rotated-out backup tree would — if it resolved at all — execute an undefined mixture of old and new code. The skill's rule is explicit: after an interrupted install, "repair from an external shell by re-running the pinned formal install (never hand-copy package directories or hand-write shims)." Hand-patching also destroys the evidence trail npm needs to treat the tree as owned, so a later formal install has to overwrite guesses instead of starting from a known state.

## 3. The repair actually applied, and why it works

Per `repair-notes.md`, the external repair session (a *different* agent CLI, running outside dsh) did:

1. **Re-ran the formal, pinned install from the registry:** `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`. Because the executor was an external process with no dependency on the dsh tree, npm could complete both phases: content placement **and** shim regeneration → `dsh`, `dsh.cmd`, `dsh.ps1` all regenerated; `dsh --version` → `0.1.2-rc.1`. This works precisely where the in-session attempt could not: nothing executing the install dies when the old tree is removed. It also heals the non-standard hand-swapped state by letting npm replace the tree authoritatively rather than reconciling with it.
2. **Aligned the source checkout** (the host-source reference workspace) from the alpha.5 tag to `dsh-v0.1.2-rc.1`; no local-modification conflicts.

**Verification of the result:** shim presence + `dsh --version → 0.1.2-rc.1` (wrapper layer); the notes leave to the user the runtime/behavior layers — start `dsh --profile web`, **hard-refresh the browser** (the old GUI tab is a dead connection to a dead process), and confirm plugins load (whale / progress / etc.). That maps onto the skill's validation ladder (enablement → runtime cold-start → behavior) and its checklist step "restart `dsh web`, hard-refresh the browser, verify version markers and plugins." Optional follow-up: clean up the `dsh-old-*` backup directories once rc.1 is confirmed.

## 4. The protocol the agent should have followed

**What the agent should have recognized:** the upgrade target (`@deepseek-ai/dsh` global install) is *itself*. The session, the tool worker, and the GUI are all runtime components of the running host. Recognizing that relationship immediately converts "update dsh" from an executable task into a hand-off: per the skill, "Never execute the global host upgrade from inside a session on that host; hand the user the external procedure." This is a hard agent-discipline boundary — not "do it for the user," but "hand the user a procedure you must not execute yourself." Checking release notes (which the agent did do) is fine; executing the install is the one forbidden action.

**The external procedure to hand the user (order matters):**

1. **Fully stop every dsh process before npm runs** — the host, the web GUI, all sessions. A running host also holds native-module file locks (Windows → `EBUSY`); a browser tab refresh or closing the tab is *not* a host stop.
2. **From an EXTERNAL terminal** (not a dsh session, not a tool worker), run the **pinned** install: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`. The explicit version is mandatory: a bare `npm install -g @deepseek-ai/dsh` resolves to whatever the `latest` dist-tag currently is, which can silently land on an older line (the rc.1 corridor card measured `latest` moving between `0.1.1-rc.2` and `0.1.2-rc.1` on consecutive days — channel drift is real for this package).
3. **Restart `dsh web`, hard-refresh the browser, and verify** version markers and that plugins load.

**Which parts follow from known rules vs. what is new for this incident:**

- *Already follows from the known upgrade rules:* the pinned-version requirement (dist-tag drift is a documented install-channel pitfall in the rollup/reference set), the stop-before-install discipline for file locks (`EBUSY` on native modules), the never-hand-copy/hand-write-shims repair rule, and the restart/hard-refresh/verify checklist — all pre-existing skill content for global host upgrades.
- *New / sharpened by this incident:* the structural framing that the **session IS the host process**, so the in-session global upgrade is fatal *by construction* — the tool result cannot even be durably recorded because the recorder is destroyed by the command. Previously the guidance targeted "a running host holds native-module file locks"; this incident shows the deeper failure mode: even with no lock conflict, the executor dies mid-install and leaves the signature seen here (content present, shims never generated). The agent-side corollary — recognize self-upgrade and refuse to execute, handing off instead — is the boundary this incident makes explicit.

## 5. Prevention

**Agent-side guard (this class of failure):** a pre-execution check on shell/install tool calls that recognizes the *self-host upgrade* pattern and refuses it:

- **Identity check:** the agent knows its own host process (`node .../node_modules/@deepseek-ai/dsh/...`) and the session's runtime context. A guard intercepts any command whose effect is to install/replace that package — pattern-matching `npm install -g @deepseek-ai/dsh*` (any package manager: npm/pnpm/bun/yarn global), plus any direct write into the host's own `node_modules\@deepseek-ai\dsh` tree or shim directory (`%APPDATA%\npm\dsh*`).
- **Behavior on hit:** refuse execution, explain the structural reason ("I am running inside the package you asked me to replace; the session and this tool call would not survive the install, and the interrupted install leaves the `dsh` command dead"), and emit the external procedure from §4 as the deliverable. Guarding against obvious equivalents matters too: re-running it in a sub-shell, backgrounding it, or `npm rebuild` against the live tree are the same failure.
- **Why refuse rather than warn:** the skill classifies this as "structurally fatal" — there is no safe in-session variant, so a confirmation prompt only creates a slower path to the same crash.

**Post-upgrade checklist for this machine (given the alpha.5→rc.1 findings):**

1. **Version markers:** `dsh --version` → `0.1.2-rc.1`; all three shims (`dsh`, `dsh.cmd`, `dsh.ps1`) present and fresh.
2. **Runtime cold-start:** start `dsh web` (or `dsh --profile web`), hard-refresh the browser, confirm the GUI connects.
3. **Plugin fleet:** confirm plugins load (whale / progress / etc.) and that required/provided Cordis services activate rather than staying pending.
4. **No plugin re-migration needed — evidence:** the repair notes' key finding matches the corridor card `v0.1.2-rc.1.md` exactly: diff `dsh-v0.1.2-alpha.5..dsh-v0.1.2-rc.1` = 252 files, **all `package.json` version bumps, zero API/feature changes** (cardCount: 0). Plugins already migrated to any 0.1.2-alpha.x land on identical code at rc.1; no corridor work remains for this edge. (Conversely, any plugin still on ≤0.1.1-rc.2 must follow the full corridor chain rc.2→alpha.1→…→alpha.5→rc.1.)
5. **Source checkout alignment:** the host-source reference workspace is on the `dsh-v0.1.2-rc.1` tag (repair step 2) — verify it stays aligned so future reference/inspection matches the installed host.
6. **Cleanup:** once rc.1 is confirmed healthy, remove the `dsh-old-*` backup directories; they also represent stale-artifact risk (a stale `dsh.ps1` pointing into a backup tree is what made the CLI unusable).
7. **Re-run a message → tool → response flow** through the new host to prove the session/worker plumbing end-to-end after the reinstall.

---

## Self-check against the task's tested criteria

- **Structural (not flaky) failure:** §1 — session/worker are components of the host process npm replaces; the host dies first; no durable result recorder survives.
- **Interrupted-install signature:** §2 — died at `linkStuff` after content placement, before shim generation → content present, `dsh`/`dsh.cmd` missing, `dsh.ps1` stale; hand-swapping creates a non-standard install and is worse.
- **Correct repair + justification:** §3 — external pinned formal re-install regenerates shims and heals the hand-swapped tree; verified via version, cold-start, hard-refresh, plugin load.
- **Agent-discipline boundary:** §4 — recognize self-relationship, never execute, hand off the ordered external procedure with a pinned version; known-rule vs. new-for-this-incident split stated.
- **Prevention + checklist:** §5 — agent-side self-upgrade guard pattern; checklist grounded in the alpha.5→rc.1 zero-card finding (version bumps only, no re-migration).

**Note on evidence paths:** the brief references `/app/fixture/`; the actual read-only fixture resides at `E:\deepseek-harness\dsh-plugin-upgrade-skill\benchmark\tasks\S16-self-host-upgrade-trap\environment\fixture\` and was used unchanged. No files inside the fixture or benchmark repository were modified; the only write is this report.
