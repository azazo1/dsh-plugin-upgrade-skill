# S14 · Link-Install File-Lock Trap — Analysis Report

## 0. What actually happened (one-paragraph summary)

The profile entry `C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input` is **not a copied dependency** — it is an **NTFS Junction** whose target is the repo itself (`E:\dev\dsh-attach-input`, confirmed by `LinkType: Junction`, `Target : {E:\dev\dsh-attach-input}` in profile-introspection.txt, and the `# link:E:\dev\dsh-attach-input` marker in cordis.patch.yml). The profile's "installed copy" and the repo are therefore **the same directory**. Editing the repo already "deployed" the change; the Copy-Item was never needed, and the rename-aside trick renamed the repo's own entry files (which then made the subsequent copy fail with "source does not exist" — the source it had just destroyed). The stale browser behavior had nothing to do with files being out of date: the running dsh host still held the old plugin code in memory (and Windows file locks on the loaded lib files), so only a full host restart + hard refresh was ever required.

---

## 1. What the profile entry actually is

Evidence (profile-introspection.txt):

~~~
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
~~~

and in the profile's `cordis.patch.yml`:

~~~
- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)
~~~

**Meaning:** the profile "install" is a **junction (directory link)** from the profile's `node_modules` path to the live repo tree. For a junction install, **the repo tree IS the installed copy** — there is exactly one physical copy of `lib/client.js` and `lib/index.js` on disk, reachable through two path names (`E:\dev\dsh-attach-input\lib\...` and `C:\...\node_modules\@org\dsh-attach-input\lib\...`). Any edit in the repo is, by construction, already visible at the profile path. The `# link:...` comment in `cordis.patch.yml` is the install marker recording that this entry was created as a link (on 2026-08-30), not a copied dependency.

**Was Copy-Item ever the right move? No.** Copying repo files "into the profile's node_modules" is a **copied-install** deployment step. For a link install there is nothing to copy — worse, `Copy-Item ... -Force` writes the file onto *itself* through the junction (source and destination resolve to the same physical file). It is both unnecessary and, as the session shows, fails with EBUSY anyway because the running host holds the files open. The generic "copy into node_modules" advice is actively harmful for link installs (see §5).

## 2. The two locks, and who owns them

Two distinct staleness/locking effects were observed; both belong to the **running dsh host process**, not the browser:

1. **Stale code after a browser refresh.** The client plugin (`lib/client.js`) is served as a bundle **by the dsh web host process** (the Node process running the `web` profile), and the host plugin half (`lib/index.js`) is loaded by that same host at startup. The host had loaded/cached the plugin code when it started — after step 1's repo edits, the host was never restarted, so it kept serving the **old** client bundle and running the **old** host half. The browser faithfully rendered what it was served; refreshing the tab (or even closing it) cannot change what the host has in memory. Hence "restart dsh web and hard-refresh the browser to verify" — the maintainer's own instruction in step 2 was correct; only the browser-refresh half was actually performed by the user.

2. **EBUSY on the lib files, surviving browser-tab closure.** On Windows, the running dsh host process holds the plugin's lib files open (loaded module / served-bundle file handles). `Copy-Item -Force` needs to open the destination for writing and gets `IOException: ...being used by another process` on `client.js`, `index.js`, and `package.json`. **Closing the browser tab releases nothing** — the browser never held these file handles; the lock owner is the host Node process. Only fully stopping that host process releases the locks. (This is also why the lock is irrelevant to the correct procedure: for a link install you never need to write those files while the host runs.)

## 3. Why rename-aside destroyed the SOURCE too, and exact recovery

**Why both directories lost their files:** through the junction, the "profile" path and the "repo" path are the **same physical directory**. `Rename-Item ($dst + '\client.js') 'client.js.old2'` renamed the one physical file `E:\dev\dsh-attach-input\lib\client.js` to `client.js.old2`. Both `Get-ChildItem E:\dev\dsh-attach-input\lib` and `Get-ChildItem $dst` then list the same directory contents (`client.js.old2`, `index.js.old2`) because they *are* one directory. The follow-up `Copy-Item 'E:\dev\dsh-attach-input\lib\client.js' ...` then failed with "source does not exist" — the rename-aside had just removed its own source. Net result: the plugin (and the repo) has **no entry files at all** under their original names.

**Exact recovery from the current broken state** (only `client.js.old2` / `index.js.old2` exist):

1. **Stop the dsh web host process first** (so no file handles interfere with the renames; also required anyway for activation).
2. Rename the files back to their original names — one rename in *either* path (they are the same file; do not touch both paths):
   ~~~powershell
   Rename-Item 'E:\dev\dsh-attach-input\lib\client.js.old2' 'client.js'
   Rename-Item 'E:\dev\dsh-attach-input\lib\index.js.old2'  'index.js'
   ~~~
   (Operating via the repo path keeps the mental model on "the repo is the real copy".)
3. **Verify syntax** of both restored files before activating: `node --check E:\dev\dsh-attach-input\lib\client.js` and `node --check E:\dev\dsh-attach-input\lib\index.js` (and confirm the edited hover-preview code is present, e.g. `Select-String` for a new symbol).
4. Confirm `Get-ChildItem E:\dev\dsh-attach-input\lib` shows exactly the original entry files back; the `.old2` leftovers can be deleted only after verification (optional).
5. Then activate (§4).

No re-copy, reinstall, or git surgery is needed: the `.old2` files *are* the edited files (the repo edits from step 1 were made before the rename), just misnamed.

## 4. Complete, ordered activation procedure for a link-installed lib-only Web plugin after repo edits

1. **Edit the repo files** (`lib/client.js`, `lib/index.js`) — for a junction install this is the entire "deployment"; there is no build step and nothing to copy.
2. **Syntax-check** the edited files (`node --check`) so a broken plugin fails at your desk, not inside the host.
3. **Fully stop the running dsh web host process** (the profile's Node host). This releases the Windows file locks on the lib files and discards the in-memory old plugin code. Closing browser tabs is neither necessary nor sufficient for this.
4. **Restart the host** (`dsh web` under the `web` profile). The host re-reads `lib/index.js` (host half) and serves `lib/client.js` from the repo tree through the junction.
5. **Hard-refresh the browser** (cache bypass: Ctrl+F5 / Ctrl+Shift+R, or DevTools "Disable cache"). Why a *hard* refresh: the browser may have the **old `client.js` bundle in its HTTP cache**; a normal refresh can revalidate to the cached copy and show stale client code even though the host now serves the new one. This answers "why can it still show stale code after the host restarted": the host restart fixes the server side; the cache bypass fixes the client side. (If the harness provides an HMR-style client-plugin reload path, that can avoid the refresh — but the baseline correct procedure is host restart + hard refresh.)
6. **Verify the new code actually loaded**:
   - Client: trigger the hover-preview on an image attachment; check DevTools → Network for `client.js` (status 200, not "from disk cache", expected new size/timestamp) or console output added by the new feature.
   - Host: exercise the new read-only host route added in `lib/index.js` and confirm it responds; or check the host startup log for the plugin loading from `node_modules/@org/dsh-attach-input` without errors.
   - If the old behavior persists: confirm the host process actually restarted (not just a new browser tab), then confirm the browser fetched the bundle fresh (Network panel), then re-check the junction target has not changed.

**Order matters:** host stop → host start → browser hard refresh. Restarting the host while planning to copy files (the maintainer's step 4) was the wrong goal entirely; the restart is needed *to load the new code*, not to enable copying.

## 5. Pre-flight check: determine the install mode BEFORE touching any file

Before any deploy/verify action on a plugin in a profile, inspect the profile entry:

~~~powershell
Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input |
  Select-Object FullName, LinkType, Target
~~~

- **LinkType `Junction` (or `SymbolicLink`) with `Target` = repo path** → link install: repo tree IS the installed copy; deployment = *edit the repo only*; activation = host restart + browser hard refresh (§4). Never copy files into the profile's node_modules.
- **LinkType empty / no Target** → a real copied directory: deployment may involve replacing the files (after stopping the host), or better, reinstalling via the profile mechanism.
- Cross-check the profile's `cordis.patch.yml` install marker: a `# link:<target path> (installed <date>)` comment on the `node_modules/...` entry records that this entry was created as a link. Both signals agreed here: `LinkType: Junction`, `Target : {E:\dev\dsh-attach-input}`, and `# link:E:\dev\dsh-attach-input`.

**Why generic "copy into node_modules" advice is actively harmful for link installs:**

1. It is a no-op semantically (source = destination through the junction) yet still *writes* — on Windows it collides with the running host's file locks and fails EBUSY, inviting exactly the destructive rename-aside "recovery" seen here.
2. Rename/move/delete operations performed on the profile path operate on the **real repo files** — the trick that is merely risky on a copied install *destroys the source* on a link install.
3. It masks the real problem. Here staleness was never a file-propagation issue; it was an un-restarted host plus browser cache. The copy advice sent the maintainer down a path that broke the plugin entirely instead of fixing a simple restart issue.

**Bottom line:** for this junction-installed, lib-only plugin: repo edit → `node --check` → stop host → start host → hard refresh → verify via the Network panel / new feature behavior. Recovery from the current state: stop host, rename the `.old2` files back (via the repo path), syntax-check, then activate in that order.
