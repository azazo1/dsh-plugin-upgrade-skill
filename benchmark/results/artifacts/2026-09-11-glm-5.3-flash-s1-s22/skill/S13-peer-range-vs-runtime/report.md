# S13 · Peer Range vs Runtime Reality — Diagnostic Report

Case: `@deepseek-harness-tui/dsh-tui@0.1.0-beta.4` on dsh `0.1.2-alpha.5` — npm install clean, plugin crashes at startup.
Mode: A · inspect (read-only). Evidence pack: `environment/fixture/` (README.md, npm-install-output.txt, crash-stack.txt, plugin-source-excerpt.js, dsh-changelog-excerpt.md). Skill corridor card: `references/v0.1.2-alpha.4.md` card DSH-0.1.2-A4-03.

---

## 1. The exact runtime incompatibility

**WHAT was removed:** the `Session.events` property — the eagerly materialized events array on Session objects.

**WHEN:** dsh `0.1.2-alpha.4` (the alpha.3 → alpha.4 edge). The pack's `dsh-changelog-excerpt.md` states, under **dsh-v0.1.2-alpha.4 release notes → Other Changes**:

> "**Replace `Session.events` with on-demand read APIs**: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions."

The same release notes also flagged the companion change ("Distinguish `SessionSeq` and `SessionLogOffset` with strong types"), carded as DSH-0.1.2-A4-04 — relevant to any plugin that carries plain `number` seq values.

**What replaced it** (card DSH-0.1.2-A4-03 migration ledger):

| Old (`<= alpha.3`) | New (`>= alpha.4`) |
|---|---|
| `session.events.length` | `session.seq` (a `SessionLogOffset`) |
| `session.events[i]` | `session.eventAt(SessionSeq(i))` |
| `session.events` (whole log) | `session.snapshotEvents()` |
| `session.events.slice(a, b)` | `session.snapshotEvents(SessionLogOffset(a), SessionLogOffset(b))` |
| fork-parent exclusion | `session.ownEvents()` |

**The crash chain, grounded in the pack:** `plugin-source-excerpt.js` shows the plugin reading the removed property — `const events = liveAgent.session.events;` (line 734), `replayEvents(agent.session.events);` (line 6685), `session.events.at(-1)` (line 657), and "42 total references to `.events` on session objects". At alpha.4+ the `events` getter no longer exists, so the untyped JavaScript read returns `undefined`. `crash-stack.txt` then shows the consequence: `TypeError: events is not iterable` at `prepareReplayEvents (channel.js:623:25)` → `replayEvents (channel.js:6127:33)` → `createChannel (channel.js:6685:5)` → `apply (plugin.js:425:21)` → `Fiber._reload (cordis/lib/index.js:1355:5)` — i.e. the plugin tree fails to load and the whole plugin activation fails at startup. The host is fine; the plugin's assumption is dead.

---

## 2. Why npm installed silently despite the runtime break

The plugin's peerDependencies (from `npm-install-output.txt`) declare `"^0.1.2-alpha.2"` for `@deepseek-ai/dsh-llm`, `@deepseek-ai/dsh-agent`, `@deepseek-ai/dsh-session`, "... (24 more dsh-* packages, all \"^0.1.2-alpha.2\")". The installed dsh bundles these at `0.1.2-alpha.5`, which satisfies `>=0.1.2-alpha.2 <0.2.0-0` in semver ordering (prerelease: alpha.5 > alpha.4 > alpha.3 > alpha.2). npm's peer check is a pure range-satisfaction computation over version strings — it passes, and emits zero warnings.

**What a peer range guarantees:** only that the *declared version numbers* are in range at install/dependency-resolution time. It is a static, package-metadata-level comparison.

**What it does NOT guarantee:**

- That any particular API that existed at the range's floor still exists at the resolved version. Semantic versioning promises no removals within a major (0.x is even less protected: minor = breaking territory, and prereleases carry no stability promise at all), but the range `^0.1.2-alpha.2` has no mechanism to encode "no API removals" — it encodes nothing but two version numbers.
- That the plugin's code actually uses only the APIs that survive the whole range. The author declared a floor of alpha.2 with no testing above it; `Session.events` was removed at alpha.4, squarely inside the declared range.
- Any behavioral contract: signatures, event payloads, service registration shapes, module inventories — none of it is checked by npm.

In short: `alpha.5 > alpha.2` in semver ordering says nothing about whether `Session.events` exists at alpha.5. Version ordering is not API compatibility.

---

## 3. The fundamental principle

- **"Peer range satisfaction" checks:** package *metadata* — do the version strings in the installed dependency graph fall inside the declared semver ranges? Executed by npm/pnpm at resolution time, before any code runs, comparing numbers only.
- **"Runtime compatibility" checks:** the *behavior of actual code against the actual host* — does every property read, method call, service injection, event, and module import the plugin executes exist with the expected signature on the running dsh? Only provable by typechecking against the target's declarations and by actually mounting the plugin on a real host of that version.

**Categories of breakage that pass peer-range validation but crash (or misbehave) at runtime** — this incident is category 1:

1. **Property/API removal**: a getter or field is deleted (`Session.events` → `seq`/`eventAt()`/`snapshotEvents()`, alpha.4). Untyped JS reads `undefined` and throws downstream — exactly `events is not iterable` here. Same class on this corridor: `seedLength` → `isSeeded` + `inheritedEventCount` (card A4-04), `SubprocessHandle.pid` (alpha.2 of 0.1.3), `ctx.agent` (0.1.5-alpha.1).
2. **Signature/type-shape drift**: a method keeps its name but changes its parameters or return type (e.g. `ProjectionDefinition.init(header, seedLength)` → `init(header, inheritedEventCount)`, card A4-04; command execution signature changes at 0.1.2-alpha.2). Calls "succeed" with wrong arguments or silently wrong behavior.
3. **Package/module inventory changes**: a whole package is removed or renamed (`tool-subagent-report` removed, card A4-01; `dsh-code-runtime-python` renamed, card A4-02; `dsh-client-runtime` removed at alpha.2). Peer ranges on remaining packages resolve fine; the import or profile row fails at load.
4. **Behavioral/default changes**: no API is removed, but defaults flip (`web_fetch` enabled by default in the base bundle, card A4-06; `workflow` dropped from the `ptc` preset, card A4-05). Nothing crashes at install or boot; behavior diverges at run time.

---

## 4. What the plugin author should have done

**Catch it before publishing (test against the actual target version):**

- Pin the *intended* dsh cohort — e.g. an exact version or `~0.1.2-alpha.5` — in devDependencies and run the plugin's build + `tsc --noEmit` against that cohort's declarations. Card A4-03's verification step is exactly this: "`tsc --noEmit` of the plugin against `@deepseek-ai/dsh-session` at `dsh-v0.1.2-alpha.4` passes with no `events` access" — against alpha.4+ this plugin would have failed with "Property 'events' does not exist on type 'Session'" across 42 references, before ever shipping.
- Cold-start a real dsh host at the target version with the plugin mounted (the skill's runtime validation layer) and execute one core path. `TypeError: events is not iterable` would surface in minutes. A clean install is not a passing test — the skill states it explicitly: successful installation does not mean the host enabled the plugin.
- Subscribe to the dsh changelog/migration cards per release edge (DSH-0.1.2-A4-03 names this exact break) and re-run the corridor suite before each plugin release.

**Help users — encode constraints where they are checkable, guard where they are not:**

- **Peer range / `engines`-style field** should encode what the author actually verified: an exact cohort (e.g. `"0.1.2-alpha.4"` / `"~0.1.2-alpha.4"`) or a range that stops before the breaking edge — not a floor-bare `^0.1.2-alpha.2` that silently admits alpha.4/alpha.5. If the plugin genuinely supports both sides of a break, ship separate lines or feature-detect.
- **Runtime feature-detection guard** is required for anything the range cannot express (this removal happened *inside* the author's own declared range): probe before use, fail loud with an actionable message, e.g.

  ```js
  if (typeof session.snapshotEvents !== 'function') {
    throw new Error('dsh-tui requires dsh >= 0.1.2-alpha.4 (Session.events was removed there); found ' + dshVersion);
  }
  const events = session.snapshotEvents(); // >= alpha.4
  ```

  (For pre-alpha.4 hosts the probe would be inverted.) Feature detection at activation turns a cryptic mid-startup `TypeError` into "upgrade/downtake dsh to X" — and a hard `engines`/`peerDependencies` floor catches it even earlier at install.

---

## 5. What the user can do RIGHT NOW (concrete pre-install check)

Before installing a community plugin, run one read-only check that npm will not do for you:

```sh
npm view @deepseek-harness-tui/dsh-tui@0.1.0-beta.4 peerDependencies
```

Then cross-check the plugin's *supported* cohort against your dsh version's release notes/changelog for breaking changes **at or after the peer-range floor**. Concretely here: the floor is `0.1.2-alpha.2`, and the dsh changelog for `0.1.2-alpha.4` (in `dsh-changelog-excerpt.md`) records the removal of `Session.events` — an API a TUI transcript-replay plugin obviously depends on. That mismatch is visible *before* installing, from metadata plus release notes alone. If a grep of the plugin's published source is possible, a single `grep -rn '\.events' `
— or the skill's read-only migration planner / pre-flight touchpoint scan — turns the suspicion into a confirmed hit. Since 0.x prerelease lines carry no stability promise, treat any `^`-range on a `0.1.2-alpha.*` cohort as "no compatibility claim at all" unless the author documents tested versions.

---

## Bottom line

npm's silence was correct: every declared peer range was satisfied by the resolved version strings. The crash was equally correct: `Session.events` was removed in dsh `0.1.2-alpha.4` (replaced by `seq` / `eventAt()` / `snapshotEvents()` / `ownEvents()`), and the plugin reads it 42 times. Range satisfaction is a metadata check; runtime compatibility is a code-level reality, provable only by typechecking and mounting against the exact target version — which the author skipped and the user can approximate pre-install via `npm view ... peerDependencies` cross-checked against the release changelog.
