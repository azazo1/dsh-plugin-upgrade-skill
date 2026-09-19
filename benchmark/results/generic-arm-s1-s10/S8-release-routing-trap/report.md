# S8 — Release Routing Trap: Release-Engineering Diagnosis

Analyst note: this diagnosis was produced with a framework-agnostic migration
methodology manual only (no vendor changelog, no migration cards, no framework
docs). Every claim below is tied to a specific fixture file/line; anything that
cannot be established from the evidence pack is marked **undetermined** rather
than guessed.

## 0. Evidence base (read-only inventory)

Per the methodology (§1 inventory before conclusions), the coupling/release
surface in `/app/fixture/`:

| Evidence | File | Key fact |
|---|---|---|
| Mirror tag set | `ls-remote-tags.txt:3-14` | `public-org/dsh-ui-progress` carries tags v0.1.0 → v0.9.1, then **jumps to v0.9.7**; v0.9.2–v0.9.6 (including **v0.9.5**) are absent |
| Consumer runtime | `dsh-version.txt:2` | `dsh --version` → **0.1.1-rc.2** |
| Compatibility table | `compat-table.md:5-6` | plugin **v0.9.3 ↔ dsh 0.1.1-rc.1** (rc.2 = rc.1 + additive image preprocessing); plugin **v0.9.7 ↔ dsh v0.1.2-alpha.1** (migrated to the alpha.1 client API: views/legacy projection + `useConversation` seat) |
| Release sync script | `sync-script.sh:3-6` | per-mirror loop pushes **only `HEAD:main`** via `--force-with-lease`; **no tag push anywhere** |
| README default install | task brief | pins `@github:public-org/dsh-ui-progress#v0.9.5` |

Crash symptom (from the brief, not a fixture log): `TypeError: useConversation is not a function` in the browser slot entry after installing `#v0.9.7`.

## 1. Attempt-1 root cause: `#v0.9.5` never reached the mirror (tag distribution defect)

This is a **release-engineering defect in tag distribution**, not a consumer-side
network or command problem.

- The README's default install command pins `#v0.9.5` against the mirror
  `github:public-org/dsh-ui-progress`.
- The mirror's own tag listing (`ls-remote-tags.txt:3-14`) does not contain
  `refs/tags/v0.9.5` — the sequence goes `v0.9.0`, `v0.9.1`, `v0.9.7`. A
  git-commit-ish dependency on a nonexistent ref cannot resolve, so pnpm fails
  at resolution time, immediately, before any download.
- The mechanism is visible in `sync-script.sh:5`: the post-release sync runs
  `git push --force-with-lease "$remote" HEAD:main` for each remote and nothing
  else. **Branch heads are mirrored; tags are not.** Whatever tags exist on the
  mirror got there by some path outside this script (the exact path is
  **undetermined** from the evidence — most plausibly a one-off manual push,
  which would explain why v0.9.7 is present while v0.9.2–v0.9.6 are not).
- Conclusion: the README advertised an install source (mirror + tag) that the
  release pipeline never produced. The defect is "docs reference a ref the
  sync tooling does not distribute," i.e. the README pin and the mirror's
  actual tag set were never verified against each other.

## 2. Attempt-2 root cause: newest tag is forward-migrated past the consumer's runtime (version routing defect)

This failure has a **different root cause** from attempt 1: the tag existed, the
install succeeded, and the breakage is a **runtime API-compatibility mismatch**
in the forward direction.

- Compatibility direction, straight from `compat-table.md:5-6`: plugin **v0.9.7
  targets dsh v0.1.2-alpha.1**. Its notes say v0.9.7 "migrated to the alpha.1
  client API (views/legacy projection + `useConversation` seat)" — i.e. the
  plugin now calls a host API (`useConversation`) that belongs to the **0.1.2
  line**.
- The consumer's actual runtime (`dsh-version.txt`) is **dsh 0.1.1-rc.2** — one
  corridor step *behind* 0.1.2-alpha.1. On 0.1.1-rc.x the client API does not
  provide the `useConversation` seat the plugin invokes at call time, so the
  slot entry throws `TypeError: useConversation is not a function`.
- Why restarting dsh didn't help: this is not stale state or a half-finished
  install; it is a deterministic call-time coupling to an API the installed
  host simply doesn't have. Rebooting cannot conjure the symbol. (Methodology
  §1.2: host API imports used at **call time** surface exactly like this — the
  module loads, the first call explodes.)
- Corridor note (methodology §2): the table explicitly classifies 0.1.1-rc.2 as
  rc.1 + **additive** image preprocessing, so the plugin line verified on rc.1
  (v0.9.3) remains valid on rc.2. The breaking step in the corridor is
  0.1.1-rc.x → 0.1.2-alpha.1, which is precisely the step the consumer cannot
  take (production freeze) and the step v0.9.7 already took.
- In short: "newest tag" ≠ "compatible tag." Routing the consumer to the newest
  release routed them to an artifact built for a **newer** DSH than they run.

Whether the plugin manifest declares an engine/peer range that *should* have
blocked this install is **undetermined** — no plugin manifest is included in the
evidence pack. Empirically, the install-time layer did not block it (the install
succeeded), so any such guard is absent or not enforced on this path.

## 3. Exact remedy for the consumer right now (no dsh upgrade allowed)

The consumer's runtime is 0.1.1-rc.2; the only plugin version the compatibility
table verifies against the 0.1.1-rc line is **v0.9.3** (rc.2 is additive over
rc.1). So the remedy is to pin the compatible release line, not the newest tag:

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

**Important caveat, evidenced not assumed:** the mirror listing
(`ls-remote-tags.txt`) does **not** contain v0.9.3 either (same tag-distribution
defect as v0.9.5). So:

1. First check where `v0.9.3` actually exists:
   `git ls-remote --tags <candidate-repo>` for the primary GitHub repo (`origin`
   in the sync script) and the second mirror (`mirror2`). The fixture only
   lists `public-org`'s tags, so the tag sets of `origin`/`mirror2` — and even
   their org names/URLs — are **undetermined** from the given evidence.
2. Install from whichever repo carries the tag, e.g.
   `@org/dsh-ui-progress@github:<org-that-has-it>/dsh-ui-progress#v0.9.3`.
3. If no published repo carries v0.9.3, the maintainer must push the missing
   tag (step 4 below); there is no consumer-side workaround that is both
   evidence-backed and safe. Pinning v0.9.1 (which *is* on the mirror) is
   **not** a defensible fallback: the compatibility table does not state which
   dsh version v0.9.1 targets, so its compatibility with 0.1.1-rc.2 is
   undetermined.

Do **not** keep v0.9.7 installed on dsh 0.1.1-rc.2; uninstall/replace it as part
of the same change.

## 4. Maintainer-side fix so neither defect recurs

### 4a. Release tooling — distribute tags, then prove it

1. `sync-script.sh` must push refs, not just the branch head. Add an explicit
   tag push per remote, e.g. `git push "$remote" "refs/tags/v$VERSION"` for the
   release tag (or `git push "$remote" --tags` if wholesale mirroring is
   intended). Pushing only `HEAD:main` is the direct cause of attempt 1.
2. Add a post-release verification gate (methodology §4: verify in layers —
   here the "install-time" layer for the *release* itself): after syncing, run
   `git ls-remote --tags` against **every** remote and diff the tag set against
   the expected release set; fail the release pipeline on divergence. This
   turns "README pins a missing tag" from a consumer-reported incident into a
   CI failure.
3. Backfill: push the missing historical tags (v0.9.2–v0.9.6, at minimum
   v0.9.3) to all mirrors so the compatibility table's recommended versions are
   actually installable from the documented sources. Keep `--force-with-lease`
   discipline for branches, but never force-push published tags.

### 4b. Docs — route each consumer to the artifact for their runtime

1. The README default install command must pin a tag that (a) exists on the
   exact repo in the command and (b) matches the compatibility table's entry
   for the current stable dsh line. Today the default should be `#v0.9.3` for
   dsh 0.1.1-rc.x users; `#v0.9.7` must be labeled "requires dsh
   v0.1.2-alpha.1+".
2. Generate (or at least release-check) the README's install snippet and
   compatibility table from a single source at release time, so the pin, the
   tag set, and the table cannot drift apart. A release checklist item
   "README pin ∈ `git ls-remote --tags` of every mirror" closes the loop.
3. Longer term, declare the host-version floor in the plugin manifest
   (engine/peer range, methodology §1.1/§3.6) so that an install of a
   forward-migrated plugin against an older dsh fails **at install time** with
   a clear message instead of crashing **at call time** in the browser. Whether
   dsh's plugin manifest supports such a range is undetermined from the
   evidence; if it does not, a load-time guard in the plugin's slot entry
   (probe for `useConversation`, fail closed with a readable error) is the
   fallback.

## 5. Confidence and undetermined items (honesty ledger)

Established directly from evidence: the v0.9.5 absence from the mirror; the
sync script pushing no tags; the v0.9.7 → dsh 0.1.2-alpha.1 coupling and its
`useConversation` note; the consumer runtime being 0.1.1-rc.2; rc.2 being
additive over rc.1.

Undetermined from the given materials (stated, not guessed):
- The exact pnpm error text for attempt 1 (no log in the pack); the missing-ref
  resolution failure is inferred from the tag listing.
- The tag sets, org names, and URLs of `origin` and `mirror2`; only
  `public-org`'s listing is provided.
- How v0.9.7 reached the mirror when v0.9.2–v0.9.6 did not (a manual push is
  plausible but unproven).
- The plugin manifest contents (entry points, engine ranges), so the existence
  of any install-time compatibility guard cannot be confirmed.
- No upstream changelog or migration cards were available to this analyst; any
  card-ID-style mapping of the 0.1.1→0.1.2 API change would have to be made by
  reading the upstream release notes for every version in the corridor
  (methodology §2), which is outside this evidence pack.
