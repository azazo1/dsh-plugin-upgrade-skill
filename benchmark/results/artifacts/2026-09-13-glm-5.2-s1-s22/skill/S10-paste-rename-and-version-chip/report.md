# S10 · Paste Renaming & Version-Chip Follow-Ups — Analysis Report

Task: read-only design/diagnosis report for `@org/dsh-attach-input` v0.2.10 (lib-only bundle, no build step).
Evidence: fixture pack (attachment flow + dock chip excerpt, version-chip excerpt, user threads, captured tags-API response).
Mode: Mode A–style read-only inspection per the plugin-upgrade skill; no files under the fixture were modified, no installs or migrations executed.

---

## 1. Follow-up A — renaming design for pasted files

### Exact naming scheme

- Pasted **images**: `paste_image.png` for the first, then `paste_image(2).png`, `paste_image(3).png`, …
- Other pasted **files**: `paste_file.<ext>` for the first, then `paste_file(2).<ext>`, `paste_file(3).<ext>`, …
- Numbering is per base stem (`paste_image` / `paste_file`), continuing across separate paste actions within the same session input: the first occurrence of a stem carries no suffix; each subsequent one takes `max(existing suffix) + 1`.
- Detection of "image" should be by MIME type (`image/*`), not by the file name (the clipboard name is always `image.png` anyway, but a pasted image could in principle arrive under another name).

### Where the rename is applied — and which paths stay untouched

The paste path, the drop path, and the file/folder picker all funnel into `add()`. The rename must be applied **on the paste acquisition path only**, at the point where clipboard `DataTransfer` items are converted into the `{ file, path }` items — i.e. in the paste handler before calling `add()` (or at the very top of a paste-specific entry, never inside shared `add()` logic). Concretely the renamed value must replace **both** places the name escapes:

- `record.label` (what the dock chip renders: `record?.label ?? occurrence.label`), and
- `item.path` as used in the upload body (`files: record.items.map(item => ({ path: item.path, … }))`) — otherwise the chip would say `paste_image(2).png` while the uploaded file still lands as `image.png`.

Paths that must keep real names: **drag-and-drop** and the **file/folder picker**. Their items must reach `add()` with `item.path` untouched. Keeping the rename out of `add()` (do it in the paste handler / pass an explicit per-path rename option) is what scopes the behavior change to one acquisition path; `add()` and `validateItems()` stay name-agnostic (the in-batch duplicate check still runs on the post-rename paths, and is now actually meaningful for pastes).

### How the number is chosen, and the authoritative "names already taken" source

When a paste arrives:

1. Take a fresh `input.state.getSnapshot()`.
2. Collect the set of names already present from `snapshot.occurrences` (the existing attachment names in the composer input for this session) — this is the **authoritative conflict source**.
3. Pick the stem (`paste_image` / `paste_file` + extension) and find `n = max` over existing names matching `^stem(?:\((\d+)\))?\.ext$`; emit `stem(n+1).ext`, or `stem.ext` if the stem is untaken. Re-scan after each item in a multi-file paste so two screenshots in one paste get consecutive numbers.

**Why the plugin-side `records` Map alone is the wrong source:** `records` is a derived cache with an alive-subscription that retires entries on **any momentarily empty snapshot** — the code comments in the fixture itself flag `records.delete(ref)` as firing on a momentary empty snapshot (before `occurrences` repopulates, or during transient state changes). Any entry dropped that way is invisible to a records-based counter, so the next paste would reuse `paste_image(2).png` while that attachment still exists in the composer. The composer's own `occurrences` are the ground truth: they exist exactly as long as the attachment exists in the input the user sees, which is precisely the collision domain the rename must avoid. Use `records` (if at all) only as a display cache; always compute the next number from the live snapshot, taken at paste time.

---

## 2. Extension rule and display (guidance, not scored)

- **Original name first**: if the clipboard item's file name has a usable extension (`image.png` → `.png`, `report.pdf` → `.pdf`), keep that extension on the renamed stem. Note the browser's clipboard name for images is already `image.png`, so the image case is stable.
- **MIME fallback**: when the name has no extension (or an unhelpful one like `image`), map `file.type` to an extension (`image/png`→`png`, `image/jpeg`→`jpg`, `application/pdf`→`pdf`, …); if the MIME type is empty or unknown, fall back to the original extension or no extension — never invent content.
- **Dock chip**: display the renamed label (`paste_image(2).png`) — set `record.label` to the renamed value at creation.
- **Uploaded path**: the upload body's `path` must be the same renamed value, so what the model/host receives matches what the user saw on the chip. Chip and upload path must never diverge.

---

## 3. Follow-up B — root cause and the correct chip rule

### Root cause

The captured response (`tags-api-response.txt`, ~90 s after pushing `v0.2.11`) shows:

- `x-cache: HIT`, `age: 178`, `cache-control: … s-maxage=300` — the GitHub tags API page was served from CDN cache and was ~3 minutes old;
- the cached body lists only `v0.2.9`, `v0.2.8`, `v0.2.7` — it **predates the v0.2.10 and v0.2.11 pushes**, while `git ls-remote` confirms both tags exist on the remote.

So `latestFromTags()` returned `v0.2.9`. Because `semverCmp('v0.2.9', '0.2.10') <= 0`, the code took the "already latest" branch — and `renderCurrentChip(tag)` prints the **fetched** tag, producing "already the latest version v0.2.9" for a user actually running 0.2.10 minutes after 0.2.11 shipped. Two compounding mistakes:

1. trusting a **cached remote value** (up to `s-maxage=300` stale, ~5 min of lag after every push) as ground truth, and
2. echoing that untrusted fetched value in the UI instead of the locally-known running version.

### The display rule the chip should follow

Compare exactly two values: **fetched latest tag vs. local `PLUGIN_VERSION`**.

- If `semverCmp(latest, PLUGIN_VERSION) <= 0` → green "already latest" chip showing **`PLUGIN_VERSION`** (the local, hand-inlined constant). The fetched tag must never be rendered in this branch: when the comparison says "you are current", the only version you can state with confidence is the one you are running. A stale fetch can then only produce a *conservative* wrong answer ("you're current" when an update exists) — the same failure the update check already has — never the self-contradictory "latest v0.2.9 < your 0.2.10".
- If `semverCmp(latest, PLUGIN_VERSION) > 0` → update chip showing the fetched tag (here the fetched value is only *shown* when it strictly exceeds the local version, so a stale cache can't fabricate it).

Optional hardening (secondary): request `cache: 'no-cache'` / add a cache-busting query param on the tags fetch, or compare against the releases endpoint; and note in release announcements that the chip may lag pushes by up to ~5 min because of the CDN `s-maxage=300`. The primary fix remains: the green chip displays `PLUGIN_VERSION`, not the fetched tag.

---

## 4. Regression tests that would have caught both

**Follow-up A (paste renaming):**

1. *Multi-paste naming*: paste three clipboard files all named `image.png` in one action → labels/paths are exactly `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`; assert both `record.label` **and** the upload-body `path` for each.
2. *Cross-paste numbering*: paste one image, then paste another → second is `paste_image(2).png` (counter continues from the snapshot's occurrences across paste actions).
3. **Authoritative-source test (the records-cache trap)**: paste an image, then simulate the alive-subscription firing on a momentarily empty snapshot (so `records` drops the entry while the occurrence still exists in `input.state`), then paste again → the new paste must **not** reuse `paste_image.png`; assert it gets `paste_image(2).png`. This test fails on any records-Map-based counter.
4. *Non-image pastes*: pasted `report.pdf` → `paste_file.pdf`, second → `paste_file(2).pdf`; pasted file without extension + MIME `application/pdf` → `paste_file.pdf`.
5. *Scope test (unchanged paths)*: add files via drag-and-drop and via the file/folder picker with identical names — labels and upload paths keep the original names verbatim; no `paste_` prefix appears.
6. *Existing validation still holds*: in-batch duplicate check fires on duplicate post-rename paths.

**Follow-up B (version chip):**

1. *Stale-cache test*: mock `fetch` to return a tag list whose max is `v0.2.9` while `PLUGIN_VERSION = '0.2.10'` → the rendered chip text must contain `0.2.10` and must **not** contain `v0.2.9`/"latest v0.2.9". (This is exactly the reported failure; it fails against the shipped code.)
2. *Update path*: mocked latest `v0.2.11` > running `0.2.10` → update chip shows `v0.2.11`.
3. *Equal*: mocked latest `v0.2.10` = running → green chip shows `0.2.10`.
4. *Offline / non-2xx / timeout / no stable tags* → offline chip, no version claim.
5. *Semver ordering sanity*: `v0.2.11` sorts above `v0.2.9` (string compare would fail).

---

## 5. Lib-only release hygiene items this touches

1. **Hand-inlined version constant**: `PLUGIN_VERSION` in `lib/client.js` is duplicated knowledge of `package.json`'s `version` (no build step to inject it). Add a release gate — a tiny test or `scripts/verify` step that parses `PLUGIN_VERSION` out of `lib/client.js` and asserts equality with `package.json` `version` — and make it part of the release checklist so a forgotten bump can't ship a chip that lies about the running version in the *other* direction.
2. **Bundle syntax check**: with no build step, `lib/*.js` ships verbatim; a syntax error reaches users directly. Add `node --check lib/*.js` (or equivalent parse-only check) to CI/release so the bundle is at least proven parseable before tagging. Pair it with the version-equality check above as the two mechanical pre-tag gates.
3. **How users actually receive the update**: this plugin has **no host-side update endpoint** — the chip can only *inform*, never install. Users update by redoing their acquisition step (re-running their install command / `git pull`ing the vendored copy / replacing the lib directory per the README's install instructions) and then hard-refreshing the browser so the client bundle is reloaded. The chip's "update available" copy/link should say exactly that (point at the install/upgrade instructions), not imply self-update. Also account for the tags-API CDN lag (`s-maxage=300`): a user checking within ~5 minutes of a push may still see the conservative "current" chip even after the display fix — release announcements should mention the ~5-minute window.

---

## Skill report structure mapping

- **pre-existing / baseline**: not collected (no package scripts run; read-only fixture).
- **Completed**: full analysis above; fixture read only; report written to the designated output directory.
- **Skipped**: no runtime verification (plugin not installed in this container; fixture is static by design); no migration/install executed per brief.
- **Pending/residual risk**: the exact "how users install" wording in item 5 depends on the plugin README's real install instructions, which are not in the evidence pack; the CDN-lag window (~5 min) is inherent to the tags API and only mitigated, not eliminated.
- **Rollback**: nothing was modified; nothing to roll back. Fixture untouched.
- **Recommendations**: single-source the version constant (codegen or gate); consider a `releases/latest` endpoint or `no-cache` fetch for the chip; add the section-4 tests before v0.2.12 ships.
