# S12 · Global Upgrade EBUSY + Downgrade Trap — Diagnosis Report

**Mode:** A · inspect (read-only diagnosis; skill's "Global DSH host upgrades (agent discipline)" section).
No migrations, installs, or writes were executed; the fixture was only read.

**Environment under diagnosis (from the evidence pack):**
- OS: Windows; DSH installed globally via npm.
- Running dsh host: `0.1.2-alpha.4`; six community Web plugins across three GitHub mirrors.
- Desired target: `dsh-v0.1.2-alpha.5` (`@deepseek-ai/dsh@0.1.2-alpha.5`).
- Registry dist-tags at the time (`npm-dist-tags.txt`): `latest: 0.1.1-rc.2`, `next: 0.1.1-rc.2`, `alpha: 0.1.2-alpha.5`.

---

## 1. Attempt 1 root cause — why `koffi.node` is EBUSY

**What happened** (`attempt1-ebusy.log`): `npm install -g @deepseek-ai/dsh@0.1.2-alpha.5` failed with
`EBUSY` on `copyfile` of `@koromix/koffi-win32-x64/win32_x64/koffi.node` into npm's temp staging dir
(`@deepseek-ai/.dsh-TMPDIR/.../koffi.node`).

**Who holds the file** (`running-processes.txt`): `node.exe` PID **42432**, the **dsh web host**. The host
loaded `koffi.node` — a native FFI addon used for sandbox/filesystem operations — into its own process at
startup. On Windows, a loaded native `.node` PE binary keeps an OS-level file lock (the image section is
mapped) that persists until the *process* exits. Windows cannot replace/delete a file backing a loaded module,
so npm's copy/replace of that file fails with `EBUSY`. Note the second running dsh-side process
(PID 23768, the agent session worker) may hold locks of its own; any dsh-descended node process is suspect,
but the fixture names the web host as the `koffi` holder.

**Why a browser-page refresh does not free the lock:** refreshing only reloads the browser SPA (the Web
Client). The dsh **host process** — the node.exe that actually loaded `koffi.node` — keeps running and keeps
the module mapped. The lock is owned by the host OS process, not by any browser tab; nothing short of the
host process exiting releases it.

**Correct stop-then-upgrade sequence** (per the skill's agent discipline — also note this task's own session
never runs the upgrade in-process):

1. Fully stop every dsh process: the `dsh web` host **and** any agent/session worker processes. Verify with
   the process listing that no `node.exe` belonging to dsh (host, workers) remains — a browser refresh is
   *not* a host stop.
2. From an **external terminal** (not from inside a dsh session), run the **pinned** install (§3).
3. Restart `dsh web`, hard-refresh the browser, verify `dsh --version` and that the six plugins still
   resolve.

Because the host is fully stopped before npm runs, nothing can crash mid-install — a crash during the upgrade
is a signature of doing it wrong, not a tolerated risk. Attempt 1's interrupted install also matches the
skill's warning signature: it can leave package content present without regenerated shims (`dsh` gone until
an external pinned re-install repairs it).

## 2. Attempt 2 root cause — why `dsh --version` printed `0.1.1-rc.2`

**What happened** (`attempt2-downgrade.log`): after stopping dsh, the user ran a README's combined
`npm install -g @deepseek-ai/dsh @deepseek-harness-tui/dsh-tui`. It installed fine, but
`dsh --version` → `0.1.1-rc.2` — a **silent downgrade** from the installed `0.1.2-alpha.4`.

**Why:** the bare package name `@deepseek-ai/dsh` (no version specifier) resolves to the **`latest`
dist-tag**, not to "current installed version or newer". At the time (`npm-dist-tags.txt`):
`latest = 0.1.1-rc.2` and `next = 0.1.1-rc.2`, while the wanted `0.1.2-alpha.5` lives only on the
**`alpha`** dist-tag. npm treats dist-tags as the resolution authority for unpinned names — it does not
compare against the currently installed version and never "advances" from it; it simply installs whatever
`latest` points at. Since the 0.1.2 line was still pre-release, `latest` still pointed at the older rc.2,
and the unpinned install happily replaced alpha.4 with the *older* rc.2. This matches the skill's warning that
"a bare package name resolves to the `latest` dist-tag and can silently downgrade to an older line."

To reach alpha.5 without a full pin you would need `@deepseek-ai/dsh@alpha` (the `alpha` tag); the fully
deterministic form is the exact version pin `@0.1.2-alpha.5` (§3).

## 3. Exact safe upgrade commands for this situation

Goals: host `0.1.2-alpha.5`, plus the TUI plugin. All commands run in an **external** terminal, never inside
a dsh session on that host.

1. Stop dsh completely (host + session workers; verify with the node process listing; browser refresh is not a stop).
2. Install the pinned host and the TUI plugin — pin the host exactly; the plugin may follow its own current tag:
   ```
   npm install -g @deepseek-ai/dsh@0.1.2-alpha.5 @deepseek-harness-tui/dsh-tui
   ```
   (Equivalently `@deepseek-ai/dsh@alpha` targets the alpha line today, but the exact pin is deterministic and
   immune to future tag movement.)
3. Restart `dsh web`, hard-refresh the browser.
4. Verify: `dsh --version` must print `0.1.2-alpha.5`; confirm the six community Web plugins still resolve and
   register (per the skill, also check the client combo/roster after an in-place global upgrade — a host restart
   self-heals a stale module roster; see DSH-0.1.5-A1-20-style symptom).

Rollback baseline: the previous global install was `0.1.2-alpha.4`; if anything fails, re-run the same
external pinned install with `@0.1.2-alpha.4` (never hand-copy package directories or hand-write shims —
repair is always a re-run of the pinned formal install).

## 4. Prevention — guidance for plugin README authors

- **Never publish an unpinned `npm install -g @deepseek-ai/dsh`** in install/upgrade instructions. It follows
  the `latest` dist-tag and can silently *downgrade* a user running a newer pre-release line (exactly the
  attempt-2 trap). Either pin the exact version the plugin was tested against
  (`@deepseek-ai/dsh@0.1.2-alpha.5`) or name the dist-tag explicitly (`@alpha`) with a note about what it
  tracks.
- **State the stop-before-install precondition explicitly**: "fully stop all dsh processes (host and session
  workers) before running this; refreshing the browser page does not stop the host." On Windows a running host
  holds native-module file locks (`koffi.node`) → EBUSY (attempt-1 trap), and an interrupted global install
  can leave `dsh` without shims.
- **Instruct running the install from an external terminal**, never from a shell/tool inside a running dsh
  session — the session IS the host process being replaced.
- Prefer one command that pins the host and lists the plugin separately (or separate host-upgrade and
  plugin-install steps), so the host version is never implied by a tag the user didn't choose. If a combined
  one-liner is kept, every `@deepseek-ai/dsh` occurrence in it must carry an explicit version or tag.

---

## Report structure per the skill

- **pre-existing (baseline failures):** not collected — read-only Mode A diagnosis; no builds/tests run.
- **Completed:** both root causes diagnosed from the evidence pack (process listing + EBUSY log + dist-tags
  listing); safe ordered upgrade procedure and README-author prevention guidance produced. No files, installs,
  or configuration were changed.
- **Skipped:** no corridor-card analysis — no plugin source migration is involved; the six Web plugins and three
  mirrors are context only. No registry/network lookups performed (offline; `npm-dist-tags.txt` is the
  authoritative capture).
- **Pending/residual risk:** dist-tags move over time — `@alpha` vs `latest` relationships captured here are
  point-in-time; the exact pin in §3 avoids that dependency. Windows-specific EBUSY behavior confirmed for this
  host; untested on other platforms (out of scope).
- **Rollback:** not applicable (nothing changed). Baseline recorded: host `0.1.2-alpha.4`, dist-tags as
  captured in `npm-dist-tags.txt`.
- **Recommendations:** adopt the README guidance in §4; consider tooling that warns when an unpinned global
  `dsh` install would move the installed version backwards.
