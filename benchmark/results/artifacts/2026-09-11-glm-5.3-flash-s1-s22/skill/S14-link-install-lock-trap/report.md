# S14 · Link-Install File-Lock Trap — Diagnostic Report

Skill applied: dsh-plugin-upgrade (Mode A · inspect — read-only diagnosis; no migration or installation executed). Evidence base (all read-only, all paths under the evidence pack):

- profile-introspection.txt — Get-Item ... | Select-Object FullName, LinkType, Target on the profile entry and on the repo directory, plus the cordis.patch.yml install marker.
- copy-session.txt — the PowerShell transcript: two failed Copy-Item -Force attempts (EBUSY), the rename-aside attempt, the failed copy, and the final directory listings.
- maintainer-thread.md — the maintainer's own account of steps 1–6.

---

## 1. What the profile entry actually is — and why "copy into node_modules" was never the right move

Decisive evidence from profile-introspection.txt:

    FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
    LinkType : Junction
    Target   : {E:\dev\dsh-attach-input}

and the real directory:

    FullName : E:\dev\dsh-attach-input
    LinkType :
    Target   : {}

plus the composition marker in C:\Users\me\.dsh\profiles\web\cordis.patch.yml:

    - node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)

**Finding.** The profile's node_modules\@org\dsh-attach-input is a **filesystem junction** (an NTFS directory link) whose target is the maintainer's own repo checkout E:\dev\dsh-attach-input. There is exactly **one directory** on disk; the profile path and the repo path are two names for it. This matches the "link:" install marker recorded in cordis.patch.yml.

Deployment semantics of this install mode:

- The **repo tree IS the installed copy**. Every edit to lib/client.js / lib/index.js in E:\dev\dsh-attach-input is already "installed" at the profile path the instant the file is saved. There is no build step (lib-only bundle) and no deployment step.
- Therefore Copy-Item E:\dev\dsh-attach-input\lib\*.js into the profile's node_modules\@org\dsh-attach-input\lib\ was **never necessary — and in fact was a self-copy**: source and destination resolve to the same underlying directory. Step 4 in maintainer-thread.md ("I assumed the profile must be running an installed COPY") was based on a false premise; the profile runs the repo files directly.

So the answer to the maintainer's direct question is: **no, copying was never the right move for THIS install.** For a link/junction install the only "deploy" action is saving the files in the repo; the remaining work is entirely process restart + browser cache, i.e. activation (§4).

## 2. The two locks and their owners — why refresh showed stale code and closing the tab did not release EBUSY

Two distinct mechanisms are involved, but a single process owns both.

**(a) Who serves the client bundle → the running dsh host process.** @org/dsh-attach-input is a Web plugin with lib/client.js as its client entry. The browser does not read the plugin files from disk; the **dsh host** (dsh web) serves the client bundle over HTTP. The first refresh showed old behavior because:

1. the host process had been started before the repo edits and had not been restarted, so it served the previously loaded module state; and/or
2. the browser had the old bundle in its HTTP cache — a plain refresh can serve from cache (see §4 on why a *hard* refresh is required for client.js).

Neither a plain refresh nor closing the tab touches the host process, so no amount of browser action could make the new code appear.

**(b) Who holds the lib files open → the same running dsh host, not the browser.** The EBUSY in copy-session.txt:

    Copy-Item : The file "...\node_modules\@org\dsh-attach-input\lib\client.js" is being used by
    another process, so the process cannot access this file.  (IOException)

The lock owner is the **running dsh host** (the Node process serving dsh web): through the junction, the profile's lib\client.js *is* E:\dev\dsh-attach-input\lib\client.js, and the host has the module loaded/open for serving. It is not the browser — the browser only received an HTTP response and keeps no handle to the file. That is exactly why the maintainer's step "closes the browser tab, waits, retries" got the **same IOException for client.js, index.js, package.json**: closing a tab releases nothing on the host's file handles. Only fully stopping the host process releases the lock. The refresh-vs-lock confusion has one attribution: **one process — the running dsh host — explains both observations.**

## 3. Why rename-aside destroyed the SOURCE directory too, and the exact recovery

**Mechanism.** Because of the junction:

    C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input\lib  ≡  E:\dev\dsh-attach-input\lib

The maintainer renamed the *destination-path* files (Rename-Item $dst\client.js 'client.js.old2', same for index.js), but $dst is the same physical directory as the repo's lib\. Renaming through either path renames the single underlying files — so the **source** repo immediately lost client.js/index.js as well. The subsequent copy then failed with:

    Copy-Item : Cannot find path "E:\dev\dsh-attach-input\lib\client.js" because it does not exist.

and the final listings confirm one shared, gutted directory on both paths:

    Get-ChildItem E:\dev\dsh-attach-input\lib   →  client.js.old2, index.js.old2
    Get-ChildItem $dst                          →  client.js.old2, index.js.old2

The rename-aside pattern (rename the locked target aside, write a fresh file at the old name) is a valid trick only for **copied** installs on Windows, where the rename can succeed while a handle stays open. Here it silently performed a destructive operation on the authoritative repo copy and left the plugin with **no entry files at all** — the "completely broken" state in maintainer-thread.md step 5.

**Exact recovery from the current state (only client.js.old2 / index.js.old2 exist, identical files visible through both paths):**

1. **Stop the host first** (fully exit the dsh web process per §4) — required for the later activation anyway, and it removes any doubt about active handles.
2. **Restore the original names** — one set of files, either path (same directory):

       $lib = 'E:\dev\dsh-attach-input\lib'   # or the profile path — same directory
       Rename-Item "$lib\client.js.old2" 'client.js'
       Rename-Item "$lib\index.js.old2"  'index.js'

   Verify Get-ChildItem $lib shows client.js and index.js and no *.old2 remains; both paths agree automatically.
3. **Verify syntax before activating** (the .old2 files carry the new hover-preview edits, so validate what is actually there):

       node --check "$lib\client.js"
       node --check "$lib\index.js"

   Both must exit 0. package.json was never renamed (its copy attempt only hit EBUSY), so the original manifest is intact — no manifest repair needed.
4. **Activate** by the procedure in §4. Do **not** attempt to "re-copy" the files from anywhere: the restored files *are* the current repo source containing the hover-preview edits.

Contingency: if node --check fails (truncated/corrupt content), recover from the repo's Git working tree (git checkout -- lib/) or the editor's local history — never by copying into the profile, which is the same directory.

## 4. Complete, ordered activation procedure for a link-installed lib-only Web plugin after repo edits

For this install mode the "install" is already done by editing the repo; what remains is process lifecycle plus browser cache. Two independent caches must be cleared: the host's in-memory module state and the browser's HTTP cache of client.js.

1. **Fully stop the dsh host** — exit the dsh web process completely. This releases the locks behind every EBUSY in copy-session.txt. A browser refresh or tab close is **not** a host stop (the plugin-upgrade skill states the same invariant: a running host holds file handles; "a browser refresh is not a host stop").
2. **(Recommended) sanity-check the files** while stopped: node --check lib\client.js and lib\index.js — fail loud before bringing a broken entry back up.
3. **Start the host again** (dsh web). Cold start makes the host re-read node_modules\@org\dsh-attach-input\lib\ — which, through the junction, is the freshly edited repo tree — so the new hover-preview code and new read-only host route load from disk. Verify the plugin entry activates and no required service stays pending in the host boot output.
4. **Hard-refresh the browser** (cache bypass: Ctrl+F5 or DevTools "Disable cache"). Why hard refresh specifically: lib/client.js is served as a static HTTP asset, and the browser may honor its cached copy on a normal refresh even though the host now serves new bytes. A plain refresh — what the user did in maintainer-thread.md step 3 — can therefore still show stale code even after a correct host restart. This answers "why can it still show stale code after the host restarted".
5. **Verify the new code actually loaded** (behavioral proof, not a bare HTTP 200):
   - DevTools → Network: client.js returns 200 with a new response body/etag/length matching the edited file, not a "(disk cache)" hit;
   - Search the served client.js source for a hover-preview-only identifier — its presence proves the new bundle reached the page;
   - Exercise one core path: hover an image attachment and observe the preview; confirm the new read-only host route responds.
6. If anything still looks stale (partial step, stale served-module roster), one further full host restart + hard refresh self-heals.

## 5. Pre-flight: determine install mode BEFORE touching any file — and why "copy into node_modules" advice is actively harmful here

**Read-only checks, in order:**

1. **LinkType/Target on the profile entry** — the check that would have prevented everything (exactly what profile-introspection.txt eventually ran, too late):

       Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input | Select-Object FullName, LinkType, Target

   - LinkType : Junction (or SymbolicLink) with Target {E:\dev\dsh-attach-input} → **link install**: the repo tree IS the installed copy; no deployment copy step exists or is needed.
   - LinkType empty and Target {} (a plain directory, as the second introspection line shows for E:\dev\dsh-attach-input itself) → **copied install**: only then is copying new build output into the profile the correct deployment move.
2. **The composition/install marker in the profile's cordis.patch.yml** — the corroborating signal, also in the introspection file:

       - node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)

   The "link:<path>" marker documents the install track at installation time; it agrees with the junction. (Per the skill, resolved config is verification evidence and cordis.patch.yml is composition truth — both point the same way here.)
3. If ambiguity remains, compare file identity rather than guessing: a marker change in a repo file must appear at the profile path instantly for a link — they cannot diverge.

**Why the generic advice is actively harmful for link installs.** "Copy the new files into the profile's node_modules" presumes two disjoint directories (source ≠ destination). Under a junction:

- the copy degenerates into a **self-copy onto files the running host has open** → guaranteed EBUSY (observed in copy-session.txt);
- the common recovery for that failure — rename-aside — **renames the authoritative repo source itself**, destroying the plugin's entry files on both paths simultaneously (§3);
- even a "successful" copy would be a no-op overwrite of the very files already serving the profile, adding risk (partial overwrite, package.json clobbering) for zero benefit.

The correct pre-flight conclusion once Junction + Target + the link: marker are seen: **no file transfer at all — stop host → (syntax check) → start host → hard refresh → behavioral verify** (§4); and if any file operation is ever unavoidable, stop the host first so no lock exists.

---

## Summary table

| Observation in the pack | Attribution | Correct action |
|---|---|---|
| Refresh showed nothing new (maintainer-thread step 3) | Browser cache and/or un-restarted host serving old bundle | Full host restart + hard refresh |
| EBUSY on Copy-Item -Force (copy-session.txt) | Running dsh host holds lib/client.js, lib/index.js, package.json open through the junction | Stop the host before any file operation — or simply never copy (link install) |
| Same EBUSY after closing the browser tab | Browser holds no file handles; lock owner is the host | Stop the host process |
| Rename-aside wiped the repo too | Both paths are one directory via Junction → E:\dev\dsh-attach-input | Rename *.old2 back, node --check, restart host, hard refresh |
| "Copy into node_modules" instinct (maintainer-thread step 4) | Wrong install-mode assumption; pre-flight LinkType/Target + cordis.patch.yml link: marker would have shown Junction | Link install: repo edits are already deployed; activate via process restart only |

---

- **Completed**: read-only inspection of all three evidence files; report covering the five numbered items.
- **Skipped**: no migration/installation executed (diagnosis-only scope); no baseline run (Mode A — "not collected").
- **Pending/residual risk**: none introduced; the fixture was not modified and the only file written is this report.
- **Rollback**: not applicable (no writes outside this report).
