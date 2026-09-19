# S14 · Link-Install File-Lock Trap — Diagnostic Report

Evidence pack (read-only): profile-introspection.txt, copy-session.txt, maintainer-thread.md.

---

## 1. What the profile entry actually is — Junction install semantics

profile-introspection.txt shows, verbatim:

    FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
    LinkType : Junction
    Target   : {E:\dev\dsh-attach-input}

    FullName : E:\dev\dsh-attach-input
    LinkType :
    Target   : {}

The profile entry is an **NTFS junction** (a directory link) pointing at the source repo E:\dev\dsh-attach-input. The repo itself is a plain directory (no LinkType/Target), confirming the link lives on the profile side only. The cordis.patch.yml marker confirms it: `- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)`.

**Deployment semantics:** a junction is not a copy. There is exactly **one** directory on disk; the profile path and the repo path are two names for the same files. "Deploying" a repo edit therefore requires **zero file operations** — editing E:\dev\dsh-attach-input\lib\client.js already changed what the profile loads at C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input\lib\client.js. The repo tree **is** the installed copy.

**Was Copy-Item ever the right move?** No — never for this install mode. Every Copy-Item E:\dev\dsh-attach-input\lib\*.js ...\@org\dsh-attach-input\lib\ in copy-session.txt copies a file **onto itself** through the junction: source and destination are the same directory. Even without any lock it would be a no-op (or self-clobber), and with locks it fails with EBUSY. The maintainer's assumption in maintainer-thread.md step 4 ("I assumed the profile must be running an installed COPY of the plugin") is the root-cause misdiagnosis.

## 2. The two locks and their owners — why refresh is stale and why EBUSY persists

There are two independent "locks" (only the second is a real file lock):

**a) Stale browser code.** The Client bundle lib/client.js is served by the **running dsh web host process** (the Node process hosting the profile's Web plugins), not by the browser. The browser tab only holds the copy it already downloaded; a normal refresh re-requests the bundle, but the *host* still has the **old module loaded in memory** (Node's module cache does not re-read files per request). So refreshing the tab shows old behavior because the serving process never reloaded the module — no new code ever left the host. maintainer-thread.md step 3: "The user refreshed the browser tab only — nothing changed."

**b) The real file lock (EBUSY).** The running dsh host process holds the plugin's lib files open/loaded (loaded module state, open handles, or a watcher on the plugin tree). This is why copy-session.txt shows the same `IOException ... being used by another process` for client.js **even after the maintainer closed the browser tab and waited**: the browser tab never owned the file lock — the host process did. Closing a tab only destroys the browser's in-memory copy of the bundle; it releases nothing on disk. Lock owner to attribute: **the running dsh host**, not the browser.

## 3. Why rename-aside destroyed the SOURCE directory, and the exact recovery

**Why both directories lost the files:** Rename-Item C:\...\@org\dsh-attach-input\lib\client.js 'client.js.old2' operates through the junction. The destination path resolves to E:\dev\dsh-attach-input\lib\client.js — the same file. So the renames renamed the **source repo's** files in place (rename succeeds on a file the host holds open where delete/replace does not), and the subsequent Copy-Item 'E:\dev\dsh-attach-input\lib\client.js' ... failed with "Cannot find path ... because it does not exist" because the source had just been renamed away. copy-session.txt confirms the end state — **both** Get-ChildItem E:\dev\dsh-attach-input\lib and Get-ChildItem $dst list only client.js.old2 and index.js.old2; the plugin has no entry files under either name. The .old2 files contain the NEW hover-preview edits (they are today's edited files, renamed).

**Recovery from the current broken state:**

1. Make the tree valid again by renaming back to the canonical entry names. Do this exactly once, from either side of the junction (both views are the same files):
   - Rename-Item E:\dev\dsh-attach-input\lib\client.js.old2 client.js
   - Rename-Item E:\dev\dsh-attach-input\lib\index.js.old2 index.js
   Then verify BOTH paths (repo and profile) list client.js / index.js.
2. **Verify syntax** before activating: node --check E:\dev\dsh-attach-input\lib\client.js and node --check ...\index.js — a lib-only plugin ships these files verbatim with no build step, so a syntax error would crash the web profile at load.
3. Then run the full restart/activation procedure from item 4. No copy step exists anywhere in the recovery — the junction already "installs" whatever sits in the repo.

## 4. Complete ordered activation procedure for a link-installed lib-only Web plugin

1. **Edit** the repo files in place (E:\dev\dsh-attach-input\lib\client.js, lib\index.js). No deployment/copy step — the junction already makes the edit visible at the profile path.
2. **Syntax-check** the shipped files (node --check on each); there is no build step to catch errors.
3. **Fully stop the dsh web host process** (the Node process running the profile), not just the browser. It is the process that (a) loaded the old modules into its module cache and (b) holds the lib files locked. Until it exits, no reload is possible and any file replacement EBUSYs.
4. **Restart the host** so it re-reads and re-instantiates the plugin from the (junctioned) profile path, loading the new code from disk.
5. **Hard refresh (cache bypass, e.g. Ctrl+F5) the browser** for client.js. Required because the browser caches the Client bundle: even with a freshly restarted host, a normal refresh can serve the previously cached client.js and keep showing old behavior. The browser cache is the second, independent staleness source after the host's module cache.
6. **Verify the new code actually loaded**: inspect the served bundle (DevTools → Network → the client.js response contains a hover-preview identifier), exercise the new read-only host route, or ship a runtime-visible version/log marker inside client.js.

Order matters: nothing browser-side matters until the host is restarted; a hard refresh before that gets stale modules from the old host, and even after a restart a normal refresh may serve the cached bundle.

## 5. Pre-flight check: determine install mode BEFORE touching any file

Before any "deploy" action, run `Get-Item <profile entry> | Select-Object FullName, LinkType, Target` on the profile's node_modules entry:

- **LinkType Junction (or SymbolicLink) with a Target** → link install. The Target path (E:\dev\dsh-attach-input) is the real directory; the repo tree **is** the installed copy. Correct action: edit repo → restart host → hard-refresh browser. **No copying, ever.**
- **No LinkType/Target** → a copied dependency; only then is copying rebuilt artifacts into the profile node_modules the relevant (still lock-sensitive) operation.
- Cross-check the cordis.patch.yml install marker, which here reads `# link:E:\dev\dsh-attach-input` — a second, zero-cost signal available before any file was touched.

**Why the generic "copy into node_modules" advice is actively harmful for link installs:** through a junction the copy is a self-copy — source and destination are the same directory, so it can only no-op or self-clobber, and against a host-held lock it EBUSYs. Worse, the customary "rename the locked file aside, then copy" workaround, applied through the junction, renames the **source repo's** files, leaving repo and profile simultaneously broken — exactly the client.js.old2 / index.js.old2 state recorded in copy-session.txt. Checking LinkType/Target (and the patch-yml link marker) first would have prevented steps 4 and 5 entirely.
