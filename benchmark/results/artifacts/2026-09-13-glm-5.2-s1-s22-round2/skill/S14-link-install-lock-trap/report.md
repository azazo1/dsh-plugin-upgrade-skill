# S14 · Link-Install File-Lock Trap — Diagnostic Report

Task type per the plugin-upgrade skill: **Mode A · inspect** (read-only diagnosis and
report). No migrations, installs, or file writes were performed; the fixture was left
untouched. This report is written to the designated output directory only.

Evidence used: `copy-session.txt` (EBUSY Copy-Item transcript), `profile-introspection.txt`
(LinkType/Target and cordis.patch.yml marker), `maintainer-thread.md` (timeline), all
under the read-only fixture.

---

## 1. What the profile entry actually is

`profile-introspection.txt` shows:

```
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

and in the profile's `cordis.patch.yml`:

```
- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)
```

The profile entry is **not a copy** — it is a Windows **directory junction** pointing at
`E:\dev\dsh-attach-input`. The profile's `node_modules\@org\dsh-attach-input\lib\client.js`
and `E:\dev\dsh-attach-input\lib\client.js` are **the same file on disk**, reached
through two paths.

Deploy semantics of a link install: **the repo tree IS the installed copy**. Editing
`lib/client.js` in the repo already "deploys" it — there is nothing to copy. The only
activation requirement is that the processes holding the old module image in memory
reload it (see §4).

Therefore step 4 (Copy-Item from the repo into the profile's node_modules) was **never
necessary for this install** — it was a self-copy: source and destination resolved to the
same physical directory. Worse, it was actively harmful: `Copy-Item -Force` opens the
destination file for writing, which collides with the host's open handles and produced
the EBUSY, and the subsequent rename-aside "recovery" mutated the repo itself (§3).

## 2. The two locks and their owners

Two independent staleness/lock mechanisms were mistaken for one:

1. **Stale client code after a browser refresh.** The browser does not pick up repo
   edits made while the host was already running. The **running dsh host** serves the
   client bundle/artifact: it resolved and loaded the plugin (Host half `lib/index.js`,
   and the client artifact advertised to the browser) at profile start. A plain browser
   refresh re-fetches from the *host process*, which still holds the old in-memory
   module image / advertised artifact — and the browser cache may additionally serve the
   cached `client.js`. So refreshing the tab alone cannot show the new code; the
   **host process must be restarted**, and the browser must then do a **hard refresh**
   (cache bypass) for `client.js`.
2. **EBUSY on the lib files.** The holder is the **running dsh host (Node.js) process**,
   not the browser. Windows keeps the plugin's `lib/*.js` files held by the host that
   imported them. That is why closing the browser tab released nothing — the tab was
   never the owner. The lock persists until the dsh host fully stops.

Per the skill's global-host-upgrade discipline (same class of Windows file-lock issue):
a browser refresh is **not** a host stop; only fully stopping every dsh process releases
the module file locks.

## 3. Why the rename-aside destroyed the SOURCE directory, and the exact recovery

Because the profile entry is a junction to `E:\dev\dsh-attach-input`,
`Rename-Item ($dst + '\client.js') 'client.js.old2'` renamed **the one physical file**
`E:\dev\dsh-attach-input\lib\client.js` to `client.js.old2`. Both `Get-ChildItem`
listings then show only the `.old2` files because both listings enumerate the same
directory through the junction. The follow-up
`Copy-Item E:\dev\dsh-attach-input\lib\client.js ...` failed with "source does not
exist" — the maintainer had just renamed the source away. The plugin is broken in both
places at once, but there is only **one** broken place.

**Exact recovery from the current state** (no files were deleted — only renamed):

1. Stop the dsh host first (avoid another lock collision), then restore the original
   names in the repo path (equivalently the profile path — same directory):
   ```powershell
   Rename-Item E:\dev\dsh-attach-input\lib\client.js.old2 client.js
   Rename-Item E:\dev\dsh-attach-input\lib\index.js.old2 index.js
   ```
2. Verify the restored files are syntactically intact, e.g.
   `node --check E:\dev\dsh-attach-input\lib\client.js` (and `index.js`), and confirm
   `Get-ChildItem` shows both entry files under their original names.
3. Activate per §4 (host restart + hard refresh).
4. Optionally clean up any leftover `.old2` debris (none should remain after step 1).

Note: the renamed-aside content IS the edited code (the renames were applied to the
already-edited files), so restoring the names restores the hover-preview feature — no
re-editing needed unless verification fails.

## 4. Complete, ordered activation procedure (link-installed, lib-only Web plugin)

1. **Before editing** (or as step 0 here): confirm the install mode (§5).
2. **Edit repo files** (`E:\dev\dsh-attach-input\lib\client.js`, `lib/index.js`). No
   copy step — the junction already serves these files.
3. **Syntax check** the edited files (`node --check`) before restarting, so a broken
   entry fails loudly at a known point.
4. **Fully stop the dsh host** (`dsh web` process tree). This is the process that
   (a) holds the old Host-half module (`lib/index.js`) and (b) serves the client
   artifact to the browser. Closing the browser tab alone is insufficient — it owns
   neither lock.
5. **Restart the host** (`dsh web`). On boot it re-resolves the profile composition;
   because the junction target contains the new files, it loads the new code with no
   install/copy step. Watch host startup output for successful plugin activation (no
   pending/failed registration for `@org/dsh-attach-input`).
6. **Hard-refresh the browser** (Ctrl+F5 / cache bypass) — needed specifically for
   `client.js`, because the browser may have the previous `client.js` in HTTP cache and
   would otherwise keep executing the old client half even against a restarted host.
   This is exactly what the user's step-3 plain refresh could not achieve.
7. **Verify the new code actually loaded:**
   - Host half: exercise the new read-only host route (the hover-preview's data
     endpoint) and confirm it responds — proves `lib/index.js` reloaded.
   - Client half: trigger the hover-preview UI on an image attachment and observe the
     new behavior; if the plugin exposes a version marker, check it in the UI/network
     payload. A cache-busted request for the client artifact in DevTools Network should
     return the new bundle bytes.
8. If anything still looks stale, confirm no second dsh host instance is still running
   (an old process still holding the junction files) before touching any files.

## 5. The pre-flight check: determine install mode BEFORE touching files

Before any "deploy" action, inspect the profile entry:

```powershell
Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input `
  | Select-Object FullName, LinkType, Target
```

- **LinkType `Junction` (or `SymbolicLink`) + Target** → link install: the repo tree is
  the installed copy; deployment = edit the repo; activation = host restart + browser
  hard refresh. Never copy into the profile's node_modules.
- **LinkType empty / Target empty** (plain directory) → copied registry dependency: file
  replacement in the profile's node_modules is the mechanism that would apply (after
  stopping the host), or better, a proper package-manager update.
- Cross-check the profile's `cordis.patch.yml` for the install marker: a comment like
  `# link:E:\dev\dsh-attach-input (installed 2026-08-30)` records the link provenance.

Why the generic "copy into node_modules" advice is actively harmful here: with a
junction, source and destination are the same directory, so the copy is at best a no-op
and at worst a self-clobber — and under a running host it hits EBUSY, tempting
rename-aside tricks that rename the repo's own files away (exactly the accident in
`copy-session.txt`). The advice belongs only to copied installs.

## Recommendations

- Add a version/commit marker visible in the plugin's client UI or a debug route, so
  "did the new code load?" is checkable without guessing.
- For link-installed plugins, treat "restart host + hard refresh" as the whole
  activation procedure and document it in the plugin README.
- Never attempt file replacement under a running dsh host on Windows; stop the host
  first (mirrors the skill's global-host-upgrade lock discipline).

## Report structure notes (per skill validation/reporting)

- **pre-existing / baseline**: not collected (Mode A read-only inspection; no builds or
  tests were run — the plugin is currently broken and must be recovered per §3 first).
- **Completed**: diagnosis of install mode, both locks, the rename-aside mechanism, and
  the ordered recovery/activation procedure, from fixture evidence.
- **Skipped**: no runtime verification, no file writes, no installs — outside the
  read-only scope of this task.
- **Pending/residual risk**: recovery steps in §3 are inferred from the transcripts and
  have not been executed against the fixture (read-only). The `.old2` files' content is
  assumed to be the intended edited code, per the maintainer timeline.
- **Rollback**: not applicable — nothing was modified by this inspection.
