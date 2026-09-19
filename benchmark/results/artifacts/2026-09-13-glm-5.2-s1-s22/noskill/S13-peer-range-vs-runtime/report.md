# S13 · Peer Range vs Runtime Reality — Report

## 1. The exact runtime incompatibility

**What was removed:** the eagerly materialized `Session.events` array.

**When:** dsh `0.1.2-alpha.4` (changelog excerpt titled "dsh-v0.1.2-alpha.4 release notes").

**What replaced it:** on-demand read APIs — `seq`, `eventAt()`, and `snapshotEvents()`. The same release also split `SessionSeq` and `SessionLogOffset` into strongly typed (branded) values, so the replacement is not a drop-in rename: call sites must use the new APIs and the branded sequence types.

**Changelog citation** (fixture `dsh-changelog-excerpt.md`):

> - **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` - the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility. (@kermanx)

**Crash evidence:** `TypeError: events is not iterable` at `prepareReplayEvents (channel.js:623)` / `replayEvents (channel.js:6127)`, triggered from the plugin's `createChannel` reading `liveAgent.session.events` (plugin-source-excerpt.js line 734 area). Under alpha.5, `session.events` is `undefined`, so iterating it throws.

## 2. Why npm installed without warnings

npm's peer-dependency resolution is a **pure static metadata check**: it compares version *strings* of installed packages against the semver *ranges* declared in `peerDependencies`. The plugin declares `^0.1.2-alpha.2` for every `@deepseek-ai/dsh-*` package; the installed dsh bundles them at `0.1.2-alpha.5`, and `0.1.2-alpha.5` satisfies `>=0.1.2-alpha.2 <0.2.0-0`. So npm's check passes silently.

What `^0.1.2-alpha.2` **does** guarantee: the installed package's *version number* falls inside that semver range. That is all.

What it does **NOT** guarantee:

- That any specific API still exists in those versions — semver ranges say nothing about the actual exported surface of the code.
- That pre-`1.0.0` releases are backwards compatible at all. Semver explicitly states that anything below 1.0.0 may change at any time; the `^0.x` range treats `0.1.x` as compatible, but prerelease/beta churn in the `0.x` line routinely breaks APIs. The changelog itself flags "Developers should pay attention to compatibility."
- That the *peer package author* honored semver when publishing — the dsh maintainers removed `Session.events` within the same `0.1.2-alpha` series (alpha.2 → alpha.4), which is legal for `0.x` software and invisible to any range check.

In short: peer-range satisfaction is computed from `package.json` text; the crash lives in `channel.js` code. npm never loads or executes the plugin, so it cannot see the mismatch.

## 3. Fundamental principle: peer range vs runtime compatibility

- **Peer-range satisfaction** checks: *package-metadata-level version arithmetic* — "is the installed version number inside the declared semver range?" It is static, cheap, and content-blind.
- **Runtime compatibility** checks: *behavioral, code-level reality* — "does the plugin's actual usage of the host's APIs still work against the code that is actually loaded?" It can only be verified by loading/executing (or statically analyzing the real call sites against the real exports).

Categories of breakage that pass peer-range validation but crash at runtime (at least two required; five given):

1. **API removal/rename within a satisfying range** — exactly this case: `Session.events` removed in alpha.4 while `^0.1.2-alpha.2` still admits alpha.4/5.
2. **Type/strength changes to values crossing the boundary** — `SessionSeq` vs `SessionLogOffset` became branded types; code passing bare numbers/strings still type-erases past npm but fails at runtime or misbehaves.
3. **Behavioral/semantic changes with the same signature** — e.g. an API becoming lazy/async, throwing on new preconditions, or returning a different structure while keeping its name.
4. **Duplicate-instance / module-identity issues** — npm resolves the peer range to the host's copy today, but a slightly different install layout (nested copy satisfying the same range) yields two Cordis instances, and `instanceof`/context checks crash despite versions "satisfying".
5. **Timing/lifecycle changes** — a service the plugin consumes at apply-time appears later (or requires `inject`) in a newer satisfying version; the plugin loads but crashes at startup.

## 4. What the plugin author should have done

**Before publishing (catch it early):**

- Test/CI against the *actual* target versions, not just the declared floor: run the plugin's smoke/e2e suite against the latest released dsh (`0.1.2-alpha.5` at the time), and ideally a matrix including the range floor and the newest prerelease. A single "does it boot and replay a session" test against alpha.5 would have caught `events is not iterable` immediately.
- Treat the changelog's "Developers should pay attention to compatibility" notes as a to-do: alpha.4's note names `Session.events` removal explicitly.

**Encoding constraints correctly:**

- The peer range should encode the versions the plugin was actually *tested and known to work* against — for `0.x` prerelease ecosystems that means pinning tightly, e.g. `0.1.2-alpha.5` exact or `~0.1.2-alpha.5`/`>=0.1.2-alpha.5 <0.1.3`, not an optimistic `^0.1.2-alpha.2` that predates a known breaking removal. Widening the range is a claim that requires re-testing, not a default.
- `engines` can encode host-CLI/runtime constraints (Node version, dsh CLI range) — but only coarse, install-time facts. It cannot encode "API X exists".
- Anything finer-grained must be a **runtime feature-detection guard** in the plugin: e.g. check `typeof session.snapshotEvents === 'function'` (or `session.events === undefined`) and branch — use `snapshotEvents()`/`eventAt()` when present, fall back or emit a clear "requires dsh >= 0.1.2-alpha.4" error when absent. Never dereference the removed API unconditionally.

## 5. What the user can do RIGHT NOW (pre-install check)

A concrete pre-install check: **inspect the plugin's declared peer range against the target host version's changelog/breaking-change history before installing** — practically:

```sh
# 1. What does the plugin require?
npm info @deepseek-harness-tui/dsh-tui peerDependencies --json

# 2. What changed between the range floor and my installed version?
#    Read the host changelog for every release in (0.1.2-alpha.2, 0.1.2-alpha.5]:
#    dsh's 0.1.2-alpha.4 notes list "Replace Session.events ... removed".
```

Even more direct (works without executing the plugin): **grep the plugin's published source for the fragile API symbol** against the changelog's removal list, e.g. after `npm pack`/`npm i --dry-run` or on the installed tarball:

```sh
grep -rn "\.session\.events\|session\.events" node_modules/@deepseek-harness-tui/dsh-tui/
```

42 references to `.events` on session objects would show up instantly, and cross-referencing the alpha.4 changelog ("`Session.events` removed") identifies the break before the first run. Optionally do this inside a throwaway dry-run install (`npm install --dry-run` + tarball inspection) so nothing is executed on the real environment.

---
*Sources: fixture evidence pack (npm-install-output.txt, crash-stack.txt, plugin-source-excerpt.js, dsh-changelog-excerpt.md), read-only.*
