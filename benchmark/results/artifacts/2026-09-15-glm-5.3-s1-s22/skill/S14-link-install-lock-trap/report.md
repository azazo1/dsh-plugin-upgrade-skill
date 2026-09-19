# S14 · Link-Install File-Lock Trap — Report

**Mode:** A-equivalent read-only diagnosis (skill `plugin-upgrade`, Mode A "inspect"; the
benchmark authorization replaces the usual user confirmation). No file inside the fixture
was touched; no install, migration, or lifecycle script was executed. Evidence: the four
files in the task's `environment/fixture/` (`copy-session.txt`,
`profile-introspection.txt`, `maintainer-thread.md`, `README.md`).

---

## 1. What the profile entry actually is

`profile-introspection.txt` is decisive:

```
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

and the profile composition carries the link marker:

```
# cordis.patch.yml
- node_modules/@org/dsh-attach-input  # link:E:devdsh-attach-input (installed 2026-08-30)
```

So the profile's `node_modules/@org/dsh-attach-input` is **not a copied dependency — it is
an NTFS directory junction pointing at the maintainer's repo** `E:devdsh-attach-input`
(the repo itself has `LinkType:` empty / `Target: {}`, i.e. a real directory, the link
source of truth). Deployment semantics for a Junction install:

- **The repo tree IS the installed copy.** Every path under the profile entry
  (`...\node_modules\@org\dsh-attach-input\lib\client.js`) resolves through the
  junction to `E:devdsh-attach-input\lib\client.js`. Editing the repo file *is*
  deploying the edit; there is nothing to copy.
- Copying repo files into the profile's node_modules was therefore **never the right move
  for this install mode** — it is at best a no-op self-copy (destination == source through
  the junction) and, as the transcript shows, actively destructive when combined with
  rename-aside. That advice belongs to a *copied* dependency install, where the profile
  entry is a real directory holding an independent snapshot of the package. The correct
  discipline per the skill's shared preparation is to record installation identity
  (junction/workspace vs registry/copy) *before* choosing any update mechanism.

## 2. The two locks and their owners

Two independent staleness/lock layers, both owned by the **running dsh host process**, not
the browser:

1. **Client-bundle staleness (why the refresh showed nothing).** For a Web Client plugin,
  the *host* (`dsh web`) is the process that serves the client artifact `lib/client.js`
  to the browser. The plugin's Host half is loaded once at host boot; the client bundle is
  fetched by the browser but produced/registered by the running host. A plain browser
  refresh re-fetches from a host that still holds the *old* module state (and the browser
  may additionally serve from cache), so the user saw the old behavior with no
  hover-preview. The fix requires restarting the host, not just the tab.
2. **File locks / EBUSY (why Copy-Item failed even with no tab open).** The running dsh
  host Node process has the plugin's `lib\client.js`, `lib\index.js` (and
  `package.json`) open — its module loader resolved them through the junction when the
  profile booted. Windows keeps those handles until the host process exits, which is
  exactly why the files were "being used by another process" and why **closing the browser
  tab released nothing**: the browser never held these handles; the lock owner is the host.
  Consistent with the skill's global-host-upgrade note that a *running* host holds native /
  module file locks and a browser refresh is not a host stop.

So: staleness = host serving old code; EBUSY = host holding the very files open. Browser
restart addresses neither.

## 3. Why rename-aside destroyed the SOURCE too, and the exact recovery

Because both paths denote the **same directory through the junction**,
`Rename-Item ($dst + '\client.js') 'client.js.old2'` renamed
`E:devdsh-attach-inputlibclient.js` itself. There was never a second copy. The
subsequent `Copy-Item E:devdsh-attach-inputlibclient.js $dst` failed with "source
does not exist" because the rename had already destroyed its own source; both
`Get-ChildItem` listings then show only the `.old2` files — the repo *and* the profile
"both" lost the entry files because they are one directory. (The OS allowed the rename
despite the open handles because a rename within the same volume does not need write
access to the file's data, only the directory entry — which is what made this trick more
dangerous than the copy.)

**Recovery from the current state** (only `client.js.old2` / `index.js.old2` exist in
`E:devdsh-attach-inputlib`; the profile needs no separate repair since it is the same
tree):

1. Fully stop the dsh host (`dsh web`) first — the `*.old2` files may still be held open
   by the running host; renaming them back while it runs can hit EBUSY again. A running
   host is the lock owner established in §2. (Confirm with no `node`/dsh processes
   holding the tree if in doubt.)
2. Rename the files back to their original names, in the repo directory:
   `Rename-Item E:devdsh-attach-inputlibclient.js.old2 client.js` and
   `Rename-Item E:devdsh-attach-inputlibindex.js.old2 index.js`. Do not copy — rename,
   so no open-handle or same-file copy issue arises.
3. Verify syntax of both files before activation: `node --check
   E:devdsh-attach-inputlibclient.js` and `node --check ...libindex.js` (lib-only
   plugin, no build step, so a syntax check is the available static gate). Also confirm
   the hover-preview edits are actually present in the restored content (the `.old2`
   files are the edited versions — they were the live repo files before the rename).
4. Then activate per §4. If the host was stopped in step 1, restart `dsh web` and
   hard-refresh the browser.

Note the maintained edits are *not* lost: `.old2` is the renamed current file, not a
backup of the old version — restoring the names restores the feature work.

## 4. Complete, ordered activation procedure for a link-installed lib-only Web plugin

After editing repo files (`lib/index.js` Host half, `lib/client.js` Client half):

1. **Stop the dsh host completely** (`dsh web`). This releases the file locks and
   discards the old loaded Host-half module state. A browser refresh or tab close does
   not do this (§2). Order matters: the host must be stopped before any file operation on
   the tree, and restarted only after the tree is in its final state.
2. (If not recovering from an accident, nothing else is needed — the junction already
   "deploys" the repo edits. There is **no copy step** for a link install.)
3. **Restart `dsh web`** so the host re-imports `lib/index.js` fresh and re-registers /
   re-serves the client bundle `lib/client.js` with the new content.
4. **Hard-refresh the browser** (cache bypass, e.g. Ctrl+F5 / Ctrl+Shift+R). Reason: the
   browser may still serve the previously fetched `client.js` from HTTP cache; a normal
   refresh can re-use it and show stale client code *even after the host restarted*.
   The client bundle is the artifact most prone to this because it is fetched per page
   load rather than re-read from disk.
5. **Verify the new code actually loaded**, in increasing strength:
   - boot log / host console shows the plugin entry activating without pending services;
   - the served artifact carries the new code: fetch `lib/client.js` from the host's
     client-artifact URL (or check the file's content/size served over HTTP) and grep for
     a marker unique to the hover-preview feature;
   - behavior: trigger the feature (hover an image attachment) and observe the preview;
   - for a stronger signal, exercise one Host-half path touched by the edit (the new
     read-only host route) end-to-end — the skill's validation layers (runtime entry
     activation, then one core behavior path).
6. Only if verification fails, diagnose (host console, served-artifact diff) — do **not**
   respond with file copies into node_modules (§5).

## 5. The pre-flight check that should come first

Before touching any file, determine the **install mode** from the profile:

- `Get-Item <profile>\node_modules\@org\dsh-attach-input | Select-Object FullName,
  LinkType, Target` — `LinkType: Junction` (or `SymbolicLink`) with `Target` pointing
  at the repo means a **link install**: the repo is the live installed copy; the only
  activation mechanics are process restarts (§4). Empty `LinkType` means a **copied
  dependency**: the profile entry is an independent snapshot, and updating it requires the
  package-manager / copy flow that matches its identity (and, per the skill, only the
  package manager that owns the lockfile).
- Cross-check the composition file: `cordis.patch.yml` (or `agent.cordis.yml` / legacy
  `cordis.yml`) — the `# link:E:devdsh-attach-input` comment on the entry is the
  install marker recording when and from where the link was made. Composition files are
  the authoritative record of *how* the profile resolves the plugin.

**Why generic "copy into node_modules" advice is actively harmful here:** for a link
install the destination *is* the source, so the copy is a self-copy at best; under a
running host it collides with the host's open handles (EBUSY, unfixable by closing the
browser); and any "rename aside / delete first" variant of that advice operates on the
repo's real files through the junction and destroys the only copy — precisely the S14
accident. The right mental model: **link install ⇒ files are already deployed; restart
host + hard-refresh browser; never file-copy.**

---

## Skill-mode summary

- **Completed:** read-only diagnosis of a link (Junction) install vs copied dependency;
  lock attribution (host process for both client-bundle staleness and EBUSY); recovery
  plan for the rename-aside accident; ordered activation procedure; pre-flight install-mode
  check. Evidence cited from all three fixture artifacts.
- **Skipped:** no dependency/lockfile scans, card corridors, or runtime verification — not
  applicable: no version migration is involved (same plugin version, local edits only),
  and executing anything against the fixture is forbidden.
- **Pending/residual risk:** the recovery steps are prescribed, not executed (read-only
  task). If the `.old2` files were themselves stale (e.g. an editor had unsaved buffer
  state), content verification in step 3 of §3 would catch it. Untested assumption from
  the transcript alone: that the host was still running during the renames — if it had
  been stopped, EBUSY would not have appeared for the copies, which the transcript
  contradicts.
- **Rollback:** not applicable — no state was changed by this report; the fixture is
  untouched.
