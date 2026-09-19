# S16 · The Self-Host Upgrade Trap — Analysis Report

Task: explain, from the read-only evidence pack in the fixture, why an in-session global
`dsh` upgrade fails structurally, what state it left, how it was repaired, and what the
agent should have done instead. Methodology: `plugin-upgrade` skill (Mode A read-only
diagnosis; the skill's "Global DSH host upgrades (agent discipline)" section is the
governing rule). No files outside the report directory were written; the fixture is
untouched.

---

## 1. Structural root cause — failure by construction, not by accident

The requesting agent ran inside a `dsh web` session, and a session **is** the host
process: the node process whose executable tree is
`...\node_modules\@deepseek-ai\dsh\...` (session log header). The `pwsh` tool call
executed in a worker **of that host**. So the upgrade had this topology:

- **The thing npm was replacing = the thing doing the replacing.** `npm install -g` on
  Windows rewrites the global package in place: the log shows `npm warn cleaning
  node_modules/@deepseek-ai/dsh` (16:41:02) then `npm info remove @deepseek-ai/dsh`
  (16:41:05). From those first seconds, the running host's own module files — the code
  mid-execution, plus everything the tool worker and the GUI's RPC path depend on — were
  deleted out from under the live process.
- **What dies first:** the host process and its web GUI. The browser tab lost connection
  between 16:41:09 (`fetch`) and 16:41:31 (`linkStuff`) — i.e., during the middle of the
  install, exactly when removed native/JS content was being touched or shim regeneration
  had not yet happened. A running host also holds native-module file locks (EBUSY
  candidates), which makes a clean completion even less likely on Windows.
- **Why the tool call never returned:** the tool result is recorded by the host's session
  machinery — the same process npm was dismantling. The host died before the subprocess
  finished (or before its output could be persisted), so the call was interrupted after
  being recorded but no result was durably recorded; its outcome is unknown to the log.

This is not flakiness or a timeout: any ordering of "remove the running process's own
package tree" kills the process. The skill states it directly: a global host upgrade run
from inside a session on that host is *structurally fatal*, and a crash during the
upgrade is a signature of doing it wrong, not a risk to tolerate.

## 2. The broken state afterwards

Machine state after (env-state.txt / session log):

- The **package content was still present** — rc.1 files in
  `node_modules\@deepseek-ai\dsh` (partially replaced mid-install, later also touched by
  the user's manual swap attempt), plus a `dsh-old-0.1.1-rc.1` backup directory.
- Yet `dsh`, `dsh web`, even `dsh --version` → *command not found*.

Why the command vanished while content survived: a global npm install is two distinct
steps — (a) place package content, (b) **generate the launch shims** (`dsh`,
`dsh.cmd`, `dsh.ps1`) in `%APPDATA%\npm`. The log died in the middle: content
removal/fetch/link happened (`linkStuff` at 16:41:31) but shim regeneration either never
ran or half-ran. The after-state confirms it precisely: **`dsh.cmd` and the extensionless
`dsh` are MISSING; `dsh.ps1` is stale, still pointing into the old tree**. Content
without shims = an unusable CLI. This is the classic interrupted-install signature:
package present, install non-standard, launcher gone.

Why hand-repair by swapping/patching directories makes it worse:

- Copying package directories or hand-writing shims produces a **non-standard install**
  that no tool can reason about — version identity, file completeness, and npm metadata
  no longer agree (the repair notes found exactly this: "replaced/manually swapped"). A
  stale `dsh.ps1` pointing into the old tree can even execute the *wrong* version while
  reporting another.
- It risks mixing cohort versions (old native addons with new JS, or alpha.5 leftovers
  beside rc.1 files), which produces runtime failures far harder to diagnose than a
  missing command.
- The skill's rule is explicit: repair an interrupted install **only** by re-running the
  pinned formal install from an external shell — never hand-copy package directories or
  hand-write shims.

## 3. The repair actually applied, and why it works

From repair-notes.md:

1. **Re-ran the formal install from the registry, externally:**
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`. This regenerated
   `dsh` / `dsh.cmd` / `dsh.ps1` and normalized the package directory;
   `dsh --version → 0.1.2-rc.1`.
2. Aligned the host-source-reference workspace checkout from the `dsh-v0.1.2-alpha.5`
   tag to `dsh-v0.1.2-rc.1` (no conflicts).

Why this form succeeds where the in-session attempt could not:

- It runs **with the host fully stopped**, so nothing executes from the tree npm is
  rewriting and nothing holds file locks. All npm's phases — remove, fetch, link,
  **shim generation** — complete. The in-session attempt could never let the last phase
  run because its own executor was deleted first.
- Re-running the pinned formal install (rather than patching) restores the single
  standard state npm itself defines, overwriting whatever non-standard mixture the
  interrupted install and the user's manual swap left behind.

Verification of the result: shims present, `dsh --version` reports rc.1; plus the
left-for-user runtime checks — start `dsh web` (the notes say `dsh --profile web`),
hard-refresh the browser, confirm plugins load, and only then optionally clean up the
`dsh-old-*` backups.

## 4. The protocol the agent should have followed

**Recognition.** The agent should have noticed that its own runtime identity — the node
process serving the GUI at 127.0.0.1:3080 and its tool worker — *is* the upgrade target.
Upgrading `@deepseek-ai/dsh` globally is not plugin work (Mode B/C) at all; the skill
carves it out as a separate class with its own discipline.

**Should it execute the install?** No — never from inside a session on that host. The
correct behavior is the boundary between "do it for the user" and "hand the user a
procedure you must not execute yourself": the agent's job ends at a read-only impact
assessment (Mode A: current alpha.5 → rc.1, diff shows pure version bumps, zero plugin
re-migration) plus the external procedure.

**The external procedure (order matters):**

1. **Fully stop every dsh process first** — the running host holds native-module file
   locks (EBUSY), and a browser refresh is *not* a host stop.
2. From an **external terminal** (no dsh session involved), run the **pinned** install:
   `npm install -g @deepseek-ai/dsh@0.1.2-rc.1`. The version must be explicit: a bare
   `npm install -g @deepseek-ai/dsh` resolves the `latest` dist-tag and can silently
   downgrade to an older line (indeed, at the rc.2-era the `latest` tag still pointed at
   rc.1 — tag drift is real on this channel).
3. Restart `dsh web`, hard-refresh the browser, verify version markers and that plugins
   load.

**Which parts are known rules vs new for this incident:** steps 1–3 in their exact order,
the pinned-version requirement, and the never-from-inside-a-session prohibition all
follow directly from the skill's established global-upgrade rules. What is incident-
specific (new): the **recovery half** — recognizing the interrupted-install signature
(content present, shims missing/stale, `dsh` gone) and repairing it by re-running the
pinned formal install from an external shell while refusing directory swaps or hand-made
shims, including cleaning up the user's manual partial repair before trusting the tree.

## 5. Prevention

**Agent-side guard.** Intercept any tool call that would modify the running host's own
install — pattern: `npm(-related) install/uninstall/link` targeting `@deepseek-ai/dsh`
(or any write into the global tree the current process executes from), plus filesystem
writes into `%APPDATA%\npm\node_modules\@deepseek-ai\dsh*` or its shims. On hit, the
guard should refuse execution and emit the external procedure above. Cheap heuristics
that help: detect "the resolved real path of my own `process.execPath`/import tree lies
under the target path" (self-upgrade detection), and detect the interrupted-install
signature (package dir present + shims absent) to answer repair requests with "external
pinned re-install", never with manual patching.

**Post-upgrade checklist for this machine** (given the alpha.5→rc.1 findings):

- Corridor impact: alpha.5 → rc.1 diff = 252 files, **all package.json version bumps,
  zero API/feature changes** — plugins already migrated for 0.1.2-alpha.x need **no
  re-migration**; do not invent migration work.
- Verify install standardness: `dsh`, `dsh.cmd`, `dsh.ps1` all regenerated and
  coherent; `dsh --version → 0.1.2-rc.1`.
- Runtime: restart `dsh web`, hard-refresh the browser, confirm plugins load
  (whale / progress / etc.).
- Source reference: workspace checkout aligned to the `dsh-v0.1.2-rc.1` tag (done in the
  repair); keep it in sync so future version checks read the right source.
- Housekeeping: only after rc.1 is confirmed working, optionally delete the
  `dsh-old-*` backup directories (including `dsh-old-0.1.1-rc.1` seen in the log) so
  a stale `dsh.ps1` can never resolve into a dead tree again.
- Guard against tag drift on any future upgrade: always pin the exact version; check
  which dist-tag (`latest`/`next`) carries the target before handing over the command.

---

*Sources: fixture `agent-session-log.txt`, `env-state.txt`, `repair-notes.md`,
`README.md`; `plugin-upgrade` SKILL.md ("Global DSH host upgrades (agent
discipline)", Mode A/B/C, safety boundaries, validation) and its references
(`references/v0.1.2-rc.1.md` — zero-card pure version bump; `references/v0.1.5-rc.2.md`
— `latest` dist-tag drift note).*
