# S10 · Paste Renaming & Version-Chip Follow-Ups — Report

Plugin under review: `@org/dsh-attach-input` v0.2.10 (community Web plugin, clipboard files →
composer attachments, lib-only bundle, no build step). Evidence: fixture pack
(`plugin-attachment-flow.js`, `plugin-version-chip.js`, `user-threads.md`,
`tags-api-response.txt`). Read-only analysis; nothing in the fixture was modified.

---

## 1. Follow-up A — unified renaming for pasted files

### Naming scheme (exact)

- Pasted **images** land as `paste_image.png`, then `paste_image(2).png`, `paste_image(3).png`, …
  (the extension is the original pasted file's extension when it has one — clipboard screenshots
  are typically `image.png` — so the stem is fixed and the extension is preserved).
- Other pasted files land as `paste_file.<ext>` (`paste_file.pdf`, `paste_file.zip`, …) with the
  same numbering: first occurrence bare, subsequent occurrences `paste_file(2).pdf`, …
- Image-ness is decided by MIME type (`item.file.type.startsWith('image/')`) — not by extension —
  because the browser-supplied clipboard name is unreliable evidence.

### Where the rename is applied — and which paths stay untouched

`add()` is the single funnel for three acquisition paths (paste, drag-and-drop, file/folder
picker). The rename must be applied **only on the paste path**, before any state is created:

1. The paste caller must tag the call with its acquisition source (e.g.
   `add(sessionId, items, { source: 'paste' })`, or a per-path wrapper). `add()` currently has
   no notion of source, so this is a required signature/plumbing change.
2. Inside `add()`, when `source === 'paste'`, compute the renamed path per item and use it for
   **everything downstream**: `record.label`, the `item.path` sent in the upload body, and the
   path passed to `insertReference()`. The dock chip (`record?.label ?? occurrence.label`) and
   the uploaded path then both carry the new name automatically, with no second code path.
3. **Drag-and-drop and file/folder picker paths pass `source: 'drop' | 'picker'` (or no rename
   flag) and keep `item.path` verbatim.** The rename is scoped at the acquisition-path boundary,
   not inside a shared helper that all paths call blindly, so real user file names can never be
   rewritten.

The rename must happen before `validateItems()`'s duplicate check and before
`insertReference()`, so that two pasted screenshots in one batch stop colliding on
`image.png` and the composer occurrence is created under the final name (renaming after insert
would leave the composer and the upload body disagreeing).

### How the number is chosen

The number is **derived fresh at each paste from the set of names already taken**, not from a
persistent counter:

- Collect the taken names from the authoritative source (below).
- If `paste_image.png` (resp. `paste_file.<ext>`) is not taken, use the bare name.
- Otherwise pick the **smallest k ≥ 2** such that `paste_image(k).png` is not taken. Smallest-gap
  filling, not `max+1`: if the user removes `paste_image(2).png` from the composer, the next
  paste reuses that slot, which matches how chat apps behave and never leaves unreachable holes.

Per batch, names claimed by earlier items of the same batch count as taken for later items, so a
single multi-file paste numbers itself consecutively.

### Authoritative "names already taken" source — and why the records Map alone is wrong

**Authoritative source: the composer's own live state — `input.state.getSnapshot()` and its
`occurrences` (the labels/names currently present in the session's input), unioned with the
names being claimed by the current batch.** The plugin's `records` Map is at best a secondary
overlay.

Why a plugin-side records cache alone is the wrong source, concretely from the fixture code:

- The records subscription retires entries on **any momentary empty snapshot**: the handler runs
  `current.occurrences.some(...)` and, if the ref is absent and nothing is inflight, unsubscribes
  and deletes the record. A transiently empty/rebuilding snapshot (re-render, state replacement,
  the same snapshot-refresh window the code already juggles around `insertReference`) makes the
  cache "forget" an attachment that is still in the composer. The next paste would then reuse
  `paste_image.png` for a genuinely new file while the original is still attached — a silent name
  collision, worse than the bug being fixed.
- Records also cannot see attachments that were removed, re-added, or restored by session
  replay/refresh outside the plugin's own `add()` calls; only the composer state knows what names
  are actually occupied right now.
- The records Map is keyed by `ref` and trimmed by liveness heuristics — it is a render cache,
  not a ledger. Conflict detection needs the durable, host-owned truth: the snapshot's
  occurrences. The rename function should re-read the snapshot at paste time (the code already
  takes `snapshot = input.state.getSnapshot()` at the top of `add()`) and treat that as the
  conflict set.

## 2. Extension rule and display (guidance, not scored)

- **Extension precedence:** use the extension of the original pasted name when it has one
  (`image.png` → `.png`). If the clipboard file has no usable extension, fall back to the MIME
  type: map `item.file.type` (`image/png` → `png`, `image/jpeg` → `jpg`, `application/pdf` →
  `pdf`, …); if MIME is empty/unknown, fall back to `bin`. The stem (`paste_image` /
  `paste_file`) is chosen by MIME image-ness as in §1.
- **Dock chip:** shows the renamed, human-facing label — `paste_image(2).png` — via the existing
  `record.label` flow (`record?.label ?? occurrence.label`). No truncation logic changes needed.
- **Uploaded path:** the upload body's `files: [{ path: item.path, ... }]` must carry the same
  renamed path, so the file the model/host sees has the identical name shown in the chip. The two
  must never diverge, which is why the rename is applied once, upstream of both.

## 3. Follow-up B — root cause and the display rule

### Root cause

The captured response in `tags-api-response.txt` shows the GitHub tags API answered **from a
shared CDN cache**: `x-cache: HIT`, `age: 178`, `cache-control: private, max-age=60,
s-maxage=300` — a page cached ~3 minutes earlier that predates both the `v0.2.10` and `v0.2.11`
pushes; `git ls-remote` proves both tags exist on the remote. So minutes after pushing
`v0.2.11`, `latestFromTags()` returned `v0.2.9` as "latest".

The chip logic then compounded the stale value: `semverCmp('v0.2.9', '0.2.10') <= 0` is true, so
`renderCurrentChip(tag)` ran and printed **the fetched tag** — `already the latest version
v0.2.9` — a claim that was wrong twice over: the user was running 0.2.10, and 0.2.11 existed.
The green "already latest" chip trusted a cached remote value as ground truth next to a
locally-known running version. ("A while later it changed its mind" = the CDN cache expired and
a fresh fetch returned `v0.2.11`.)

### The display rule the chip should follow

Compare exactly two values: **fetched latest tag vs. the locally running `PLUGIN_VERSION`.**

- fetched > running → update chip, showing the **fetched** tag (that is the one actionable fact).
- fetched <= running → "current" chip, showing **the running `PLUGIN_VERSION`, never the fetched
  tag**. The running version is locally known and trustworthy; the fetched tag is only an
  upper-bound estimate filtered through a CDN cache, and displaying it can only ever show the
  user an older version as "latest" — exactly the reported bug. When fetched < running, the most
  honest rendering is "running vX (registry data stale)"; at minimum the version string must be
  `PLUGIN_VERSION`.
- fetch failure / no stable tag → offline chip, no version claim.

Additionally: request the tags endpoint with `cache: 'no-store'` (or a cache-busting query
parameter) so the chip isn't fed an `s-maxage=300` page at all — but the display rule above is
the actual fix; cache-busting only narrows the window.

## 4. Regression tests that would have caught both

Follow-up A (renaming):

1. **Sequence test:** paste three `image.png` items (separate `add()` calls) → labels/upload paths
   are exactly `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`; a pasted
   `report.pdf` → `paste_file.pdf`, second → `paste_file(2).pdf`.
2. **Scope test:** drag-and-drop and picker acquisitions of the same files keep `item.path`
   verbatim even when a `paste_image.png` already exists (no rename, no numbering).
3. **Authoritative-source test (the scored trap):** simulate the fixture's subscription firing on
   a momentary empty snapshot so `records` is emptied while the composer snapshot still contains
   the occurrence; then paste again → the rename must still produce `paste_image(2).png` because
   it consults the composer snapshot's occurrences, not the (now empty) records Map. A
   records-based implementation fails this test by reusing the bare name.
4. **Gap-filling + collision test:** with `paste_image.png` taken and `paste_image(2).png` removed,
   next paste takes `(2)`; pasting when the user's own real file named `paste_image.png` is
   attached numbers from `(2)`.
5. **Consistency test:** dock chip label and upload-body `path` are identical and both renamed.

Follow-up B (chip):

6. **Stale-cache test:** mock `fetch` to return the captured cached page (max tag `v0.2.9`) with
   `PLUGIN_VERSION = '0.2.10'` → the green chip renders **0.2.10**, never `v0.2.9`. (Fails on
   v0.2.10 code, which prints the fetched tag.)
7. **Update-available test:** mocked tags max `v0.2.11`, running `0.2.10` → update chip shows
   `v0.2.11`.
8. **Offline test:** rejected/timed-out fetch → offline chip, no version claim.

## 5. Lib-only release hygiene items this touches

- **Hand-inlined version constant:** `PLUGIN_VERSION` is duplicated by hand in `lib/client.js`
  and must match `package.json` at every release (this bug class is exactly what made follow-up B
  hard to reason about). Add a release check — a test or pre-publish script asserting
  `PLUGIN_VERSION === package.json#version` — or move the constant to a single tiny
  `lib/version.js` that both the chip and any packaging metadata read, so there is one source of
  truth to bump.
- **Bundle syntax check:** with no build step, nothing transpiles or type-checks `lib/*.js` before
  it ships. Run `node --check lib/<every>.js` (plus the package's test suite) in the release
  checklist/CI so a syntax error cannot reach users. A lib-only plugin is published exactly as
  authored; the only safety net is a mechanical check you run yourself.
- **How users actually receive the update:** the plugin has **no host-side update endpoint** — the
  chip is informational only. Users get new code only when their package manager reinstalls/
  updates the package into their DSH profile (npm/browser cache must also be defeated: serve the
  bundle with no-cache headers or a versioned URL, since a hard-refresh was needed here even to
  see the new chip logic). Consequences for this release: (a) the fixed chip and renaming ship
  together in the next version; (b) the chip's "update available" state should link to the real
  update instruction (upgrade/reinstall command), not merely display a tag; (c) tag-fetch
  staleness (`s-maxage=300` CDN page) must be accounted for — request with `cache: 'no-store'`
  and render the running version in the "current" state as specified in §3.

---

## Summary of scored answers

1. **Conflict source:** composer snapshot occurrences (re-read at each paste), not the records Map,
   whose liveness subscription deletes entries on momentary empty snapshots and therefore
   under-counts taken names. **Scope:** rename only when the acquisition source is `paste`;
   drop/picker keep real names. **Numbering:** smallest unused ` (k)` gap-fill derived from the
   taken-name set at paste time.
3. **Root cause:** CDN-cached tags page (`x-cache: HIT`, `age: 178)) missing `v0.2.10`/`v0.2.11`;
   the chip rendered the fetched stale tag (`v0.2.9`) in the "<= running" branch. **Rule:**
   compare fetched latest vs. running `PLUGIN_VERSION`; show the fetched tag only when it is
   strictly newer; otherwise show the running version.
4. Tests 1–5 (renaming, scope, authoritative-source, gap-fill, chip/upload consistency) and 6–8
   (stale-cache, update-available, offline chip).
5. Version-constant single-source/check, `node --check` syntax gate on the lib-only bundle, and
   update delivery via package-manager reinstall + cache-busting, with the chip linking to real
   update instructions.
