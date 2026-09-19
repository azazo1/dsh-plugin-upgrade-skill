# S10 — paste renaming and version-chip follow-ups

## 1. Paste-only renaming design

Carry acquisition provenance into `add()`, for example
`add(sessionId, items, { acquisition: 'paste' })`.  The paste handler passes that
value; the drop handler and file/folder picker pass their own values.  Do not infer
provenance from a filename such as `image.png`.

For a paste, normalize a cloned item descriptor before `validateItems()` runs.  The
clone keeps the original `File` object/bytes but replaces the transport/display path
with the generated name.  This ordering matters: several clipboard items can all
arrive as `image.png`, so validating the raw items first would reject the batch as a
duplicate before the renamer gets a chance to make them unique.

The generated candidates are:

* an image: `paste_image.<ext>`;
* any other pasted file: `paste_file.<ext>`.

The first free candidate has no numeric suffix.  Subsequent candidates use
`paste_image(2).<ext>`, `paste_image(3).<ext>`, or the corresponding `paste_file`
name.  For each base/extension, choose the smallest available suffix (try the
unsuffixed name first, then 2, then 3, and so on), rather than using the batch index
or merely adding one to the largest observed number.  Add every chosen name to a
temporary `reserved` set as it is allocated, so duplicate raw names within one paste
batch are also handled.

The initial `taken` set must come from a fresh
`input.state.getSnapshot().occurrences`—filtered to the plugin's attachment source
(`SOURCE`) and projected to the occurrence's canonical attachment path/name (the
same name represented by its label/path).  This is the authoritative live composer
state.  Include the temporary reservations for the current batch, and refresh the
snapshot before later insertions if the state can be changed between insertions.
After normalization, run `validateItems()` on the normalized descriptors and use
those descriptors for both the record and `insertReference()`.

The `records` map is bookkeeping, not the conflict database.  Its alive subscription
deletes a record when a snapshot briefly contains no occurrence, so it can lose a
still-live name during a transient empty snapshot (and it can also retain a stale
name after removal).  Using it to decide availability would either permit a real
collision or invent one.  A record can still provide metadata for rendering, but
availability must be derived from the current composer snapshot.

For drop and picker acquisitions, pass the descriptors through unchanged.  Their
real paths/names must reach validation, the record, the dock, and the upload body;
the renaming branch must not run for those paths.

## 2. Extension, dock, and upload behavior

Take the extension from the original pasted filename/path when it has a usable
suffix.  If it has no usable suffix, derive one from `item.file.type` using a MIME
mapping (for example `image/png` -> `png`, `image/jpeg` -> `jpg`, and
`application/pdf` -> `pdf`).  Normalize the generated extension to a safe lowercase
suffix.  If both sources are absent or unknown, use a deterministic safe fallback
such as `bin`, rather than producing an ambiguous name.

Classify an image from the file MIME (`type.startsWith('image/')`, with a sensible
extension fallback only when the browser supplied no type); the extension selection
still follows the original-name-first rule above.  Thus the normal clipboard case
produces `paste_image.png`, while a nameless JPEG can become `paste_image.jpg`.

The generated path is the user-visible attachment name as well as the upload path:

* set `record.label` from the normalized item path, so the dock chip displays
  `paste_image.png`/`paste_image(2).png` (or the `paste_file` equivalent);
* put the normalized item in `record.items`, so
  `files: record.items.map(item => ({ path: item.path, ... }))` uploads that same
  generated path.

Do not try to mutate the read-only `File.name`; the attachment descriptor's path/name
metadata is the right place to apply the rename.  Drop/picker chips and uploaded
paths remain their original names.

## 3. Follow-up B root cause and display rule

The tag endpoint was successfully reached, but its response was not current.  The
captured response was a CDN/cache hit (`x-cache: HIT`, `age: 178`) governed by a
cache lifetime and contained only `v0.2.9`; it predated both `v0.2.10` and the newly
pushed `v0.2.11`.  `latestFromTags()` therefore returned `v0.2.9`.  Since
`semverCmp(tag, PLUGIN_VERSION) <= 0` for fetched `v0.2.9` and local `0.2.10`,
`startUpdateChip()` took the current-version branch, but `renderCurrentChip(tag)`
printed the stale fetched tag.  Cache expiry later made the symptom disappear.

Compare these two values semantically:

1. the highest stable tag returned by the remote check (`tag`, including its `v`
   prefix as handled by `semverCmp`); and
2. the locally known running bundle version (`PLUGIN_VERSION`).

If `tag` is greater, show an update chip containing the remote tag.  If `tag` is
equal to or lower than the local version, show the green current chip containing
`PLUGIN_VERSION`, never the fetched tag—for this incident it must say
`... latest version v0.2.10`, not `v0.2.9`.  An absent/failed result remains the
offline state.  The local running version is the only trustworthy value for what
the current bundle actually is; a cached lower remote value must not overwrite it.

## 4. Regression tests

Attachment tests should cover:

1. A single paste batch containing three image items all named `image.png` produces
   `paste_image.png`, `paste_image(2).png`, and `paste_image(3).png`, and passes
   validation.
2. Two separate paste operations also continue the sequence by reading the current
   composer state, rather than restarting at the base name.  Include a non-image
   item such as a PDF and assert `paste_file.pdf` then `paste_file(2).pdf`.
3. A live `SOURCE` occurrence for `paste_image.png` present in
   `input.state.getSnapshot()` but absent from `records` forces the next paste to
   use `(2)`.  A simulated transient empty snapshot must not make the records
   subscription the source of truth.  Conversely, a records-only stale entry must
   not force a suffix when the authoritative snapshot has no such occurrence.
4. A drop item and a picker item with real names (including names that are not
   paste-generated) retain those exact names in the record, dock label, and upload
   body.  This guards the acquisition-path boundary.
5. Assert both surfaces for a paste: the dock reads the generated `record.label`,
   and the upload request reads the generated `record.items[].path`.
6. Exercise extension precedence: `photo.webp` with a conflicting MIME keeps
   `.webp`; a nameless file with `image/png` or `application/pdf` gets the MIME
   fallback.

Version-chip tests should mock the tag response and assert:

* local `0.2.10` plus stale remote `v0.2.9` renders the green chip with
  `v0.2.10` and does not claim that `v0.2.9` is current;
* local `0.2.10` plus remote `v0.2.11` renders an update chip for `v0.2.11`;
* equal local/remote versions render the current chip with the local version; and
* an unavailable/invalid response renders the offline chip.

The first case is the release-blocking regression from the captured response; the
second ensures the fix does not suppress a real update.

## 5. Lib-only release hygiene

Because there is no build step, the release checklist must explicitly:

* bump `package.json` and every hand-inlined shipped version constant, especially
  `PLUGIN_VERSION` in `lib/client.js`, to the same version;
* inspect the actual lib bundle (and search for the previous version) so the file
  users load contains the new code and version;
* run a syntax check on the shipped JavaScript, e.g. `node --check lib/client.js`
  (and repeat for any other shipped JS entry files), plus the focused regression
  tests; and
* publish/distribute the updated package or lib artifact and tag it only after those
  checks pass.

The version chip only checks tags and reports status—it is not an updater.  With no
host-side update endpoint, users receive the fix by upgrading/reinstalling the
published plugin/package (or by the host's normal mechanism for loading a newly
published plugin), then reloading the plugin/bundle.  A hard refresh of a page that
still has the installed `v0.2.10` lib cannot install `v0.2.11`; a Git tag alone is
not delivery.
