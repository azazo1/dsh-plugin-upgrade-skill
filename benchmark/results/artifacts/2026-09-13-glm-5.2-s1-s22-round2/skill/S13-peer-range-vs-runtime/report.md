# S13 · Peer Range vs Runtime Reality — Report

Task: diagnose why `@deepseek-harness-tui/dsh-tui@0.1.0-beta.4` installs cleanly against
`@deepseek-ai/dsh@0.1.2-alpha.5` (peer range `^0.1.2-alpha.2`, satisfied) yet crashes at startup.
Mode A (read-only inspection) per the plugin-upgrade skill; no migrations or installs were executed and the
fixture directory was not modified.

Evidence used: `npm-install-output.txt`, `crash-stack.txt`, `plugin-source-excerpt.js`,
`dsh-changelog-excerpt.md` (all under the task's `environment/fixture/`), cross-checked against the skill's
corridor card `references/v0.1.2-alpha.4.md`.

## 1. The exact runtime incompatibility

**What was removed:** the eagerly materialized `Session.events` array — the property on the dsh Session
object that plugins read to get the full transcript event list (e.g. `session.events.at(-1)`).

**When:** removed in **dsh v0.1.2-alpha.4**. The changelog excerpt states:

> **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` —
> the eagerly materialized events array is removed to reduce memory overhead in long sessions.
> Developers should pay attention to compatibility. (@kermanx)

(The same release also branded `SessionSeq`/`SessionLogOffset`, per the skill's alpha.4 corridor card.)

**What replaced it:** three on-demand read APIs — `session.seq`, `session.eventAt()`, and
`session.snapshotEvents()`.

**Why the plugin crashes:** `dsh-tui@0.1.0-beta.4` was authored against the alpha.2-era API and reads
`session.events` in 42 places (fixture `plugin-source-excerpt.js`, e.g. line 734
`liveAgent.session.events`, line 657 `session.events.at(-1)`). On alpha.5 the property no longer exists,
so `session.events` evaluates to `undefined`; `prepareReplayEvents` then tries to iterate it, producing
`TypeError: events is not iterable` inside `createChannel → apply`, which fails the whole plugin tree load
(`crash-stack.txt`). Because the crash occurs during plugin `apply()`, the host aborts startup rather than
degrading gracefully.

## 2. Why npm install succeeded without warnings

npm's peer-dependency resolution is a **static, package-metadata-level semver check**. It asks exactly one
question: *does the installed version string of each peer package fall inside the range declared in
`peerDependencies`?* Here `^0.1.2-alpha.2` on the 0.x line means `>=0.1.2-alpha.2 <0.2.0-0`; the host's
bundled `0.1.2-alpha.5` falls inside that interval (npm treats later prereleases of the same
`0.1.2-alpha*` series as comparable, and the fixture notes npm passed silently). So the check succeeds.

What a peer range **guarantees**: only that npm will not warn about, or (under strict peer handling) reject,
the *version-string combination*. It encodes the author's *declared belief* about compatibility at publish
time — nothing more.

What it does **NOT** guarantee:

- that the author ever tested against any version in the range beyond (at best) the one they built against;
- that any API the plugin's code touches still exists, has the same name, signature, or semantics in the
  resolved version;
- that behavioral contracts (event ordering, async vs sync, type strictness) hold across the range;
- anything at all about the *code inside* the published tarballs — npm never loads or executes the plugin
  during install (no lifecycle script here), so nothing observes the runtime breakage.

In short: the range `^0.1.2-alpha.2` is a *claim*, not a *verification*. alpha.5 satisfying the range says
only that `5 > 2` in prerelease semver ordering — not that `Session.events` still exists at alpha.4/5.

## 3. Fundamental principle: peer-range satisfaction vs runtime compatibility

- **Peer-range satisfaction** checks *package metadata*: a version-string interval comparison between the
  declared range and the resolved version. It is static, cheap, and blind to code.
- **Runtime compatibility** checks *behavior*: whether the plugin's actual imports, property accesses, and
  call signatures against the *real loaded modules* of the resolved host version work when the plugin's
  `apply()` runs.

At least two categories of breakage that pass peer-range validation but crash at runtime:

1. **Removed/renamed API surface** (this case): the host deletes or renames an export/property
   (`Session.events` → `seq`/`eventAt()`/`snapshotEvents()`) within the same 0.x "compatible" range.
   Version metadata is unchanged in spirit; the property access `session.events` yields `undefined` and
   iteration throws.
2. **Behavioral/contract changes with unchanged names**: a method keeps its name but changes signature or
   semantics — e.g. the alpha.4 release also re-typed `SessionSeq`/`SessionLogOffset`, and adjacent
   corridors record signature changes (parameters added/reordered, sync→async, stricter payload validation,
   required fields on event contracts). The peer range still matches; the call throws or silently
   misbehaves at runtime.

(Further examples from the corridor cards: injected-surface signature drift, non-ignorable session events,
removed client runtime — all in-range.)

## 4. What the plugin author should have done

**Before publishing (catch it at the source):**

- Test against the *actual target versions*, not just the floor: CI matrix installing each released dsh
  version the peer range claims to cover — at minimum the range floor (alpha.2) and the current latest
  (alpha.4/5 at publish time) — and run a **real mount** (cold-start a profile, load the plugin, exercise
  one core path), not just typecheck against one pinned version.
- Keep the peer range honest: shrink it to what was actually tested (e.g. pin `0.1.2-alpha.2`–tested
  versions exactly, or `~`/exact pins on 0.x where semver's `^` is nearly meaningless for prereleases),
  and re-publish a new plugin release with a widened range only after re-verification. An untested
  `^0.1.2-alpha.2` spanning known-breaking alpha.4 removals is a false compatibility claim.
- Encode what metadata *can* encode: `peerDependencies`/`engines` for hard version floors and known-bad
  ceilings; everything else needs code.

**To help users (runtime resilience):**

- Add **runtime feature detection** instead of blind property access: e.g.
  `const events = typeof session.snapshotEvents === 'function' ? session.snapshotEvents() : session.events`,
  guarding each of the 42 `.events` touchpoints (or centralizing them behind one accessor), so the plugin
  degrades with a clear "unsupported dsh version, please upgrade dsh-tui" message instead of
  `TypeError: events is not iterable` killing the whole plugin tree at startup.
- Fail loud and early with a version/feature check at `apply()` time (per the DSH "misconfiguration fails
  loud" convention) rather than crashing deep in channel setup.

## 5. What the user can do RIGHT NOW (pre-install check)

Concrete pre-install check: **before installing, compare the plugin's peer range against the target dsh
release's changelog/breaking-change list** — e.g.
`npm view @deepseek-harness-tui/dsh-tui@0.1.0-beta.4 peerDependencies` alongside reading the dsh release
notes for every version between the range floor and the installed host (alpha.2 → alpha.5), looking for
"removed"/"replaced"/"developers should pay attention to compatibility" entries that touch APIs the plugin
uses. Here that single step surfaces the alpha.4 note `Replace Session.events with …` and flags the install.

A second, code-level variant: fetch the tarball (`npm pack --dry-run` / `npm view … dist.tarball`) and grep
the plugin's shipped code for the removed symbol (`grep -r "\.events" lib/`) — 42 hits against an API the
changelog says was removed in alpha.4 is disqualifying *before* anything is installed. (Equivalent skill
tooling: the read-only corridor cards in `references/v0.1.2-alpha.4.md` + a touchpoint grep of the plugin
source, per the skill's pre-flight seven-class scan.)

---

## Skill-structured summary

- **Pre-existing / baseline:** not collected (read-only diagnosis; no repository under migration).
- **Completed:** full root-cause analysis from the four fixture artifacts, cross-checked against the
  alpha.4 corridor card; all five report questions answered above.
- **Skipped:** no runtime reproduction (rules forbid installs/executions; the crash is fully explained by
  the static evidence). No Mode B/C actions — user asked for diagnosis, not migration.
- **Pending/residual risk:** the fix itself (migrating dsh-tui's 42 `.events` touchpoints to
  `seq`/`eventAt()`/`snapshotEvents()`, or pinning the host back to `<=0.1.2-alpha.3`) is out of scope
  for this read-only report; as a stopgap the user can downgrade the host to alpha.3 or wait for/patch a
  fixed dsh-tui release.
- **Rollback:** nothing was changed; no rollback needed.
- **Recommendations:** for the user, adopt the pre-install changelog/tarball grep check; for the plugin
  author, version-matrix CI with real mounts plus runtime feature guards as in §4.
