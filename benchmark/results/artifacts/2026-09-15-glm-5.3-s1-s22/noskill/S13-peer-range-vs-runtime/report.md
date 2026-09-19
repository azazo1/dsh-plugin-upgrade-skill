# S13 · Peer Range vs Runtime Reality — Report

## Summary

The plugin `@deepseek-harness-tui/dsh-tui@0.1.0-beta.4` installs cleanly against dsh `0.1.2-alpha.5`
because the plugin's peer ranges (`^0.1.2-alpha.2`) are satisfied by alpha.5 in semver ordering — but
dsh **removed the eagerly materialized `Session.events` array in v0.1.2-alpha.4**, and the plugin reads
that array in 42 places, so it crashes at startup with `TypeError: events is not iterable`.

## 1. The exact runtime incompatibility

**What was removed:** `Session.events` — the eagerly materialized events array on the session object.

**When:** dsh **v0.1.2-alpha.4** (a prerelease *between* alpha.2 and alpha.5, both of which the peer
range admits).

**What replaced it:** on-demand read APIs — `seq`, `eventAt()`, and `snapshotEvents()` — plus
strongly typed `SessionSeq` / `SessionLogOffset` distinctions.

**Changelog citation** (fixture `dsh-changelog-excerpt.md`, "dsh-v0.1.2-alpha.4 release notes"):

> - **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and
>   `snapshotEvents()` - the eagerly materialized events array is removed to reduce memory overhead
>   in long sessions. Developers should pay attention to compatibility. (@kermanx)
>
> - **Distinguish `SessionSeq` and `SessionLogOffset` with strong types** - developers should pay
>   attention to compatibility. (@tianyicui)

**Crash chain:** `plugin.js:425 apply` → `createChannel` (`channel.js:6685`) → `replayEvents`
(`channel.js:6127`) → `prepareReplayEvents` (`channel.js:623`) → `TypeError: events is not iterable`.
The plugin source reads `liveAgent.session.events` (`channel.js:734`), `session.events.at(-1)`
(line 657), and 42 total `.events` references; on alpha.4/5 that property no longer holds an
iterable array, so the very first read blows up inside the plugin's own code during
`Fiber._reload` — i.e., at plugin-apply time, before any UI appears.

## 2. Why npm installed without warnings

npm's peer-dependency resolution is a **static, metadata-level semver check**. It asks exactly one
question: *does the installed version specifier fall inside the declared range?*

- Range `^0.1.2-alpha.2` means `>=0.1.2-alpha.2 <0.2.0-0`. In prerelease semver ordering,
  `0.1.2-alpha.5 > 0.1.2-alpha.2`, so alpha.3, alpha.4, and alpha.5 all satisfy the range. The check
  passes, npm prints nothing.
- **What the peer range guarantees:** only that npm considers the *version numbers* compatible —
  the host package will be deduped/colocated with the peer rather than installed as a second copy.
- **What it does NOT guarantee:** anything whatsoever about the *code* inside those versions. It does
  not parse the plugin's imports, does not check that APIs it uses still exist, does not read
  changelogs, and does not run the plugin. A breaking API removal shipped inside the range
  (prerelease stream or not) is invisible to it. Notably the changelog itself flags "Developers
  should pay attention to compatibility" — that signal lives in release notes, not in package.json,
  and npm never sees it.

There is also an authoring error here: alpha.4 made a **breaking** change, so semver hygiene would
demand at least a `0.1.3-alpha.1`-style bump (or restricting the peer range to `~0.1.2-alpha.2` /
`<=0.1.2-alpha.3`). By leaving `^0.1.2-alpha.2` in place, the author told every consumer "any
0.1.2-alpha.N ≥ 2 is fine", which the runtime then falsified.

## 3. Peer range satisfaction vs runtime compatibility

- **Peer range satisfaction** checks: a static, package-metadata-level relationship — *version
  numbers* against a semver range. It is satisfiable without loading a single line of code.
- **Runtime compatibility** checks: a behavioral, code-level reality — whether the APIs, data
  shapes, events, and lifecycle contracts the plugin *actually calls* still behave as assumed in the
  specific build it lands on.

Categories of breakage that pass peer-range validation but crash (or misbehave) at runtime:

1. **API removal/rename** (this case): `Session.events` deleted in favor of `eventAt()` /
   `snapshotEvents()`. Static range check passes; `events is not iterable` at apply time.
2. **Type/semantic changes without a version signal**: e.g. the `SessionSeq` vs `SessionLogOffset`
   split from the same release — a number that used to be interchangeable is now two strongly
   typed concepts; arithmetic mixing them compiles/installs fine and produces off-by-one or wrong-
   event bugs at runtime.
3. Other recurring categories: behavioral contract changes (an event that used to fire eagerly now
   fires lazily or never — Waterfall listeners that must call `next()`, eagerly-vs-on-demand
   materialization timing), removed/renamed config fields that silently change defaults, and async/
   timing changes (a formerly-synchronous property is now a promise or a method), which surface as
   `TypeError`s or hangs rather than install warnings.

## 4. What the plugin author should have done

**Before publishing (catch it):**

- Run the plugin's test suite / smoke-start against the *actual newest* versions inside every
  declared peer range — here, specifically 0.1.2-alpha.4 and alpha.5, not just alpha.2. A single
  `dsh-tui` launch against alpha.5 would have hit `events is not iterable` immediately.
- Treat changelog entries marked "developers should pay attention to compatibility" as release-
  blocking inputs: read the host changelog between the version tested and the top of the peer range.
- Follow semver for the *host-facing* range: since the host shipped a breaking removal inside the
  alpha stream, pin the range to what was actually verified (e.g. `>=0.1.2-alpha.2 <0.1.2-alpha.4`
  or a `~`-style tight bound), and widen it only after re-testing.

**To help users (encode vs guard):**

- **Encode in metadata** (peerDependencies / engines): the *set of host versions actually tested and
  known to work* — a narrow, empirically verified range, not an optimistic one.
- **Runtime feature-detection guard**: what metadata can never capture (API presence/behavior within
  a satisfying version) needs code:

  ```js
  const events = typeof session.snapshotEvents === 'function'
    ? session.snapshotEvents()      // dsh >= 0.1.2-alpha.4
    : session.events                // legacy shape
  if (events === undefined) {
    throw new Error('dsh-tui: this dsh build exposes neither Session.events nor snapshotEvents(); ' +
      'please report your dsh version')
  }
  ```

  Better: migrate the plugin to the new `eventAt()`/`snapshotEvents()` APIs outright and keep the
  guard only as a loud, actionable error message rather than a raw `TypeError`.

## 5. What the user can do right now (pre-install check)

**Concrete check: diff the host changelog against every API the plugin touches, before installing.**
Practically:

1. Read the host's changelog between the peer-range floor and the version you have installed
   (here: v0.1.2-alpha.3 through alpha.5). The alpha.4 entry explicitly says `Session.events` was
   removed — a 30-second read that predicts the exact crash.
2. Grep the plugin's dist/source for the host APIs it uses (`grep -c "\.events" dist/*.js` → 42
   hits) and intersect that list with the "removed/renamed" bullets from the changelog. Any overlap
   is a red flag that npm will never raise.
3. Cheapest dynamic variant: install into a scratch directory/throwaway global prefix and run the
   plugin's startup command once (`dsh-tui` then exit) before relying on it — a smoke-start against
   the real host version exposes "installs fine, crashes at apply" breakage instantly.

The general lesson: peer-range satisfaction is necessary but nowhere near sufficient; it is a version
arithmetic check, and only a changelog review plus a one-shot runtime smoke test validates behavioral
compatibility.

## Evidence

All findings cite the read-only fixture: `npm-install-output.txt` (clean install, satisfying
ranges), `crash-stack.txt` (`events is not iterable` stack), `plugin-source-excerpt.js` (42
`.events` references, line 734/6685/657), `dsh-changelog-excerpt.md` (alpha.4 removal entry).
