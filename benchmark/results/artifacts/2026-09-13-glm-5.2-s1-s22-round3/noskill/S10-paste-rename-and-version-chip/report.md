# S10 · Paste Renaming & Version-Chip Follow-Ups — Report

Plugin under maintenance: `@org/dsh-attach-input` v0.2.10 (lib-only client bundle, no
build step). Evidence: fixture excerpts `plugin-attachment-flow.js`,
`plugin-version-chip.js`, `user-threads.md`, `tags-api-response.txt`.

---

## 1. Follow-up A — unified renaming for pasted files

### Naming scheme

- Pasted **images** → `paste_image.png`, then on collision `paste_image(2).png`,
  `paste_image(3).png`, …
- Other pasted files → `paste_file.<ext>` with the same numbering:
  `paste_file.pdf`, `paste_file(2).pdf`, …
- Drag-and-drop and the file/folder picker keep `item.path` verbatim — the rename is
  scoped **only to the paste acquisition path**.

### Where the rename is applied

The rename must happen at the top of the **paste path only**, before the item reaches
`add()`'s record construction (or as the first step inside `add()` gated on an
`origin: 'paste'` flag that only the paste path sets). Concretely:

- The paste handler tags its items as paste-origin (the clipboard API already tells us
  these are clipboard files — every one named `image.png`, which is exactly the symptom).
- `add()` computes `label = isPaste ? renamedPath : item.path` and uses `renamedPath`
  both for the record `label` and for the `path` sent in the upload body
  (`files: [{ path: … }]`), so the dock chip and the uploaded path agree.
- Drop/picker items bypass the renaming entirely; they must remain byte-identical to
  today's behavior, including the existing in-batch duplicate check in `validateItems`.

### How the number is chosen

For each pasted item, in order:

1. Start with the base name (`paste_image.png` or `paste_file.<ext>`).
2. If that name is already taken, try `base(2)`, `base(3)`, … incrementing until an
   unused name is found; assign it and mark it taken.
3. "Taken" is evaluated against the union of (a) all names currently present in the
   authoritative source below and (b) names assigned earlier **within the same paste
   batch** — two screenshots pasted in one paste event both named `image.png` must get
   `paste_image.png` and `paste_image(2).png`, not two collisions on the same name.

### The authoritative "names already taken" source

The authoritative source is the **composer input snapshot**:
`input.state.getSnapshot().occurrences` filtered to this plugin's `SOURCE`, mapping each
occurrence to its label/path. That is what the user actually sees in the composer, so it
is the ground truth for "is this name taken".

A plugin-side `records` Map alone is the **wrong** source, and the fixture shows why:
the alive-subscription in `add()` deletes a record whenever a snapshot *momentarily*
shows no matching occurrence (`if (alive || record.inflight !== undefined) return;
… records.delete(ref)`). Any transient empty snapshot — re-render, state reconciliation,
or the window between inserts in a multi-item batch — retires the entry early. The
record for `paste_image.png` can vanish from `records` while the attachment is still in
the composer, so a purely records-based name check would hand the same name to the next
paste. The records Map may be used only as a cache for re-rendering, never as the
conflict source; when in doubt, re-read the snapshot.

---

## 2. Extension rule and what each surface displays (guidance, not scored)

- **Extension:** take the extension from the original clipboard file name when it has one
  (`image.png` → `.png`). If the name has no extension, fall back to the file's MIME
  type (`file.type`): `image/png` → `png`, `application/pdf` → `pdf`,
  `image/jpeg` → `jpg`, etc. If neither yields an extension, emit the base name with
  no suffix (`paste_file`) rather than inventing one.
- **Dock chip:** displays the renamed label (`record.label`), i.e. `paste_image(2).png`
  — never the raw clipboard `image.png` for pasted items.
- **Uploaded path:** the upload body must send the same renamed `path`, so the host-side
  stored file name matches what the chip promised. Keeping the two identical is the point
  of the follow-up; diverging them recreates the bug in a worse place.

---

## 3. Follow-up B — the chip showed an OLDER tag as "latest"

### Root cause

The GitHub tags API response was **served from cache and predates the last two pushes**.
`tags-api-response.txt` (captured ~90 s after pushing `v0.2.11`) shows:

- `x-cache: HIT`, `age: 178`, `cache-control: … s-maxage=300` — a CDN copy up to
  ~5 minutes old is considered fresh;
- the tag list tops out at `v0.2.9` while `git ls-remote` confirms `v0.2.10` and
  `v0.2.11` exist on the remote.

The chip logic then did the worst possible thing with that stale value:
`semverCmp(tag, PLUGIN_VERSION) <= 0` → `renderCurrentChip(tag)`, and
`renderCurrentChip` prints **the fetched tag**: "already the latest version v0.2.9".
So a stale *lower* tag both suppressed the update notice for `v0.2.11` and displayed a
version the user provably wasn't running. The bug is not the caching — it's treating a
cached remote value as displayable ground truth next to a locally-known running version.

### The display rule the chip should follow

Compare **fetched latest tag** vs **locally compiled-in `PLUGIN_VERSION`**; display
**the local `PLUGIN_VERSION`** in the "already latest" chip:

- `semverCmp(fetched, PLUGIN_VERSION) > 0` → update chip showing the fetched tag
  (that's the only case where the remote value is the news).
- `<= 0` → green chip showing `PLUGIN_VERSION` ("running 0.2.10"), never the fetched
  tag. A fetched tag older than the running version is by definition stale cache, not a
  version to announce.
- Additionally treat a fetched tag that is *lower* than the running version as a
  no-information signal (offline-style chip) rather than "latest", and keep the 8 s
  timeout/failure path as `renderOfflineChip()` unchanged.

---

## 4. Regression tests that would have caught both

**Follow-up A:**

1. `paste twice → distinct names`: simulate two paste acquisitions whose clipboard files
   are both named `image.png`, with the first attachment still present in the composer
   snapshot. Assert labels/paths `paste_image.png` and `paste_image(2).png`, and that
   the upload body carries the renamed paths.
2. `non-image paste`: clipboard file `report.pdf` → `paste_file.pdf`; second paste →
   `paste_file(2).pdf`.
3. `multi-item single paste`: one paste event with two `image.png` files →
   `paste_image.png`, `paste_image(2).png` (in-batch numbering, no duplicate-path
   rejection).
4. `drop and picker untouched`: drag-drop and picker acquisitions with real names assert
   `item.path` verbatim for label and upload path — proves the change is scoped to paste.
5. `records cache is not the conflict source`: after the alive-subscription retires a
   record via a momentary empty snapshot (simulate one snapshot with no occurrences while
   the attachment is logically present), a new paste must still number off the composer
   snapshot — i.e. `paste_image(2).png`, not a reused `paste_image.png`.

**Follow-up B:**

6. `stale tag response`: with `PLUGIN_VERSION = '0.2.10'`, mock `fetch` returning a tag
   list whose max stable tag is `v0.2.9` (the captured response). Assert the green chip
   renders **0.2.10**, contains no reference to `v0.2.9`, and no update chip appears.
7. `genuinely newer tag`: mock max stable tag `v0.2.11` → update chip renders and shows
   `v0.2.11`.
8. `failure/timeout`: rejected `fetch` or `AbortSignal.timeout` firing → offline chip,
   no version claim at all.

Tests 1, 4, 5 and 6 are the ones that directly fail on v0.2.10's code.

---

## 5. Lib-only release hygiene this touches

- **Hand-inlined version constant:** `PLUGIN_VERSION` is duplicated in `lib/client.js`
  next to `package.json` because there is no build step to inject it. Every release must
  update both in the same commit; add a release checklist line (or a tiny pre-publish
  assertion comparing the two, e.g. a grep in CI) so a skipped bump is caught. Follow-up
  B's fix also raises the stakes: the chip now *displays* this constant, so a stale
  inlined version is user-visible misinformation, not just an internal mismatch.
- **Bundle syntax check:** with no build step, nothing else validates the shipped file.
  Run `node --check lib/client.js` (and any other `lib/` files) before tagging — a
  hand-edited syntax error ships directly to every user.
- **How users actually receive the update:** the plugin has **no host-side update
  endpoint**; the chip is informational only. Delivery is: push the tag, then users
  manually re-fetch/reinstall the bundle (or hard-refresh if the host caches the plugin
  file) — and any host-side copy may itself be cached, so the release note should tell
  users to verify the rendered version after refreshing. The chip's job after this fix is
  to at least never lie about which version is running while they wait.
