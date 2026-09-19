# S13 Diagnostic Report - Peer Range vs Runtime Reality

User reports: @deepseek-harness-tui/dsh-tui@0.1.0-beta.4 installed cleanly against dsh 0.1.2-alpha.5 (no peer warnings), but crashes at startup. Evidence pack (fixture README.md, npm-install-output.txt, crash-stack.txt, plugin-source-excerpt.js, dsh-changelog-excerpt.md) confirms the diagnosis below.

## 1. The exact runtime incompatibility

WHAT was removed: the `Session.events` property - the eagerly materialized events array on the session object.

WHEN: dsh `v0.1.2-alpha.4`. The changelog excerpt (dsh-changelog-excerpt.md, "dsh-v0.1.2-alpha.4 release notes") says:

> **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` - the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility.

What replaced it: the on-demand read APIs `seq`, `eventAt(index)`, and `snapshotEvents()` (returning the events array on demand instead of holding it on the session object). A companion change in the same release ("Distinguish `SessionSeq` and `SessionLogOffset` with strong types") further signals that event/sequence access APIs changed shape.

How this produces the observed crash: the plugin reads the removed property in many places - plugin-source-excerpt.js shows:

- line 734: `const events = liveAgent.session.events;`
- line 6685: `replayEvents(agent.session.events);`
- line 657: `const last = session.events.at(-1);`
- lines 2685, 3004, "... 42 total references to `.events` on session objects"

At alpha.4+ `session.events` is `undefined`. The crash stack (crash-stack.txt) shows exactly that: `TypeError: events is not iterable` at `prepareReplayEvents (channel.js:623:25)` inside `createChannel (channel.js:6685:5)` during `Fiber._reload` - the plugin iterates `undefined` because it passed `session.events` (now `undefined`) into `replayEvents`, which tries to iterate it.

## 2. WHY npm installed with no warnings

npm's peer-dependency check is a pure semver arithmetic check on package metadata. The plugin declares `"@deepseek-ai/dsh-session": "^0.1.2-alpha.2"` (plus ~27 other `dsh-*` packages, per npm-install-output.txt). The installed packages are 0.1.2-alpha.5.

What `^0.1.2-alpha.2` guarantees: the installed version satisfies the numeric interval `>=0.1.2-alpha.2 <0.2.0-0` (caret on a 0.x version pins the minor and allows only patch/prerelease increments; prerelease comparison orders alpha.2 < alpha.5 within 0.1.2). 0.1.2-alpha.5 sits inside that interval, so npm's check passes - silently, as the install log shows ("added 77 packages...", "No peer dependency warnings were emitted").

What it does NOT guarantee:

- That any exported API surface (properties, methods, types) still exists - semver ranges only compare version strings; they carry no information about the API at those versions.
- That the maintainer honored semver discipline within a pre-release channel: in 0.1.x-alpha territory, breaking API removals (like removing `Session.events` in alpha.4) are routinely shipped as prerelease bumps, which the caret range happily accepts.
- `ehavioral compatibility - same-named APIs can change signature, return type, iteration semantics, or sync/async-ness.

So "npm said nothing" only means "0.1.2-alpha.5 is within the declared numeric range", nothing more.

## 3. The fundamental principle

- Peer-range satisfaction checks: does the declared version string of the installed dependency fall inside the declared semver interval? It is a static, package-metadata-level comparison of two numbers - it never reads code, never runs code, and knows nothing about which APIs exist at either version.
- Runtime compatibility checks: does the actual code of the host at the installed version still provide the APIs the plugin's actual code calls, with compatible shape and semantics? It is a behavioral, code-level reality, observable only by executing (or statically analyzing) both sides against each other.

At least two categories of breakage that pass peer-range validation but crash at runtime:

1. Removed API (this case): `Session.events` deleted in alpha.4; 0.1.2-alpha.5 still satisfies `^0.1.2-alpha.2`, yet 42 references to `.events` in the plugin hit `undefined`.
2. Changed API shape/semantics under the same name: e.g., the same release's `SessionSeq`/`SessionLogOffset` strong-type split - a property that keeps its name but changes type, signature, or sync-to-async behavior passes any range check yet breaks call sites (type errors at compile time, `not iterable`/`not a function` at runtime). Also common: exported symbols moved/renamed between packages, and protocol/wire-format changes - all invisible to semver arithmetic.

## 4. What the plugin author should have done

To catch this before publishing (testing against the actual target version):

- Add an integration test that installs the plugin against each dsh version in the supported range's prerelease stream (at minimum the latest `0.1.2-alpha.x`) and exercises the startup path (`createChannel`) - a single smoke test iterating a session's events would have caught `events is not iterable` before release.
- Pin CI to the exact dsh versions the range spans (alpha.2 ... latest alpha) - e.g., a small version matrix installing `@deepseek-ai/dsh@0.1.2-alpha.N` per job.
- Track the host's changelog for pre-release channels; the alpha.4 notes explicitly say "Developers should pay attention to compatibility" about exactly this change.

What to encode in metadata vs. guard at runtime:

- Peer range / engines field should encode what is actually tested and true: if the plugin requires the pre-alpha.4 session API, declare `">=0.1.2-alpha.2 <0.1.2-alpha.4"` (an explicit upper bound), or better, restrict to a known-good version (`"0.1.2-alpha.3"`) until the plugin is migrated. A range that "looks friendly" but spans a known breaking change is a false advertisement. An engines-style host-version field follows the same rule: encode verified bounds, not aspirations.
- Runtime feature detection is the right tool when the plugin wants to support both API generations. Instead of `liveAgent.session.events`, guard once at the seam:

  const events = typeof session.snapshotEvents === 'function'
      ? session.snapshotEvents()        // alpha.4+: on-demand read API
      : session.events;                 // legacy: eagerly materialized array
  if (!Array.isArray(events)) throw new Error('unsupported dsh session API; require dsh <0.1.2-alpha.4 or upgrade dsh-tui');

  A fail-loud guard with a clear message beats an opaque `events is not iterable` deep in the stack. Feature detection enables supporting a wider range; the peer range should still honestly state what is supported.

## 5. What the user can do RIGHT NOW (pre-install check)

A concrete check before installing any community plugin against a pre-release host:

- Read the host's changelog for every version inside the plugin's declared peer range, not just the top. Here: the plugin claims `^0.1.2-alpha.2`; that interval contains 0.1.2-alpha.4, whose release notes (in the fixture) remove `Session.events`. Ten seconds of changelog reading would have predicted the crash.
- Equally concrete: diff the API surface the plugin uses against the installed host - inspect the plugin source (published on npm / GitHub) for the session properties it touches (`.events`, `.seq`, `eventAt`) and verify each exists in the installed dsh version's typings or source.
- Cheapest of all: install into a throwaway environment first (a container/VM or a temp npm prefix) and smoke-run `dsh-tui` before touching the real installation - a crash in a sandbox costs nothing.

## Key evidence citations

- npm-install-output.txt: peer deps all `"^0.1.2-alpha.2"`; installed `@deepseek-ai/dsh@0.1.2-alpha.5` "satisfies >=0.1.2-alpha.2 <0.2.0-0 in semver. npm's peer check passes silently."
- crash-stack.txt: `TypeError: events is not iterable` at `prepareReplayEvents (channel.js:623:25)` <- `createChannel (channel.js:6685:5)` <- `Fiber._reload`.
- plugin-source-excerpt.js: `const events = liveAgent.session.events;  // <- line 734`; "42 total references to `.events` on session objects".
- dsh-changelog-excerpt.md: dsh `v0.1.2-alpha.4` - "**Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` - the eagerly materialized events array is removed".
