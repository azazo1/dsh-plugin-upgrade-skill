# S13 · Peer Range vs Runtime Reality — Diagnostic Report

Evidence pack: `environment/fixture/` (read-only): `README.md`, `npm-install-output.txt`, `crash-stack.txt`, `plugin-source-excerpt.js`, `dsh-changelog-excerpt.md`.

## 1. The exact runtime incompatibility

**Removed API:** `Session.events` — the eagerly materialized events array. **Removed in:** `dsh v0.1.2-alpha.4`.

Changelog evidence (`dsh-changelog-excerpt.md`):

> "Replace `Session.events` with on-demand read APIs: `seq`, `eventAt()`, and `snapshotEvents()` — the eagerly materialized events array is removed to reduce memory overhead in long sessions. Developers should pay attention to compatibility. (@kermanx)"

A companion alpha.4 change ("Distinguish `SessionSeq` and `SessionLogOffset` with strong types") reinforces that alpha.4 was a developer-facing breaking release.

**What replaced it:** the on-demand read APIs `seq`, `eventAt()`, and `snapshotEvents()`.

**How it crashes:** the plugin (`plugin-source-excerpt.js`) reads the removed property in many places — `liveAgent.session.events` (line 734), `replayEvents(agent.session.events)` (line 6685), `session.events.at(-1)` (line 657), and "42 total references to `.events` on session objects". Under alpha.5, `session.events` is `undefined`, and iterating `undefined` throws:

`crash-stack.txt`: `TypeError: events is not iterable` at `prepareReplayEvents (channel.js:623:25)` inside `createChannel`, surfacing as `failed to apply loader entry dsh-tui ... events is not iterable` during plugin apply (`Fiber._reload`). The crash happens on the plugin's first run, entirely at startup.

## 2. Why npm installed silently despite the breakage

The plugin's `peerDependencies` declare `"^0.1.2-alpha.2"` for every `@deepseek-ai/dsh-*` package (`npm-install-output.txt`). Semver treats a prerelease range literally and narrowly here: `^0.1.2-alpha.2` resolves to `>=0.1.2-alpha.2 <0.2.0-0` **within the same prerelease lineage** — it matches `0.1.2-alpha.3`, `0.1.2-alpha.4`, `0.1.2-alpha.5`, ..., `0.1.1.x`? No — it matches `0.1.2-alpha.2` through `0.1.2-alpha.N` and `0.1.2`/`0.1.x` releases, and the installed `0.1.2-alpha.5` satisfies it. npm's job is done: version ordering says alpha.5 ≥ alpha.2, so the constraint is met and no warning is emitted.

What the peer range does **not** guarantee:

- A semver range is a **pure version-number comparison against static package metadata**. It encodes only the author's *claim* of compatibility; it validates nothing about the actual code.
- For prerelease (0.x / alpha) lines, "greater than" says nothing about API stability — a higher prerelease (alpha.4, alpha.5) can remove or reshape APIs freely, and this one did exactly that between alpha.2 and alpha.4.
- npm does not scan either package's source for the symbols/properties used. The 42 references to `.events` are invisible to the resolver.

Hence: "added 77 packages", no warnings (exact evidence in `npm-install-output.txt`), then a hard crash on first launch.

## 3. The fundamental principle

- **Peer-range satisfaction** checks *declared metadata*: do the installed packages' version numbers fall inside the declared semver ranges? It is a static, package-metadata-level check — string comparison over versions, executed by the package manager at install time.
- **Runtime compatibility** checks *behavioral, code-level reality*: do the actual exported symbols, object properties, function signatures, and semantics that the plugin touches exist and behave as expected in the running host?

Categories of breakage that pass peer-range validation but crash at runtime (this pack exhibits both):

1. **Removed/renamed API surfaces** — e.g. `Session.events` removed in alpha.4 while the range "matches" alpha.5.
2. **Changed types/semantics of existing APIs** — e.g. alpha.4's `SessionSeq` vs `SessionLogOffset` strong-type split: code that compiles/passes range checks can still misbehave or throw against reshaped signatures.
(Other recurring classes: reordered/renamed function parameters, changed event payloads, altered async/return contracts.)

## 4. What the plugin author should have done

**Catch it before publishing:**
- Test against the actual target host versions: install dsh `0.1.2-alpha.4`/`alpha.5` in CI and run the plugin's startup path (smoke/e2e), not just against the version the range was written for. A single `dsh-tui` launch on alpha.4 reproduces `TypeError: events is not iterable` immediately.
- Because `^0.1.2-alpha.2` implicitly claims "compatible with all alpha.2+", each new host alpha needs a regression run — or the range must be narrowed so the claim matches what was tested.

**Encode the right constraint vs. guard at runtime:**
- If the plugin is only verified against ≤ alpha.3, the peer range should say so explicitly (e.g. `=0.1.2-alpha.3` or a bounded range excluding alpha.4+), or use an `engines`-style constraint on the host version, so npm actually warns instead of passing silently.
- What belongs in **metadata** (peer range / engines): the tested host version window — the author's honest compatibility claim.
- What belongs in **code**: a runtime feature-detection guard, e.g. `if (typeof session.snapshotEvents !== 'function') throw new Error('dsh-tui requires dsh >=0.1.2-alpha.4 (Session.events removed; use snapshotEvents())')` — a loud, actionable message at apply time instead of `events is not iterable`. Feature detection complements (not replaces) the range: ranges can't express "the API I use still exists".

## 5. What the user can do right now (pre-install check)

Concrete check before installing: **read the plugin's changelog/README and peer range against the host changelog, then smoke-test in a scratch environment.** Practically:

1. Compare the plugin's declared peer range with your dsh version's changelog: fetch dsh's release notes for versions inside the range (here alpha.4's note explicitly says "Replace `Session.events` ... Developers should pay attention to compatibility" — a red flag for any plugin written against `session.events`).
2. Check whether the plugin's stated supported/last-tested dsh version covers your installed version; if the plugin pins or documents a host version (e.g. "tested on 0.1.2-alpha.3") while you run alpha.5, treat it as unverified on prereleases.
3. Before installing globally, do a throwaway trial — install both in a temp directory (or use `npm pack`/`npx`) and run the plugin once; a 10-second smoke run surfaces startup crashes like this one before they touch your main environment.

The single most effective habit: **never trust a peer range on an alpha/0.x dependency chain — verify the host's changelog for breaking developer-facing changes within that range, and smoke-test first.**
