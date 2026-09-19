# S10 · Paste Renaming & Version-Chip Follow-Ups — Analysis Report

Plugin under maintenance: `@org/dsh-attach-input` v0.2.10 (lib-only bundle, no build step).
Evidence: fixture pack (attachment flow, version chip, user threads, captured tags-API
response). All analysis is read-only; no code was modified.

---

## 1. Follow-up A — renaming design for pasted files

### Naming scheme

- **Images pasted** (clipboard item is an image, by MIME type or original extension):
  `paste_image.png`, then `paste_image(2).png`, `paste_image(3).png`, …
- **Other pasted files**: `paste_file.<ext>` — e.g. `paste_file.pdf` — with the same
  `(2)`, `(3)`… numbering on collision.
- The first item gets no suffix; numbering starts at `(2)` for the second collision,
  matching the chat-app convention the user asked for.

### Where the rename is applied (and what stays untouched)

All three acquisition paths — paste, drag-and-drop, file/folder picker — funnel into
`add()`, which currently uses `item.path` verbatim (`const label = item.path`). The
rename must be **scoped to the paste path only**:

- Apply the rename where the paste handler constructs the item (or at the top of `add()`
  gated on `item.acquisition === 'paste'` / an equivalent flag threaded in from the
  paste handler). Rename **before** `input.insertReference(...)` so the composer
  occurrence, the record `label`, and the upload body all carry the final name — never
  rename after insertion or only at render time.
- **Drag-and-drop and picker items keep their real names** (`item.path` untouched).
  Those files arrive with genuine user-visible names; renumbering them would corrupt the
  user's mental model of their own filesystem.

This is a behavior change deliberately scoped to one acquisition path, per the maintainer's
own commitment in the thread.

### How the number is chosen

For each pasted item, compute the base name (`paste_image.png` or `paste_file.<ext>`).
If the base is free in the "names already taken" set, use it as-is. Otherwise try
`base(2)`, `base(3)`, … with the **extension preserved** — the `(n)` counter goes
before the dot, so `paste_image(2).png`, never `paste_image.png(2)`. Within a single
multi-file paste batch, each accepted name is immediately added to the taken-set so the
next item in the same batch sees it (the existing in-batch `paths` Set in
`validateItems` is per-batch only and cannot do this across batches).

### The authoritative "names already taken" source

**The DSH composer input state — `input.state.getSnapshot()` occurrences — is the
authoritative source**, unioned with the names being committed in the current `add()`
batch. Before assigning a name, list the labels/paths already present among the plugin's
occurrences in the snapshot and pick the first free candidate.

**Why a plugin-side records cache alone is the wrong source:** the module-level
`records` Map is *lossy by design*. Its subscription retires an entry whenever a
snapshot momentarily shows **zero** matching occurrences (`alive` check fails on any
momentary empty snapshot — e.g. during a composer state transition or history
compaction), at which point `records.delete(ref)` fires and the record's name silently
disappears from the cache while the attachment may still exist (or a same-named
occurrence added by another route may exist). Consequences if the cache were used as the
conflict source:

1. A retired entry frees a name that is actually still taken in the composer → the
   dedupe hands out a duplicate name, and the plugin's own `insertReference` /
   occurrence list now has two `paste_image.png` items.
2. Attachments inserted by drag-drop or the picker are often **never in the records
   Map's paste path** (and entries can be evicted as above), so a pasted
   `paste_image.png` could collide with a real `image.png`-adjacent state the cache
   simply doesn't know about.
3. The cache is also lost entirely on page reload, while composer input state is the
   durable, live truth the plugin itself already renders from.

So: read the snapshot's occurrence labels (the same source `changed()` re-renders from)
as ground truth, use the records Map only as a secondary index, and always re-check
against a fresh `getSnapshot()` at rename time.

---

## 2. Extension rule and display (guidance item, not scored)

- **Extension rule:** derive the extension from the original clipboard file name when it
  has one (`image.png` → `.png`). If the name has no usable extension, fall back to
  the item's MIME type mapped to an extension (e.g. `image/png` → `png`,
  `application/pdf` → `pdf`); if the MIME type is unknown/unmappable, omit the
  extension rather than guessing. Non-image pastes use `paste_file.<ext>` with the same
  derivation.
- **Dock chip:** displays the renamed label — `record.label`, i.e. the final
  `paste_image(2).png`-style name (existing `record?.label ?? occurrence.label` keeps
  working once `label` is set to the renamed value).
- **Uploaded path:** the upload body's `files: [{ path: item.path, ... }]` must send
  the **same renamed path** that the chip shows — one rename, applied once before
  insertion, and both the dock chip and the wire path derive from it. Never rename at
  upload-time only; the user would see one name in the UI and another on the server.

---

## 3. Follow-up B — root cause of the "latest v0.2.9" chip

### Root cause

The green "already latest" chip renders **the fetched tag**, not the running version:
`lbl.textContent = '… already the latest version ' + tag` where `tag` came from the
GitHub tags API. The captured response (`tags-api-response.txt`) shows why that tag was
stale *minutes after pushing v0.2.11*:

- `cache-control: private, max-age=60, s-maxage=300` with `x-cache: HIT` and
  `age: 178` — the CDN served a **cached page up to 5 minutes old** (s-maxage=300).
- That cached page listed only `v0.2.9`, `v0.2.8`, `v0.2.7` — it predates the
  `v0.2.10` and `v0.2.11` pushes (`git ls-remote` confirms both tags exist on the
  remote).
- `latestFromTags()` filtered to stable tags and reduced to the max — `v0.2.9` — from
  the stale list.
- `semverCmp('v0.2.9', '0.2.10') <= 0` is true, so `renderCurrentChip('v0.2.9')` fired
  and **asserted a cached remote value as ground truth**, telling a v0.2.10 user that the
  latest version was v0.2.9 — an *older* version than the one running. "A while later it
  changed its mind" = the cache aged out and the API returned fresh tags.

The chip has **no host-side update endpoint** (lib-only community plugin), so the remote
tag list is inherently a cache-lagged, eventually-consistent value; treating it as
authoritative next to the locally-known running version is the bug.

### The display rule the chip should follow

Compare **fetched latest tag vs. the locally-known running `PLUGIN_VERSION`**, but:

1. **When the fetched tag ≤ running version, display the running version, not the fetched
   tag**: "✓ attach-input v0.2.10 is up to date" — or, more honestly for the stale-cache
   case, "running v0.2.10; no newer release found". The locally-known running version is
   the only value the plugin can vouch for; a fetched tag that is *older* than the
   running version is proof of a stale cache, not information about "latest".
2. Only show an **update** chip when the fetched tag is strictly **greater** than
   `PLUGIN_VERSION` (`semverCmp(tag, PLUGIN_VERSION) > 0`) — in that direction the
   fetched value is actionable even if slightly lagged (worst case: the update notice
   arrives a few minutes late, which is benign).
3. Optionally treat `fetched < running` as a red flag for cache staleness and either
   retry after the cache window or suppress the "latest" claim entirely rather than
   printing a version that contradicts the running one.

The two values compared: **remote max stable tag** vs. **hand-inlined `PLUGIN_VERSION`**;
the one *shown* in the "current" chip: **`PLUGIN_VERSION`**.

---

## 4. Regression tests that would have caught both follow-ups

### Follow-up A (renaming)

1. **Paste-collision numbering:** simulate two consecutive pastes whose clipboard files
   are both named `image.png` (fresh `getSnapshot()` between them); assert the dock
   labels are `paste_image.png` and `paste_image(2).png`, and that the upload body's
   `files[].path` values equal those same names.
2. **In-batch numbering:** one paste of three image items all named `image.png`; assert
   `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`.
3. **Non-image paste:** paste a `report.pdf`; assert `paste_file.pdf` and
   `paste_file(2).pdf` on the second paste.
4. **Path isolation (the scoping test):** drag-and-drop an `image.png` and pick an
   `image.png` via the picker; assert both keep their verbatim names and do **not**
   consume paste-numbering slots; then paste an image and assert it still gets
   `paste_image.png` (drop/picker names don't collide-block the paste namespace, per
   the requested scheme).
5. **Authoritative-source test:** after inserting attachments, force the records-Map
   subscription to fire on a momentarily empty snapshot (retiring entries), then paste
   another `image.png`; assert the rename consults the composer snapshot and still
   produces `paste_image(2).png` — proving the cache alone isn't the conflict source.
6. **Extension fallback:** paste an image with no extension in its clipboard name; assert
   the extension is derived from MIME.

### Follow-up B (chip)

1. **Stale-cache chip:** mock `fetch` to return tags `["v0.2.9","v0.2.8","v0.2.7"]`
   with `PLUGIN_VERSION = '0.2.10'`; assert the chip **never displays a version older
   than the running one** — i.e. the text contains `0.2.10` (the running version), not
   `v0.2.9`.
2. **Newer-tag direction:** mock tags `["v0.2.11", "v0.2.10"]` with
   `PLUGIN_VERSION = '0.2.10'`; assert the update chip shows `v0.2.11`.
3. **Equal-tag:** mock `["v0.2.10"]` at `0.2.10`; assert the current chip shows
   `0.2.10`.
4. **Failure/offline:** fetch rejects or returns non-OK; assert the offline chip renders
   without any "latest version" claim.

---

## 5. Lib-only release hygiene items this touches

1. **Hand-inlined version constant:** `PLUGIN_VERSION = '0.2.10'` lives in
   `lib/client.js` because there is no build step to inject it. Every release must
   bump **both** `package.json` *and* this constant in the same commit — and since the
   chip's correctness (per item 3) now depends on the running version being locally
   truthful, a mismatch here directly reproduces follow-up-B-class lies. Add a
   pre-release check (or test) that parses `PLUGIN_VERSION` out of the bundle and
   compares it to `package.json`'s version.
2. **Bundle syntax check:** with no build step, `lib/` **is** the shipped artifact —
   there is no compiler to catch syntax errors. Before tagging, run at minimum
   `node --check` on each `lib/*.js` file (and ideally a smoke `import` of the
   bundle in a clean directory) so a typo can't ship as the "latest" tag.
3. **How users actually receive the update:** there is **no host-side update endpoint**
   for this community plugin — updates arrive only when users re-pull/reinstall the
   package (npm/registry or git pull) and **hard-refresh** so the browser drops the old
   cached bundle. Practical consequences:
   - The version chip is advisory only; it can't push an update. Its update chip should
     link to the release/install instructions rather than imply self-updating.
   - Browser/CDN caching applies to the tag API *and* potentially the bundle itself;
     release notes should tell users to hard-refresh after reinstalling.
   - Ship fixes for both follow-ups as one next release (e.g. v0.3.0 / v0.2.12) with the
     version-constant bump, syntax check, and the chip fix included, so the
     "already latest" message can be trusted going forward.

---

## Summary of key judgments

| Question | Answer |
|---|---|
| Conflict source for renaming | Composer `input.state.getSnapshot()` occurrences (fresh per rename), not the records Map |
| Why the cache is wrong | Subscription retires entries on momentary empty snapshots; cache also misses non-paste inserts and resets on reload |
| Paths renamed | Paste only; drag-drop and picker keep real names |
| Chip root cause | Green chip printed the *fetched* tag; GitHub tags API served a CDN-cached page (s-maxage=300, age=178) listing only v0.2.9 |
| Chip display rule | Compare fetched max tag vs. local `PLUGIN_VERSION`; when fetched ≤ running, show the **running** version; update chip only on strictly-greater fetched tag |
