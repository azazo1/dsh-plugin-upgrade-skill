# S10 — Paste Renaming & Version-Chip Follow-Ups: Analysis Report

Plugin under review: `@org/dsh-attach-input` v0.2.10 (lib-only bundle, no build step).
Evidence: `plugin-attachment-flow.js`, `plugin-version-chip.js`, `user-threads.md`,
`tags-api-response.txt` (all read-only, unmodified).

Method note: this analysis follows a framework-agnostic migration/change methodology
(inventory the coupling surface, choose authoritative sources over fragile caches, scope
behavior changes to one acquisition path, verify in layers). No framework-specific
changelog or migration-card material was available; where an exact upstream mapping would
be needed, that is stated explicitly rather than guessed.

---

## 1. Renaming design (Follow-up A)

### Naming scheme
- Pasted **images**: `paste_image.png`, `paste_image(2).png`, `paste_image(3).png`, …
- Pasted **non-image files**: `paste_file.<ext>`, `paste_file(2).<ext>`, … (same numbering).
- Files arriving via **drag-and-drop or the file/folder picker keep their real names,
  completely untouched**.

### Where in the flow the rename is applied
The rename must be applied **only on the paste acquisition path**, before the item enters
`add()` — i.e. in the paste handler, which rewrites `item.path` (and/or a dedicated
display label) for items it acquired from the clipboard, then calls `add()` unchanged.
The drop handler and the picker handler call `add()` with their items verbatim.

Rationale: all three paths funnel into the shared `add()`
(`plugin-attachment-flow.js:17`), and `add()` currently keeps `item.path` verbatim as the
record label (`:24`). Putting the rename inside `add()` unconditionally would break the
"keep real names" requirement for drop/picker; gating it inside `add()` on a flag would
work too, but the cleanest scoping is: the acquisition path that *knows* the files came
from a clipboard owns the renaming policy, and `add()` stays acquisition-agnostic. The
behavior change is thereby scoped to exactly one acquisition path, with the other two
paths provably untouched.

### How the number is chosen
Compute the set of currently-taken base names, then pick the smallest N such that the
candidate is free: first try the bare name (`paste_image.png`); if taken, try
`paste_image(2).png`, `paste_image(3).png`, … incrementing until free. The in-batch loop
must also add each just-assigned name to the taken-set so a single paste of several
screenshots numbers them `(1)→bare, (2), (3)…` within the batch. The existing
`validateItems` duplicate check (`:11`) only guards *within one batch*; it stays, but it
is not the cross-batch numbering mechanism.

### Authoritative "names already taken" source — and why the records Map is wrong
The authoritative source should be the **composer's live state**: the labels/paths of
occurrences in `input.state.getSnapshot()` (the same snapshot `add()` already reads at
`:20` and refreshes per item at `:29`), i.e. what the composer actually shows and will
upload. If the host exposes a dedicated "existing attachment names" query, prefer that
documented source; from the given excerpt, the snapshot occurrences are the observable
ground truth.

The plugin-side `records` Map must **not** be the source, because it is a fragile cache,
not a ledger:

- Each record has a subscription (`:31-39`) that calls `records.delete(ref)` whenever a
  snapshot **momentarily** shows no occurrence for that ref and nothing is inflight
  (`:33-36`). The comment in the fixture says it plainly: "fires on ANY momentary empty
  snapshot."
- So a name can be still visible in the composer while its record has already been
  retired from the Map. Numbering off the Map would then reuse a still-taken name and
  produce duplicate chips / conflicting upload paths — the exact bug class the user is
  reporting, one layer down.
- Caches derived from subscriptions reflect eventual, lossy state transitions; conflict
  detection needs the state of record *at decision time*. The general rule: never treat a
  locally cached mirror of remote/host state as ground truth when the authoritative state
  is one `getSnapshot()` away.

A pragmatic hybrid is acceptable: compute candidates against the snapshot, and treat the
records Map only as a *secondary* hint — never as proof a name is free.

---

## 2. Extension rule and what each surface shows (completeness item)

- **Extension rule**: keep the pasted file's original extension when the browser supplies
  a name (clipboard screenshots arrive as `image.png` → `.png` → `paste_image.png`). When
  the original name has no usable extension (or no name at all), fall back to deriving the
  extension from the file's **MIME type** (e.g. `image/png` → `.png`,
  `application/pdf` → `.pdf`). If the MIME type is unknown/absent, fall back to no
  extension or a generic `.bin` — the exact last-resort token cannot be determined from
  the given material and should be pinned against the host's attachment-path validation
  rules.
- **Image vs non-image classification** should likewise key off MIME (`image/*`), not the
  extension, since the whole problem is that clipboard names are unreliable.
- **Dock chip** (`:44`): renders `record?.label ?? occurrence.label` — the chip must show
  the **renamed display label** (`paste_image(2).png`), so `record.label` must be set to
  the renamed value at insert time.
- **Upload body** (`:45`): sends `item.path` — the uploaded path must carry the **same
  renamed path**, otherwise chip and server-side attachment disagree. Since both surfaces
  read from the same item/record, rewriting `item.path` once on the paste path (and
  deriving `label` from it, as `add()` already does) keeps them consistent by
  construction. If the host requires the upload path to differ from the display label,
  that constraint is not visible in the given excerpt and would need checking against host
  docs.

---

## 3. Follow-up B — root cause of the lying version chip

### What happened
1. Maintainer pushed tag `v0.2.11`. ~90 seconds later, the chip's fetch of
   `…/tags?per_page=10` returned a **stale, cached page**: the capture shows
   `x-cache: HIT`, `age: 178`, `cache-control: … s-maxage=300`
   (`tags-api-response.txt:4-7`). The body lists `v0.2.9, v0.2.8, v0.2.7` — both `v0.2.10`
   and `v0.2.11` are absent because the cached page predates both pushes, while
   `git ls-remote` confirms they exist on the remote (`:16-18`).
2. `latestFromTags()` (`plugin-version-chip.js:7-16`) reduces that stale list to its max:
   `v0.2.9`.
3. `startUpdateChip()` compares `v0.2.9` against the hand-inlined running version
   `PLUGIN_VERSION = '0.2.10'`: `semverCmp(v0.2.9, 0.2.10) <= 0` is true, so it renders
   the green "already latest" chip (`:21`).
4. `renderCurrentChip` then displays **the fetched tag**, not the running version:
   `"already the latest version v0.2.9"` (`:27`). The user, running v0.2.10, is told
   v0.2.9 is "the latest version" — an older tag presented as ground truth — and nothing
   mentions v0.2.11.

### Root cause (two layered defects)
- **Trusting a cached remote value as ground truth.** The tags API answer is an
  eventually-consistent, CDN-cached observation (here up to 300 s stale by its own
  `s-maxage`). It is *evidence*, not *fact*. Any fetched "latest" that is **older than
  the locally known running version** is self-evidently stale: the running bundle is
  proof a newer release exists. The code had no sanity check for this case.
- **Wrong display rule.** Even with a fresh response, showing the *fetched* tag in the
  "you are current" chip is wrong whenever fetched ≠ running. The chip claimed "latest is
  v0.2.9" to a user running v0.2.10 — a statement no fresh data could justify either.

### The display rule the chip should follow
Compare exactly two values: the **fetched latest stable tag** (`latest`) and the
**locally known running version** (`PLUGIN_VERSION`):

- `latest > PLUGIN_VERSION` → update chip, showing `latest` (a real newer release exists).
- `latest == PLUGIN_VERSION` → green chip, showing **`PLUGIN_VERSION`** ("you are running
  the latest version vX") — the value that has actually been verified.
- `latest < PLUGIN_VERSION` → the response is provably stale. Never display the older
  value as "latest". Show the green chip with **`PLUGIN_VERSION`** (the locally known
  good value), optionally note "update check returned stale data", and retry later /
  bypass cache on retry.
- Fetch failure/non-200 → offline chip, unchanged.

In short: the chip always displays the **running version** when claiming "up to date";
it displays the **fetched tag** only when claiming an update exists. The fetched value is
never shown next to a locally-known newer running version. Additionally the fetch should
request fresh data (`cache: 'no-store'` / a cache-busting parameter) — this mitigates but
does not replace the display rule, since shared CDN caches (`s-maxage`) may ignore client
hints.

---

## 4. Regression tests that would have caught both follow-ups

Follow-up A (renaming):
1. **Multi-paste numbering**: paste three clipboard items all named `image.png` (separate
   `add()` calls *and* one batch) → labels/paths are `paste_image.png`,
   `paste_image(2).png`, `paste_image(3).png`. Cross-batch numbering is the case the old
   in-batch-only `validateItems` check structurally cannot cover.
2. **Non-image paste**: paste `file.pdf` named `report.pdf` (or unnamed, MIME
   `application/pdf`) → `paste_file.pdf`, then `paste_file(2).pdf`.
3. **Scoping test**: drag-and-drop and picker items keep their real names verbatim — a
   dedicated assertion per acquisition path so a future refactor of `add()` cannot
   silently rename user files.
4. **Authoritative-source test**: seed the snapshot with an existing `paste_image.png`
   occurrence while the `records` Map has already retired that entry (simulate the
   momentary-empty-snapshot eviction at `:36`) → the next paste must still get
   `paste_image(2).png`, not a duplicate. This test fails if numbering reads the Map.
5. **Extension/MIME fallback**: pasted file with no name/extension but `image/png` MIME →
   `paste_image.png`.

Follow-up B (version chip):
6. **Stale-cache test**: stub `fetch` with the captured response shape (tags list whose
   max, `v0.2.9`, is *below* `PLUGIN_VERSION = 0.2.10`, mirroring
   `tags-api-response.txt`) → chip must render green showing **0.2.10**, and must never
   render the string "v0.2.9" as "latest". This exact fixture would have caught the bug.
7. **Normal ordering**: fetched `v0.2.11` > running `0.2.10` → update chip showing
   `v0.2.11`; fetched == running → green chip showing the running version.
8. **Failure path**: non-200 / timeout → offline chip, no "latest" claims.
9. **Pre-release/property check**: for any stubbed tag list, assert
   displayed-version ≥ running version whenever the chip claims "already latest".

---

## 5. Lib-only release hygiene items this touches

Because the bundle is lib-only with **no build step**, nothing generates or validates the
artifacts a build pipeline normally would:

- **Hand-inlined version constants**: `PLUGIN_VERSION` in `lib/client.js`
  (`plugin-version-chip.js:5`) must be bumped in lockstep with `package.json` at every
  release; there is no codegen to sync them. Add a release-time check (a small script or
  CI step asserting `PLUGIN_VERSION === package.json#version === the tag being pushed`)
  so a forgotten bump fails the release. This bug class compounds Follow-up B: the chip's
  entire correctness rests on that constant being right.
- **Bundle syntax check**: with no build step, a syntax error ships straight to users.
  Run a parse check (e.g. `node --check` on the shipped file(s)) as a release gate before
  tagging.
- **No host-side update endpoint**: users receive updates only by re-fetching/re-installing
  the bundle themselves (a hard refresh is exactly what the user in thread B did). The
  version chip is therefore the **only** update-notification channel, which raises the
  stakes on §3's display rule. Release hygiene should include: documenting the manual
  update path, serving the bundle with cache headers that let hard refresh actually get
  the new file, and making the chip's tag fetch as fresh as the API allows
  (`no-store`), accepting that `s-maxage` shared caching may still lag for a few
  minutes — hence the defensive display rule rather than blind trust.

---

## Honesty notes (what could not be determined from the given material)

- The exact host API for querying existing attachment names beyond `getSnapshot()`
  occurrences is not in the excerpt; if the host documents a dedicated conflict-check or
  insertion-time dedupe, that documented path should be preferred after checking host
  docs/upstream source.
- The final fallback extension when both name and MIME are unusable is a policy choice not
  pinned by the fixture.
- No framework-specific changelog or "migration card" numbering was available; none was
  required here, but any claim about host-side behavior beyond the excerpt would need
  verification against upstream release notes before being treated as fact.
