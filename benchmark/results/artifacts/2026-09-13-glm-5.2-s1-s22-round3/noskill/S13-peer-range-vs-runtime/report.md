# S13 - Peer Range vs Runtime Reality - Report

Scenario: `@deepseek-harness-tui/dsh-tui@0.1.2-beta.4` declares peer `^0.1.2-alpha.2` on every `@deepseek-ai/dsh-*` package; the host `dsh@0.1.2-alpha.5` satisfies that range and npm installs silently, yet the plugin crashes at startup with `TypeError: events is not iterable`.

## 1. The exact runtime incompatibility

- **WHAT was removed:** the eagerly materialized `Session.events` array. dsh **replaced** it with **on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()`. (A companion change in the same release also split `SessionSeq` vs `SessionLogOffset` into strongly typed values.)
- **WHEN:** release **0.1.2-alpha.4** - per the changelog excerpt, under "Other Changes": *"Replace Session.events with on-demand read APIs: seq, eventAt(), and snapshotEvents() - the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility. (@kermanx)"*
- **Why the plugin crashes:** `channel.js` reads `liveAgent.session.events` (42 references to `session.events` in the excerpt) and iterates it in `prepareReplayEvents`. At alpha.4+ the property no longer exists as an iterable array, so `replayEvents` throws `events is not iterable` inside `apply()`, failing the whole loader entry.
- **Fix direction:** replace `session.events` reads with the new APIs - e.g. `session.snapshotEvents()` for the full replay list, and `session.eventAt(session.seq - 1)` instead of `session.events.at(-1)`.

## 2. Why npm installed without warnings

- The peer range `^0.1.2-alpha.2` means **>=0.1.2-alpha.2 <0.2.0-0** (prerelease comparison orders alpha.5 > alpha.2). 0.1.2-alpha.5 satisfies it, so npm's **static, metadata-level** peer check passes.
- A peer range guarantees only **version-number set membership**: the installed version's version *string* falls inside the declared semver interval. That is all.
- It does **not** guarantee:
  - that APIs the plugin actually calls still exist with the same name, shape, or return type in those versions;
  - that no breaking change happened inside the range (pre-1.0/alpha packages routinely break within `^` ranges; the changelog itself flags "developers should pay attention to compatibility");
  - behavioral/semantic compatibility (iterability, sync vs async, optionality, event ordering);
  - that the peer resolves to the same package instance the plugin was tested against (bundled monorepo versions vs independently resolved peers can diverge).

npm never loads the plugin against the installed peer; it only compares strings in package.json.

## 3. The fundamental principle

- **Peer-range satisfaction** = a *static, package-metadata* check: "is the installed version number inside the declared semver interval?" It validates the dependency graph, not the program.
- **Runtime compatibility** = a *behavioral, code-level* reality: "does the plugin's actual code path against this concrete build's exported APIs work?" It is only proven by executing the integration.

Breakage classes that pass peer-range validation but crash at runtime (two required, three given):

1. **Removed/renamed API surface** - exactly this case: `Session.events` deleted in alpha.4 while `^0.1.2-alpha.2` still admits alpha.4/5. Generic form: TypeError "X is not a function / not iterable" on a missing export.
2. **Type/semantic drift** - an API keeps its name but changes meaning: return-type changes (array to lazy cursor), sync to async, branded types (`SessionSeq` vs `SessionLogOffset`) making previously interchangeable numbers fail, changed event ordering or optionality.
3. *(bonus)* **Multiple-instance / initialization-order issues** - the peer resolves to a different package instance than the one the host bundles, or an API exists only after async init that the plugin calls too early. Version strings match; object identity or lifecycle does not.

## 4. What the plugin author should have done

**Before publishing (catch it):**
- Run the plugin's test suite / smoke startup against the **actual releases inside the declared peer range**, especially the newest member of the range and the alpha bleeding edge (alpha.4 broke it, yet the range claims alpha.4 works). CI matrix: oldest allowed peer + newest allowed peer + current tag.
- Treat a pre-1.0/alpha host as unstable by default: pin the range to the exact tested version(s) (e.g. `"0.1.2-alpha.2"` or tight comparators) rather than `^` across alphas; widen only after re-testing.

**Encode vs feature-detect (help users):**
- **Peer range / engines** should encode only facts derivable from version metadata: which host versions are tested/verified and hard floors where required APIs definitively changed. For a pre-1.0 host that realistically means a tight range, not `^`.
- **Runtime feature detection** must guard code-level API availability that versions cannot express: at plugin startup check `typeof session.snapshotEvents === 'function'` before using the new API and fall back to `session.events` when present (supporting old and new hosts), or fail loudly with an actionable message ("this plugin needs a dsh build with snapshotEvents(); your build removed Session.events") instead of "events is not iterable". Also audit every host-API reference (the 42 `.events` uses) against the target release notes before publishing.

## 5. What the user can do RIGHT NOW (concrete pre-install check)

**Changelog-diff check across the peer interval, before installing:**

```sh
# 1. Read the plugin's declared floor and the installed host version
npm info @deepseek-harness-tui/dsh-tui@0.1.2-beta.4 peerDependencies
npm ls -g @deepseek-ai/dsh          # -> 0.1.2-alpha.5

# 2. Diff the host changelog across every version in the interval
#    [floor, installed] = 0.1.2-alpha.2 .. 0.1.2-alpha.5, looking for
#    removed / replaced / renamed / breaking entries. The alpha.4 entry
#    "Replace Session.events with on-demand read APIs" sits inside that
#    interval, so the plugin's .events usage is suspect.

# 3. Cheap static confirmation against the plugin code:
grep -n "\.events" node_modules/@deepseek-harness-tui/dsh-tui/channel.js | head
# and, if types are shipped: tsc --noEmit against the host's type stubs
```

Heuristic for pre-1.0 hosts: **any prerelease movement inside a `^` peer range is a potential breaking change until proven otherwise** - check the changelog for every intermediate release and smoke-launch the plugin in a scratch profile before relying on it. (Post-hoc, the stack trace "events is not iterable ... at apply" pinpointed the same fact; the pre-install variant reads the changelog before the crash happens.)

## Verdict

The plugin is broken because it consumes an API (`Session.events`) removed in dsh 0.1.2-alpha.4 while its peer range `^0.1.2-alpha.2` still claims compatibility with alpha.4/5. Peer-range satisfaction is a version-string check, not an API contract check; the author should have tested against the range's newest member and feature-detected `snapshotEvents()` / `eventAt()`, and the user's best pre-install defense is diffing the host changelog across the peer interval plus a grep/typecheck of the plugin's host-API usage.
