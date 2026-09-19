# S14 · Link-Install File-Lock Trap — Diagnostic Report

Evidence pack: `profile-introspection.txt`, `copy-session.txt`, `maintainer-thread.md` (fixture, read-only).

## 1. What the profile entry actually is — and why Copy-Item was never the right move

The introspection is decisive:

```
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

The second `Get-Item E:\dev\dsh-attach-input` shows `LinkType` empty — the repo is the real directory; the profile entry is only a **junction** pointing at it. The profile's own `cordis.patch.yml` confirms the install mode:

```
- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)
```

**Deployment semantics:** there is no installed copy. The repo tree at `E:\dev\dsh-attach-input` **is** the installed plugin — every byte under the profile path is literally the same storage as the repo path. Editing `lib/client.js` / `lib/index.js` in the repo already "deployed" the hover-preview feature to the profile at the moment of saving; nothing needed to be copied, linked, or installed again.

Therefore step 4 in the maintainer thread ("I assumed the profile must be running an installed COPY, so I tried to Copy-Item the new lib files into the profile's node_modules") was **never the right move for this install mode**. It was a no-op conceptually (copying a directory onto itself through the junction) that failed purely because of open file handles. The only remaining work after a repo edit is process restart (host) + browser reload (see §4).

## 2. The two locks and their owners

There are two independent reasons stale code appears, with two different owners:

- **Browser cache (stale code after refresh).** The client bundle `lib/client.js` is served to the browser by the **running dsh web host** process, which loads the plugin's client code from the profile path (i.e., from the repo through the junction). A plain refresh can serve the browser's cached copy of `client.js`, so the maintainer saw "old behavior, no preview" even though the file on disk was already new. Owner: the browser's HTTP cache — but the *serving* process is the host, not the plugin repo.
- **File locks (EBUSY / "being used by another process").** The `Copy-Item` failures on `client.js`, `index.js`, and `package.json` are held by the **running dsh host process**, which has the plugin's lib files open (loaded/required for serving). The browser tab holds **no handle** on those files — it only holds a received, cached copy of the bundle in browser memory/disk cache.

**Why closing the tab did not release EBUSY:** the second attempt in `copy-session.txt` ("maintainer closes the browser tab, waits, retries") failed with "same IOException for client.js, index.js, package.json" because the lock owner was never the browser — it was the still-running dsh host that had loaded the plugin. Attributing the lock to the browser was the wrong diagnosis; only stopping the host (or not copying at all, per §1) can release the handles.

## 3. Why rename-aside destroyed the SOURCE directory too — and the exact recovery

### Why both paths lost their entry files

Because the destination "profile" lib directory is the **same directory** as the source repo lib directory through the junction:

```
C:\...\node_modules\@org\dsh-attach-input  --(Junction)-->  E:\dev\dsh-attach-input
```

So `$dst = 'C:\...\dsh-attach-input\lib'` and `E:\dev\dsh-attach-input\lib` are one directory with two names. The transcript shows exactly what happened:

1. `Rename-Item ($dst + '\client.js') 'client.js.old2'` — renamed the file **in the real directory** (the repo), so the repo's `client.js` disappeared too.
2. Same for `index.js` → `index.js.old2`.
3. `Copy-Item 'E:\dev\dsh-attach-input\lib\client.js' ...` — failed: "Cannot find path ... because it does not exist." The "source" had just been renamed away by step 1; it was never missing independently.
4. `Get-ChildItem` on **both** paths shows only `client.js.old2` / `index.js.old2` — one directory, listed twice through the junction.

The rename-aside trick exists for *copied* installs where source and destination are distinct files; on a link install it is self-destructive: renaming the locked file aside renamed the repo's own entry files aside, and the plugin now has no `client.js`/`index.js` at all.

### Recovery from the current broken state

Both surviving files are the maintainer's own newly edited files (they were renamed, not replaced), so recovery is simply restoring their names — no content is lost:

1. **Rename back** (either path works; they are the same directory):
   ```powershell
   $lib = 'E:\dev\dsh-attach-input\lib'
   Rename-Item ($lib + '\client.js.old2') 'client.js'
   Rename-Item ($lib + '\index.js.old2') 'index.js'
   ```
2. **Verify the restored files are the new feature code and syntactically valid** before activating, so a broken host startup cannot masquerade as a plugin bug:
   ```powershell
   node --check E:\dev\dsh-attach-input\lib\client.js
   node --check E:\dev\dsh-attach-input\lib\index.js
   Get-Content E:\dev\dsh-attach-input\lib\index.js   # confirm hover-preview code present
   ```
3. **Verify both names resolve** through the junction too (`Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\client.js`) — sanity that the entry files are back in the one real directory.
4. Then follow the activation procedure in §4 (restart host, hard-refresh browser). Note: had the maintainer's last `Copy-Item` succeeded, it would have overwritten the new code with itself; on a link install no copy step belongs in recovery either.

## 4. Complete ordered activation procedure for a link-installed lib-only Web plugin after repo edits

Precondition: install mode confirmed as link (§5). Files edited in the repo; nothing to copy.

1. **(One-time, only if recovery was needed)** Restore entry-file names and syntax-check (§3).
2. **Stop the dsh web host fully** — the process that serves the client bundle and holds the lib files open. This is the step that actually releases the file locks; a browser tab close does nothing for them.
3. **Start the host again.** It re-reads `lib/client.js` / `lib/index.js` from the profile path — which is the repo path through the junction — so it loads the new hover-preview code. Host restart is mandatory: the host had the old module code loaded in memory even though the files on disk were already new.
4. **Hard refresh (cache bypass, e.g. Ctrl+F5 / DevTools "Disable cache") in the browser.** A plain refresh may reuse the browser's cached `client.js`; the hard refresh forces a re-fetch so the browser receives the bundle the restarted host now serves. This is why the user's step-3 plain refresh showed "nothing new" and why stale code can persist even after the host has restarted if only a soft refresh is done.
5. **Verify the new code actually loaded**, at three points:
   - Host side: the new read-only host route responds (e.g., request the new route and confirm the hover-preview response).
   - Client side: in DevTools, confirm the served `client.js` (Network tab, response body / source) contains the hover-preview code, and the hover-preview UI behaves in the page.
   - Sanity: `Get-ChildItem E:\dev\dsh-attach-input\lib` shows plain `client.js` / `index.js` (no `.old2` strays left behind).

Order matters: host restart before browser refresh (otherwise the browser re-fetches from the old in-memory host), hard refresh last.

## 5. The pre-flight check — determine install mode before touching any file

Before any copy/rename/reinstall action, run the introspection the maintainer eventually ran:

```powershell
Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input |
  Select-Object FullName, LinkType, Target
```

- `LinkType: Junction` (or `SymbolicLink`) with `Target: {E:\dev\dsh-attach-input}` ⇒ **link install**: the repo tree IS the installed copy. Correct action after edits: restart host + hard-refresh browser. **No file operations on the profile path at all.**
- `LinkType` empty ⇒ a real copied directory ⇒ copying new files in would at least be directionally right (after stopping the host to release locks).

Corroborate with the profile's `cordis.patch.yml` install marker, which this profile already carried: `node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)` — the word `link:` states the mode explicitly.

**Why the generic "copy into node_modules" advice is actively harmful for link installs:** it treats the profile path as a distinct destination, but on a link install it is the same directory as the source. Consequences, all visible in this pack: (a) it is unnecessary — edits are already live in the profile; (b) it hits EBUSY on the running host's open handles and misdirects debugging toward the browser (§2); (c) the "rename-aside" recovery variant is self-destructive — renaming at the destination renames the repo's own entry files, which is exactly how both directories ended up with only `client.js.old2` / `index.js.old2` and the plugin broken (§3). One 5-second `Get-Item ... LinkType, Target` pre-flight would have prevented the entire incident.
