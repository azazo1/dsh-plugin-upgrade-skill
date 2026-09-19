# S10 Diagnostic Report · Paste Renaming & Version-Chip Follow-Ups

Plugin: `@org/dsh-attach-input` v0.2.10 (lib-only client bundle, no build step). Evidence: `plugin-attachment-flow.js`, `plugin-version-chip.js`, `user-threads.md`, `tags-api-response.txt`. Read-only diagnosis; no fixture or skill files modified.

---

## 1. Renaming design for Follow-up A (paste path only)

**Exact naming scheme** (as requested in `user-threads.md`, kaylint thread):

- Pasted images → `paste_image.png`, `paste_image(2).png`, `paste_image(3).png` …
- Other pasted files → `paste_file.<ext>`, `paste_file(2).<ext>`, … same numbering.
- Files from **drag-and-drop or the file/folder picker keep their real `item.path` untouched** — per kaylint: "those are my actual files."

**Where the rename must be applied.** All three acquisition paths funnel into the single `add()` in `plugin-attachment-flow.js`, so the rename must be applied at *entry to add() conditioned on the acquisition path*, not inside `add()` unconditionally. Concretely: tag each item with its origin (paste / drop / picker) at the point the browser event is captured (the `clipboardData.files` handler for paste; `dataTransfer` / `<input type=file>` handlers elsewhere), and rename **only** items whose origin is paste — before `validateItems()` and before the `label = item.path` assignment (the excerpt shows `const label = item.path;  // ← pasted "image.png" stays "image.png"`). Drop/picker items must reach `add()` with their original `item.path` and skip the renaming branch entirely. Do not rename in the upload layer or the dock renderer — the renamed name is the identity used everywhere downstream.

**How the number is chosen.** Keep a paste-session counter per base name that always advances on paste: first paste of a run gets the bare `paste_image.png`; each subsequent pasted item in the same session gets `paste_image(2)`, `paste_image(3)`, … monotonically (do not skip or reuse numbers just because an earlier record was removed). Images vs. other files keep independent counters keyed by their base name so a pasted PDF never consumes an image's number.

**Authoritative "names already taken" source: the live composer state, not the records Map.** The uniqueness check must read the current composer snapshot — `input.state.getSnapshot()` occurrences/paths (the same snapshot `add()` already reads after `input.insertReference`) — plus the names allocated earlier in this same in-flight batch. The plugin's `records` Map is the **wrong** authority because it is an evicting cache, not a record of occupied names: in `plugin-attachment-flow.js` its subscription deletes an entry whenever `current.occurrences.some(o => o.source === SOURCE && o.ref === ref)` is false, with the explicit comment `// ← fires on ANY momentary empty snapshot`. A transient snapshot (streaming render, list reset, re-mount) that momentarily shows no occurrences retires the record and its name, even though the file still exists in the composer or its upload is in flight. Numbering from that cache could re-issue `paste_image(2)` while the original was still present → duplicate paths, which is exactly what `validateItems()` then rejects. Cache is a display hint; the composer snapshot is ground truth. Additionally `validateItems()`'s duplicate check is only ``paths.has(item.path)'' within one batch (the maintainer note confirms: "Two pastes of two screenshots both carry 'image.png'"), so cross-batch uniqueness must come from the live snapshot scan.

## 2. Extension rule and what each surface displays (guidance, not scored)

- **Extension rule:** pasted images get `.png` from the browser's clipboard file name / `file.type` mapping (`image/png` is the dominant paste case). For other pasted files, prefer the original file-name extension when present; when absent or not derivable, fall back to the MIME type (via a MIME→ext map); when neither is available, omit the extension rather than inventing `.bin`. Never trust the pasted name for anything but the extension — the base is always replaced.
- **Dock chip:** shows the renamed label (`record.label`, e.g. `paste_image(2).png`); today's `h('span', { className: 'dshca-name' }, record?.label ?? occurrence.label)` already renders `record.label`, so only the label value changes.
- **Upload path:** the upload body `files: record.items.map(item => ({ path: item.path, ... }))` must carry the **renamed** path, so the pasted file lands under its new name; the internal file/blob reference stays the browser's clipboard `File`.

## 3. Follow-up B root cause: stale cached GitHub API response shown as ground truth

**Evidence chain.** `plugin-version-chip.js` fetches `https://api.github.com/repos/org/dsh-attach-input/tags?per_page=10`, reduces the stable tags with `semverCmp`, and if `semverCmp(tag, PLUGIN_VERSION) <= 0` renders the green "already the latest version" chip showing **the fetched tag**: `'✓ attach-input already the latest version ' + tag` (comment: `// ← shows the FETCHED tag`).

The captured response in `tags-api-response.txt` was taken "~90 seconds after pushing tag v0.2.11 (which does exist on the remote)" and shows the actual cause: `cache-control: private, max-age=60, s-maxage=300`, `x-cache: HIT`, `age: 178` — the response was served from a CDN cache whose copy **predates both pushes**; the tag list is `v0.2.9, v0.2.8, v0.2.7` with "v0.2.10 and v0.2.11 absent", while `git ls-remote --tags origin` confirms both refs exist on the remote. So the user on v0.2.10 got `latest = v0.2.9` from the stale page; `semverCmp('v0.2.9', '0.2.10') <= 0` → green "already the latest version v0.2.9" — an *older* tag labeled as latest, minutes after v0.2.11 shipped. It "changed its mind a while later" only when the cache expired (s-maxage=300s).

**Display rule the chip should follow.** The chip compares the fetched latest tag against the locally-known running version (`PLUGIN_VERSION = '0.2.10'`, hand-inlined in the bundle). Two fixes to the rule:

1. **Never show the fetched tag as "latest" in the up-to-date chip.** When `fetched <= running`, the *only* defensible statement is about the running version: "✓ attach-input v0.2.10 is up to date". The two values compared are the fetched latest vs. the running `PLUGIN_VERSION`; the value **shown** in the current-chip must be the **running version** (locally known, cannot be stale), and the fetched tag may appear only in the *update* chip (`renderUpdateChip(tag)`), where it names the available upgrade.
2. **Treat the cached response as a hint, not ground truth:** `x-cache: HIT` / `age` / short `max-age` mean the fetched list can lag a just-pushed tag. A fetched value older than the running version (`fetched < running`) is positive evidence of staleness — the running build cannot be newer than the true latest if the fetch were fresh — so that case should trigger a cache-busting revalidation (`Cache-Control: no-cache` request, or fetch the specific known tag / `releases/latest`) before declaring "already latest", and otherwise fall back to the neutral offline/offline-style chip rather than the confident green chip.

## 4. Regression tests that would have caught both follow-ups

**Follow-up A (renaming):**
- Paste three screenshots in one paste → assert paths `paste_image.png`, `paste_image(2).png`, `paste_image(3).png` and dock chip labels match.
- Paste two screenshots, then a PDF in a second paste → assert `paste_image(2).png` (counter continuity across batches) and `paste_file.pdf`; assert the second batch's `image.png` did not survive verbatim.
- Drop a file named `report.pdf` and pick a file `photo.jpg` → assert `item.path` is unchanged (no `paste_*` prefix) — pins the acquisition-path scoping.
- Paste an image, then simulate the composer snapshot momentarily losing the occurrence (the `records.delete(ref)` path), then paste again → assert the new name does **not** collide with the live composer's still-present name (authoritative-source regression: numbering must consult the snapshot, not the evicted Map).
- Non-image paste with extensionless/MIME-only clipboard file → assert the MIME-fallback extension.

**Follow-up B (version chip):**
- Unit-test the chip with the exact captured payload from `tags-api-response.txt` (tags `v0.2.9`, `v0.2.8`, `v0.2.7` + `x-cache: HIT`, `age: 178`) against a running `PLUGIN_VERSION = '0.2.10'` → assert the chip does **not** render a green "already the latest version v0.2.9", and that any up-to-date text shows the running version `0.2.10`, never the fetched tag.
- Simulated fresh response where latest `>=` running → assert the update chip shows the fetched tag.
- Staleness-revalidation path: fetched latest `<` running with cache headers → assert a second no-cache request is issued and, while unresolved, no false "latest" claim is rendered.
- Bundle-sync guard: a release check asserting the bundle's hand-inlined `PLUGIN_VERSION` equals `package.json` version (the excerpt notes it "must be kept in sync with package.json at every release").

## 5. Lib-only release hygiene items touched

- **Hand-inlined version constants:** the lib-only, no-build-step bundle duplicates the version as `const PLUGIN_VERSION = '0.2.10'` inside `lib/client.js`; every release must update it in lockstep with `package.json` (and any other inlined copies, e.g. a chip header). A release script or CI check that greps the bundle and compares to `package.json` prevents the drift that would itself corrupt the chip's comparison.
- **Bundle syntax check:** with no bundler/transpiler in the pipeline, the shipped `lib/*.js` is executed directly by the browser, so releases need an explicit syntax gate — `node --check lib/client.js` (or equivalent parse of every shipped file) in CI — since a typo ships verbatim with no compile step to catch it.
- **How users actually receive the update:** the plugin "has no host-side update endpoint" and is a client-side lib-only bundle; the chip is informational only — it can display "update available" but cannot install anything. The user receives v0.2.11 only by the manual install path (e.g. re-running the plugin's install/update command or replacing the bundle per the plugin's README) and reloading the Web Client; the chip's job is therefore to be honest about staleness (per item 3) and point at that manual step, never to imply an in-place self-update happened.
- Release versioning stays the plugin's own SemVer (`0.2.10 → 0.2.11`); it is independent of any DSH host cohort, and the tag pushed must appear in `git ls-remote` (as v0.2.10/v0.2.11 do in the capture) even though the tags API cache may lag — so announcements should not rely on the tags endpoint being fresh.
