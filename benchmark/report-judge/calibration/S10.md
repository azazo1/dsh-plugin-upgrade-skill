# S10 Follow-ups design (reference answer)

## 1. Renaming design — scheme, scope, numbering, conflict source

**Scheme**: pasted images become `paste_image.<ext>`; every other pasted file becomes
`paste_file.<ext>`. On collision with an occupied name, append `(2)`, `(3)`… before the
extension (`paste_image(2).png`), incrementing until free.

**Scope**: apply the rename **only on the paste path** (the clipboard-files entry point),
before `add()` mints the record. Drag-and-drop and the file/folder picker funnel into the
same `add()` but must keep their real names — rename at each acquisition site, never inside
`add()` itself, or drops would be renamed too.

**Numbering / conflict source**: the occupied-name set must be built from the **live
composer occurrences** (`snapshot.occurrences` filtered to our source, by chip label) — the
authoritative state — unioned with the records Map as an accelerator for in-flight entries
whose chip has not landed yet. My records Map alone is the wrong source: the
alive-subscription retires a record whenever ANY snapshot momentarily shows no occurrences
(reconcile/remount flicks), so a cache-only set silently empties and the numbering restarts
at the base name while the chip is still on screen.

**Both views must show the renamed name**: the record's `label` (dock chip) and the
uploaded `files[].path` (so the file that lands in the attachments directory is
`paste_image(2).png` exactly as displayed).

## 2. Extension rule

Prefer the extension of the original clipboard file name; when the browser hands a name
with no extension, fall back to a small MIME map for the common clipboard types
(`image/png → .png`, `image/jpeg → .jpg`, `image/webp → .webp`, `image/gif → .gif`,
`application/pdf → .pdf`, `text/plain → .txt`, …). Unknown MIME with no extension ships
extension-less; the numbering still works because it is applied to the full
base+extension string.

## 3. Follow-up B — root cause and the display rule

The captured response shows the tag endpoint was a **CDN cache HIT** (`x-cache: HIT`,
`age: 178`, page listing only up to v0.2.9) served ~90s after v0.2.11 was pushed —
GitHub's tags API caches for minutes after a push. My chip then rendered the **fetched
tag** verbatim in the green "already latest" chip, so a user on 0.2.10 was told the latest
was v0.2.9. The fetched value is not ground truth during that window.

**Rule**: compare the fetched tag against the running `PLUGIN_VERSION`; decide
"update available" only when the fetched tag is strictly newer, and for the "already
latest" chip display **whichever of the two is newer** (when the fetched tag is older than
the running build, show the running version). Never present a fetched remote value that is
older than the local build as the latest.

## 4. Regression tests that would have caught both

1. Paste the same-named clipboard file twice (and a third time): assert `paste_image.png`,
   `paste_image(2).png`, `paste_image(3).png` coexist — two composer occurrences + two
   dock chips, none displaced; the committed upload paths carry the renamed names.
2. Drop the same-named real file twice via the drop path and once via the picker: assert
   the real names are untouched (scope gate).
3. Delete a chip, then paste the same name again: the freed name may be reused (conflict
   set is live state, not history).
4. Version chip: with the tag endpoint stubbed to a stale older tag, a running version
   newer than it must NOT render the stale tag as "latest" (assert the shown version is
   the newer of the two); with a strictly newer stub, the update chip appears.

## 5. Lib-only release hygiene

- The running version is **hand-inlined** next to `package.json` — both must be bumped in
  the same commit, and the bundle re-checked with `node --check` (no build step exists to
  catch drift).
- Users receive updates by **hard refresh** (the served artifact is the edited file); with
  no host-side update endpoint, the update chip's action is copying the pinned-tag install
  prompt for a session to run — so the chip's notion of "latest" is the update funnel
  itself and must not be CDN-lagged.
