# S10 Report — Paste Renaming & Version-Chip Follow-Ups (`@org/dsh-attach-input` v0.2.10)

Analysis of the evidence pack in the read-only fixture: `plugin-attachment-flow.js`,
`plugin-version-chip.js`, `user-threads.md`, `tags-api-response.txt`.

---

## 1. Renaming design (Follow-up A)

### Naming scheme
- Pasted **images** (clipboard file with an image MIME type, typically `image/png`):
  - 1st: `paste_image.png`
  - 2nd: `paste_image(2).png`
  - 3rd: `paste_image(3).png` … i.e. bare name first, then ` (n)` for n = 2, 3, …
- Other pasted files: `paste_file.<ext>` with the same numbering (`paste_file.pdf`,
  `paste_file(2).pdf`, …).
- The rename applies to **both** the dock chip label and the `path` sent in the upload
  body — the displayed name and the uploaded name must be the same string, otherwise the
  user sees one name and the host stores another.

### Where the rename is applied — and which paths stay untouched
The rename must be applied **only on the paste acquisition path**, at the moment items
enter `add()`: detect the acquisition source (paste vs drop vs file/folder picker) —
the caller that produced the `items` knows which browser event it handled — and for
paste-originated items replace `item.path` with the generated name *before* the record
is created (`label`) and before `insertReference`. Drop and picker items pass through
with their real `item.path` verbatim; they participate only as *occupiers* of names
(see below) so a pasted `paste_image.png` cannot collide with a dragged-in file of the
same name.

Scoping matters: `add()` is a shared funnel for three paths, so the change is a
per-item decision at the top of the loop, not a change to `add()` semantics globally.

### How the number is chosen
Compute the set of names already taken, then pick the first free name:

1. Seed `taken` with every name visible in the **authoritative source** (below).
2. Also add names already assigned **within the current batch** (a single paste of three
   `image.png` files must yield `paste_image.png`, `paste_image(2).png`,
   `paste_image(3).png` — the existing in-batch `validateItems` duplicate check throws
   on identical raw paths before renaming runs, so the batch check must run on the
   *renamed* paths, or renaming must happen before `validateItems`).
3. For each pasted item, try the bare name, then ` (2)`, ` (3)`, … until free; add the
   winner to `taken` immediately.

### Authoritative "names already taken" source — and why the records Map is wrong
The authoritative source is the **composer input state itself**: `input.state.getSnapshot()`
occurrences for this session (filtered to this plugin's `SOURCE`), reading each
occurrence's label/path. That is what the user actually sees attached, and it survives
plugin-side bookkeeping errors.

The plugin-side `records` Map alone is the wrong source because of its alive-subscription:
`subscribe` deletes a record (`records.delete(ref)`) whenever a snapshot **momentarily
shows no occurrences** for that ref — the guard is "alive OR inflight", so any transient
empty/rebuilding snapshot (state swap, re-render, race between insert and snapshot
propagation) retires the record **even though the attachment still exists in the
composer**. Consequences if numbering were derived from `records`:

- A retired record frees `paste_image.png`, and the next paste reuses it → two live
  attachments with the same uploaded path (the exact bug class the duplicate check was
  meant to prevent, now crossing batches).
- Numbering resets mid-session (`paste_image(2).png` appears twice with different files).

The snapshot is the ground truth the user and the host both observe; `records` is at best
a render cache. Number from the snapshot (+ current batch), never from `records` alone.

---

## 2. Extension rule and display (guidance, not scored)

- **Extension**: prefer the original clipboard file name's extension when it has one
  (`image.png` → `.png`). Fallback when there is no usable extension: map the MIME type
  (`file.type`, e.g. `image/png` → `png`, `image/jpeg` → `jpg`, `application/pdf` →
  `pdf`), with a small MIME→ext table; final fallback `bin`. Pasted images always use
  the `paste_image` stem regardless of the browser-given filename (that filename is
  `image.png` by convention and carries no user intent).
- **Dock chip**: shows `record.label` — i.e. the renamed path for pasted items, the real
  name otherwise. It already reads `record?.label ?? occurrence.label`, so setting
  `label` at record creation is sufficient; the `occurrence.label` fallback must also
  carry the renamed value via `insertReference` metadata so a page reload that reconstructs
  from occurrences shows the same names.
- **Upload path**: the upload body's `files: [{ path: item.path, … }]` must send the
  **renamed** path for pasted items. Rename once, at acquisition, and let both consumers
  read the same value — never rename independently in chip and upload code.

---

## 3. Version-chip root cause (Follow-up B)

### Why the chip showed an OLDER tag as "latest"
The chip's data source is the GitHub tags API, and the captured response
(`tags-api-response.txt`, ~90 s after pushing `v0.2.11`) shows:

```
cache-control: private, max-age=60, s-maxage=300
x-cache: HIT
age: 178
body: ["v0.2.9", "v0.2.8", "v0.2.7"]   # v0.2.10 and v0.2.11 absent
```

The API answer was served from a **shared CDN cache** (`x-cache: HIT`, `age: 178`, and
`s-maxage=300` allows the shared cache to serve it for up to ~5 minutes). The cached page
predates the last two pushes, so the newest tag the chip could see was `v0.2.9` even
though `git ls-remote` confirms `v0.2.11` exists on the remote. Fetching "from the API"
did not mean fetching fresh data.

Then the rendering compounded it: `semverCmp(tag, PLUGIN_VERSION) <= 0` (`0.2.9 ≤ 0.2.10`)
took the "already latest" branch, and `renderCurrentChip(tag)` printed **the fetched tag**,
not the running version — producing "already the latest version **v0.2.9**" on a client
running **0.2.10**. That message is self-contradictory: it claimed a version older than
the one running was the latest. ("A while later it changed its mind" = the cache entry
expired and a fresh response returned `v0.2.11`.)

### The display rule the chip should follow
Compare exactly two values: **remote latest tag** vs **locally known running version
(`PLUGIN_VERSION`)**, and follow these branches:

- `remote > local` → update chip: "update available v0.2.11" (show the remote tag).
- `remote == local` → green chip: "already the latest version **X**", and X must be the
  **local `PLUGIN_VERSION`** (or the equal tag — they are the same here). Never print a
  value that was not confirmed equal to the running version.
- `remote < local` (the stale-cache case, and any fetch failure/timeout) → **do not claim
  "latest" at all**. A remote value older than the code that is provably running is proof
  the remote data is stale, not proof of being up to date. Render a neutral chip
  ("running v0.2.10; update check unavailable") or nothing. `renderOfflineChip()` should
  cover this branch too.

Principle: the locally-known running version is ground truth about what the user has; a
cached remote value is at best advisory. The "already latest" claim must be gated on
`remote == local`, and the displayed version in that claim is the local one.

---

## 4. Regression tests that would have caught both

### Follow-up A (renaming)
1. **Cross-batch paste numbering**: two separate `add()` calls, each with one clipboard
   `image.png` (paste source). Assert labels/upload paths `paste_image.png` then
   `paste_image(2).png`. (v0.2.10 fails: both stay `image.png` / duplicate-path throw.)
2. **In-batch paste numbering**: one paste event with three `image.png` files →
   `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`; asserts rename runs
   before/consistently with `validateItems`.
3. **Path scoping**: drop-source and picker-source items with the same `image.png` keep
   their real names, and a subsequent paste still numbers correctly past a dragged-in
   `paste_image.png` (snapshot names are honored).
4. **Non-image fallback**: paste of a clipboard PDF with no extension → `paste_file.pdf`
   (MIME map); second paste → `paste_file(2).pdf`.
5. **Numbering survives records retirement**: after attaching, force the alive-subscription
   to fire on a momentary empty snapshot (records Map now empty), then paste again — the
   new name must still avoid the ones visible in the composer snapshot
   (`paste_image(2).png`, not a reused `paste_image.png`). This is the test that pins
   the authoritative source choice.

### Follow-up B (chip)
6. **Stale remote older than local**: mock `latestFromTags()` returning `v0.2.9` with
   `PLUGIN_VERSION = '0.2.10'`. Assert the chip never renders "latest" with `v0.2.9`
   (neutral/offline chip instead). v0.2.10 fails exactly as the user reported.
7. **Equal versions show local**: mock remote `v0.2.10` → green chip text contains the
   running version string taken from `PLUGIN_VERSION`, not from the fetched payload.
8. **Newer remote**: mock remote `v0.2.11` → update chip naming `v0.2.11` (guards
   against over-correcting into never showing updates).
9. **Fetch failure/timeout** → neutral chip, no "latest" claim.

---

## 5. Lib-only release hygiene items this touches

- **Hand-inlined version constant**: `PLUGIN_VERSION = '0.2.10'` lives in the shipped
  `lib/client.js` with no build step to inject it. Every release must bump
  `package.json` **and** this constant in lockstep. Add a release-checklist gate (e.g. a
  one-line script asserting the inlined constant equals `package.json`'s version —
  `grep`/read both, compare) that runs before tagging; a mismatch silently breaks both
  chip branches. Follow-up B makes this doubly load-bearing: the entire fixed display rule
  keys off the local constant.
- **Bundle syntax check**: with no build step, nothing else validates the shipped file.
  Before tagging, run a parse check on the exact published artifact — `node --check
  lib/client.js` (plus loading it / a smoke import) — so a hand-edit syntax error cannot
  ship. Do this for every `lib/*.js` file that ships.
- **How users actually receive the update**: the plugin has **no host-side update
  endpoint** — the chip is informational only; delivery is the user reinstalling or
  replacing the lib (their package manager / copy of the bundle) and reloading. Two
  consequences: (a) release notes / the update chip should say *how* to update, since
  nothing auto-applies it; (b) the tags API is only an *announcement* channel, and it is
  CDN-cached for up to ~5 minutes (`s-maxage=300`) — the chip must therefore treat
  remote data as advisory (rule in §3) and never as ground truth next to the locally
  known running version. Optionally add cache-busting (a cache-bypassing header cannot
  be forced from the browser for this API, so the practical fix is the stale-safe
  display rule, not cache tricks).
