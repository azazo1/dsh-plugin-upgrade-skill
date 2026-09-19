# S14 · Link-Install File-Lock Trap - Analysis Report

Task: diagnose a failed "deploy" of repo edits for the community Web plugin `@org/dsh-attach-input` (v0.2.11, lib-only bundle, no build step), where a browser refresh showed stale code, a Copy-Item into the profile's node_modules hit EBUSY, and a rename-aside "recovery" left both the repo and the profile without entry files.

Evidence used (read-only fixture): `copy-session.txt`, `profile-introspection.txt`, `maintainer-thread.md`, `README.md`. Skill mode: A · inspect (read-only); no files, installs, or migrations were executed. Per the benchmark brief's unattended authorization, the "confirm before write" step of the skill is satisfied by the brief itself and limited to this report.

---

## 1. What the profile entry actually is

`profile-introspection.txt` shows:

```
FullName : C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input
LinkType : Junction
Target   : {E:\dev\dsh-attach-input}
```

and `cordis.patch.yml` carries the link marker:

```
- node_modules/@org/dsh-attach-input  # link:E:\dev\dsh-attach-input (installed 2026-08-30)
```

The profile entry is **not a copied dependency - it is an NTFS junction pointing at the maintainer's repo**. The profile's `node_modules\@org\dsh-attach-input` and `E:\dev\dsh-attach-input` are **two pathnames for one and the same directory tree**. The repo checkout IS the installed copy; there is nothing to "deploy".

Consequence for deployment: editing `lib/client.js` / `lib/index.js` in `E:\dev\dsh-attach-input` **is** the deployment. Step 4 (Copy-Item of repo files into the profile's node_modules) was never necessary for this install - it was a no-op-at-best self-copy through the junction (source and destination resolve to the same physical files), and in practice it collided with the file locks described next. "Copy into node_modules" is the correct advice only for a *copied* dependency install; for a link install it is actively harmful (see section 5).

## 2. The two locks and their owners

There are two independent reasons the verification failed, and neither is the browser alone:

**Lock A - stale client code in the browser (why the refresh showed nothing).** The Web client bundle (`lib/client.js`) is served to the browser by the **running dsh host process** (`dsh web`), not read live from disk by the page. The maintainer's own instruction (thread step 2) was "restart dsh web and hard-refresh"; the user did only a browser refresh (step 3). A plain refresh can also reuse cached module artifacts, so even after a host restart the browser may run the old `client.js` from cache. Correct attribution: the *host* must be restarted to pick up changed files, and the *browser* needs a hard refresh (cache bypass) for `client.js`.

**Lock B - EBUSY on the lib files (why Copy-Item failed even with the tab closed).** The files `client.js`, `index.js`, `package.json` under the junction were held open by the **still-running dsh host process** (the Node host that loaded the plugin's entry/module map), not by the browser. Closing the browser tab does not terminate the host; the tab is only a client of the host's HTTP server. Windows keeps the loaded module files locked, so any in-place write (`Copy-Item -Force`) fails with "being used by another process" regardless of browser state. Releasing this lock requires fully stopping the dsh host process - a browser tab close or refresh is irrelevant to it.

## 3. Why rename-aside destroyed the SOURCE directory, and the exact recovery

Because the profile entry is a junction to `E:\dev\dsh-attach-input`, the "destination" path `C:\...\node_modules\@org\dsh-attach-input\lib\client.js` and the "source" path `E:\dev\dsh-attach-input\lib\client.js` are the **same file**. So:

- `Rename-Item ($dst + '\client.js') 'client.js.old2'` renamed the *repo's own* file - which is also why the subsequent `Copy-Item E:\dev\dsh-attach-input\lib\client.js ...` failed with "source does not exist": the rename had already removed that very name.
- `Get-ChildItem` on both directories shows the same listing (`client.js.old2`, `index.js.old2`) because both commands enumerate one directory through two names.

Net state: the plugin (and the repo) currently have **no entry files at all** - only `.old2` renames. Nothing was deleted or overwritten, however: the renamed files *contain the new edited code* (the edits were made in step 1, before all of this).

**Exact recovery from the current broken state:**

1. (Order matters for a clean rename on Windows) **Fully stop the dsh host** that is holding the lib files open - stop `dsh web` / the profile's host process; a browser refresh is not a host stop.
2. Rename the files back to their original names, in the repo path (equivalently the junction path - same directory):
   ```powershell
   Rename-Item E:\dev\dsh-attach-input\lib\client.js.old2 client.js
   Rename-Item E:\dev\dsh-attach-input\lib\index.js.old2  index.js
   ```
   (Rename succeeds once no process holds the files open; if it still fails, identify the lingering host process and stop it.)
3. **Verify syntax** before activating: `node --check E:\dev\dsh-attach-input\lib\client.js` and `node --check E:\dev\dsh-attach-input\lib\index.js` (this plugin is lib-only with no build step, so a parse check is the available static gate).
4. Confirm the tree is intact: `Get-ChildItem E:\dev\dsh-attach-input\lib` shows `client.js`, `index.js`; `package.json` still lists the expected entry points; `Get-Item` on the profile entry still shows `LinkType: Junction` targeting `E:\dev\dsh-attach-input`.
5. **Activate** per section 4. No file content was lost - the "broken" state is purely a naming accident.

## 4. Complete, ordered activation procedure for a link-installed lib-only Web plugin after repo edits

1. **Edit the repo files** (`E:\dev\dsh-attach-input\lib\*.js`). This is already "deployed" - the junction makes the repo the installed copy. Do **not** copy anything into node_modules.
2. **Static check** the edited files (`node --check` on each lib entry) - cheap protection before a host restart loop.
3. **Fully stop the running dsh host** for the profile (`dsh web` / the profile's host process). This releases Lock B (module file handles) and is what makes the host re-read `lib/index.js` (Host-half entry) and re-serve `lib/client.js` on next start.
4. **Restart the host** (`dsh web` for the profile). The host re-loads the plugin entry from the junctioned tree and re-publishes/serves the client artifact from the new `client.js`.
5. **Hard-refresh the browser** (cache bypass, e.g. Ctrl+F5 / empty-cache-and-reload) for the `client.js` URL. This addresses Lock A: a normal refresh can satisfy the client module from browser cache and show old behavior even after a correct host restart - exactly the stale-code symptom in thread step 3.
6. **Verify the new code actually loaded**, on both planes:
   - Host plane: confirm the plugin entry is active (host boot/log shows `@org/dsh-attach-input` loaded without errors; the new read-only host route from the edit responds).
   - Client plane: prove the served `client.js` is the new revision - e.g. fetch the client artifact URL and check for a marker unique to the hover-preview code, or exercise the registered contribution in the Web UI (hover an image attachment and see the preview). Do not accept a bare HTTP 200 as proof of the new code.
7. Only after verification, clean up any stray `.old2` names if recovery left them (after recovery step 2 above there should be none).

Order rationale: host stop must precede any file rename/write (releases Windows file locks); host restart must precede the browser hard refresh (the browser must fetch from the *new* host-served artifact - a hard refresh before the restart would just re-cache the old bytes).

## 5. The pre-flight check that should come before touching any file

Before any "deploy" action, determine the install mode of the profile entry:

```powershell
Get-Item C:\Users\me\.dsh\profiles\web\node_modules\@org\dsh-attach-input |
  Select-Object FullName, LinkType, Target
```

- **LinkType `Junction` (or `SymbolicLink`) with a Target** means a link install: the target directory IS the installed package; edits to the repo are live; the only activation work is host restart + browser hard refresh (section 4). Never copy, move, or rename files "in node_modules" - those operations act on the repo itself.
- **No LinkType / empty Target** means a copied dependency: the profile holds an independent copy, and updating it belongs to the package-manager track (the lockfile's own package manager, per the skill's Mode B rules) - not to ad-hoc `Copy-Item`, which bypasses the lockfile and can be defeated by file locks anyway.

Corroborate with the composition marker: `cordis.patch.yml` in the profile shows `# link:E:\dev\dsh-attach-input (installed 2026-08-30)` - the `link:` comment records the link-install provenance and date. Also note `Get-Item E:\dev\dsh-attach-input` itself has no LinkType: the *repo* is the real directory; only the profile-side name is the junction.

Why the generic "copy into node_modules" advice is actively harmful here: (a) it is redundant - source and destination are the same directory through the junction; (b) it invites exactly this EBUSY fight against the running host's file locks; (c) any fallback that renames or deletes "destination" files silently operates on the source repo, so a routine lock workaround (rename-aside) can strip the repo of its entry files - which is precisely the accident that happened.

---

## Report per the skill's validation structure

- **pre-existing / baseline**: not collected (read-only Mode A analysis of a static fixture; no commands executed against any live profile).
- **Completed**: full attribution of the failure chain from the fixture evidence; install-mode determination (Junction link install); recovery and activation procedures as above.
- **Skipped**: no runtime verification possible - the fixture is a static evidence pack (transcripts), not a live profile; no build/typecheck applicable (lib-only plugin, files currently misnamed).
- **Pending/residual risk**: none identified in the analysis; the physical file content was never lost (renames only). If the host process cannot be stopped cleanly, an external pinned restart is the fallback per the skill's host-upgrade discipline.
- **Rollback**: n/a (no changes were made; the fixture and benchmark repository were not modified).
- **Recommendations**: institutionalize the section-5 pre-flight (LinkType/Target + `cordis.patch.yml` marker) as the first step of any plugin-deploy runbook; for link installs, document "repo edit, host restart, browser hard refresh, marker-based verification" as the whole procedure.
