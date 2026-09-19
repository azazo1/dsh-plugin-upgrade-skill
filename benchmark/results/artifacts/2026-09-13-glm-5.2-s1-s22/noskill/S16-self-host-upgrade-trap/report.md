# S16 · The Self-Host Upgrade Trap — Report

Evidence: session log excerpt (`agent-session-log.txt`), machine state before/after (`env-state.txt`), external repair notes (`repair-notes.md`). All observations below are grounded in that pack.

## 1. Structural root cause

The agent's session, its tool worker, and the web GUI all lived **inside** the very process tree that npm was about to replace. The host was `node .../node_modules/@deepseek-ai/dsh/...` — i.e. the running dsh web host was executing from the global npm package directory that `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` targets. The pwsh tool call ran as a child worker of that host.

This fails by construction, not by accident:

- npm's global install of an existing package is not atomic. The log shows the sequence: `npm warn cleaning node_modules/@deepseek-ai/dsh` (16:41:02) → `remove` (16:41:05) → `fetch` (16:41:09) → `linkStuff` (16:41:31). The **remove/clean step deletes the old package content out from under the running host** while the host process still has modules loaded (or lazily loads them) from that tree.
- The host process and its worker are children of the thing being replaced. When npm removed the old tree, the host died mid-install — the browser tab lost connection at exactly that point. Whatever dies first, the tool worker is a descendant of it, so the `npm install` child process was killed/interrupted along with the host, before npm reached its shim-generation/bin-linking completion phase.
- The tool call "never returned a result" because the tool-result recording path runs through the same host/session that just died: the call was recorded as started, but no result could be durably recorded — the recorder itself was gone. From the agent's perspective the outcome is unknowable, which is itself the signature of a self-host upgrade: the observer cannot survive observing it.

## 2. The broken state afterwards

Why `dsh` vanished although the package content was still present:

- On Windows, a command is resolvable only through npm's **shims** in `%APPDATA%\npm`: `dsh`, `dsh.cmd`, `dsh.ps1`. The interrupted install died in/before the link phase: `dsh.cmd` and the extensionless `dsh` shim were **never regenerated** (npm removes/refreshes shims near the end of the operation), and `dsh.ps1` was left **stale**, pointing into the old tree. A PowerShell session resolves `dsh` via `dsh.cmd`/`dsh.ps1` — both gone/stale → "command not found", even though `node_modules\@deepseek-ai\dsh\` still held (partially placed, partly hand-patched) rc.1 content.
- The content directory itself was in a **non-standard state**: partially replaced by npm, then manually swapped/patched by the user, plus a `dsh-old-0.1.1-rc.1` backup directory. Package content without valid shims and a consistent layout is not a functioning install.

Why hand-swapping/patching directories makes it worse:

- npm's install state is more than files: it includes the shim trio, npm's own metadata (package-lock / `_modules` bookkeeping for the global tree), bin links, and content integrity. Manual directory swaps leave that metadata inconsistent — npm can no longer reason about what is installed, and a later formal install may refuse, "clean" the wrong thing, or duplicate backups. Hand-patching also mixes unknown provenance files (some rc.1 files placed by hand, some by npm) into one directory, so no version can be trusted. The user's partial manual repair attempt is exactly what turned "interrupted install" into "non-standard install that only an external tool can repair" (`env-state.txt` verdict).

## 3. The repair actually applied, and why it works

From `repair-notes.md`:

1. **Re-ran the formal install from the registry**: `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — from a *different* agent CLI running **outside** dsh. This regenerated `dsh`, `dsh.cmd`, `dsh.ps1`; `dsh --version` → `0.1.2-rc.1`. The re-install replaces the hand-mangled directory wholesale with a registry-verified tree, so shims, bin links, and content are consistent again. It works precisely because the executing process is *not* a child of the target install — nothing npm touches is load-bearing for the repair agent, so the install can run to completion. The in-session attempt could never have this property.
2. Aligned the source checkout (host-source reference workspace) from the alpha.5 tag to `dsh-v0.1.2-rc.1`; no local-modification conflicts.

Verification: `dsh --version` returns `0.1.2-rc.1`, all three shims present. Remaining verification left for the user on the real machine: start `dsh --profile web`, hard-refresh the browser, confirm plugins (whale / progress / etc.) load; optionally remove the `dsh-old-*` backups after rc.1 is confirmed.

## 4. The protocol the agent should have followed

**Self-recognition:** the agent must recognize that it *is* part of the upgrade target — its session, tool worker, and GUI are children of the global dsh install being replaced. Any command it runs is executed from inside the blast radius. Therefore it must **never execute the global install itself**; the correct behavior is the "hand the user a procedure" branch of agent discipline, not "do it for the user". It should say so explicitly: "I cannot upgrade the package I am running from; running the install from here would kill my own host mid-install."

**The external procedure to hand the user (order matters):**

1. **Stop the dsh host first** — exit `dsh web` / the GUI session and any running dsh processes — *before* running npm. This is the step that makes the upgrade safe: no process has modules loaded from the tree npm will remove, so nothing dies mid-install and no tool call is orphaned.
2. **Then, from a plain terminal outside any dsh session:** `npm install -g @deepseek-ai/dsh@0.1.2-rc.1` — the exact, formal registry install. Pinning the exact version matters on this machine because its global tree is already non-standard (hand-patched content, stale shims, `dsh-old-*` backups); a bare `@deepseek-ai/dsh@latest`-style or partial/manual swap would not reliably regenerate the shim trio or normalize the tree.
3. Verify: `dsh --version` → `0.1.2-rc.1`, then restart `dsh web`, hard-refresh the browser, confirm plugins load; clean up `dsh-old-*` afterwards.

**Known vs new:** the "stop the host, then run the formal global install from outside, then verify with `dsh --version` and a GUI restart" shape follows from the ordinary dsh upgrade rules (never self-host an upgrade; use the registry installer). What is **new for this incident** is the repair-shaped detail: because this machine's global tree was left non-standard by the interrupted install plus manual patching, the install command must be the exact-version formal re-install (to rebuild shims and overwrite the hand-mangled tree), the source-checkout tag alignment is needed, and `dsh-old-*` cleanup is a post-verification item.

## 5. Prevention

**Agent-side guard (class-level):**
- A pre-execution check in the shell/subprocess tool path (or a host-side guard plugin) that inspects the command before it runs: if it is a global install/uninstall/update (`npm i/install/update/remove -g`, or any package-manager equivalent) whose target resolves to the running dsh package itself (match the package name against the host's own install path / `dsh --version` source), **reject the call** with a structured error explaining the self-host relationship, and emit the external procedure text for the user instead.
- More generally: flag any command that mutates the directory tree the current host process runs from (`$APPDATA\npm\node_modules\@deepseek-ai\dsh`), not just npm — directory swaps, renames, deletions included.
- Also: the agent should treat "tool call recorded but no durable result" as a signal that its own host died, and never retry the same self-targeting command.

**Post-upgrade checklist for this machine (given the alpha.5→rc.1 findings):**
- `dsh --version` → `0.1.2-rc.1`; all three shims (`dsh`, `dsh.cmd`, `dsh.ps1`) present and fresh.
- Start `dsh --profile web`; hard-refresh the browser; confirm the GUI connects and plugins (whale / progress / etc.) load.
- **No plugin re-migration needed**: the alpha.5→rc.1 diff is 252 files, all `package.json` version bumps, zero API/feature changes (repair-notes key finding) — plugins migrated for 0.1.2-alpha.x stay valid; verify one plugin loads rather than re-running migrations.
- Confirm the source checkout sits on the `dsh-v0.1.2-rc.1` tag with no local-modification conflicts (already done by the repair session).
- Remove the `dsh-old-*` backup directories only after the above checks pass.
