# S13 · Peer Range vs Runtime Reality — Diagnostic Report

Case: `@deepseek-harness-tui/dsh-tui@0.1.2-beta.4` (brief says `0.1.0-beta.4`; fixture consistently shows the alpha-range peer deps) installed cleanly on `@deepseek-ai/dsh@0.1.2-alpha.5`, yet crashes at startup. All evidence quoted from the fixture pack.

## 1. The exact runtime incompatibility

**WHAT was removed:** the eagerly materialized `Session.events` array.

**WHEN:** dsh **v0.1.2-alpha.4**.

**Changelog citation** (`dsh-changelog-excerpt.md`):

> ## dsh-v0.1.2-alpha.4 release notes (excerpt)
> - **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility. (@kermanx)
> - **Distinguish `SessionSeq` and `SessionLogOffset` with strong types** — developers should pay attention to compatibility. (@tianyicui)

**What replaced it:** `session.seq`, `session.eventAt(n)`, and `session.snapshotEvents()` (on-demand reads instead of a live array).

**Where the crash comes from** (`plugin-source-excerpt.js`): the plugin still reads the removed property, 42+ times:

```js
const events = liveAgent.session.events;    // line 734
replayEvents(agent.session.events);         // line 6685
const last = session.events.at(-1);         // line 657
// ... 42 total references to .events on session objects
```

On alpha.4/5, `session.events` is now `undefined`. Iterating `undefined` produces the observed error in `crash-stack.txt`:

```
TypeError: events is not iterable
    at prepareReplayEvents (channel.js:623:25)
    at replayEvents (channel.js:6127:33)
    at createChannel (channel.js:6685:5)
```

The comment in the stack file confirms the mechanism: "The crash happens INSIDE the plugin's own code, reading something called `events` from the dsh session object and trying to iterate it." The user runs alpha.5, the removal landed in alpha.4, so the plugin (written against ≤ alpha.3) crashes.

## 2. Why npm installed without any warnings

The plugin's peerDependencies (`npm-install-output.txt`) are, for all 27 `@deepseek-ai/dsh-*` packages:

```
"@deepseek-ai/dsh-llm": "^0.1.2-alpha.2"
"@deepseek-ai/dsh-agent": "^0.1.2-alpha.2"
"@deepseek-ai/dsh-session": "^0.1.2-alpha.2"
... (24 more dsh-* packages, all "^0.1.2-alpha.2")
```

The installed dsh 0.1.2-alpha.5 satisfies `^0.1.2-alpha.2` (i.e. `>=0.1.2-alpha.2 <0.2.0-0` in semver ordering). npm's peer check is therefore **silently satisfied** — "No peer dependency warnings were emitted."

**What a peer range guarantees:** only that the *version numbers* of the host packages fall inside the declared semver interval at install time. It is a static comparison of metadata strings against semver ordering rules.

**What it does NOT guarantee:**

- That the *APIs the plugin actually calls* still exist, still have the same signatures, or still have the same behavior in any version inside that range. `0.1.2-alpha.5 > 0.1.2-alpha.2` in semver order says nothing about whether `Session.events` survived from alpha.2 to alpha.5.
- That pre-1.0 releases are "compatible". Under semver, `^0.1.2` admits changes within `0.1.x`, and `0.x` releases routinely carry breaking changes (as here: a removal inside the same `0.1.2` pre-release line, alpha.2 → alpha.4).
- That runtime behavior (iteration protocol, event availability, memory characteristics) is preserved.

So "peer range satisfied" is a statement about declared version intervals, not a compatibility contract about code behavior.

## 3. The fundamental principle

- **Peer-range satisfaction** checks: *package metadata*. It answers "do the declared version intervals overlap the installed versions?" — a static, numeric, install-time check performed by npm against `package.json` fields.
- **Runtime compatibility** checks: *behavior*. It answers "does the plugin's code actually work against the host's real exported API at the installed version?" — a dynamic, code-level property that can only be established by loading/executing the plugin against the real host (or by API-surface comparison).

**Two categories of breakage that pass peer-range validation but crash at runtime:**

1. **Removed / renamed APIs** — the exact case here: dsh alpha.4 removed `Session.events`; the plugin's 42 references to `session.events` now read `undefined` and `TypeError: events is not iterable` is thrown, even though every version number satisfies the declared `^0.1.2-alpha.2` range.
2. **Changed signatures / types on surviving APIs** — the same changelog entry's second bullet: "**Distinguish `SessionSeq` and `SessionLogOffset` with strong types**". An API that still exists but changed its parameter or return type (or argument order/shape) passes any version-range check yet breaks callers at runtime.

Other examples in the same class: changed semantics/return shapes of an existing method (e.g. array → on-demand accessor, precisely the eager-events → `snapshotEvents()` change), or changed initialization/lifecycle contracts.

## 4. What the plugin author should have done

**To catch it before publishing (test against the actual target version):**

- Run the plugin's own test suite (or a minimal smoke load: `apply()` a plugin instance against a real host session) in CI against the **current published dsh release**, not only the pinned dev version. A single smoke run against dsh 0.1.2-alpha.4/5 would have thrown `events is not iterable` before publication.
- Track the host's prerelease line: subscribe to dsh changelogs and re-run tests on every alpha/beta that mentions compatibility ("Developers should pay attention to compatibility" was already flagged in the alpha.4 notes). Breaking changes in `0.x` prereleases must be treated as expected.
- Prefer running against a matrix of supported dsh versions rather than a single lock, since `^0.1.2-alpha.2` claims to support the whole interval.

**To help users (peer range / engines vs runtime guard):**

- **Narrow or cap the peer range to versions actually tested** — e.g. `">=0.1.2-alpha.2 <0.1.2-alpha.4"` (or a pinned exact range) — so installing on alpha.4/5 produces a hard `ERESOLVE` peer conflict warning instead of a silent pass. Version metadata can only encode what was verified.
- **Use `engines` / host-version metadata** where the host supports it, to declare the exact dsh build the plugin is compatible with.
- **Add a runtime feature-detection guard** for the APIs that changed, because no metadata field can prove behavior. For example, at startup:

  ```js
  if (typeof session.snapshotEvents !== "function") {
    throw new Error(
      `dsh-tui requires dsh <0.1.2-alpha.4 (Session.events removed in alpha.4). Update dsh-tui for dsh >=0.1.2-alpha.4.`);
  }
  ```

  or branch on the new APIs (`session.snapshotEvents()` / `session.eventAt(i)`) when present, falling back to `session.events` only for older hosts. Feature detection turns a confusing mid-startup `TypeError` into an actionable message — and a dual-path plugin supports both host generations.

## 5. What the user can do RIGHT NOW (concrete pre-install check)

Before installing a plugin, run a dry-run resolution and inspect the declared peer range against your host version's *prerelease deltas*, e.g.:

```sh
npm install --dry-run @deepseek-harness-tui/dsh-tui
npm view @deepseek-harness-tui/dsh-tui peerDependencies
```

Then compare the plugin's declared maximum supported version with your installed dsh (`dsh --version` → `0.1.2-alpha.5`) and check the host changelog between them: any entry between the plugin's declared base (`alpha.2`) and your version (`alpha.5`) that says "replace/remove ... pay attention to compatibility" (here, the alpha.4 `Session.events` removal) means the plugin was written against an API that no longer exists. Concretely: `npm view @deepseek-ai/dsh@0.1.2-alpha.4` / read the v0.1.2-alpha.4 release notes and look for removals touching the plugin's APIs *before* installing. If the plugin's peer range spans a release with a breaking-API changelog entry, expect exactly this class of install-clean-but-crashes-at-runtime failure — and, as an immediate remedy, either downgrade dsh to 0.1.2-alpha.3 or wait for a dsh-tui release updated for the alpha.4 API.
