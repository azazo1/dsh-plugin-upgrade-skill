# S13 · Peer Range vs Runtime Reality — Diagnostic Report

## 1. The exact runtime incompatibility

**What was removed:** the `Session.events` property — the eagerly materialized array of session events that plugins could read and iterate directly.

**When:** dsh release **0.1.2-alpha.4**. The fixture changelog (`dsh-changelog-excerpt.md`, "dsh-v0.1.2-alpha.4 release notes (excerpt)") states:

> **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions.

**What replaced it:** three on-demand read APIs — `seq`, `eventAt()`, and `snapshotEvents()`. (A second alpha.4 change, "Distinguish `SessionSeq` and `SessionLogOffset` with strong types", is also flagged as a compatibility-relevant change.)

**Where the plugin breaks:** the plugin reads the removed property and iterates it. `plugin-source-excerpt.js` shows `liveAgent.session.events` (channel.js line 734), `replayEvents(agent.session.events)` (line 6685), `session.events.at(-1)` (line 657), and "42 total references to `.events` on session objects". `crash-stack.txt` shows the resulting failure on dsh 0.1.2-alpha.5:

```
TypeError: events is not iterable
    at prepareReplayEvents (channel.js:623:25)
    at createChannel (channel.js:6685:5)
    at apply (plugin.js:425:21)
    at async Fiber._reload (cordis/lib/index.js:1355:5)
```

On alpha.5 the property no longer exists (or no longer holds an array), so `events` is `undefined`, iteration throws `events is not iterable`, and the loader refuses the plugin: "plugin tree failed to load: failed to apply loader entry dsh-tui (@deepseek-harness-tui/dsh-tui)".

## 2. Why npm installed silently — what a peer range does and does not guarantee

`npm-install-output.txt` records: "No peer dependency warnings were emitted. The plugin's peerDependencies: \"@deepseek-ai/dsh-llm\": \"^0.1.2-alpha.2\" ... (24 more dsh-* packages, all \"^0.1.2-alpha.2\")". The explanation is in the same file: the installed `@deepseek-ai/dsh@0.1.2-alpha.5` bundles those packages at 0.1.2-alpha.5, "which satisfies >=0.1.2-alpha.2 <0.2.0-0 in semver. npm's peer check passes silently."

**What a peer range guarantees:** only a static version-number comparison. `^0.1.2-alpha.2` means "any version in the same minor (0.1.x) range ≥ 0.1.2-alpha.2 and below 0.2.0". The installed 0.1.2-alpha.5 satisfies that numeric interval, so npm's metadata-level check passes.

**What it does NOT guarantee:** that the plugin's code still calls APIs the host actually provides. Semver ordering (alpha.5 > alpha.2) says nothing about whether a breaking change was introduced between alpha.2 and alpha.5. In this project's pre-1.0 reality, an **alpha patch bump (alpha.2 → alpha.4) carried a removal-level breaking change** — exactly the situation semver ranges cannot see. Peer ranges are package-metadata declarations; they are never a runtime compatibility test.

## 3. The fundamental principle

- **Peer-range satisfaction** checks *static package metadata*: do the declared version strings of the host packages fall inside the declared semver intervals, as computed by npm at install time. It verifies *numbers*, not behavior.
- **Runtime compatibility** checks *code-level reality*: does the host, at the moment the plugin executes, actually export the symbols, methods, and object properties the plugin reads — with compatible signatures and semantics.

Two-plus categories of breakage that pass peer-range validation but crash at runtime:

1. **Removed/renamed APIs within the same semver range** — this case: `Session.events` removed in alpha.4 while `^0.1.2-alpha.2` still accepts alpha.4/5.
2. **Changed semantics/shape of a surviving API** — e.g. the same alpha.4 note's "Distinguish `SessionSeq` and `SessionLogOffset` with strong types": a value is still present but is now a branded type with different behavior, so iterating or comparing it fails.
3. **Changed signatures or config/protocol contracts** — a method still exists but takes/returns a different structure; the range still matches, the first call throws.

## 4. What the plugin author should have done

**Catch it before publishing (test against the actual target):**
- Run the plugin's integration/startup path against the *installed* dsh version(s) in CI — load the plugin in a real dsh session (as this crash does via `Fiber._reload`), not just against the version the typings were written for.
- Since alpha releases ship breaking changes, the CI matrix should track the host's latest alpha, not a pinned alpha.2; a single smoke test exercising the session-events read path would have caught all 42 `.events` references failing.

**Encode and guard appropriately (split static vs dynamic responsibility):**
- **Peer range / engines:** pin conservatively to the versions actually tested. After a known removal, `^0.1.2-alpha.2` is wrong; encode reality, e.g. `">=0.1.2-alpha.2 <0.1.2-alpha.4"` (or at least add `engines`/`peerDependenciesMeta` notes) so npm *does* warn on alpha.4+ instead of silently accepting it. For 0.x/alpha software, wide carets are a false promise.
- **Runtime feature-detection guard:** for APIs that may evolve, check presence before use and fail with an actionable message, e.g. `if (typeof session.snapshotEvents !== "function") throw new Error("dsh-tui requires dsh <0.1.2-alpha.4 or a release with snapshotEvents()")`. The migration to `seq`/`eventAt()`/`snapshotEvents()` should ideally be adopted in the plugin with a guard that supports both hosts.

## 5. What the user can do right now before installing

Concrete pre-install check: **read the plugin's declared peer range and compare it against the host's changelog for every version inside that range** before installing. In practice:

- Check the plugin's `peerDependencies` (`npm view @deepseek-harness-tui/dsh-tui peerDependencies`) and its own changelog for a statement like "tested against dsh 0.1.2-alpha.N".
- Then scan the host changelog in that interval: here, `dsh@0.1.2-alpha.4` explicitly announces "Replace `Session.events` ... Developers should pay attention to compatibility" — with your host at alpha.5, that is a red flag the peer range cannot give you.
- Failing that, install in a disposable environment (or `npm install --dry-run` plus a startup smoke test) so the "events is not iterable" crash surfaces before it touches your real session.

**Bottom line:** npm was correct — 0.1.2-alpha.5 *does* satisfy `^0.1.2-alpha.2`. The peer range and the runtime simply check different things, and this plugin published a range wider than its tested reality while alpha.4 removed the one API it depends on 42 times.
