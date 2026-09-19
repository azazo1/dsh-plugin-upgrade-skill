# S14 · Link-Install File-Lock Trap — Analysis Report

Fixture evidence reviewed (read-only): `copy-session.txt`, `profile-introspection.txt`, `maintainer-thread.md`, `README.md`.

---

## 1. What the profile entry actually is

`profile-introspection.txt` shows:

```
FullName : C:Usersme.dshprofilesweb
ode_modules@orgdsh-attach-input
LinkType : Junction
Target   : {E:devdsh-attach-input}
```

and `cordis.patch.yml` in the profile contains the install marker:

```
- node_modules/@org/dsh-attach-input  # link:E:devdsh-attach-input (installed 2026-08-30)
```

The profile's `node_modules@orgdsh-attach-input` is **not a copy** — it is an NTFS **junction** pointing at the repo directory `E:devdsh-attach-input`. The repo tree IS the installed copy. Any path under the profile entry resolves to the very same on-disk directory as the repo path; there is exactly one physical copy of `lib/client.js` and `lib/index.js`.

Deploy semantics for a link install: **editing the repo files already "deploys" them.** There is nothing to copy, publish, or sync. Step 4 of the maintainer's thread (Copy-Item of `E:devdsh-attach-inputlib*.js` into the profile's node_modules) was never necessary for this install — and it was worse than useless, because source and destination were the same directory. The copy attempted to overwrite files with themselves while those files were held open by the running dsh host, which is exactly what produced the EBUSY. The generic "copy into node_modules" advice is actively harmful here: for a link install it is a no-op-at-best, an EBUSY/self-overwrite at worst, and (as step 5 showed) it can destroy the only copy of the files.

## 2. The two locks and their owners

Two separate staleness/locking effects were mistaken for each other:

**Lock A — stale client code after a browser refresh.** The browser does not read `lib/client.js` from disk. The dsh web host (the `dsh web` / profile server process) loads the plugin's client half and serves the client bundle to the browser. With the host still running the pre-edit code (and the browser possibly caching the previously served bundle), a plain tab refresh re-fetches the old bundle. The lock on the *served code* is owned by the **running dsh host process**, not by the browser.

**Lock B — EBUSY on the lib files.** The `IOException ... being used by another process` on `client.js`, `index.js`, and `package.json` is Windows file locking: the **running dsh host process** holds the plugin's lib files open (it loaded the host-half `index.js` from the junctioned directory and keeps handles into it). Closing the browser tab released nothing because the browser never held those file handles — the tab only ever talked HTTP to the host. The process that had to stop was the host.

So both locks trace to the same owner: the running dsh host. The browser refresh (step 3 of the thread) could not pick up new code because the host had not restarted; the EBUSY (step 4) could not clear because, again, the host had not stopped.

## 3. Why rename-aside destroyed the SOURCE too, and the exact recovery

Because the profile entry is a junction to `E:devdsh-attach-input`, these two paths name the **same directory**:

- `C:Usersme.dshprofilesweb
ode_modules@orgdsh-attach-inputlib`
- `E:devdsh-attach-inputlib`

`Rename-Item ($dst + '\client.js') 'client.js.old2'` therefore renamed the single physical file — the repo's own `client.js` — to `client.js.old2`. The subsequent `Copy-Item 'E:devdsh-attach-inputlibclient.js' ...` failed with "source does not exist" because the rename had already removed that very source name. Hence both `Get-ChildItem` listings show only the `.old2` files: they are two views of one directory, and the plugin has no entry files at all.

**Exact recovery from the current state** (only `client.js.old2` / `index.js.old2` exist):

1. Stop the dsh host (`dsh web` for this profile) so nothing holds handles in the junctioned directory. The old names are gone, so even without locks the plugin cannot load — stop first anyway to make the renames race-free.
2. Rename the files back to their original entry names, in the repo (either path works — do it once, via the repo path, to make the identity obvious):
   ```powershell
   Rename-Item E:devdsh-attach-inputlibclient.js.old2 client.js
   Rename-Item E:devdsh-attach-inputlibindex.js.old2  index.js
   ```
   Do NOT copy anything — the `.old2` files ARE the edited v0.2.11 files (the edits were made before the failed copy attempts; nothing ever overwrote them).
3. Verify the restored files are syntactically valid (they were edited by hand):
   ```powershell
   node --check E:devdsh-attach-inputlibclient.js
   node --check E:devdsh-attach-inputlibindex.js
   ```
   (`node --check` works for plain script; for ESM files use `node --input-type=module --check < file` or import them in a throwaway script.) Also confirm `package.json` `main`/`exports` still point at `./lib/index.js` and `./lib/client.js`.
4. Only then activate (procedure in §4).

Because the install is a link, restoring the repo names restores the profile simultaneously — there is nothing to propagate.

## 4. Complete, ordered activation procedure for a link-installed lib-only Web plugin

After editing `lib/client.js` / `lib/index.js` in the repo:

1. **Verify syntax** of the edited files (`node --check`) before restarting anything — a broken entry file takes the whole profile down.
2. **Fully stop the dsh host** for the profile (`dsh web` / the profile's server process). This is what releases the file handles on the junctioned lib files and what discards the in-memory old plugin code. "Closing the browser tab" is not a substitute — the tab holds no file handles and no plugin code.
3. **Start the host again.** On load it re-reads `lib/index.js` (host half) through the junction from the repo tree — the new code is now what the host has. No copy step exists or is needed.
4. **Hard-refresh the browser (cache bypass)**: the client half `client.js` is served to the page as a bundle the browser may have cached under the same URL. A normal refresh can re-serve the stale bundle from HTTP cache even though the host restarted; Ctrl+F5 / DevTools "Disable cache" + reload / empty-cache-and-hard-reload forces re-fetch of the new `client.js`. This is why the browser can still show stale code after a host restart.
5. **Verify the new code actually loaded** — do not trust the absence of errors:
   - Host half: exercise the new read-only host route (the v0.2.11 addition) and confirm it responds; check the host's plugin-load log line for `@org/dsh-attach-input` and its resolved path (should be the junction target `E:devdsh-attach-input`).
   - Client half: trigger the hover-preview on an image attachment; if the plugin exposes a version/registration marker, confirm v0.2.11 in the page (console or plugin panel). As a last resort, add a temporary `console.log` tag in `client.js` and confirm it appears after the hard refresh — then remove it.

Order matters: syntax check → host stop → host start → browser hard refresh → behavioral verification.

## 5. Pre-flight check: determine the install mode BEFORE touching any file

Before any "deploy" action, inspect what the profile entry actually is:

```powershell
Get-Item C:Usersme.dshprofilesweb
ode_modules@orgdsh-attach-input |
  Select-Object FullName, LinkType, Target
```

- **LinkType `Junction` (or `SymbolicLink`) with a Target** → link install: the repo tree is the installed copy; edits are live after host restart + browser hard refresh; **never copy files into node_modules**.
- **LinkType empty / Target empty** → a real copied directory: the profile runs its own copy, and updating it requires replacing files there — with the host stopped.

Cross-check the install marker in the profile config:

```powershell
Get-Content C:Usersme.dshprofileswebcordis.patch.yml | Select-String dsh-attach-input
#  - node_modules/@org/dsh-attach-input  # link:E:devdsh-attach-input (installed 2026-08-30)
```

The `link:<path>` marker records that this entry was link-installed. Had this check been done first, the maintainer would have seen the junction and skipped the copy entirely.

Why the generic "copy into node_modules" advice is actively harmful for link installs: (a) it is redundant — source and destination are the same directory, so there is nothing to update; (b) it can hit EBUSY because the running host holds the very files you are "overwriting"; (c) any file-management trick performed "in the profile" (rename-aside, delete-then-copy) mutates the repo's only copy of the files, so a failed or half-completed operation leaves the source tree broken too, exactly as happened in step 5.

---

### Summary of root causes

| Symptom | Root cause |
|---|---|
| Browser refresh showed nothing new | dsh host still running pre-edit code; possibly browser-cached bundle |
| EBUSY on copy, even with browser closed | Running dsh host holds the lib file handles (not the browser) |
| Copy-Item attempted at all | Install mode never checked — entry is a Junction to the repo |
| Both dirs left with only `.old2` files | Junction makes profile path and repo path the same directory; rename-aside renamed the sole physical copies |
