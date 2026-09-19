# S10 · Paste Renaming & Version-Chip Follow-Ups — Analysis Report

Task: read-only post-release follow-up analysis for `@org/dsh-attach-input` v0.2.10
(lib-only community Web plugin, clipboard files → composer attachments).
Skill mode: **A · inspect (read-only)** — no migrations, installs, or writes to the fixture.

Evidence used (all read-only, fixture unchanged):

- `plugin-attachment-flow.js` — `add()` / `validateItems()`, records `Map` + alive-subscription, dock chip label, upload body
- `plugin-version-chip.js` — `PLUGIN_VERSION`, `latestFromTags()`, `startUpdateChip()`, `renderCurrentChip()`
- `user-threads.md` — follow-up A (kaylint) and follow-up B (rho_9)
- `tags-api-response.txt` — captured HTTP response ~90 s after pushing `v0.2.11`

---

## 1. Follow-up A — renaming design for pasted files

### Naming scheme (exactly as requested)

- Pasted **images**: `paste_image.png`, then on conflict `paste_image(2).png`, `paste_image(3).png`, …
- Other pasted files: `paste_file.<ext>` with the same numbering (`paste_file.pdf`, `paste_file(2).pdf`, …).
- Numbering always starts at the un-numbered base name; the first free suffix ≥ 2 wins. There is no "(1)".

### Where the rename is applied — and which paths stay untouched

All three acquisition paths (paste, drag-and-drop, file/folder picker) funnel into `add()`,
so `add()` itself must **not** rename unconditionally. The rename belongs at the **paste
acquisition path only**, i.e. where the clipboard event produces the `items` array, before
it reaches `add()` (or, if implemented inside `add()`, gated on an explicit `origin: 'paste'`
flag threaded from the clipboard handler). Concretely:

- **Paste path**: rename `item.path` (and the label derived from it) per the scheme above before the record is created. The renamed path must be used for **both** `record.label` (what the dock chip renders: `record?.label ?? occurrence.label`) **and** the upload body (`files: record.items.map(item => ({ path: item.path, ... }))`) so the uploaded filename always matches the chip the user saw.
- **Drag-and-drop path**: keep `item.path` verbatim. No renaming.
- **File/folder picker path**: keep `item.path` verbatim. No renaming.

Anything else in `add()` — coordinate handling, `insertReference`, record bookkeeping, the
alive-subscription — is unchanged by this feature.

### How the number is chosen

For each pasted item, compute the base name (`paste_image.png` / `paste_file.<ext>`), then
scan the **taken-names set** (below) for `base`, `base(2)`, `base(3)`, … and take the first
free one. Two ordering rules matter:

1. **Within one paste batch**: numbering continues across items in the same `add()` call —
   the second `image.png` in one multi-file paste becomes `paste_image(2).png`, not a
   duplicate. (Today `validateItems()` would actually *throw* `Duplicate attachment path`
   for two clipboard `image.png` in one batch; after renaming, the renamed paths are distinct
   and the check passes naturally. Run `validateItems()` **after** renaming, on the final names.)
2. **Across pastes / against existing attachments**: the scan must see attachments that
   already sit in the composer, including ones whose records entries were retired.

### The authoritative "names already taken" source — and why the records Map alone is wrong

**Authoritative source: the live composer input state** — `input.state.getSnapshot().occurrences`
(the same ground truth the dock renders and the upload consumes), filtered to attachment
occurrences, plus the plugin's own `records` entries only as a supplement for **in-flight**
items whose occurrence has not landed yet. In pseudo-code:

```js
const taken = new Set();
for (const o of input.state.getSnapshot().occurrences) taken.add(labelOf(o)); // authoritatively present
for (const r of records.values()) if (r.inflight !== undefined) taken.add(r.label); // in-flight supplement
```

Why the plugin-side `records` Map alone is the **wrong** source: the alive-subscription in
`add()` retires entries **on ANY momentary empty snapshot**. The callback deletes
`records.delete(ref)` whenever `current.occurrences` momentarily shows no occurrence with
`(source === SOURCE && ref === ref)` — during re-renders, transient snapshot states, or
coordinate re-inserts, the occurrence list can briefly appear empty or missing the entry,
and the subscription unsubscribes and drops the record even though the attachment is still
(or again) present in the composer. A records-only set therefore **under-reports** taken
names exactly when it matters: the next paste would re-derive `paste_image.png`, collide
with a still-attached `paste_image.png`, and the numbering silently restarts. The composer
state is the durable, host-owned truth; `records` is a render cache that can be evicted by
its own subscription.

---

## 2. Extension rule and what each surface displays (guidance, not scored)

- **Extension source**: take the extension from the original clipboard file name
  (`image.png` → `.png`) when it has one. If the browser hands over an extension-less or
  generic name, fall back to mapping `item.file.type` (MIME) to an extension:
  `image/png`→`png`, `image/jpeg`→`jpg`, `application/pdf`→`pdf`, `image/svg+xml`→`svg`, etc.
  If both fail, omit the extension (`paste_file`) rather than inventing one. The type test
  for the image/file split is likewise `item.file.type.startsWith('image/')` (or a known
  image-extension check on the original name).
- **Dock chip**: must display the **renamed** label — `record.label` set to the final
  `paste_image(2).png`-style path, so consecutive pastes are distinguishable at a glance.
- **Uploaded path**: the upload body's `files[].path` must carry the **same renamed path**
  the chip shows. Chip and upload must never disagree; the rename is applied once, upstream
  of both, and both read `item.path`/`record.label` unchanged.

---

## 3. Follow-up B — root cause and the display rule

### Root cause

The chip's "latest" is derived from `GET /repos/org/dsh-attach-input/tags`, and that
response is **CDN-cached and eventually consistent**. The captured evidence, taken ~90 s
after pushing `v0.2.11`, shows:

- `x-cache: HIT`, `age: 178` — the served page is ~3 minutes old, i.e. it **predates both
  the `v0.2.10` and `v0.2.11` pushes** (also visible in `cache-control: … s-maxage=300`);
- the tag list contains only `v0.2.9`, `v0.2.8`, `v0.2.7` — `v0.2.10`/`v0.2.11` absent;
- `git ls-remote` proves both newer tags exist on the remote.

So `latestFromTags()` returned `v0.2.9`. Then `startUpdateChip()` compared it to the local
`PLUGIN_VERSION = '0.2.10'`: `semverCmp('v0.2.9', '0.2.10') <= 0` → `renderCurrentChip('v0.2.9')`.
The bug is in `renderCurrentChip`: it prints **the fetched tag**, not the running version.
A cached remote value that is *older than the locally-known running version* is by
construction stale — it can never be authoritative about what "latest" means for a user
already running something newer. The chip then asserted "already the latest version
v0.2.9" to a user on 0.2.10 while 0.2.11 existed. ("A while later it changed its mind" —
the cache aged out and the list caught up.)

### The display rule the chip should follow

- **Compare**: fetched latest tag **vs** local `PLUGIN_VERSION` (the running bundle's
  hand-inlined version — the only ground truth about what the user actually runs).
- **Show**:
  - fetched > local → update chip with the fetched tag (correct today).
  - fetched ≤ local → "current" chip that displays **`PLUGIN_VERSION`**, never the fetched
    tag: "✓ attach-input v{PLUGIN_VERSION} is the latest known version" or, more honestly,
    treat `fetched < local` as a *stale-cache / not-yet-published* signal (show the local
    version, optionally a neutral "up to date as far as known") rather than a confident
    "already the latest" claim about a tag list that is provably behind the running build.
  - fetch failed / timed out (8 s abort) → offline chip, as today.
- Net rule: a remote value older than the local running version must never be rendered as
  "latest"; the local version is authoritative for the "you are current" message.

---

## 4. Regression tests that would have caught both

### Follow-up A (renaming)

1. **Paste collision across batches**: seed composer state with an occurrence labeled
   `paste_image.png`; make the plugin `records` Map empty (simulating the subscription
   having retired the entry on a momentary empty snapshot); paste another clipboard
   `image.png`. Assert the new chip label and upload `files[0].path` are
   `paste_image(2).png`. (This is the test that pins "composer state, not records, is the
   conflict source".)
2. **Multi-paste in one batch**: paste two `image.png` items in a single `add()`; assert
   `paste_image.png` and `paste_image(2).png` and that `validateItems` no longer throws
   `Duplicate attachment path`.
3. **Acquisition-path scoping**: drag-drop and picker items named `report.pdf` keep label
   and upload path `report.pdf` verbatim; only the paste path renames.
4. **Non-image pasted file**: clipboard file `invoice.pdf` → `paste_file.pdf`;
   extension-less clipboard file with `file.type = 'application/pdf'` → `paste_file.pdf`
   (MIME fallback).
5. **Chip/upload agreement**: for every renamed item, assert dock label === upload body path.

### Follow-up B (version chip)

1. **Stale-cache scenario** (the exact incident): mock `fetch` returning a tag list whose
   newest stable is `v0.2.9`; set `PLUGIN_VERSION = '0.2.10'`. Assert the chip renders
   **0.2.10** (the local version) — not "latest v0.2.9" — and does not claim a specific
   older tag is "latest".
2. **Equal versions**: fetched `v0.2.10`, local `0.2.10` → current chip showing `0.2.10`.
3. **Newer remote**: fetched `v0.2.11`, local `0.2.10` → update chip showing `v0.2.11`.
4. **Network failure/timeout**: fetch rejects or aborts at 8 s → offline chip; no unhandled rejection.
5. (Optional hardening) tag-list filtering: non-semver tags ignored; empty stable list → offline chip.

---

## 5. Lib-only release hygiene touched by these fixes

1. **Hand-inlined version constant**: `PLUGIN_VERSION` in `lib/client.js` must be bumped in
   lock-step with `package.json` `version` at every release — there is no build step to
   inject it. Add a release-checklist step (or tiny gate script) that compares the constant
   against `package.json` and fails on drift; the "current chip shows local version" fix in
   §3 makes this constant user-visible, so a stale one now lies on screen, not just in metadata.
2. **Bundle syntax check**: with no build step, nothing validates the shipped file — run
   `node --check lib/client.js` (and any other lib files) before tagging, so a hand-edit
   syntax error cannot ship. Ideally also a quick import/smoke of the lib in a scratch
   profile.
3. **How users actually receive the update**: this plugin has **no host-side update
   endpoint** — the chip is informational only. Users update by reinstalling/replacing the
   plugin (npm install/copy the lib bundle into their profile) and restarting/refreshing;
   the chip can never push the update. Given the tags API's CDN staleness (up to
   `s-maxage=300` plus HIT age), release announcements must not assume the chip reflects a
   fresh push within minutes — and the chip itself must degrade gracefully per §3. If a
   more reliable "latest" is wanted later, consider the releases API or a `latest` dist-tag
   style endpoint with explicit cache-busting, and still never display a fetched value
   older than the running version.

---

## Skill report structure

- **pre-existing (baseline)**: not collected — read-only inspection task; no builds/tests were run against the fixture.
- **Completed**: full renaming design (§1), extension/display guidance (§2), chip root-cause and display rule (§3), regression-test plan (§4), release-hygiene items (§5); all from static fixture evidence.
- **Skipped**: no runtime verification, no migration planner run, no touchpoint scan beyond the client excerpt — the task is a design/diagnosis follow-up, not a corridor migration; no version cards apply (no DSH host upgrade involved).
- **Pending/residual risk**: the exact composer-occurrence label field name inside `insertReference` is elided in the excerpt (`/* ... */`), so the taken-name extraction in §1 may need to read the occurrence's rendered label rather than a `path` field; the CDN staleness window is evidenced by one capture (`age: 178`) — treat exact TTLs as approximate.
- **Rollback**: not applicable — nothing was modified; the fixture was only read and remains unchanged.
- **Recommendations**: consider moving `PLUGIN_VERSION` to a single generated/verified source or a release gate; consider a tiny `node --check` + label-drift check in the release checklist; longer term, prefer a host/public update-notification seam over scraping the tags API.

## Verdict

- Follow-up A: implement paste-scoped renaming with numbering derived from **live composer occurrences (plus in-flight records)**, never from the records Map alone — its alive-subscription retires entries on momentary empty snapshots and under-reports taken names.
- Follow-up B: the chip trusted a CDN-cached tags page (age 178 s, pre-dating v0.2.10/v0.2.11) and rendered the **fetched** tag in the "already latest" message; it must compare fetched-latest vs local `PLUGIN_VERSION` and, when fetched ≤ local, display the **local running version**.
