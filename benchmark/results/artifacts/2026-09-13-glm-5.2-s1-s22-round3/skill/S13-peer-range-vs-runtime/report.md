# S13 · Peer Range vs Runtime Reality — Report

Task: read-only diagnosis (skill Mode A · inspect). Evidence pack: `fixture/` (npm install output, crash stack, plugin source excerpt, dsh changelog excerpt); corridor card `references/v0.1.2-alpha.4.md` (DSH-0.1.2-A4-03).

## 1. The exact runtime incompatibility

**What was removed:** the `Session.events` eagerly-materialized events array — the property the plugin reads 42 times (`liveAgent.session.events`, `session.events.at(-1)`, `replayEvents(agent.session.events)`, …).

**When:** removed in **dsh v0.1.2-alpha.4**. Changelog citation (fixture `dsh-changelog-excerpt.md`, "dsh-v0.1.2-alpha.4 release notes"):

> **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility.

The same change is carded as **DSH-0.1.2-A4-03** in the plugin-upgrade skill's 0.1.2-alpha.3 → 0.1.2-alpha.4 corridor.

**What replaced it:** the on-demand read API on `@deepseek-ai/dsh-session`:
- `session.seq` — current log length (a `SessionLogOffset`);
- `session.eventAt(SessionSeq(i))` — one accepted, deeply frozen event;
- `session.snapshotEvents(fromSeq?, toSeqExclusive?)` — frozen snapshot of a half-open range (complete snapshot cached until next append);
- `session.ownEvents()` — events this session appended itself, excluding the fork-inherited prefix.

Ledger for this plugin's call sites: `session.events.length` → `session.seq`; `session.events.at(-1)` → `session.eventAt(SessionSeq(session.seq - 1))`; whole-log iteration (the crashing `replayEvents(...)` / `for...of` in `prepareReplayEvents`) → `session.snapshotEvents()`. Note also DSH-0.1.2-A4-04: seq/offset values are now branded `SessionSeq`/`SessionLogOffset` numbers, and the returned snapshot must not be cached across appends when live data is needed.

**Why the crash looks like it does:** the plugin is plain JavaScript, so `session.events` reads as `undefined` instead of failing typecheck; `prepareReplayEvents` then tries to iterate it and throws `TypeError: events is not iterable`, which surfaces as `failed to apply loader entry dsh-tui` during `Fiber._reload` — a startup load failure of the whole plugin tree entry.

## 2. Why npm installed without warnings

The plugin declares `peerDependencies: "@deepseek-ai/dsh-*": "^0.1.2-alpha.2"` (all 27 packages). The host bundles those packages at **0.1.2-alpha.5**, and in semver — including npm's prerelease-aware comparison — `0.1.2-alpha.5` satisfies `>=0.1.2-alpha.2 <0.2.0-0`. npm's peer check is a **pure version-range arithmetic check against package metadata**: it compares version strings, nothing else.

**What `^0.1.2-alpha.2` does guarantee:** the host packages' *version numbers* fall inside the range, so npm considers the peer "compatible" and installs silently (no ERESOLVE, no warning).

**What it does NOT guarantee:** anything about the actual exported API of those versions. npm never inspects whether symbols the plugin imports still exist, whether types changed, or whether the host's runtime behavior matches what the plugin's code assumes. The range encodes only what the *plugin author asserted* when publishing — and the author asserted a range that spans a known breaking edge (alpha.3 → alpha.4 removed `Session.events`). Semver ordering says alpha.5 > alpha.2, but semver ordering says nothing about API stability across prereleases; a `^` range over prerelease versions is a claim of compatibility the author did not verify. npm also does not know DSH's per-release breaking-change policy — that knowledge lives in release notes/corridor cards, not in package metadata.

## 3. The fundamental principle

- **Peer-range satisfaction** is a *static, package-metadata-level* check: "is the installed package's version string inside the declared semver range?" It validates numbers against ranges.
- **Runtime compatibility** is a *behavioral, code-level* reality: "does the plugin's code, as it executes against the host's actual exported objects, find the properties, methods, signatures, and semantics it expects?" Only load-and-run (or a typecheck against the real declarations) can validate it.

**Categories of breakage that pass peer-range validation but crash at runtime** (two required; more listed):

1. **Removed/renamed API surface** — exactly this case: `Session.events` (and e.g. `seedLength`, both removed at alpha.4 while inside the satisfied `^` range). The property is `undefined` at runtime; version strings still match.
2. **Changed function signatures / call contracts** — e.g. a parameter added, dropped, or re-typed (A4-04: plain `number` no longer valid where branded `SessionSeq`/`SessionLogOffset` is expected; constructors now throw `TypeError` on invalid input). Versions match; the call throws.
3. **Behavioral/semantic changes** — defaults flipped, events reordered, validation tightened (e.g. the `history` request's `atSeq` now rejected as `gateway/bad-request`), which crash or corrupt logic without any version conflict.
4. **Missing exports / renamed packages** — importing a name that no longer exists resolves to `undefined` (untyped JS) or fails at module load, again invisible to semver.

## 4. What the plugin author should have done

**Before publishing (catch it):**
- Run the plugin's typecheck and tests against the *actual* target versions, not just the range floor: `tsc --noEmit` and the test suite with `@deepseek-ai/dsh-*` resolved at `0.1.2-alpha.5`. A typed build would have failed immediately with "Property 'events' does not exist on type 'Session'" (per A4-03's documented symptom). Shipping untyped JS makes this step mandatory, not optional.
- Run a real mount/verification layer: cold-start a real DSH profile at each supported host version and confirm the plugin applies and a core path executes (the skill's runtime-validation layer / `verify-runtime.mjs` pattern), rather than trusting the green install.
- Consult the host's release notes / corridor cards for each edge the declared range spans. The range `^0.1.2-alpha.2` spans alpha.3→alpha.4, which contains a documented breaking removal aimed exactly at this plugin's touchpoint (session-log reads). Publishing a range across a known breaking edge without testing that edge is the root authoring error.

**To help users (encode vs. detect):**
- **What the peer range / engines should encode:** the *verified* compatibility cohort — the exact set of host versions the plugin was actually built and tested against. Across prerelease/breaking-prone lines, that means a **pinned exact version** (or narrow `~`/exact pin per package, consistent across the whole `dsh-*` cohort), widened only after each new host version is tested. A caret range over prereleases asserts unverified compatibility.
- **What needs a runtime feature-detection guard:** API-presence checks that degrade gracefully instead of crashing — e.g. before replay, branch on `typeof session.snapshotEvents === 'function'` (new API) vs `Array.isArray(session.events)` (old API), and fail with a clear "host version unsupported" message otherwise. Removals of this kind (a whole property disappearing) are cheap to detect at apply() time and turn a hard `TypeError: events is not iterable` startup crash into an actionable diagnostic.

## 5. What the user can do RIGHT NOW (pre-install check)

**Concrete check: inspect the plugin's declared API usage against the target host's actual declarations before installing.** For example:

1. **Cheap metadata check first:** `npm view @deepseek-harness-tui/dsh-tui peerDependencies` — a caret prerelease range (`^0.1.2-alpha.2`) spanning known breaking edges is itself a red flag that the author did not pin a verified cohort.
2. **The decisive check:** fetch the tarball without installing it (`npm pack @deepseek-harness-tui/dsh-tui --dry-run` or download and extract), grep the shipped code for host-API access patterns (`grep -n "\.events" *` / `session.events`), and typecheck or cross-reference those names against the installed host's type declarations (`node -e "console.log('events' in require('@deepseek-ai/dsh-session/lib/types'))"` or `tsc` against the local `@deepseek-ai/dsh-session@0.1.2-alpha.5` declarations). `Session.events` is absent from the alpha.4/5 declarations while the plugin references it 42 times → predicted breakage, do not install.
3. Equivalently, consult the host release notes / corridor cards for every version edge inside the declared range and check whether any card touches an API the plugin uses (here: DSH-0.1.2-A4-03 names `Session.events` removal and its replacement API directly).

The generic rule: peer ranges are read at install time and verify nothing about code; the only reliable pre-install signal is comparing the plugin's *referenced symbols* against the target host's *exported symbols* (types or runtime reflection).

## Summary table

| Question | Answer |
|---|---|
| Broken API | `Session.events` (array) read 42× by the plugin |
| Removed in | dsh v0.1.2-alpha.4 ("Replace `Session.events` with on-demand read APIs") |
| Replacement | `session.seq`, `session.eventAt()`, `session.snapshotEvents()`, `session.ownEvents()` (card DSH-0.1.2-A4-03; + branded seq types A4-04) |
| Why npm silent | `0.1.2-alpha.5` satisfies `^0.1.2-alpha.2`; peer check is version-string arithmetic only, never API inspection |
| Principle | peer range = static metadata check; runtime compatibility = behavioral code-level check |
| Passes-range-but-crashes classes | removed/renamed symbols; changed signatures/typed contracts; behavioral/semantic changes |
| Author fix | test/typecheck/mount against actual target versions; pin verified cohort in peers; feature-detect (`typeof session.snapshotEvents === 'function'`) instead of assuming |
| User pre-install check | `npm pack --dry-run` + grep plugin for host-API symbols + verify against target host's type declarations / release-note corridor cards |

*Fixture directory untouched; no migrations, installs, or external access performed; report written to the designated output directory only.*
