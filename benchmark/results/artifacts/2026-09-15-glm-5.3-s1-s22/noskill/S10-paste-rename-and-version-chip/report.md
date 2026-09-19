# S10 · Paste Renaming & Version-Chip Follow-Ups — Analysis Report

Plugin under maintenance: @org/dsh-attach-input v0.2.10 (community Web plugin, clipboard
files → composer attachments; lib-only bundle, no build step). Evidence: the four files in
the read-only fixture (attachment-flow excerpt, version-chip excerpt, user threads, one
captured tags-API response).

---

## 1. Follow-up A — unified renaming for pasted files

### Naming scheme (exactly)

- Pasted images → paste_image.png, then paste_image(2).png, paste_image(3).png, …
- Other pasted files → paste_file.<ext> with the same numbering: paste_file.pdf,
  paste_file(2).pdf, … The extension is preserved from the original clipboard file name;
  the base name is discarded (only the extension survives).
- The counter is per kind+extension series (paste_image(N).png and paste_file(N).pdf
  number independently) and scoped to the current session's composer input.

### Where the rename is applied — and what stays untouched

The paste path, the drop path, and the file/folder picker all funnel into add(), and
add() cannot tell them apart. So the acquisition path must be distinguished at the point
of acquisition, where the DOM event source is still known, and the rename applied before
add() is called:

- In the paste event handler only: build the rename (paste_image.png / paste_file.<ext>
  + numbering) and pass the renamed path down (either rewrite item.path on a copied item,
  or pass an explicit displayName that add() prefers over item.path for label and the
  upload body).
- Drag-and-drop and the file/folder picker paths must keep real names — the user's
  actual files flow through unchanged; no renaming code runs on them. Scoping the change
  to the single paste acquisition path is the whole point: a rename inside add() itself
  would leak into drop/picker and break the keep-my-real-names requirement.
- The batch-level duplicate check in validateItems continues to operate on whatever
  paths the items now carry (renamed pasted paths are unique within a batch by
  construction; real-name duplicates within one drop/pick batch are still rejected).

### How the number is chosen

Before assigning paste_image.png (or paste_file.<ext>), scan the authoritative
names-already-taken set (below) for existing entries matching the pattern
paste_image(N).png (resp. paste_file(N).<ext>), where N is a bare number or absent
(absent = 1). Pick the smallest unused number: 1 → no suffix, 2 → (2), etc. Choosing the
smallest free slot (rather than max+1) also reuses slots freed when earlier pasted
attachments are removed. Apply the check per item as the batch is built, so a multi-file
paste of three image.png files becomes paste_image.png, paste_image(2).png,
paste_image(3).png in one go.

### The authoritative names-already-taken source

The live composer input state — input.state.getSnapshot()'s occurrences (the
labels/paths actually present in the DSH composer input for this session), plus the paths
of items already staged in the current in-flight batch. That is the ground truth the user
sees and the upload will send.

Why the plugin-side records Map alone is the wrong source: the excerpt's
alive-subscription retires a record whenever ANY momentary snapshot shows zero matching
occurrences — the composer's state machine can transiently produce an empty/intermediate
snapshot during reparsing or batched updates, so records.delete(ref) fires spuriously and
the Map silently under-counts. Consequences if numbering were derived from records:

- a record retired by a momentary empty snapshot frees a name that is still displayed in
  the composer → the next paste reuses it → visible duplicate chips and colliding upload
  paths (the exact bug the user filed, just delayed);
- records also knows nothing about attachments added by other means (other plugins,
  another tab, a page reload wiping the module-level Map while the composer persists), so
  it is neither complete nor durable.

The live snapshot is authoritative precisely because it is what the dock chip renders and
what the upload sends; records is at best a rendering cache and must never decide naming.

## 2. Extension rule and what each surface displays (guidance, unscored)

- If the clipboard file name has an extension, keep it (image.png → .png, report.pdf →
  .pdf).
- If it has none (or an empty name — some browsers hand clipboard blobs without one),
  derive the extension from file.type via a small MIME map (image/png → .png,
  image/jpeg → .jpg, application/pdf → .pdf, …); fall back to .bin for unknown/empty
  MIME.
- Dock chip displays the renamed label — set record.label to the rename result so the
  h('span', {className:'dshca-name'}, record?.label ?? occurrence.label) render shows
  paste_image(2).png.
- Uploaded path must carry the same renamed path (files: record.items.map(item =>
  ({ path: renamedPath, … }))), so what the recipient receives matches what the chip
  promised. Divergence between the two (chip shows rename, upload sends image.png)
  recreates the collision on the receiving side.

## 3. Follow-up B — why the chip claimed latest v0.2.9

### Root cause

The captured response (tags-api-response.txt) shows the GitHub tags endpoint served a
CDN-cached page: cache-control: private, max-age=60, s-maxage=300, x-cache: HIT,
age: 178 — a page cached up to ~5 minutes that predates both the v0.2.10 and v0.2.11 tag
pushes (the API listed only v0.2.9/v0.2.8/v0.2.7, while git ls-remote confirms v0.2.10
and v0.2.11 exist on the remote).

The chip logic then did two compounding things:

1. latestFromTags() returned the stale v0.2.9 as latest.
2. semverCmp('v0.2.9', '0.2.10') <= 0 → renderCurrentChip(tag), and the green chip
   echoed the fetched tag — the text 'attach-input already the latest version v0.2.9' —
   presenting a cached remote value as ground truth even though the locally-known running
   version (PLUGIN_VERSION = 0.2.10) already disproved it. A fetched tag older than the
   running version is by definition stale/incomplete data, and the code trusted it
   anyway.

### The display rule the chip should follow

Compare exactly the fetched latest tag vs. the locally-known running PLUGIN_VERSION:

- fetched > local → update chip, showing the fetched tag (update available v…).
- fetched ≤ local → green already-latest chip showing the local PLUGIN_VERSION — never
  the fetched tag. (Optionally, when fetched < local, treat the response as stale: skip
  the latest claim or note the check may lag, since the tags API can serve data up to
  s-maxage=300 old.)
- fetch failed/timeout/no stable tags → offline chip, as today.

The remote value is only ever used for the comparison and the update prompt; the running
version is the only value entitled to the words you are on.

## 4. Regression tests that would have caught both

### Follow-up A (renaming)

1. Sequential image paste: simulate three paste events each carrying a clipboard file
   named image.png (MIME image/png) into the same session → assert labels/upload paths
   paste_image.png, paste_image(2).png, paste_image(3).png.
2. Non-image paste: paste report.pdf then another report.pdf → paste_file.pdf,
   paste_file(2).pdf; extension preserved from the original name.
3. Other paths untouched: drag-drop a file literally named image.png and pick one via the
   file picker while paste_image.png exists → both keep image.png verbatim (and existing
   in-batch duplicate rejection still fires for a double-pick of the same real file).
4. Authoritative source, not the cache: force the failure mode of the records Map —
   deliver a momentary empty snapshot to the alive-subscription (retiring the record),
   then paste another image.png → the rename must still produce paste_image(2).png
   because it scanned the live composer occurrences, not records. Also: remove an
   attachment, paste again → smallest free slot is reused.
5. Upload-path/chip consistency: after rename, the upload body's path equals the chip
   label for every pasted item.

### Follow-up B (chip)

1. Stale-tags regression: stub fetch to return tags [v0.2.9, v0.2.8, v0.2.7] with
   PLUGIN_VERSION = 0.2.10 (exactly the captured response) → assert the green chip text
   contains 0.2.10 (the running version) and does not contain v0.2.9. This test fails on
   v0.2.10's code and pins the fix.
2. Newer tag: stub tags with v0.2.11 on top, local 0.2.10 → update chip shows v0.2.11.
3. Equal tag: stub tags with only v0.2.10 → green chip shows 0.2.10.
4. Offline: rejected/timed-out fetch → offline chip, no version claim.

## 5. Lib-only release hygiene this touches

- Hand-inlined version constant: PLUGIN_VERSION in lib/client.js is maintained by hand
  because there is no build step to inject it. Release checklist must include bumping
  package.json AND PLUGIN_VERSION in the same commit/tag, ideally with a cheap gate that
  greps the constant and fails if it diverges from package.json's version. A mismatch
  makes the chip lie in either direction (claims an update to the version you already
  run, or claims latest while outdated).
- Bundle syntax check: with no bundler in the loop, nothing validates the shipped lib/
  files — run a syntax check (node --check lib/client.js, or loading the module in a
  smoke harness) before tagging, so a stray edit cannot ship a bundle that throws on
  parse. Do this for every file in lib/.
- How users actually receive the update: this plugin has no host-side update endpoint —
  the chip is informational only. Users update by re-acquiring the published package
  through their package manager (npm/pnpm install of the new version, then reload so the
  new bundle is served). Release notes should say this explicitly, and the chip's copy
  should point users at that flow rather than implying it updated anything. Also
  document/accept that the GitHub tags API can lag a fresh push by up to ~5 minutes
  (s-maxage=300), which is precisely why rule 3 forbids presenting a
  fetched-older-than-running tag as truth.

Note on paths: the fixture references /app/fixture/ in the brief; the actual read-only
evidence read for this report was the fixture directory at
E:\deepseek-harness\dsh-plugin-upgrade-skill\benchmark\tasks\S10-paste-rename-and-version-chip\environment\fixture
(identical content: plugin-attachment-flow.js, plugin-version-chip.js, user-threads.md,
tags-api-response.txt, README.md). Nothing inside the fixture or the benchmark repository
was modified.
