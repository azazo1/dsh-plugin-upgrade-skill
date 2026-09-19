# S14 · Link-Install File-Lock Trap — Diagnostic Report

Evidence pack (read-only): `profile-introspection.txt`, `copy-session.txt`, `maintainer-thread.md` under the fixture directory.

## 1. What the profile entry actually is — Junction install semantics

The introspection is decisive:

```
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

The profile's `node_modules\@org\dsh-attach-input` is not a directory holding copied files — it is an NTFS **junction** (a directory link) whose target is the maintainer's repo at `E:\dev\dsh-attach-input`. The repo itself shows `LinkType :` (empty) / `Target : {}`, confirming it is the real directory and the profile entry is the link.

The profile patch file confirms the install mode and intent:

```
- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)
```

**Deployment meaning:** the repo tree IS the installed copy. Whatever sits in `E:\dev\dsh-attach-input\lib\` is, at the filesystem level, already exactly what the profile serves. Edits are "deployed" the instant they are saved to the repo; no deployment or copy step exists.

**Was Copy-Item into node_modules ever the right move?** No — never, for this install mode. Copying into the profile path writes into the same physical directory through the junction, so it is both unnecessary (nothing needs replacing) and harmful (it collides with the host's open handles). The maintainer's step-4 assumption in `maintainer-thread.md` — "I assumed the profile must be running an installed COPY of the plugin" — is disproved by the introspection. Copying is only meaningful for a genuinely materialized dependency install, which this is not.

## 2. The two locks and their owners

**Why the browser refresh showed nothing new — who serves the client bundle.** `lib/client.js` is served by the **running dsh host** (the web-serving process of the profile); the browser does not read files from disk on refresh. `maintainer-thread.md` step 3: "The user refreshed the browser tab only — nothing changed". The host process was never restarted, so it kept serving the code it had already loaded; the new repo content never reached the serving side.

**Why EBUSY — what holds the lib files open.** The `copy-session.txt` error is explicit: `The file "...lib\client.js" is being used by another process, so the process cannot access this file.` The owner is the **running dsh host process**, which has the plugin's lib files open (Node keeps loaded/required module files open via its module loader). It is **not** the browser: the browser only fetches HTTP responses and never opens files on the profile or repo paths.

**Why closing the browser tab did not release EBUSY:** the transcript shows that after "maintainer closes the browser tab, waits, retries", the same IOException occurs for `client.js`, `index.js`, and `package.json`. Expected — the tab was never the lock owner. Only stopping the dsh host releases the handles. Attributing the lock to the browser is the core misdiagnosis of this case.

## 3. Why rename-aside destroyed the SOURCE directory too, and exact recovery

**Why both paths lost their files:** `Rename-Item ($dst + '\client.js') 'client.js.old2'` ran against `$dst` = the profile path — but that path is a **junction to `E:\dev\dsh-attach-input`**, the same physical directory (introspection: `LinkType : Junction`, `Target : {E:\dev\dsh-attach-input}`). Renaming through the link renames the real repo file. The transcript proves it: `Copy-Item 'E:\dev\dsh-attach-input\lib\client.js' ...` fails with `Cannot find path "E:\dev\dsh-attach-input\lib\client.js" because it does not exist.`, and `Get-ChildItem` on **both** `E:\dev\dsh-attach-input\lib` and `$dst` shows only `client.js.old2` / `index.js.old2`. One directory, two views — one rename, visible from both paths.

Side note: the rename worked while the copy did not because Windows open handles typically permit rename but block overwrite/delete — which is precisely why the rename-aside trick succeeded and did its damage.

**Exact recovery (only `.old2` files exist):**

1. Restore the original names in the repo (either path addresses the same directory; the repo side is clearest):
   - `Rename-Item E:\dev\dsh-attach-input\lib\client.js.old2 client.js`
   - `Rename-Item E:\dev\dsh-attach-input\lib\index.js.old2 index.js`
   File content was never touched — only names — so renaming back fully restores the entries. (If the repo is git-tracked and clean before the accident, `git checkout -- lib/` is an equivalent restore.)

2. **Verify syntax** before activating: `node --check E:\dev\dsh-attach-input\lib\client.js` and `node --check ...\lib\index.js`; confirm `package.json` main/exports still point at the restored names.

3. Confirm the junction is intact: `Get-Item` on the profile entry still shows `LinkType: Junction` / `Target: E:\dev\dsh-attach-input`.

4. Activate per §4. Do **not** retry any Copy-Item — with a link install, restoring the names in the repo already restores the deployed copy.

## 4. Complete, ordered activation procedure for a link-installed lib-only Web plugin

1. **Pre-flight (§5):** confirm link install (`LinkType: Junction` + `Target: E:\dev\dsh-attach-input`, plus the `link:` marker in `cordis.patch.yml`). If linked, no file deployment step exists.

2. **Save and validate the repo files:** `node --check` each edited lib file; the plugin has no build step.

3. **Fully stop the dsh host** serving the profile — the process that holds the lib files open and serves both host routes and the client bundle. It must be stopped completely; closing the browser tab is not a stop. This is what releases the EBUSY locks (§2).

4. **Start the host again.** Node's module loader reads the lib files fresh from the repo tree through the junction, so the new `client.js`/`index.js` (hover-preview feature and the new read-only host route) load. No install step sits between stop and start.

5. **Hard refresh the browser (cache bypass, e.g. Ctrl+F5) for `client.js`.** Even with the host restarted and serving new code, the **browser's HTTP cache** can still hold the previously served `client.js`; a plain refresh may reuse it. A hard refresh forces re-fetch from the restarted host. This is the second, browser-side reason step 3 of the thread showed nothing new.

6. **Verify the new code actually loaded:**
   - Reach the new read-only host route via the host API — proves the host runs the new `index.js`.
   - In DevTools Network, confirm `client.js` was re-fetched (200, not from cache/304 with old bytes) and that hover-preview behavior is present.
   - Open the served bundle URL and inspect its content for the hover-preview code — this distinguishes "host serving old code" from "browser cached old code".

Order matters: browser-side actions can never pick up new code before the host restarts, because the host is what reads the repo files and serves the bundle.

## 5. Pre-flight check: determine install mode before touching any file

1. **Filesystem link check (authoritative):** `Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input | Select-Object FullName, LinkType, Target`
   - `LinkType: Junction`/`SymbolicLink` with a `Target` → **link install**: the repo tree IS the installed copy; deployment = save files in the repo; copying is wrong.
   - Empty `LinkType`/`Target` → a real directory → **copied install**: only then is copying files in (or re-running the installer) meaningful — and only with the host stopped.

2. **Install marker in the profile:** `Get-Content ...\cordis.patch.yml | Select-String dsh-attach-input` shows `# link:E:\dev\dsh-attach-input (installed 2026-08-30)` — a recorded link install corroborating the filesystem answer, and naming the authoritative source directory.

3. **Sanity check:** compare file content through both paths — for a link they are always identical, because it is one directory.

**Why "copy into node_modules" advice is actively harmful for link installs:**

- It is a no-op at best (writing into the same directory through the junction) and a corruption vector at worst.
- It collides with the host's open handles → EBUSY (`copy-session.txt`), inviting risky workarounds.
- The common EBUSY workaround — rename-aside then copy — renames the **real source files** through the junction; that is exactly how this plugin ended up with no entry files at all. On a copied install, rename-aside affects only the profile copy; on a link install it breaks the maintainer's working tree.
- It misdirects verification toward deploy/copy thinking instead of the actual activation path for linked installs: restart the host, hard-refresh the browser.

**Bottom line:** recognize the junction first (`LinkType`/`Target` plus the `link:` marker), attribute the EBUSY to the running dsh host (never the browser), recover the rename accident by restoring the `.old2` files to their original names in the repo and syntax-checking them, then activate: stop host → start host → hard refresh → verify served bundle and new host route.
