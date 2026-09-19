# S10 Diagnostic Report · Paste Renaming & Version-Chip Follow-Ups

Plugin under review: `@org/dsh-attach-input` v0.2.10 (lib-only client bundle, no build step).
Evidence: `plugin-attachment-flow.js`, `plugin-version-chip.js`, `user-threads.md`, `tags-api-response.txt` in the fixture pack. Read-only; no fixture files were modified.

---

## 1. Renaming design (Follow-up A)

### Naming scheme (matches the user request in `user-threads.md`, thread by kaylint)

- Pasted **images**: `paste_image.png`, then `paste_image(2).png`, `paste_image(3).png`, …
- Pasted **non-image files**: `paste_file.pdf`, `paste_file(2).pdf`, … — base name without a number on first use, `(n)` from the second collision on, identical numbering rules.
- The numbering lives **inside the parentheses before the extension**, never in the stem of subsequent files (`paste_image(2).png`, not `paste_image_2.png` or `paste_image(2)(2).png`).

### Where the rename applies — and what stays untouched

All three acquisition paths funnel into `add()` (per the excerpt comment in `plugin-attachment-flow.js`), so the rename must be scoped to the **paste path only**, decided by acquisition source, not by file name:

- **Rename**: files acquired via the clipboard/paste event (detectable via the paste event / clipboard API, and corroborated by the browser handing every pasted screenshot the same `image.png` name — but source of truth is the acquisition path, not the name).
- **Never rename**: the drag-and-drop path and the file/folder picker path. Kaylint is explicit: "keep the real names when I drag files in or use the picker — those are my actual files." A name-based heuristic (`if (name === 'image.png')`) would be wrong because a user's real file can legitimately be named `image.png` via drag/drop.

Mechanically, the rename must happen inside the paste acquisition path **before** `add()` builds the record — i.e. before `const label = item.path` and before `input.insertReference(...)`, and it must rewrite `item.path` itself (the upload body sends `files: record.items.map(item => ({ path: item.path, ... }))`, so renaming only `label` would leave the uploaded path stale). Drop/picker items must reach `add()` verbatim.

### How the number is chosen, and the authoritative "names taken" source

The next free number must be chosen against the **live composer state at insert time**: re-read `input.state.getSnapshot().occurrences` (filtered to this plugin's `SOURCE`) immediately before each insertion, take every path currently present (plus the other items already in the current batch), and pick the smallest `n ≥ 2` whose candidate is free. Because `add()` inserts items one at a time and re-reads the snapshot after each `insertReference` (the loop already does `snapshot = input.state.getSnapshot()`), the per-item re-read gives correct numbering within a multi-file paste.

**Why the records Map alone is the wrong source:** the excerpt's subscription retires entries non-deterministically:

```js
const unsubscribe = input.state.subscribe(() => {
  const current = input.state.getSnapshot();
  const alive = current.occurrences.some(o => o.source === SOURCE && o.ref === ref);
  if (alive || record.inflight !== undefined) return;
  unsubscribe();
  records.delete(ref);   // ← fires on ANY momentary empty snapshot
  changed();
});
```

The comment itself flags it: this fires on **any momentary empty snapshot**. A transient render where `occurrences` is briefly empty (mid-update, re-mount, subscription ordering) deletes a record whose attachment is still live in the composer. If uniqueness is derived from `records`, a "freed" name is then handed to the next paste while the original `image.png`-named occurrence still exists — producing a real duplicate that `validateItems` cannot catch (its `paths` Set is scoped to a single selection batch; the maintainer note confirms "two pastes of two screenshots both carry \"image.png\""). The live `occurrences` snapshot is ground truth; `records` is at best a display cache and must be treated as advisory, never as the collision authority.

---

## 2. Extension rule and display surfaces (guidance, not scored)

- **Extension rule**: keep the original extension when the pasted file has one (`paste_file.pdf`); when the clipboard file has no usable extension (common for pasted bitmaps named `image.png` or extension-less blobs), derive it from `file.type` via a MIME→extension fallback map (`image/png` → `.png`, `image/jpeg` → `.jpg`, `application/pdf` → `.pdf`, …). Unknown MIME with no extension: omit the extension rather than guessing.
- **Dock chip**: displays the post-rename `record.label` (`h('span', { className: 'dshca-name' }, record?.label ?? occurrence.label)`), so users see `paste_image(2).png` immediately.
- **Uploaded path**: because the rename rewrites `item.path` before the record is built, the upload body (`files: record.items.map(item => ({ path: item.path, ... }))`) sends the renamed path. Chip and upload must agree — one rename, one source, both surfaces derive from it.

---

## 3. Follow-up B root cause — the version chip lied

### What the evidence shows

`tags-api-response.txt` (captured ~90 seconds after pushing `v0.2.11`):

```
cache-control: private, max-age=60, s-maxage=300
x-cache: HIT
age: 178
```

and the tag list body contains only `v0.2.9`, `v0.2.8`, `v0.2.7` — **v0.2.10 and v0.2.11 are absent**, while `git ls-remote --tags origin` proves both exist on the remote. So the GitHub API's CDN served a **stale cached page** (`x-cache: HIT`, `age: 178`, cacheable up to `s-maxage=300`) that predates both recent pushes.

### Why the chip said "latest v0.2.9"

`plugin-version-chip.js` fetches the tag list, picks the max stable tag, then:

```js
if (semverCmp(tag, PLUGIN_VERSION) <= 0) { renderCurrentChip(tag); return; }
```

and `renderCurrentChip` renders `'✓ attach-input already the latest version ' + tag` — the **fetched** tag. With the cached response returning `v0.2.9` while the user's hand-inlined `PLUGIN_VERSION` was `0.2.10`, the comparison `v0.2.9 <= 0.2.10` took the "current" branch and the green chip displayed the stale fetched value `v0.2.9` as "latest", even though the running client was newer. The chip trusted a **cached remote value as ground truth next to a locally-known running version**.

### The display rule the chip should follow

Compare the fetched max stable tag against the locally-known `PLUGIN_VERSION`, and:

- **Green "already latest" chip displays the RUNNING version** (`0.2.10`), never the fetched tag. The locally-known running version is authoritative for "what you have"; a fetched tag that is `<=` running is only (weak, cache-tainted) evidence that nothing newer exists — it must never be shown as a version the user "is on".
- **Update chip (fetched tag > running) shows the fetched tag** — there the fetched value is the point of the message and being stale in the "older" direction is impossible, since a stale cache can only under-report, which keeps the user on the "current" branch.
- Optionally, harden the fetch itself: request with `cache: 'no-store'` (or a conditional/uncached endpoint such as `releases/latest`), and treat an ambiguous result as "offline" (`renderOfflineChip()`) rather than asserting "latest".

---

## 4. Regression tests that would have caught both follow-ups

### Follow-up A (renaming)

1. **Sequential pastes**: paste two screenshots in separate paste events → first lands `paste_image.png`, second `paste_image(2).png`; a third becomes `paste_image(3).png`.
2. **Multi-file paste batch**: a single paste event carrying two images numbers both correctly within the batch (catches numbering that only re-reads state once per `add()` call).
3. **Non-image paste**: paste `image.pdf` from clipboard → `paste_file.pdf`; a second → `paste_file(2).pdf`.
4. **Drop path untouched**: drag a real file named `image.png` → keeps `image.png` verbatim (the name-based-heuristic trap).
5. **Picker path untouched**: file/folder picker selection keeps original names, including a file literally named `image.png`.
6. **Cross-batch collision**: paste `image.png` twice (the exact kaylint scenario) → no duplicate path reaches `validateItems`; second becomes `paste_image(2).png`.
7. **Retirement resilience**: simulate a momentary empty `occurrences` snapshot between two pastes (the `records.delete` trigger) → the second paste still numbers `paste_image(2).png`, proving uniqueness derives from live composer state, not the records Map.
8. **Upload-path consistency**: after a rename, the upload body's `path` equals the renamed `item.path` (chip label and uploaded path agree).

### Follow-up B (version chip)

1. **Stale-cache green chip**: mock `fetch` returning exactly the captured payload (`["v0.2.9","v0.2.8","v0.2.7"]`) with `PLUGIN_VERSION = '0.2.10'` → the green chip must render **`0.2.10`** (running version); asserting the chip text does **not** contain `v0.2.9` would have failed pre-release and caught the bug.
2. **Update chip still shows fetched tag**: mock fetched tag `v0.2.11` > running `0.2.10` → update chip shows `v0.2.11`.
3. **Fetch failure / non-OK / timeout**: → offline chip, never a green "latest" assertion.
4. **Version-constant sync**: a release test asserting the hand-inlined `PLUGIN_VERSION` in `lib/client.js` equals `package.json`'s `version` (see item 5).
5. **Tag parsing**: non-stable tags (`v0.3.0-beta.1`) are filtered by `/^v\d+\.\d+\.\d+$/`; empty stable list → offline chip.

---

## 5. Lib-only release hygiene touched by these changes

- **Hand-inlined version constant**: `lib/client.js` has `const PLUGIN_VERSION = '0.2.10';` with the maintainer's own comment: "must be kept in sync with package.json at every release." There is no build step to do this mechanically, so every release risks drift (a drift would itself corrupt the chip's comparison). Hygiene item: a pre-publish/release check (e.g. a small script run before `npm publish`) that greps `PLUGIN_VERSION = '...'` out of `lib/client.js` and fails loudly on mismatch with `package.json` — plus a bundle syntax check (`node --check lib/client.js`, since there is no bundler/transpiler to catch syntax errors) on every changed lib file.
- **No host-side update endpoint**: this plugin ships as a lib-only client bundle; the chip is purely advisory. Users actually receive the update only by manually re-downloading/reinstalling the new bundle and reloading the client — nothing pushes code to them. Consequences: (a) the chip's only job is to tell a user a newer tag exists so they choose to reinstall, which is exactly why it must never misreport "already latest" (Follow-up B almost made rho_9 close the tab); (b) the update instructions surfaced with the chip (or README) must state the manual reinstall step; (c) because propagation depends on users acting on the chip, the fetch should minimize staleness (`cache: 'no-store'` or a less-cacheable endpoint) — the captured response's `s-maxage=300` CDN window is precisely the gap in which the bug fired (~90 s after the push, `age: 178`).
- Both follow-ups' fixes are client-bundle-only, so the release checklist is: update `package.json`, sync the inlined `PLUGIN_VERSION`, `node --check` the bundle, tag, and expect the chip's own CDN-staleness window to delay discovery of the new tag for up to a few minutes — document that so the next "your chip is stale" report is recognized as expected behavior rather than a lie.

---

### Summary

| Item | Verdict |
|---|---|
| 1 | Rename scoped to the paste path only; numbering against live `occurrences` snapshots; records Map is a fragile, non-deterministically-retired cache and must not be the collision authority |
| 2 | Extension from original name, MIME-map fallback; chip and upload both show the single renamed `item.path` |
| 3 | Root cause: GitHub CDN cached tag list (`x-cache: HIT`, `age: 178`, `s-maxage=300`) missing v0.2.10/v0.2.11 compared `<=` running and the green chip displayed the fetched tag; fix: green chip shows the running version, update chip shows the fetched newer tag |
| 4 | Paste sequential/batch/non-image tests, drop/picker name-preservation, cross-batch collision, momentary-empty-snapshot resilience; chip stale-cache/offline/update/fetch-failure tests plus version-constant sync |
| 5 | Release check syncing inlined `PLUGIN_VERSION` with `package.json`, `node --check` syntax gate, manual-reinstall update propagation, cache-busting fetch |
