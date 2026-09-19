# S14 · Link-Install File-Lock Trap — Report

## 1. What the profile entry actually is

`profile-introspection.txt` shows:

```
Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

and `cordis.patch.yml` carries the link marker:

```
- node_modules/@org/dsh-attach-input  # link:E:devdsh-attach-input (installed 2026-08-30)
```

The profile entry is **not a copied dependency** — it is an NTFS **junction** pointing at the
maintainer's repo directory. The repo tree at `E:\dev\dsh-attach-input` *is* the installed copy;
there is exactly one physical directory and both paths resolve to it.

Deployment semantics: editing `E:\dev\dsh-attach-input\lib\client.js` / `lib\index.js` already
"deploys" the change. **Copy-Item into the profile's node_modules was never the right move for
this install mode** — the destination *is* the source through the junction. The copy was at best
a no-op (identical bytes onto themselves) and at worst — as happened — a self-inflicted
rename/delete on the repo itself.

## 2. The two locks and their owners

- **Lock A — who serves the client bundle.** A Web plugin's `client.js` is served to the browser
  by the **running `dsh` host process** (the profile's Node process), not by the browser. The
  browser is only a downloader; once the tab has fetched the bundle, it holds no OS handle on the
  file. That is why the user refreshing (or even closing) the browser tab showed stale / released
  nothing: the host process still had the old code loaded in memory and kept the lib files open.
  A browser refresh can never surface new code until the **host process re-imports the plugin** —
  for a lib-only bundle with no HMR/rebuild step, that means a full host restart, since Node
  caches the loaded module and serves the client bundle from its cached copy.
- **Lock B — what holds the lib files open (EBUSY).** The EBUSY/IOException on `client.js`,
  `index.js`, and `package.json` comes from the **running dsh host process**, which has those
  files open (module loading / watching) on Windows. Closing the browser tab released nothing
  because the browser never held these handles — the lock owner is the host, and only stopping
  the host releases it.

So: browser refresh = stale code (host still serving/holding the old bundle); EBUSY after closing
the tab = the host, not the browser, owns the file handles.

## 3. Why rename-aside destroyed the SOURCE too, and exact recovery

Because `...\node_modules\@org\dsh-attach-input` is a junction to `E:\dev\dsh-attach-input`,
`Rename-Item ($dst + '\client.js') 'client.js.old2'` renamed the **single physical file** that
both paths share. After the two renames there were no `client.js`/`index.js` left anywhere, so
the subsequent `Copy-Item E:\dev\dsh-attach-input\lib\client.js ...` failed with "source does
not exist" — the maintainer had renamed away their own repo files. Both `Get-ChildItem` listings
show the same two `.old2` files because they are the same directory viewed twice.

**Recovery from the current state** (only `client.js.old2` / `index.js.old2` exist):

1. (If the host is still running, stop it first so nothing holds the files: stop the `dsh` /
   `dsh web` process for the profile.)
2. In the repo (equivalently the profile path — same directory): rename the files back —
   `Rename-Item E:\dev\dsh-attach-input\lib\client.js.old2 client.js` and
   `Rename-Item E:\dev\dsh-attach-input\lib\index.js.old2 index.js`.
   The `.old2` files are the maintainer's edited v0.2.11 sources (they were the live repo files
   before the rename), so no content is lost.
3. Verify syntax before activating: `node --check E:\dev\dsh-attach-input\lib\client.js` and
   `node --check E:\dev\dsh-attach-input\lib\index.js` (both must parse cleanly).
4. Then activate per §4. The repo edit is already "deployed" via the junction; nothing to copy.

## 4. Complete activation procedure (link-installed, lib-only Web plugin)

1. **Stop the dsh host process for the profile completely** (`dsh web` / the profile's Node
   process). This is the process that both loads `lib/index.js` (host half) and serves
   `lib/client.js` to the browser; it is also the EBUSY lock owner. A browser refresh alone
   cannot help.
2. Confirm the edits are in the repo and syntactically valid (`node --check` on both files).
3. **Restart the host** (`dsh web` with the profile). It re-imports `lib/index.js` fresh and now
   serves the new `client.js` bundle.
4. **Hard-refresh the browser (cache bypass)** — Ctrl+F5 / DevTools open → right-click reload →
   "Empty cache and hard reload". The browser may still show stale code after a host restart
   because it cached the old `client.js` HTTP response; a normal reload can serve `client.js`
   from HTTP cache without hitting the restarted host. A cache-bypassing reload forces a fresh
   fetch of the new bundle.
5. **Verify the new code actually loaded**: e.g. DevTools → Network → confirm `client.js` was
   fetched (status 200, not "(from disk cache)") after the hard reload; exercise the new
   hover-preview feature on an image attachment; optionally check the new read-only host route
   responds; or add a temporary `console.log` version marker and see it in the console.

Order matters: host stop → restart → then browser hard refresh (refreshing before the host
restart re-caches the old bundle).

## 5. Pre-flight check: determine install mode before touching any file

Before any copy/rename, inspect the profile entry:

```powershell
Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input |
  Select-Object FullName, LinkType, Target
Get-Content C:\Users\me\.dsh\profiles\web\cordis.patch.yml |
  Select-String dsh-attach-input
```

- **LinkType `Junction`/`SymbolicLink` with a Target**, or a `# link:<path> (installed …)` marker
  in `cordis.patch.yml` ⇒ **link install**: the repo tree is the deployed copy. Never copy into
  node_modules; activation is host restart + browser cache-bypass refresh only.
- **No LinkType, no link marker** ⇒ a copied dependency: replacing files in the profile's
  node_modules (after stopping the host) would be the applicable procedure.

Why the generic "copy into node_modules" advice is actively harmful for link installs: the
destination path *aliases the repo itself*, so a copy targets the source files, an in-place copy
fights the host's open handles (EBUSY), and any rename/delete "on the profile" mutates — or, as
here, destroys — the repo's own entry files.
