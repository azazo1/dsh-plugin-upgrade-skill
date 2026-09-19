# S10 · Paste Renaming & Version-Chip Follow-Ups — Diagnostic Report

Plugin: `@org/dsh-attach-input` v0.2.10 (lib-only client bundle). Evidence: `fixture/README.md`, `plugin-attachment-flow.js`, `plugin-version-chip.js`, `user-threads.md`, `tags-api-response.txt`.

## 1. Renaming design (Follow-up A)

**Naming scheme** (as requested in `user-threads.md` by kaylint):

- Pasted **images** → `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`, …
- Other pasted **files** → `paste_file.<ext>`, `paste_file(2).<ext>`, … — same numbering.
- **Drag-and-drop and file/folder picker files keep their real names untouched.** The rename must be applied only in the paste acquisition path, *before* the item reaches the shared `add()` funnel (or, if inside `add()`, gated on a `source: 'paste'` discriminator carried by the item). Renaming inside `add()` unconditionally would violate the user's explicit "keep the real names when I drag files in or use the picker" requirement — the behavior change is scoped to one acquisition path.

**How the number is chosen:** the next free suffix `n` (n=1 omits the suffix, n≥2 yields `(${n})`) is the smallest value whose candidate name is not already taken, checked against the authoritative occupied-name set (below), including names assigned earlier within the same paste batch.

**Authoritative "names already taken" source: the live composer/attachment state, not the plugin-side `records` Map.** The plugin must read the actual occurrences currently inserted in the composer — e.g. `input.state.getSnapshot().occurrences` (plus any composer-side attachment listing it exposes) — collecting the labels/paths of attachments from *all* sources, and union it with names reserved by earlier items in the current batch.

**Why the plugin-side records cache alone is wrong:** `records` is a module-level `Map<ref, record>` that self-prunes. In `plugin-attachment-flow.js` lines 30–38, every ref subscribes to `input.state` and on any snapshot where `current.occurrences.some(o => o.source === SOURCE && o.ref === ref)` is false — and `record.inflight === undefined` — it unsubscribes and does `records.delete(ref)`, with the inline comment "← fires on ANY momentary empty snapshot". So a record can vanish from the cache while its attachment is still genuinely present in the composer (a transient snapshot with no occurrences), freeing its name for reuse and causing a `paste_image.png` → `paste_image.png` collision the very next paste. A cache that can briefly forget live entries is not a source of truth; the composer's occurrence snapshot is.

The in-batch `validateItems()` duplicate check (`paths.has(item.path)` → `Duplicate attachment path`) only guards one selection batch and throws; it neither covers cross-paste duplicates nor renames anything — it stays as a validation, but renaming must happen upstream of it so legitimate same-clipboard-name pastes no longer collide.

## 2. Extension rule and displays (guidance, not scored)

- **Extension:** for images, the extension comes from the clipboard file's MIME type mapped to a canonical extension (screenshot pastes are typically `image/png` → `.png`); if the MIME type is unknown or unmapped, fall back to the extension of the original clipboard name (e.g. `image.png`), else a safe default. For non-image pasted files, keep the original name's extension when present, otherwise derive from MIME type; a file with neither gets no extension rather than a guessed one.
- **Dock chip** shows the renamed label — `record.label` (the new `paste_image(2).png`), consistent with the existing render `h('span', { className: 'dshca-name' }, record?.label ?? occurrence.label)`.
- **Uploaded path** must use the same renamed `item.path` — the upload body already sends `files: record.items.map(item => ({ path: item.path, ... }))` — so the user-visible chip, the composer attachment, and the uploaded path are all the renamed name; the original clipboard name is never displayed or sent.

## 3. Follow-up B root cause and display rule

**Root cause: the "latest" value came from a stale CDN-cached GitHub API page, and the chip presented that cached value as ground truth.** Per `tags-api-response.txt`, captured ~90 s after pushing `v0.2.11` (which `git ls-remote` confirms exists on the remote): the response headers show `cache-control: private, max-age=60, s-maxage=300`, `x-cache: HIT`, `age: 178` — the served page was a Fastly/GitHub CDN cache older than both recent pushes, so the tag list it returned was `v0.2.9, v0.2.8, v0.2.7` — "v0.2.10 and v0.2.11 absent — the cached page predates both pushes". `latestFromTags()` (`plugin-version-chip.js` lines 7–16) accepted that list, computed latest = `v0.2.9`, and since `semverCmp('v0.2.9', '0.2.10') <= 0`, `startUpdateChip()` (line 21) called `renderCurrentChip('v0.2.9')`. `renderCurrentChip` renders `'✓ attach-input already the latest version ' + tag` — "← shows the FETCHED tag" (line 27) — so a user on v0.2.10 saw "latest v0.2.9": two lies at once (stale data shown, and the fetched tag printed instead of the running version). "A while later it changed its mind" once the CDN cache expired.

**Display rule the chip should follow:** compare `PLUGIN_VERSION` (the locally-known running version, hand-inlined in the bundle) with the fetched latest tag. **When the fetched latest is ≤ running (the "already latest" branch), the chip must display the locally-known running version `PLUGIN_VERSION`**, not the fetched tag — the fetched value has just been proven unreliable in exactly this branch, and the true statement is about the installed version. Only the update chip ("new version X available") may show the fetched tag, and even then a stale fetched value that is *older* than `PLUGIN_VERSION` must never trigger an update prompt (the existing `<=` guard is right for that). Optionally treat `age`/cache headers or a re-validation as a freshness signal, but the core fix is what gets rendered in the "current" branch.

## 4. Regression tests that would have caught both

Follow-up A:
- Paste two screenshots in separate pastes → chips/paths are `paste_image.png` then `paste_image(2).png` (no thrown duplicate error, no identical labels).
- Paste a batch of 3 images → `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`; paste non-image (`application/pdf`) → `paste_file.pdf`, next → `paste_file(2).pdf`.
- Numbering respects the authoritative composer-occupied-name set: with a live attachment named `paste_image.png` present in the composer while the plugin's `records` cache has just been pruned by a momentary empty snapshot (simulate the line 36 subscription firing), the next paste still yields `paste_image(2).png`, not `paste_image.png`.
- Drag-and-drop and picker adds keep their real names (including files genuinely named `image.png`) — the rename is scoped to the paste path only.

Follow-up B:
- `latestFromTags` / chip against a stubbed fetch returning the captured stale body (`v0.2.9, v0.2.8, v0.2.7` — the exact `tags-api-response.txt` payload) with `PLUGIN_VERSION = '0.2.10'`: asserts the green "already latest" chip renders **v0.2.10** (running version) and never the fetched `v0.2.9`; asserts no update chip appears.
- A fetched latest strictly greater than the running version renders the update chip with that tag.
- Fetch failure/timeout renders the offline chip.

## 5. Lib-only release hygiene

- **Hand-inlined version constants:** `lib/client.js` carries `const PLUGIN_VERSION = '0.2.10';` with the header note that it "must be kept in sync with package.json at every release". There is no build step to derive it, so the release checklist needs a mechanical sync step (a lint/pre-publish script that greps `lib/` for the constant and diffs it against `package.json`'s version) — a missed bump makes every comparison on the chip wrong by construction.
- **Bundle syntax check:** because the lib-only bundle is never compiled, ship a CI gate that parses the shipped `lib/*.js` with `node --check` (or an acorn/esbuild parse) so a syntax error can never reach users as a dead plugin.
- **How users actually receive updates:** this plugin has **no host-side update endpoint** — the chip is informational only; nothing auto-installs. Users get the new bundle the way they originally installed it (re-fetching/re-pasting the updated `lib/` bundle into their DSH setup, then reloading the page). Consequences: (1) the "already latest" wording must be accurate, since the user's only prompt to act is reading the chip; (2) after pushing a tag, the GitHub API CDN may serve a stale tag list for up to `s-maxage=300` s, so messaging should tolerate that window (the PLUGIN_VERSION display fix in item 3 handles the worst symptom); (3) the changelog/install instructions in the release should tell users how to refresh the bundle, since the plugin cannot push it to them.
