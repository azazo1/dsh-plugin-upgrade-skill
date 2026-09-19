# S14 · Link-Install File-Lock Trap — Diagnosis & Recovery Report

Task: S14-link-install-lock-trap (read-only analysis). Evidence: fixture pack
(`copy-session.txt`, `profile-introspection.txt`, `maintainer-thread.md`). Skill mode: A ·
inspect (read-only), with a recovery/activation *procedure* to execute — no files in the
fixture, profile, or repo were touched by this analysis.

---

## 1. What the profile entry actually is

`profile-introspection.txt` is decisive:

```
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

and `cordis.patch.yml` carries the matching install marker:

```yaml
- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)
```

So the profile does **not** contain an installed copy of the plugin. The entry
`node_modules/@org/dsh-attach-input` is an **NTFS junction pointing at the maintainer's
repo** `E:\dev\dsh-attach-input`. The repo tree *is* the installed copy; both paths
resolve to the same physical directory through the junction.

**Deployment semantics:** editing `E:\dev\dsh-attach-input\lib\client.js` *is* editing
`C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\client.js`. There
is nothing to copy, sync, or deploy. Step 4 (Copy-Item of repo files into the profile's
node_modules) was not merely unnecessary — for a junction install it is a **self-copy**
(source directory == destination directory through the link). It was never the right move
for this install mode; "copy into node_modules" is the procedure for a *copied registry
dependency*, a different install track.

## 2. The two locks and their owners

Two independent staleness/lock effects were mistaken for one problem:

**Lock A — stale client code after a browser refresh.** The Web client bundle
(`lib/client.js` for this lib-only plugin) is not read from disk per page view; it is
**loaded and cached by the running dsh host process** (the `dsh web` Node process), which
serves the client artifact to the browser. A browser refresh only re-requests from the
host — the host still holds and serves the *old* module it loaded at startup. Result:
refresh shows old behavior (no hover preview) even though the repo files already contain
the new code. The process that must restart to pick up edited `client.js`/`index.js` is
the **host**, not the browser.

**Lock B — EBUSY on the lib files even with no browser tab open.** The file handles on
`client.js`, `index.js`, `package.json` are held by that same **running dsh host
process** (Node keeps required modules / watched files open; on Windows an open handle
blocks overwrite-in-place → `IOException … being used by another process`). Closing the
browser tab releases nothing, because the browser never held these file handles — the tab
only has an HTTP connection to the host. This matches the evidence: the retry after
closing the tab produced the identical EBUSY for `client.js`, `index.js`, `package.json`.

Attribution: **both locks belong to the running dsh host process.** The browser tab is
responsible for neither (it explains only *display* staleness via its own HTTP cache,
addressed in §4).

## 3. Why the rename-aside trick destroyed the SOURCE directory too

`Rename-Item ($dst + '\client.js') 'client.js.old2'` renames the file *inside the
junctioned directory* — which is physically the repo directory. Because
`$dst\lib == E:\dev\dsh-attach-input\lib` (same directory through the junction), the
rename renamed the **repo's own files** to `client.js.old2` / `index.js.old2`. The
subsequent copy then failed with "source does not exist" for the same reason: the source
path `E:\dev\dsh-attach-input\lib\client.js` no longer exists (it was just renamed
aside). Both `Get-ChildItem` listings show only the `.old2` files because they are two
views of one directory. Net state: the plugin has no entry files at all, in the only copy
that exists.

**Exact recovery from the current broken state** (only `client.js.old2` / `index.js.old2`
exist — in the repo, which is the installed copy):

1. (Optional but wise, since the host may hold handles on the `.old2` names too:) stop the
   `dsh web` host process fully first, so renames cannot hit EBUSY again.
2. In **one** location only — the repo `E:\dev\dsh-attach-input\lib` (do not touch the
   profile path; it is the same directory):
   ```powershell
   Rename-Item E:\dev\dsh-attach-input\lib\client.js.old2 client.js
   Rename-Item E:\dev\dsh-attach-input\lib\index.js.old2  index.js
   ```
   Since the `.old2` files are the *pre-edit* locked originals (the new code was never
   successfully copied anywhere — the copy failed with "source does not exist"), the
   maintainer must re-apply the hover-preview edits to these restored files, or restore
   them from version control and redo the edit. Note the maintainer edited the repo files
   *before* the rename (thread step 1), so the `.old2` content is whatever the rename
   captured — verify which version survived; do not assume the new feature is present.
3. Verify syntax before activating: `node --check E:\dev\dsh-attach-input\lib\client.js`
   and `node --check E:\dev\dsh-attach-input\lib\index.js` (and confirm
   `package.json` still lists the expected entry points; it was EBUSY-protected but never
   renamed).
4. Then follow the activation procedure in §4.

## 4. Complete, ordered activation procedure for a link-installed lib-only Web plugin after repo edits

For this install mode there is **no deploy step** — activation is purely process/cache
management:

1. **Stop the dsh host completely** (`dsh web` / the profile's Node process). Not just the
   browser: the host holds the loaded module and the file handles. A browser refresh is
   not a host stop.
2. (Edits already live in the repo tree = installed tree; `node --check` both entry files.)
3. **Start the host again** (`dsh web` for the profile). On boot it re-reads
   `lib/index.js` and re-serves `lib/client.js` from the junctioned repo directory.
4. **Hard-refresh the browser (cache bypass: Ctrl+F5 / Ctrl+Shift+R)**. The browser caches
   the fetched `client.js` artifact by normal HTTP caching; a soft refresh can re-serve
   the stale client bundle from browser cache even after a correct host restart. This is
   why stale code can survive a host restart.
5. **Verify the new code actually loaded**, e.g.: confirm the host boot/serving of the
   client artifact reflects the new file (changed byte size or ETag, or the host's client
   roster/version marker in the boot manifest); in the page, confirm the new behavior
   (hover preview appears on image attachments) and, if the plugin logs a version/feature
   marker, check it in the browser console; exercise the new read-only host route added in
   `lib/index.js` and confirm it responds. One message → tool → response flow (or the
   plugin's core path) should pass before calling it verified.

Order matters: host stop → (verify files) → host start → hard refresh → behavioral
verification.

## 5. Pre-flight check: determine install mode BEFORE touching any file

Before ever copying anything into a profile's node_modules, inspect the entry:

```powershell
Get-Item <profile>\node_modules\@org\<pkg> | Select-Object FullName, LinkType, Target
```

- **LinkType `Junction` (or `SymbolicLink`) + Target** → link install: the repo tree is
  the installed copy; *never* copy into the profile path (it writes into the repo itself);
  activation is restart-only (§4).
- **LinkType empty + Target `{}`** → a real directory: likely a copied/registry-installed
  dependency, for which copying files (after stopping the host) or reinstalling via the
  profile's package manager is the appropriate track.
- Cross-check `cordis.patch.yml` for the install marker, exactly as the fixture shows:
  `# link:E:\dev\dsh-attach-input (installed 2026-08-30)` — the `link:` marker records
  the link install and its date; a plain dependency row without the marker indicates the
  copied track.

**Why the generic "copy into node_modules" advice is actively harmful here:** on a link
install, "destination" and "source" are the same physical directory. A copy is at best a
no-op self-copy; under load it hits EBUSY; and any file-management maneuver (rename-aside,
delete-then-copy) mutates the **source repository** — exactly the destruction sequence
recorded in `copy-session.txt`. The correct mental model: for link installs, *edits are
already deployed*; only process restarts and cache busts remain.

---

## Report sections per the skill

- **pre-existing:** not collected (read-only analysis; no baseline run applicable).
- **Completed:** full diagnosis from the three evidence files; install-mode determination
  (Junction link install); lock attribution (both locks → running dsh host); rename-aside
  failure mechanism; ordered recovery and activation procedures; pre-flight check.
- **Skipped:** no runtime reproduction (no live profile/container access — fixture is
  static, read-only by rule); no version-corridor cards apply (this is an install-mode /
  process-lifecycle failure, not a DSH API migration edge).
- **Pending/residual risk:** content of the `.old2` files (pre-edit originals vs
  edited) is not determinable from the static evidence — recovery step 2 must verify and
  possibly re-apply the hover-preview edit; `package.json` was EBUSY-protected but its
  final state should be confirmed before restart.
- **Rollback:** n/a — nothing was modified; the recovery procedure in §3 is itself the
  rollback for the maintainer's accident.
- **Recommendations:** adopt the pre-flight install-mode check (§5) as a standing step
  before any profile file operation; for link-installed plugins, treat "host restart +
  hard refresh + behavioral verify" as the only activation procedure; consider version
  control (git status) before/after repo edits so a rename accident is recoverable from
  history.
