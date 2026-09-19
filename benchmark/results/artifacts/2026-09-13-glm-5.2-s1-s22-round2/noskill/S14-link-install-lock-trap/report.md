# S14 · Link-Install File-Lock Trap — Analysis Report

## 1. What the profile entry actually is

`profile-introspection.txt` shows:

```
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

and `cordis.patch.yml` contains `- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)`.

The profile's `node_modules/@org/dsh-attach-input` is **not a copy** — it is an NTFS **junction** pointing at the maintainer's repo directory `E:\dev\dsh-attach-input`. The repo tree *is* the installed copy: every path under the profile entry resolves transparently to the same physical files as under `E:\dev\dsh-attach-input`.

Deployment consequence: **editing `lib/client.js` / `lib/index.js` in the repo already "deploys" them.** There is nothing to copy. Step 4 (Copy-Item from the repo into the profile's node_modules) was never necessary for this install — worse than unnecessary, it was a self-copy: source and destination were the same physical files. The generic "copy into node_modules" advice applies only to *copied* dependency installs and is actively harmful for link installs (here it directly caused the EBUSY and, via the rename-aside variant, the data loss described below).

## 2. The two locks and their owners

- **Client-bundle staleness (what the browser serves).** The Web client code is served by the **running dsh host process** (`dsh web`), not by the browser and not freshly read from disk per page load. The host loaded `lib/client.js` into memory (and/or serves a bundled/cached client asset) when it started. A browser refresh just re-fetches from the still-running host, so the user saw old behavior. The browser holds no lock on the plugin's lib files at all.
- **EBUSY on the lib files.** The lib files were held open by the **running dsh host process** on Windows (the Node process keeps required/loaded modules and watched files open; Windows refuses in-place writes/overwrites of open files). That is why closing the browser tab changed nothing — the tab was never the lock owner. The Copy-Item hit `IOException … being used by another process` on `client.js`, `index.js`, and `package.json` because the host had them open.

Correct attribution for both symptoms: one process — the running `dsh web` host — both serves the stale client bundle and holds the lib files open.

## 3. Why rename-aside destroyed the SOURCE directory, and exact recovery

Because the profile entry is a junction to `E:\dev\dsh-attach-input`,

`C:\…\node_modules\@org\dsh-attach-input\lib\client.js` **is** `E:\dev\dsh-attach-input\lib\client.js` — same file, one physical directory.

So `Rename-Item ($dst + '\client.js') 'client.js.old2'` renamed the *repo's own* file. After that, `E:\dev\dsh-attach-input\lib\client.js` no longer existed, which is why the follow-up `Copy-Item 'E:\dev\dsh-attach-input\lib\client.js' …` failed with "Cannot find path … because it does not exist." Both `Get-ChildItem` listings then showed only the `.old2` files — they are two views of one directory. The plugin (and the repo) has no entry files at all.

Note that the edits themselves were almost certainly still present *in content*: rename preserves file content; only the names changed. Recovery (do not copy anything — the junction already handles "deployment"):

1. Stop the dsh host completely (`dsh web` process exit) so nothing holds the lib files open.
2. In the repo directory `E:\dev\dsh-attach-input\lib` (equivalently the junction path — same directory), restore the original names:
   ```powershell
   Rename-Item E:\dev\dsh-attach-input\lib\client.js.old2 client.js
   Rename-Item E:\dev\dsh-attach-input\lib\index.js.old2  index.js
   ```
3. Verify syntax before activating, e.g. `node --check E:\dev\dsh-attach-input\lib\client.js` and `node --check E:\dev\dsh-attach-input\lib\index.js` (and confirm `package.json` still lists them as entries).
4. Confirm the profile side via the junction: `Get-ChildItem C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input\lib` shows `client.js` / `index.js` again.
5. Activate per §4.

Also sanity-check for stray earlier attempts (`.old`, partial copies); if `client.js.old2` content looks older than the intended hover-preview edit, the maintainer's edited content may have been in the file at rename time — the `.old2` files *are* the latest content, since rename happened after the edits.

## 4. Complete, ordered activation procedure (link-installed, lib-only Web plugin)

1. **Fully stop the dsh host** (`dsh web`). This is the process that both loaded the plugin and holds the lib files open; closing browser tabs does nothing. Verify the process is gone (e.g. `Get-Process node` / the profile's managed job) before touching files.
2. Confirm/repair the repo files (§4 step 3 of recovery: names restored, `node --check` passes).
3. **Start the host again** (`dsh web`). On start it resolves the plugin through the junction and loads the new `lib/index.js` (host half) and reads `lib/client.js`.
4. **Hard-refresh the browser (cache bypass)** — Ctrl+F5 / Ctrl+Shift+R. Reason: even with a restarted host, the *browser* may still serve `client.js` (and other client assets) from its HTTP cache; a plain refresh can revalidate from cache and show stale client code. The host restart alone explains server-side staleness; the hard refresh addresses the client-side cache.
5. **Verify the new code actually loaded**:
   - Host half: exercise the new read-only host route (e.g. from the client/DevTools) and confirm it responds.
   - Client half: trigger the hover-preview on an image attachment; optionally check DevTools → Network that `client.js` was fetched fresh (200, not "from cache / 304 of an old ETag), or `console.log` a version marker temporarily.
   - Host logs on startup should show the plugin loaded from the linked path without errors.

## 5. Pre-flight check before touching any file

Before ever copying/renaming anything in a profile's node_modules, determine the install mode:

```powershell
Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input |
  Select-Object FullName, LinkType, Target
```

- `LinkType: Junction` (or `SymbolicLink`) with `Target` → **link install**: the repo tree is the installed copy; the correct procedure is *edit in repo → stop host → start host → hard-refresh browser*. Never copy files into the profile's node_modules.
- Empty `LinkType`/`Target` → ordinary copied dependency; only then does "replace the files in node_modules (with the host stopped)" apply.
- Cross-check the profile's `cordis.patch.yml` for a `# link:<path> (installed <date>)` marker on the entry — the fixture shows `- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)`.

Why the generic advice is harmful for link installs: it treats source and destination as independent, but through a junction they are the same physical files. Copying self-overwrites (EBUSY while the host runs; a no-op otherwise), and rename-aside "recovery" renames the *source* files away — exactly the accident that broke this plugin.
