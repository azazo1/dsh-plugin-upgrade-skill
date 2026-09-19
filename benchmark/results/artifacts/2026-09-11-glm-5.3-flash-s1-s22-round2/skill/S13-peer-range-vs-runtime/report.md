# S13 · Peer Range vs Runtime Reality — Diagnostic Report

Plugin: `@deepseek-harness-tui/dsh-tui@0.1.0-beta.4` · Host: `@deepseek-ai/dsh@0.1.2-alpha.5` · Mode A (read-only inspection)

## 1. The exact runtime incompatibility

**What was removed:** the eagerly materialized `Session.events` array. The plugin reads it at least 42 times (`plugin-source-excerpt.js`: `liveAgent.session.events` at line 734, `session.events.at(-1)` at 657, `agent.session.events` at 2685, `liveSession.events` at 3004, and the iteration in `replayEvents`). On dsh `0.1.2-alpha.5` that property no longer exists, so the plugin iterates `undefined` and crashes with `TypeError: events is not iterable` (`crash-stack.txt`, `prepareReplayEvents (channel.js:623:25)` → `createChannel` → `Fiber._reload`), surfacing as `plugin tree failed to load: failed to apply loader entry dsh-tui`.

**When:** dsh `0.1.2-alpha.4`. Changelog (`dsh-changelog-excerpt.md`): *"Replace `Session.events` with on-demand read APIs: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions."* The same release also split `SessionSeq`/`SessionLogOffset` into strong branded types — a second compatibility hazard for the plugin if it does sequence arithmetic.

**What replaced it:** on-demand read APIs — `session.seq` (current length/offset), `session.eventAt(i)` (indexed access), and `session.snapshotEvents()` (materialize a snapshot when iteration is genuinely needed). The plugin's fix is to replace its 42 `.events` reads with these APIs (or a snapshot for its replay path).

## 2. Why npm installed with no warnings

The plugin declares `peerDependencies` of `^0.1.2-alpha.2` on every `@deepseek-ai/dsh-*` package. npm's peer check is a **pure semver-range comparison against the version string in package metadata**: `0.1.2-alpha.5` satisfies `>=0.1.2-alpha.2 <0.2.0-0`, so the check passes silently ("added 77 packages", no warnings — `npm-install-output.txt`).

What a peer range **guarantees**: the host reports a version inside the author's declared range. Nothing more.

What it does **NOT guarantee**:
- That the APIs the plugin actually calls still exist, or keep their signatures, anywhere inside the range. Semver ordering (`alpha.5 > alpha.2`) says nothing about behavioral continuity — and within a `0.x` prerelease line, each alpha may carry breaking removals (as alpha.4 did). npm never inspects code, type declarations, or exports.
- That the peer declaration is even *accurate* — an author can write `^0.1.2-alpha.2` without ever testing against alpha.3–alpha.5. The range encodes the author's *claim*, not verified fact.
- Type-level compatibility either, at runtime: the plugin shipped against alpha.2's `.d.ts`; npm installs no typings check at install time.

## 3. The fundamental principle

- **Peer-range satisfaction** checks **static package metadata**: does the version string of the installed peer parse as a member of the declared semver range. It is declarative, resolved at install time, and blind to content.
- **Runtime compatibility** checks **behavior**: do the exact symbols, properties, signatures, and semantics the code touches at execution time exist and behave as expected in the loaded host build.

Two categories of breakage that pass peer-range validation but crash at runtime:
1. **API removal / property deletion** — this case: `Session.events` removed in alpha.4 while the range still spans it (→ `TypeError: events is not iterable`).
2. **Signature / semantic drift** — a function kept but with changed parameters or return type (e.g., the same alpha.4 corridor split `SessionSeq` vs `SessionLogOffset` branded types; the skill's corridor cards also record renamed services, changed command execution signatures, and moved composition fields). Similar classes: renamed modules/packages, and changed *composition* contracts (manifest/config keys removed) — all invisible to a version-number comparison.

## 4. What the plugin author should have done

**Catch it before publishing (test against real targets):**
- Add an integration/CI matrix that *cold-mounts* the plugin against each supported dsh host version (npm install dsh at the floor and at latest alpha/rc, run a real activation, not just a build). A startup-mount smoke test would have caught this immediately.
- Typecheck against the *newest* supported host's `.d.ts` (`skipLibCheck: false`), so removal of `Session.events` becomes a compile error, not a runtime `TypeError`.
- Read the host changelog / migration cards for each bump inside the claimed range before widening it.

**Encode compatibility honestly:**
- **Peer range / `engines`-style bounds** should encode *verified* upper bounds: since the plugin depends on `Session.events`, the honest declaration is `">=0.1.2-alpha.2 <0.1.2-alpha.4"` — an upper bound that excludes the breaking release. Peer ranges cannot express "works but uses removed APIs", so the range must break (and a new release re-widen it after migrating to `seq`/`eventAt()`/`snapshotEvents()`).
- **Runtime feature-detection guard** for things npm cannot check: at activation, detect the API shape before use, e.g. `const hasEvents = Array.isArray(session.events);` / `typeof session.snapshotEvents === 'function'`, and fail loud with an actionable message ("requires dsh <=0.1.2-alpha.3; upgrade the plugin for alpha.4+") instead of an opaque `events is not iterable` inside `Fiber._reload`. A single capability probe at `apply()` covers all 42 call sites.

## 5. Pre-install check the user can do right now

**Before installing, read the plugin's peer floor against the host's changelog since that floor.** Concretely: the plugin pins `^0.1.2-alpha.2`; before installing on alpha.5, skim the dsh release notes for alpha.3 → alpha.5 (or run `npm view @deepseek-ai/dsh@0.1.2-alpha.4` / check its changelog) for entries marked "breaking / developers should pay attention to compatibility". The alpha.4 entry explicitly removes `Session.events` — the API this plugin is built on. Since the plugin's last publish (0.1.0-beta.4) predates alpha.4, treat any host newer than the peer *floor* as unverified and either pin the host to `0.1.2-alpha.3` or wait for a plugin release declaring `^0.1.2-alpha.4`+. Equivalently, a dry probe: `npm view @deepseek-harness-tui/dsh-tui time.modified peerDependencies` — a plugin last touched before the host's breaking release will not satisfy it merely by its range.
