# S10 Diagnostic Report — Paste Renaming & Version-Chip Follow-Ups

Plugin: `@org/dsh-attach-input` v0.2.10 (lib-only bundle, no build step). Evidence: `plugin-attachment-flow.js`, `plugin-version-chip.js`, `user-threads.md`, `tags-api-response.txt`.

## 1. Renaming design for pasted files

**Naming scheme** (exactly as users requested in the "pasted screenshots all have the same name" thread by kaylint):

- Pasted images → `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`… (counter shared across pastes and across the batch, so the Nth pasted image overall gets `(N+1)` except the first, which gets no suffix).
- Other pasted files → `paste_file.<ext>` with the same numbering: `paste_file.pdf`, `paste_file(2).pdf`…
- A pasted batch of k images allocates k consecutive slots in one pass; a "2nd" slot that has never been used still gets the next integer (the sequence advances monotonically; gaps may occur after removals and must not be refilled).

**Where the rename is applied — one acquisition path only.** All three paths funnel into `add()` (comment in `plugin-attachment-flow.js`: "The paste path, the drop path, and the file/folder picker all funnel into add()"). The rename must therefore be applied at the *paste acquisition site* (where `DataTransfer.items` / clipboard files are read), or in `add()` behind an explicit origin flag — never uniformly inside `add()`. Paths that must stay untouched, per the user ("those are my actual files"): drag-and-drop and the file/folder picker keep their real names verbatim. The existing batch-only duplicate guard `validateItems` (its `paths` Set throws `Duplicate attachment path`) stays, but collision handling between *batches* moves to the counter/naming step below.

**How the number is chosen.** Maintain a per-session monotonic counter per family (image vs non-image) — equivalently, count pasted records created so far in the session. Format: first occurrence gets no suffix; the n-th (n ≥ 2) gets `(n)` before the extension. Collision-safe option: after computing the candidate, check it against the authoritative taken-names source (item below) and bump until free — this also covers a picker file that legitimately collides with a paste name.

**Authoritative "names already taken" source: the live composer state snapshot, not the plugin records Map.** The name check should run against `input.state.getSnapshot().occurrences` — the actual currently-attached occurrences in the composer — at the moment of naming (inside the same synchronous pass as `insertReference`, re-reading the snapshot after each insert, mirroring how `add()` already re-reads `getSnapshot()` per item).

The records Map is the wrong source for three reasons visible in the fixture:

1. **It is a cache of the composer, not the composer.** The subscription in `add()` explicitly retires entries: `if (alive || record.inflight !== undefined) return; unsubscribe(); records.delete(ref)` — with the in-code warning "fires on ANY momentary empty snapshot". A momentary snapshot that shows no `occurrences` for the ref deletes the record even though the attachment is (or is about to be) present. A name derived from a cache that self-prunes on transient emptiness can hand out a name that is in fact still taken.
2. **It can both miss and invent state**: a retired record's label is no longer "taken" per the Map even though the occurrence is still rendered, and conversely the Map cannot know about names of non-pasted files it did not create (the drop/picker paths keep real names) — the snapshot knows all occurrences regardless of acquisition path.
3. **Records are plugin-internal bookkeeping** (`records.set(ref, record)` only on successful insert); the correct truth for "does this name already appear in the composer" is the thing that renders the names — the snapshot's occurrences, filtered by `o.source === SOURCE` plus the current naming counter.

## 2. Extension rule and displays (guidance, not scored)

- **Extension rule:** for pasted images the extension is the clipboard name's extension (`.png` from `image.png`); if the pasted file has no usable name, fall back to the MIME type (`image/jpeg` → `.jpg`, `` → no extension or a generic `.bin`). For non-image pasted files, keep the real extension if the clipboard provides one (`paste_file.pdf`), otherwise MIME fallback (`application/pdf` → `.pdf`), else no extension.
- **Dock chip:** shows `record.label` (the renamed display label — `paste_image(3).png`), as in `h('span', { className: 'dshca-name' }, record?.label ?? occurrence.label)`; falling back to `occurrence.label` only when the record was retired.
- **Uploaded path:** the upload body (`files: record.items.map(item => ({ path: item.path, ... }))`) must carry the **renamed path** so the composer-side file name matches the chip; the rename must happen before `insertReference` and before the body is built, never only at render time.

## 3. Follow-up B root cause: the chip trusted a stale cached remote value

**What the evidence shows.** `plugin-version-chip.js` fetches `https://api.github.com/repos/org/dsh-attach-input/tags?per_page=10`, picks the highest stable tag, and compares `semverCmp(tag, PLUGIN_VERSION) <= 0` → `renderCurrentChip(tag)`, which sets the text to `'✓ attach-input already the latest version ' + tag` — the **fetched** tag. The captured response `tags-api-response.txt` shows the failure window: `cache-control: private, max-age=60, s-maxage=300`, `x-cache: HIT`, `age: 178`, and the tag list body contains only `v0.2.9`, `v0.2.8`, `v0.2.7` — "v0.2.10 and v0.2.11 absent — the cached page predates both pushes" — while `git ls-remote` confirms both tags exist on the remote. So ~90 seconds after pushing v0.2.11, the CDN was serving a page older than *two* releases.

**Root cause chain:** user on v0.2.10 → chip fetched the stale CDN-cached tag list → highest visible tag = `v0.2.9` → `semverCmp('v0.2.9', '0.2.10') <= 0` → `renderCurrentChip('v0.2.9')` printed "already the latest version v0.2.9". Two independent bugs combine:

1. The fetched tag list is treated as ground truth although it is a cached, potentially hours-old value (`age: 178`, `s-maxage: 300`).
2. The green "already latest" chip renders the *remote* value even when the remote value is *older than the locally known running version* — displaying a number that contradicts the user's own installation. (The maintainer note in `user-threads.md` confirms: "the chip renders the fetched tag in the green 'already latest' chip when it is <= the running version.")

**Display rule instead:** compare exactly two values — the locally known running version `PLUGIN_VERSION` and the fetched latest tag `tag` — and always **display the locally running version, never the fetched one**, in the "current/latest" chip. Concretely:

- `tag > PLUGIN_VERSION` → update chip showing the fetched `tag` (the remote value is the only source for "what's available", which is fine here because it is only claimed as an available update).
- `tag <= PLUGIN_VERSION` → green chip showing `PLUGIN_VERSION` ("already the latest version 0.2.10"). When the stale remote says older-than-running, the local value is strictly more trustworthy ("next to a locally-known running version"); the user's own installation is direct evidence, a CDN-cached list is not. Optionally treat `tag < PLUGIN_VERSION` as a stale-cache signal and retry after `max-age` before rendering anything.
- `tag` undefined (fetch failed) → the existing `renderOfflineChip()` path, which correctly claims nothing.

## 4. Regression tests that would have caught both

**Follow-up A (renaming):**
1. Paste two screenshots (both `image.png`) in one batch → chips are `paste_image.png` and `paste_image(2).png`; upload bodies carry those two distinct paths.
2. Paste across two separate batches → numbering continues (`paste_image(3).png`), no reset and no duplicate.
3. Paste a non-image (`paste_file.pdf`, then a second `paste_file.pdf`) → `paste_file.pdf`, `paste_file(2).pdf`.
4. Drag-and-drop a file named `report.pdf` → chip and upload path remain `report.pdf` (no rename on the drop path).
5. File picker selection keeps real names, including a file actually named `paste_image.png` → it is not renamed, and a subsequent paste avoids the collision (counter/bump check against the snapshot).
6. Snapshot-transience test: with a subscription subscriber that fires on a momentary occurrence-free snapshot (as in `add()`), naming still does not reuse a name whose record was just retired — the snapshot's occurrences, not the records Map, decide "taken".

**Follow-up B (version chip):**
1. Stale-cache test: fetch returns `["v0.2.9","v0.2.8","v0.2.7"]` while running version is `0.2.10` → chip shows **0.2.10**, never "latest version v0.2.9" (this exact case is the v0.2.10 user's incident).
2. Update-available test: fetched `v0.2.11` vs running `0.2.10` → update chip shows v0.2.11.
3. Equal test: fetched tag equals running version → green chip, and it shows that version.
4. Freshness/header test: when the response is served from cache (`x-cache: HIT` with `age` beyond `max-age`) or lists a tag older than the running version, the chip either retries after cache expiry or renders the local version — it must not label a lower remote tag as "latest".
5. Offline/failed fetch → `renderOfflineChip()`, no version claim.

## 5. Lib-only release hygiene items touched

- **Hand-inlined version constants.** `PLUGIN_VERSION = '0.2.10'` in `lib/client.js` is a copy of `package.json`'s version with the fixture's own warning: "must be kept in sync with package.json at every release." Since there is no build step, no bundler injects it: each release needs either a scripted sed/replacement step in the release process (a check that fails the release if `lib/client.js`'s constant ≠ `package.json`), or a tiny pre-publish codegen. The v0.2.11 release must update this constant, and the fix in item 3 makes the *display* derive from it.
- **Bundle syntax check.** With no build step there is no compiler gate, so the release process must parse `lib/client.js` (e.g. `node --check` or an `new Function`/acorn parse) as a release gate; the hand-edit that ships renaming + chip fixes is exactly the kind of edit that can introduce a syntax error that a bundler would otherwise catch.
- **How users actually receive updates.** The plugin has **no host-side update endpoint** — the chip only *tells* the user an update exists; it does not install anything. Distribution is the lib-only bundle the user already loaded: users get v0.2.11 only by re-fetching/re-installing the bundle from the published source (re-running their install step, or a hard refresh that picks up the new file if served with proper cache invalidation — note the fixture's own HTTP headers show how aggressively these assets can be cached). So the chip fix and renaming ship together in v0.2.11, users on v0.2.10 see the *correct* local-version chip until they manually update, and the release notes should state that updates are manual. Version announcement ordering matters too: the incident shows tags propagate through the GitHub API cache minutes late, so the chip design must assume the tags endpoint lags the actual push (item 3).
- Related hygiene: the `tags?per_page=10` fetch silently misses when more than 10 tags exist or when pagination shifts (the stale page dropped two tags); consider `per_page` handling or accepting that only recent tags matter — but the primary defense is the local-version display rule, not fetch tuning.
