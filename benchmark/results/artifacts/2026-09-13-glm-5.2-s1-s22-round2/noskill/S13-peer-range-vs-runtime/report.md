# S13 · Peer Range vs Runtime Reality — Report

## 1. The exact runtime incompatibility

**What was removed:** the eagerly materialized `Session.events` array — the property the plugin reads 42 times (e.g. `liveAgent.session.events` at `channel.js:734`, `replayEvents(agent.session.events)` at line 6685).

**When:** dsh **v0.1.2-alpha.4**, per the changelog excerpt:

> **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility.

**What replaced it:** three on-demand read APIs on `Session`: `seq`, `eventAt()`, and `snapshotEvents()`. (The same release also split `SessionSeq` and `SessionLogOffset` into strong types.)

**How it crashes:** `agent.session.events` is now `undefined`; the plugin's `prepareReplayEvents` tries to iterate it → `TypeError: events is not iterable` inside `apply()`, which fails the whole loader entry (`plugin tree failed to load … dsh-tui`).

## 2. Why npm install passed silently

npm's peer-dependency check is a **pure static semver-range comparison against package metadata**. The plugin declares `^0.1.2-alpha.2` on every `@deepseek-ai/dsh-*` package; the installed dsh `0.1.2-alpha.5` bundles those packages at `0.1.2-alpha.5`, and in semver `0.1.2-alpha.5 >= 0.1.2-alpha.2 < 0.2.0-0`, so the range is satisfied.

What `^0.1.2-alpha.2` **guarantees**: only that the *version string* of each installed peer falls inside the declared range. Nothing more.

What it does **not** guarantee:

- that any specific API (here `Session.events`) still exists at any version inside the range;
- that pre-1.0/alpha releases keep any behavior — semver explicitly allows breaking changes in `0.x`, and prerelease ordering (`alpha.5 > alpha.2`) says nothing about API stability between alpha tags;
- that the plugin's *code* was ever exercised against the actual peer build it will run against.

The author declared a range that was never re-validated after alpha.4 shipped a removal, so the range was a stale promise, and npm faithfully enforced only the promise as written.

## 3. Fundamental principle

- **Peer-range satisfaction** checks: *package-metadata-level version arithmetic* — "is the installed version string within the declared range?" It is static, cheap, and blind to code.
- **Runtime compatibility** checks: *behavioral, code-level reality* — "do the actual functions/properties this plugin touches exist and behave as expected in the peer build that actually loads?" It can only be verified by executing (or statically analyzing exported symbols of) the real artifact.

Categories of breakage that pass peer-range validation but crash at runtime (two required, more given):

1. **API removal/rename** (this case): `Session.events` deleted in alpha.4 while `^0.1.2-alpha.2` still admits alpha.4/5.
2. **Type/shape changes**: `SessionSeq` vs `SessionLogOffset` now distinct branded types — code passing a bare number still "satisfies the range" but fails type checks or misuses the value at runtime.
3. **Behavioral/semantic changes**: a method keeps its name but changes return shape, ordering, or error semantics (e.g. an event map member becoming required-on-read).
4. **Load-order/lifecycle changes**: plugin-protocol slots, event modes, or registration contracts that changed between alphas without a version bump that the range would exclude.

## 4. What the plugin author should have done

**Before publishing:**

- Run the plugin's test suite against the *actual* target peers — at minimum the range's upper edge and the latest published alpha (alpha.4 and alpha.5 here), not just the version the author happened to develop against (alpha.2). A CI matrix over peer versions inside the declared range would have caught `events is not iterable` immediately.
- Treat every dsh alpha bump as potentially breaking: re-run tests and re-pin the peer range before republishing, even when semver "allows" the older range.

**Encoding vs. guarding:**

- The **peerDependencies range / engines field** should encode only what metadata can honestly promise: which *versions* the plugin was actually tested against. Since dsh is `0.x` with per-alpha breakage, a range spanning untested alphas (`^0.1.2-alpha.2` covering alpha.3–5 that were never tested) is over-broad; a tighter pin (e.g. exactly the tested alphas) is the honest static signal.
- **Runtime feature detection** must guard anything not guaranteed by the version string: e.g. `if (typeof session.snapshotEvents === 'function') { … } else { /* legacy path via session.events */ }`, or fail loudly with an actionable message ("this dsh-tui build requires `Session.snapshotEvents`, introduced in 0.1.2-alpha.4") instead of `TypeError: events is not iterable`.

## 5. What the user can do right now (pre-install check)

Concrete pre-install check: **before installing, diff the peer package's public API between the range floor and your installed version** — practically: read the peer package's CHANGELOG for every release between the range floor (`0.1.2-alpha.2`) and the installed version (`0.1.2-alpha.5]), looking for "removed"/"replaced"/"breaking" entries — exactly the alpha.4 `Session.events` replacement found here. Mechanically:

```sh
npm view @deepseek-harness-tui/dsh-tui peerDependencies   # what range is promised
npm view @deepseek-ai/dsh version                          # what you actually have
# then read the dsh CHANGELOG between alpha.2 and alpha.5 for removals
```

or grep the installed peer's type declarations for the symbols the plugin uses (`grep -r "\.events" node_modules/@deepseek-ai/dsh-session/dist/*.d.ts`) — absence of `events` in the shipped typings while the plugin references it is the same red flag, visible before ever running the plugin.

---
*Sources: fixture evidence pack — `npm-install-output.txt`, `crash-stack.txt`, `plugin-source-excerpt.js`, `dsh-changelog-excerpt.md` (read-only).*
