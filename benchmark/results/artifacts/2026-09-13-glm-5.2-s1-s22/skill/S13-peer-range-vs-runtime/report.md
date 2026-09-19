# S13 · Peer Range vs Runtime Reality — Read-Only Diagnosis

**Mode A · inspect (read-only).** Task: `@deepseek-harness-tui/dsh-tui@0.1.0-beta.4` installed on dsh `0.1.2-alpha.5`; npm install was silent (peer ranges satisfied), but the plugin crashes at startup. Evidence: fixture pack under `environment/fixture/` (npm output, crash stack, plugin source excerpt, dsh changelog excerpt). No files were modified; no installs or migrations were executed.

- **pre-existing (baseline failures): not collected** — Mode A read-only diagnosis of a static fixture; no build/test baseline applies.
- Fixture files read: `npm-install-output.txt`, `crash-stack.txt`, `plugin-source-excerpt.js`, `dsh-changelog-excerpt.md`.

---

## 1. The exact runtime incompatibility

**What was removed:** the eagerly materialized `Session.events` array — the property the plugin reads 42 times (`channel.js` line 734: `const events = liveAgent.session.events`; line 657: `session.events.at(-1)`; lines 2685/3004; and `replayEvents(agent.session.events)` at line 6685).

**When:** dsh **v0.1.2-alpha.4**. The changelog excerpt states, under "Other Changes":

> **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` - the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility. (@kermanx)

(The same release also branded `SessionSeq` / `SessionLogOffset` — relevant when porting to the replacement APIs, but not the crash cause here.)

**What replaced it:** the on-demand read APIs `session.seq`, `session.eventAt()`, and `session.snapshotEvents()`. The plugin's `replayEvents(session.events)` must become `replayEvents(session.snapshotEvents())`, and `session.events.at(-1)` becomes an on-demand read such as `session.eventAt(session.seq - 1)`.

**Crash mechanism:** at alpha.5 `session.events` no longer exists; reading it yields a non-iterable value, and the plugin's own `prepareReplayEvents` tries to iterate it:

```
TypeError: events is not iterable
    at prepareReplayEvents (channel.js:623:25)
    at replayEvents (channel.js:6127:33)
    at createChannel (channel.js:6685:5)
    at apply (plugin.js:425:21)
    at async Fiber._reload (cordis/lib/index.js:1355:5)
```

The failure occurs **inside the plugin's apply path**, so Cordis reports "plugin tree failed to load: failed to apply loader entry dsh-tui" — the plugin never activates. This is exactly the removal documented in the plugin-upgrade skill's `v0.1.2-alpha.4.md` corridor card.

---

## 2. Why npm installed without warnings

The plugin declares `"^0.1.2-alpha.2"` for all 27 `@deepseek-ai/dsh-*` peer packages; the installed dsh alpha.5 bundles its packages at `0.1.2-alpha.5`. Under npm's semver prerelease rules, `^0.1.2-alpha.2` means `>=0.1.2-alpha.2 <0.2.0-0`, and prerelease versions sharing the same `[major, minor, patch]` tuple (0.1.2) with an equal-or-later prerelease identifier satisfy it: `0.1.2-alpha.5` > `0.1.2-alpha.2` in prerelease precedence. **The range is satisfied, so npm's peer check passes silently** (npm only warns on conflicts anyway — and there was no conflict).

**What a peer range guarantees:** only a *version-number* relationship — that the host packages' declared versions fall inside a numeric interval the plugin author chose. It is a static, package-metadata-level assertion, checked without looking at any code.

**What it does NOT guarantee:** that the host's *API surface* still contains everything the plugin's code touches. npm has no knowledge of exported symbols; it never compares the plugin's imports or property accesses against the host's actual runtime exports. The author wrote `^0.1.2-alpha.2` presumably because the plugin worked against alpha.2 — but alpha.4 removed `Session.events` *inside* that interval. A satisfied peer range is the author's claim "I believe this interval is compatible"; it is not a machine-verified fact.

---

## 3. The fundamental principle

- **Peer-range satisfaction** checks *declared version metadata*: "is the installed package's version string inside the declared interval?" Static, cheap, content-blind.
- **Runtime compatibility** checks *behavior*: "does the plugin's code, executing against the host's actual loaded modules, find every API it uses, with the semantics it expects?" Code-level; verifiable only by loading/running (or static type/API diffing against the real target).

**Categories of breakage that pass peer-range validation but crash at runtime** (this case is category 1):

1. **API removal/rename inside the range** — a symbol (`Session.events`) deleted in a later version that is still inside the peer interval; the property read yields `undefined` and downstream use throws (`events is not iterable`). Same class: renamed exports, moved modules, changed function signatures.
2. **Behavioral/semantic changes under unchanged names** — the API still exists but its contract changed: return type (array becomes a promise or lazy structure), argument order, stricter event-payload validation that now rejects shapes the plugin emits, newly required fields. Name checks pass; the plugin fails only when it executes the call.
3. **(Related) Structural/lifecycle drift** — injection strictness, composition rules, or event-map requirements changed mid-range, so the plugin fails during Cordis apply/Fiber reload even though every import resolves and every version satisfies the range.

---

## 4. What the plugin author should have done

**Before publishing (catch it):**

- Run the plugin's tests and a **real cold-start mount against the exact dsh versions at the top of the declared peer range** — not only the version it was developed on. Here that means alpha.2 *and* alpha.5 (and ideally each alpha in between, because the removal landed at alpha.4). The skill's runtime-verification layer is the template: real profile boot, entry activation, no pending services, and one message-to-tool-to-response flow.
- Track dsh release notes across the corridor; treat every "developers should pay attention to compatibility" entry that falls inside the declared range as a mandatory migration check before publishing or extending the range.
- Encode honestly in metadata: the peer range must cover **only versions actually verified**. `^0.1.2-alpha.2` is over-broad when alpha.4+ removes a used API; the correct declaration is a narrowed range (e.g. `>=0.1.2-alpha.2 <0.1.2-alpha.4` per affected dsh package) until the code is migrated to `seq`/`eventAt()`/`snapshotEvents()`, after which the range may widen. `engines` encodes the host runtime floor/ceiling — but neither peer ranges nor engines can encode "these specific symbols exist."
- Add **runtime feature detection** at the migration seam so one artifact spans the corridor and fails loudly on unsupported hosts:

```js
const readEvents = (session) =>
  typeof session.snapshotEvents === 'function'
    ? session.snapshotEvents()
    : session.events   // pre-alpha.4 hosts
```

**To help users:** publish a per-version compatibility matrix (README) matching the narrowed peer ranges, so `npm ls` and install-time peer conflicts actually fire for broken combinations instead of passing silently.

---

## 5. What the user can do RIGHT NOW (concrete pre-install check)

Cheapest high-signal checks, in order:

1. **Read the host changelog between the peer-range floor and your installed version.** `npm view @deepseek-harness-tui/dsh-tui@0.1.0-beta.4 peerDependencies` shows the declared floors; then scan the dsh changelog from alpha.2 to alpha.5 for API removals. One minute of reading reveals the alpha.4 `Session.events` removal sitting *inside* the satisfied range — exactly the class npm cannot see.
2. **API probe against your real install:** a one-liner import/property check in the dsh environment:

```js
const s = /* obtain a Session handle in your dsh install */
console.log('snapshotEvents' in s, 'events' in s)
```

If the plugin's referenced symbol is absent, do not install that version.
3. **Scratch-mount before trusting it:** install into an isolated scratch profile/directory and cold-start dsh with the plugin enabled. A load-time `TypeError` like this surfaces in seconds without touching your real setup.

Rule of thumb: **peer-range silence is necessary but not sufficient.** Treat host prerelease steps (alpha.3 to alpha.4) inside a satisfied range as unverified until the plugin's changelog or a scratch mount proves it.

---

## Report status (skill format)

- **Completed:** read-only diagnosis — incompatibility identified (`Session.events` removed in dsh v0.1.2-alpha.4, replaced by `seq`/`eventAt()`/`snapshotEvents()`, cited from the changelog excerpt); silent-install root cause (semver prerelease ordering satisfies `^0.1.2-alpha.2`; peer ranges are content-blind); principle and three breakage categories; author remediations; user pre-install checks.
- **Skipped:** no migration or fix authored (task is read-only; fixture must remain unchanged); no runtime reproduction executed (fixture is static evidence and the brief forbids installs).
- **Pending/residual risk:** exact replacement call shapes (`snapshotEvents()` return structure, `eventAt` indexing) are taken from the changelog excerpt only; verifying them requires the real alpha.4/5 sources, outside this fixture.
- **Rollback:** nothing was changed; no rollback needed.
- **Recommendations:** plugin author migrates to the on-demand read APIs behind a feature-detecting shim, re-verifies against alpha.5 with a real mount, republishes with a narrowed peer range and a compatibility matrix.

