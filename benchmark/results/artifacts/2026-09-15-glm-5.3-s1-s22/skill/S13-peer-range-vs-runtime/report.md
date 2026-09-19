# S13 · Peer Range vs Runtime Reality (Read-Only Diagnosis)

**Verdict in one line:** The install was "clean" because `^0.1.2-alpha.2` is a *version-range* claim, but the plugin crashes because `Session.events` was *removed* in dsh `0.1.2-alpha.4` — a behavioral change a semver range cannot see. Mode A (read-only inspect) per the plugin-upgrade skill; no files outside the report directory were touched.

---

## 1. The exact runtime incompatibility

**WHAT was removed:** the eagerly materialized `Session.events` array — the property on session objects that plugins read to replay a transcript (e.g. `agent.session.events`, `session.events.at(-1)`).

**WHEN:** dsh **`0.1.2-alpha.4`** (the release between the plugin's peer floor alpha.2 and the user's installed alpha.5).

**WHAT replaced it:** the on-demand read APIs

- `Session.seq`
- `Session.eventAt()`
- `Session.snapshotEvents()`

**Changelog citation** (from `dsh-changelog-excerpt.md`, dsh-v0.1.2-alpha.4 release notes, "Other Changes"):

> **Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility. (@kermanx)

The neighboring entry ("Distinguish `SessionSeq` and `SessionLogOffset` with strong types") is the companion change: the replacement APIs are also strongly typed, so a correct migration brands those values rather than treating them as plain numbers.

**How this produces the observed crash:** `plugin-source-excerpt.js` shows the plugin reading `liveAgent.session.events` (42 total `.events` references on session objects). On alpha.5, `session.events` no longer exists, so the expression evaluates to `undefined`; `prepareReplayEvents` (`channel.js:623`) then iterates it and throws `TypeError: events is not iterable`, which surfaces as `failed to apply loader entry dsh-tui` inside `Fiber._reload`. The crash is in the plugin's own code, exactly as the stack shows.

This matches the curated corridor card in the skill's `references/v0.1.2-alpha.4.md` (alpha.3→alpha.4: "`Session.events` replaced by `seq`/`eventAt`/`snapshotEvents`"), i.e. the alpha.2→alpha.5 corridor the plugin's peer range silently spans contains this breaking edge.

## 2. Why npm installed without warnings

npm's peer-dependency check is **pure version arithmetic against package metadata**. It asked exactly one question: *does the installed `@deepseek-ai/dsh-*` version satisfy `^0.1.2-alpha.2`?*

- In semver, `^0.1.2-alpha.2` for a `0.x` package means **`>=0.1.2-alpha.2 <0.2.0`** (prerelease ranges on the same `[major, minor, prerelease-tag]` line compare: `0.1.2-alpha.5` is greater than `0.1.2-alpha.2`, and alpha.4 in between is also inside the range).
- The bundled alpha.5 packages satisfy it, so npm's resolver is satisfied and **no ERESOLVE warning is emitted**.

What the peer range **guarantees**: only that the host will provide *some* version of each declared peer package whose version string falls inside the range — an install-graph coexistence claim.

What it does **NOT** guarantee:

- that any API the plugin's code happens to call still exists at every version inside the range;
- that the maintainer of the peer package honored any compatibility promise across prereleases (0.x/alpha lines are explicitly allowed to break);
- that the plugin was ever actually loaded/executed against the resolved peer version.

In short: peer satisfaction is checked by comparing **version strings in metadata**, never by running code. The breaking alpha.4 change is invisible to it.

## 3. The fundamental principle

- **"Peer range satisfaction" checks:** a *static, package-metadata-level* condition — "a package with a version number inside the declared range is present in the install graph."
- **"Runtime compatibility" checks:** a *behavioral, code-level* reality — "when the plugin executes against the actually-resolved host, every API it touches still exists with the expected semantics."

Two categories of breakage that pass peer-range validation but crash at runtime (the task asks for at least two):

1. **API surface removal/renames inside the range.** Exactly this case: `Session.events` existed at the range floor (alpha.2) and was removed at alpha.4, entirely inside `^0.1.2-alpha.2`. Same class: removed exports, renamed service methods, changed function signatures (e.g. the alpha.2 `SubprocessHandle.pid` removal, the alpha.5 `workspaceFiles` parameter change).
2. **Behavioral/contract changes with the same name.** An API keeps its name and arity but changes semantics or return type — e.g. an event payload schema tightened, a callback now expected to return a disposer, a synchronous call becoming async. Type-level and iteration contracts (`events is not iterable` is a *shape* failure, not a version failure) never appear in version arithmetic.

(Further same-class examples: new required parameters with no runtime default; a service the plugin injects that stops being provided — both pass the range check and fail at `apply()`.)

## 4. What the plugin author should have done

**Before publishing (catch it):**

- **Test against the actual versions the range admits, especially the top of the range and the latest release** — CI matrix installs the real `@deepseek-ai/dsh` at the newest published version and cold-mounts the plugin (the skill's runtime-validation layer: entry activation, no pending services, one core plugin path executed). A single real mount on alpha.4/5 would have thrown this exact `TypeError` at load time.
- **Treat every dsh prerelease edge as potentially breaking** and re-run the corridor on each release; consult the corridor cards/changelogs between the floor and the current release before widening a range.
- Consider adopting the community-standard manifest (`dsh-plugin.json`) with explicit compatibility coordinates so consumers can negotiate, rather than relying on bare semver.

**In metadata (encode what semver can express):**

- Encode the *tested compatibility corridor* in the peer range / engines field, not the theoretical minimum: since the plugin still uses `Session.events`, the honest range is one that **excludes** alpha.4+ — e.g. pin the corridor `>=0.1.2-alpha.2 <0.1.2-alpha.4` (or list the last-known-good exact version with `~`/exact pin) until the source is migrated. A peer range is a promise the author has verified, not a guess about the future.

**In code (what semver cannot express):**

- **Runtime feature detection instead of version sniffing:** guard the removed surface, e.g.

  ```js
  if (typeof session.snapshotEvents === 'function') {
    replayEvents(session.snapshotEvents(/* range */))   // alpha.4+ path
  } else if (Array.isArray(session.events)) {
    replayEvents(session.events)                        // legacy path
  } else {
    throw new Error('dsh-tui: unsupported dsh session API — requires snapshotEvents() or Session.events')
  }
  ```

  so an untested future host degrades with a *clear, attributable* error rather than `events is not iterable` deep inside a stack. Fail loud at the earliest resolvable point (the skill's misconfiguration principle) with the plugin's name and the missing capability in the message.

## 5. What the user can do RIGHT NOW (pre-install check)

**Concrete check: dry-run the resolution and diff the API the plugin's code uses against the changelog of every version the range spans.** In practice, the cheapest reliable variant:

1. `npm info @deepseek-harness-tui/dsh-tui peerDependencies` (no install) → note the range `^0.1.2-alpha.2`.
2. `npm view @deepseek-ai/dsh versions` → list every release inside that range (alpha.2, alpha.3, alpha.4, alpha.5, …).
3. Read the release notes/changelog for **each** in-range version and look for removals touching APIs the plugin uses — here, alpha.4's "Replace `Session.events` with `seq`, `eventAt()`, `snapshotEvents()`" is a direct hit against any TUI that replays transcripts.

Cheaper heuristics that would also have flagged it, in order of effort:

- `npm pack` / unpack the tarball and `grep` the plugin's code for host-API identifiers (`session.events`, etc.), then check each against the in-range changelogs — a static "does the symbol still exist" pass without installing anything;
- install into a **disposable directory/profile** (`npm install` there, or the skill's isolated-profile runtime verifier) and cold-start once before touching the real global environment — the crash reproduces in seconds and is fully attributed to plugin code.

The general rule: **a green npm install is an install-graph fact, not a compatibility fact.** Anything that matters at runtime has to be verified by reading the corridor's changelogs or by one real mount.

---

## Report metadata (skill validation & reporting format)

- **Mode:** A · inspect (read-only). No edits, installs, version switches, or package-script runs were performed; the fixture directory was only read.
- **pre-existing (baseline):** not collected (Mode A, static evidence pack only — no builds or tests were run, per the task's read-only constraint).
- **Completed:** full read of all five fixture files; incompatibility identified and cited; peer-range vs runtime analysis; author and user remediation guidance.
- **Skipped:** runtime reproduction of the crash (the fixture is a static evidence pack explicitly marked "do not execute"); planner/verify-runtime scripts (not applicable to a registry-package diagnosis with no source checkout).
- **Pending/residual risk:** the exact replacement-call signatures (`eventAt`/`snapshotEvents` parameters) are not in the evidence pack; a real migration should take them from the alpha.4 corridor card / packed declarations of the actual target version. 24 of the 27 peer entries were elided in the npm output ("... 24 more"); assumed same range as the shown three.
- **Rollback:** nothing to roll back — no state outside the report directory was modified.
- **Recommendations for the author:** migrate to `snapshotEvents()`/`eventAt()` + branded `SessionSeq`, keep a feature-detecting fallback for the alpha.2/3 corridor only if still supported, and add a CI cold-mount matrix against the newest dsh release before each publish.
