# S10 · Paste Renaming & Version-Chip Follow-Ups — Report

Task type: Mode A (read-only inspection/design) under the plugin-upgrade skill. No files
inside the fixture or the benchmark repo were modified; nothing was executed, installed,
or published. Evidence: the four fixture files (attachment flow, version chip, user
threads, captured tags API response) for `@org/dsh-attach-input` v0.2.10.

---

## 1. Follow-up A — renaming design for pasted files

### Naming scheme

- **Images** (clipboard items whose kind is an image — `item.kind === 'string'` /
  `file.type.startsWith('image/')` on the acquisition side): `paste_image.png`,
  `paste_image(2).png`, `paste_image(3).png`, …
- **Other pasted files**: `paste_file.<ext>` — `paste_file.pdf`, `paste_file(2).pdf`, …
- The first item takes the un-numbered base name; every later collision appends
  `(n)` with n = 2, 3, … continuing across batches (two separate pastes of two
  screenshots produce `paste_image.png` and `paste_image(2).png`, not two
  `paste_image.png`).

### Where the rename is applied — and what stays untouched

The rename belongs **on the paste acquisition path only, before the items reach
`add()`** (or, if implemented inside `add()`, gated by an explicit acquisition-path
flag such as `{ rename: 'paste' }` passed only by the paste handler). Concretely:

- In the clipboard/paste event handler, after collecting the `DataTransfer` files into
  items, rewrite each pasted item's display `path` to the computed name before calling
  `add(sessionId, items)`.
- `add()` itself, the drag-and-drop path, and the file/folder picker path stay
  **untouched**: those items keep their real `item.path` verbatim, exactly as today.
  The behavior change is scoped to one acquisition path; the drop/picker flows must be
  regression-tested to prove their names are unchanged.
- The renamed value must flow to **both** sinks that today read `item.path`: the record
  `label` (which the dock chip renders as `record?.label ?? occurrence.label`) and the
  upload body's `files: record.items.map(item => ({ path: item.path, ... }))`. Renaming
  only the chip label while the upload still sends `image.png` would reproduce the bug
  server-side.

### How the number is chosen

Before assigning `paste_image.png`, compute the set of names already taken and pick the
first free name in sequence: base name, then `(2)`, `(3)`, … until no collision. The
scan must consider names taken by any attachment currently visible in the composer for
that session, regardless of how it was added — a user can drag in a file literally named
`paste_image.png` and a later paste must not clobber it (it should get `(2)`, or the
real-name file wins and the paste skips to the next free number).

### Authoritative "names already taken" source — and why the records Map is wrong

**Authoritative source: the composer's live state snapshot**
(`input.state.getSnapshot()` — the `occurrences` labels/paths currently held by the
DSH composer input for that session), optionally unioned with the paths already staged in
the current paste batch. The composer state is what the user sees and what insertion
actually mutates, so it is the ground truth for "this name is occupied".

A **plugin-side records cache alone is the wrong source** because of the alive-subscription
shown in the fixture: every record subscribes to the input state and runs

```js
const alive = current.occurrences.some(o => o.source === SOURCE && o.ref === ref);
if (alive || record.inflight !== undefined) return;
unsubscribe();
records.delete(ref);   // ← fires on ANY momentary empty snapshot
```

Any momentary snapshot with no occurrences (a transient state during composer
reconciliation, selection changes, or snapshot replacement) makes the subscription retire
the entry and delete it from the Map. The Map is therefore **lossy and timing-dependent**:
names that are still visibly attached in the composer can vanish from the cache, so a
uniqueness check against `records` would happily hand out `paste_image.png` twice. The
records Map is a render cache for dock chips, not a durable name ledger; uniqueness must
be decided against the composer snapshot (source of truth) at the moment of insertion,
with the in-batch `paths` set from `validateItems` extended to survive across pastes
via the snapshot rather than a single call's local `Set`.

## 2. Extension rule and display (guidance, unscored)

- **Extension**: take the extension of the original clipboard file name when it has one
  (`image.png` → `.png`). When the browser hands over an extensionless name (common
  with `clipboardData` files), fall back to the `file.type` MIME primary subtype:
  `image/png` → `png`, `application/pdf` → `pdf`; if `file.type` is empty or
  unparsable, default to `bin`. The scheme prefix is chosen by kind (`paste_image` vs
  `paste_file`), the suffix only by extension.
- **Dock chip**: display the renamed path (`paste_image(2).png`) via `record.label`,
  so users can tell consecutive screenshots apart.
- **Uploaded path**: the upload body must send the **same renamed path** — chip label and
  uploaded `path` must always be the same string for a given record, so the name seen
  in chat and the name stored server-side never diverge.

## 3. Follow-up B — root cause and the correct chip rule

### Root cause

The chip fetches
`https://api.github.com/repos/org/dsh-attach-input/tags?per_page=10`. The captured
response (`tags-api-response.txt`, taken ~90 s after pushing `v0.2.11`) shows:

- `HTTP 200`, `cache-control: private, max-age=60, s-maxage=300`, **`x-cache: HIT`,
  `age: 178`** — GitHub's API CDN served a **stale cached page** well within its
  shared-cache window;
- the body lists only `v0.2.9`, `v0.2.8`, `v0.2.7` — it predates **both** the
  `v0.2.10` and `v0.2.11` pushes, while `git ls-remote` proves both tags exist on
  the remote.

So minutes after the release, the "latest" computed from the response was `v0.2.9`. The
chip logic then did two wrong things:

1. `semverCmp('v0.2.9', '0.2.10') <= 0` → decided "no update available" — correct only
   by accident of the stale data being *older* than running;
2. `renderCurrentChip(tag)` renders **the fetched tag**, not the running version:
   `'✓ attach-input already the latest version v0.2.9'` — a locally-known-false
   statement (the user runs 0.2.10, and 0.2.11 exists). "A while later it changed its
   mind" when the cached page expired and a fresh response listed v0.2.11.

The bug class: **a cached remote value rendered as ground truth next to a locally-known
running version**. A fetched "latest" that is *older than the running version* is by
definition stale/wrong data — it must never be displayed as the latest.

### The display rule the chip should follow

- **Compare**: fetched latest tag vs the hand-inlined `PLUGIN_VERSION` (running
  version).
- **Show**: the **running `PLUGIN_VERSION`** in the green "already latest" chip. The
  fetched tag is used *only* to pick which chip to render:
  - `fetched > running` → update chip advertising `fetched`;
  - `fetched <= running` → green current chip showing **running**, e.g.
    `✓ attach-input v0.2.10`;
  - `fetched < running` (the stale-cache signature) → treat the update check as
    unreliable: show the neutral/offline chip (or the running version without any
    "latest" claim), never an older tag labeled "latest". Optionally add cache-busting
    (`Cache-Control: no-cache` request header / a cache-defeating query) and a re-check,
    but the invariant alone — never display a version older than the running one as
    "latest" — fixes the user-visible lie.

## 4. Regression tests that would have caught both follow-ups

**Follow-up A (renaming):**

1. *Multi-paste numbering*: simulate two pastes of one image each (two separate `add()`
   calls, browser name `image.png` both times); assert records/upload paths are
   `paste_image.png` then `paste_image(2).png`. Would fail on v0.2.10 (duplicate
   `image.png` twice).
2. *Mixed-kind paste*: paste one PNG + one PDF in one batch; assert `paste_image.png`
   and `paste_file.pdf`.
3. *Cross-path non-interference*: drag-drop a file and pick one via the folder picker;
   assert both keep their real names verbatim. Guards the scoping of the behavior change.
4. *Authoritative-source test*: add a paste, force the alive-subscription to observe a
   momentary empty snapshot (record retired from the Map), then paste again; assert the
   second paste still gets `paste_image(2).png` because the composer snapshot — not the
   records Map — supplied the taken-names set. This is the test that pins the fragile
   cache out of the conflict source.
5. *Real-name collision*: drop a real file named `paste_image.png`, then paste an
   image; assert the paste lands on `paste_image(2).png`.

**Follow-up B (version chip):**

6. *Stale-tag chip test*: mock `fetch` to return a tag list whose newest is **older**
   than `PLUGIN_VERSION` (exactly the captured `v0.2.9`-only page); assert the chip
   never renders text containing the older tag, never says "latest v0.2.9", and the
   current chip displays the running `PLUGIN_VERSION`. Would fail on v0.2.10's
   `renderCurrentChip(tag)`.
7. *Newer-tag test*: mocked newest `v0.2.11` > running `0.2.10` → update chip
   rendered with `v0.2.11` (guards the comparison direction).
8. *Fetch-failure/timeout test*: non-ok response or `AbortSignal.timeout` abort →
   offline chip, no version claim.
9. *Cache-header test*: assert the request carries `Cache-Control: no-cache` (if
   adopted) so the stale-HIT window is not silently trusted.

## 5. Lib-only release hygiene touched by these fixes

- **Hand-inlined version constant**: `PLUGIN_VERSION = '0.2.10'` lives in
  `lib/client.js` because the bundle is lib-only with no build step that could inject
  `package.json`'s version. Hygiene items:
  - add a release check (CI or pre-publish script) that fails when the inlined
    `PLUGIN_VERSION` disagrees with `package.json` `version` — the exact class of
    drift that makes the chip compare against a phantom version;
  - or move the constant to a tiny `lib/version.js` generated/read from
    `package.json` at publish time so there is a single source of truth;
  - bump **the plugin's own SemVer** (e.g. v0.2.12) — never the DSH host version — and
    keep tag, `package.json`, packed filename, and the inlined constant in sync.
- **Bundle syntax check**: with no build step, nothing type-checks or parses `lib/`
    before publish. Add `node --check lib/client.js` (every lib file) to the release
    checklist/CI so a syntax error cannot ship; the chip and renaming code are
    hand-edited JS with no compiler safety net.
- **How users actually receive the update**: this plugin has **no host-side update
    endpoint** — the chip is informational only. Users update by reinstalling/updating
    the package through whatever track installed it (their profile's package manager /
    registry install), then reloading the Web Client. Consequences for the chip copy: it
    should link to the release/install instructions rather than imply self-updating; and
    the update-availability signal must tolerate the CDN staleness above (fresh-tag
    re-check, no-cache) because a false "already latest" actively suppresses the only
    delivery channel (user-initiated reinstall) this plugin has.

---

## Skill-conformant summary sections

- **pre-existing (baseline)**: not collected — Mode A read-only inspection; no package
  scripts were run.
- **Completed**: full analysis/design for both follow-ups from the static fixture;
  renaming scheme, authoritative conflict source, chip root cause and display rule,
  regression-test list, release-hygiene items.
- **Skipped**: no runtime verification, migration planner, or card application — the task
  is a design/analysis brief over a static evidence pack; no corridor applies (no DSH
  host version change is involved).
- **Pending/residual risk**: exact composer-snapshot field names for occurrence labels
  were inferred from the fixture excerpt (`occurrences[].label` / dock fallback); the
  MIME table is guidance (unscored per the brief).
- **Rollback**: N/A — nothing was written outside the designated report directory.
- **Recommendations**: single-source the version constant; add `node --check` and the
  version-sync gate to CI; treat the composer snapshot as the conflict authority for any
  future name/label logic.
