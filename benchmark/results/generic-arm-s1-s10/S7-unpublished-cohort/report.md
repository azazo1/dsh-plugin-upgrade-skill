# S7 · Unpublished Cohort — Installation / Type-Baseline Plan (Read-Only Report)

**Scope of analysis.** The entire fixture consists of two files, both analyzed read-only and left unchanged:

- `package.json` — declares `"private": true` and a single coupling point: `devDependencies: { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`. There is **no lockfile** (`package-lock.json` / `npm-shrinkwrap.json`) in the fixture, so nothing currently pins the resolved version.
- `README.md` — asserts "npm install gives you the type baseline" and states the npm reality: the registry has only `0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2`; **`0.1.2-alpha.1` was never published**.

Per the brief, I did not run any install, did not build a reproduction environment, and did not consult the network or any framework-specific references. Where a fact cannot be verified from the fixture alone, it is marked **unconfirmed**.

---

## 1. What the declaration actually does (semver consequence analysis)

### 1.1 The naive reading is wrong

The intuitive worry — "alpha.1 was never published, so `npm install` fails with `ETARGET` / `No matching version found`" — is **incorrect for a caret range**. `ETARGET` is what you get with an *exact* pin (`"0.1.2-alpha.1"`) or a range that admits only missing versions. That is not what this range does.

### 1.2 What `^0.1.2-alpha.1` actually resolves to

Under node-semver semantics (which npm uses):

- The caret desugars to `>=0.1.2-alpha.1 <0.2.0` (for `0.x.y`, the caret bounds at the next minor).
- The prerelease rule: a prerelease version satisfies the range **only if it shares the range's `[major, minor, patch]` tuple** — here `0.1.2` — and is `>= alpha.1` in prerelease ordering.
- Evaluating the published cohort:
  - `0.1.1-rc.1`, `0.1.1-rc.2`: **excluded** — both are `< 0.1.2-alpha.1` (below the range floor; the tuple check is moot).
  - `0.1.2-alpha.2`: **accepted** — same `0.1.2` tuple as the range's prerelease, and `alpha.2 > alpha.1`.

**Conclusion: `npm install` will *succeed* and will silently install `0.1.2-alpha.2`.** No error, no warning.

### 1.3 The real consequence: silent baseline drift, not install failure

The failure mode here is **semantic, not mechanical**:

1. The README's promise — "npm install gives you the type baseline" — is *technically* kept (install succeeds and you get types), but the baseline you get is **not the one the declaration names**. The author wrote `alpha.1`; every contributor, every CI run, resolves `alpha.2`. The declared intent and the realized state disagree, and nothing in the toolchain flags it.
2. The intended baseline (`alpha.1`) **does not exist as an artifact anywhere** — it was never published. So there is nothing to diff `alpha.2` against to answer "did the baseline change?" The author's mental model of the API surface (presumably formed while `alpha.1` existed on some internal registry or pre-publish build — **unconfirmed**) may or may not match `alpha.2`'s actual `.d.ts` surface. Any type error or runtime drift the maintainer saw during development could be attributable to this gap, and cannot be ruled out from the fixture.
3. Because there is **no lockfile**, resolution is re-evaluated on every fresh install. Today the only satisfying version is `alpha.2`, so resolution is *currently* deterministic in practice. But the range remains open at the top: the day the upstream publishes `0.1.2-alpha.3`, `0.1.2-beta.1`, or `0.1.3` (all satisfy `>=0.1.2-alpha.1 <0.2.0`; non-prerelease `0.1.2`/`0.1.3` also satisfy since they outrank same-tuple prereleases), every fresh install silently moves the type baseline again. The declaration is a floating reference dressed as a pinned one.
4. Caveat on resolver behavior: the prerelease-caret semantics above describe modern npm (v7+ / current node-semver). Very old npm versions had inconsistent handling of caret ranges over prerelease cohorts; if any contributor is on an ancient npm, behavior may differ — **unconfirmed**, and the fixture declares no `engines` or package-manager field to constrain this.

### 1.4 Classification (per generic migration methodology)

Classified against the standard change taxonomy: this is a **behavioral** issue (must re-verify), not a **breaking** one (must edit to make install work) — installs work today. But it is a *latent* breaking issue: the open top of the range plus the missing lockfile make a future silent break a matter of time, and the already-realized alpha.1→alpha.2 substitution is unverified drift that exists *now*.

---

## 2. Workable installation / type-baseline plan

Four paths, ordered from most to least recommended. All are mutually composable (A+lockfile, etc.). None requires modifying the fixture today; each describes what the maintainer should change in `package.json` and process.

### Path A — Accept reality: pin `0.1.2-alpha.2` explicitly (recommended)

Since `alpha.1` never existed as an artifact, there is no "original baseline" to preserve; `alpha.2` *is* the only candidate baseline in the `0.1.2` cohort. Make the manifest tell the truth:

1. Change the declaration to an **exact pin**: `"@deepseek-ai/dsh-llm": "0.1.2-alpha.2"` (no caret). For a type baseline, exactness is the point — a baseline that floats is not a baseline.
2. Run a real install once (outside this read-only exercise) and **commit the resulting `package-lock.json`**. This converts "deterministic by luck of the registry" into "deterministic by construction", and makes every contributor and CI job resolve identically via `npm ci`.
3. Establish the baseline empirically: after install, run the project's typecheck (`tsc --noEmit` or equivalent — the fixture contains no tsconfig or source, so the exact command is **unconfirmed**) and record the result as the green reference state.
4. Fix the README: "npm install gives you the type baseline" should become "npm ci gives you the pinned type baseline `0.1.2-alpha.2`", so the documentation stops claiming the manifest does something it doesn't.

*Tradeoffs:* you are blessing a version the original author never asked for, with no published predecessor to diff against. Mitigation: the typecheck pass in step 3 is the actual acceptance test — if the plugin's code compiles cleanly against `alpha.2`'s types, then `alpha.2` is a valid baseline regardless of what `alpha.1` would have been.

*Exit path:* if the typecheck fails against `alpha.2`, go to Path B or C.

### Path B — Retreat to the last published stable-ish line: `0.1.1-rc.2`

If `alpha.2`'s types turn out to be incompatible with the plugin's code, fall back to the highest published version that exists at all: `0.1.1-rc.2` (exact pin, same lockfile discipline as Path A).

*Tradeoffs:* `rc.2` is an entire patch-line older; whatever motivated the author to write `0.1.2-alpha.1` (new APIs, type fixes — **unconfirmed**, no changelog is available in this closed-book brief) is absent. You may need to remove or gate code that depends on `0.1.2`-era types. This is a real downgrade, not a cosmetic one.

*Exit path:* stay on `rc.2` until upstream publishes a `0.1.2+` release whose types pass the project's typecheck, then adopt it via the same pin-and-lock procedure.

### Path C — Keep the caret but add verification guards (minimal-change option)

If the maintainer refuses to touch the version spec (e.g., policy keeps caret ranges for devDependencies — **no such policy is visible in the fixture; unconfirmed**), the minimum viable hardening:

1. Keep `^0.1.2-alpha.1` but commit a lockfile and use `npm ci` everywhere — this pins `alpha.2` in practice even though the manifest floats.
2. Add a CI guard that fails when the resolved version changes: e.g., a step asserting `npm ls @deepseek-ai/dsh-llm --json` reports exactly the locked version, plus the typecheck as a regression gate.
3. Document in the README that the declared range intentionally resolves to `0.1.2-alpha.2` and that `alpha.1` was never published, so the next maintainer doesn't repeat this analysis from scratch.

*Tradeoffs:* the manifest still lies about intent; a future `npm update` or lockfile regeneration reopens the float. Strictly weaker than Path A, but better than status quo.

*Exit path:* any guard failure triggers Path A or B.

### Path D — Hold / investigate upstream (when the history matters)

If there is reason to believe `alpha.1` was published and later *unpublished* (rather than never published), or that the author's `alpha.1` types differ meaningfully from `alpha.2`, treat the baseline question as unresolved:

1. Consult the upstream project's changelog / release notes / registry metadata (`npm view @deepseek-ai/dsh-llm time --json` shows publish timestamps and would corroborate the never-published claim; an unpublish would typically leave a gap or a deprecation note). **I could not run this under the closed-book constraint; the published-version list in this report is taken from the brief/README assertion and is unverified by me firsthand.**
2. Check whether the team has an internal registry, artifact cache, or a colleague's `node_modules` that still contains `alpha.1`; if so, diff its `.d.ts` against `alpha.2`'s to enumerate the actual type-surface delta (added/removed/changed exports), classify each delta as breaking/behavioral/additive, and only then choose between Paths A and B.

*Tradeoffs:* most thorough, but depends on materials that may not exist; do not block the pin-and-lock hardening (steps 1–2 of Path A) on this investigation.

*Exit path:* regardless of findings, the investigation ends in either Path A (delta acceptable) or Path B (delta fatal).

### Recommended sequence

1. **Now:** adopt Path A (exact pin `0.1.2-alpha.2` + committed lockfile + README correction).
2. **Immediately after:** run the layered verification from §3.
3. **If verification fails:** fall to Path B; optionally run Path D's provenance check in parallel to document *why*.
4. **Never:** leave the caret range unpinned without a lockfile (the current state) — it converts a one-time silent substitution into a recurring one.

---

## 3. Verification plan (layered, cheap first)

Once edits are permitted (they are not in this read-only exercise), verify in this order; each layer must pass before the next means anything:

1. **Resolver audit (no install side effects beyond a scratch dir):** `npm view @deepseek-ai/dsh-llm versions --json` to confirm the published cohort firsthand; `npm install --dry-run` (or `--package-lock-only`) to show what the range resolves to without touching `node_modules`.
2. **Static:** fresh `npm ci` from the committed lockfile, then the project's typecheck. The typecheck passing against `alpha.2` is the acceptance test for Path A.
3. **Install-time/cold start:** the plugin loads in the host with the new dependency tree; check logs for deprecation/fallback warnings, not just crashes.
4. **Functional probe:** exercise one real end-to-end path per major feature of the plugin, including paths that don't obviously use the LLM package — type-baseline drift hides in transitively affected code.
5. **Repeatability:** wipe `node_modules`, `npm ci` again on a second machine/CI runner; confirm identical resolved versions (the lockfile's job) and identical typecheck output.
6. **Rollback rehearsal:** because the change is manifest + lockfile only, rollback is `git revert` + `npm ci`; rehearse it once so the exit path is proven, not theoretical.

---

## 4. Explicitly unconfirmed items

- **The published-version list itself.** The brief and README assert the cohort is exactly `{0.1.1-rc.1, 0.1.1-rc.2, 0.1.2-alpha.2}` with `alpha.1` never published. Under the closed-book constraint I did not query the registry; a maintainer should confirm with `npm view` before acting (step 1 of §3).
- **Whether `alpha.1` ever existed anywhere** (internal registry, pre-publish build, unpublished-after-briefly-published). No evidence in the fixture either way.
- **The type/API delta between the intended `alpha.1` and the actual `alpha.2`** — unknowable from the fixture, since `alpha.1` is not an available artifact and no changelog was provided. This is precisely the drift Path A's typecheck gate and Path D's provenance check are designed to resolve empirically.
- **Whether the plugin's code actually compiles/works against `alpha.2`'s types** — the fixture contains no source files, tsconfig, or tests, so there is nothing to check here.
- **npm/node-semver version on contributor machines** — prerelease-caret resolution as described assumes a modern npm; no `engines`/`packageManager` field exists in the fixture to guarantee this.
- **Any framework-specific migration-card or changelog mapping** for this package: I have no framework-specific references available, so no precise upstream change-card IDs can be cited. The correct procedure, when such materials are reachable, is: fetch the upstream changelog/release notes for every version in the corridor (here effectively just `0.1.2-alpha.2`, plus rc.1→rc.2 history if downgrading), map each declared change to the plugin's coupling points (imports of `@deepseek-ai/dsh-llm` types — none visible in this fixture), classify as breaking/behavioral/additive/informational, and only then finalize the baseline choice.

---

## 5. TL;DR

The caret range `^0.1.2-alpha.1` does **not** fail to install — it silently resolves to `0.1.2-alpha.2` (same `0.1.2` tuple, `alpha.2 > alpha.1`). The real defect is a **silent, unverified substitution of the type baseline**, compounded by a missing lockfile that leaves the top of the range open to future silent movement. Recommended fix: exact-pin `0.1.2-alpha.2`, commit the lockfile, correct the README, and gate on typecheck; fall back to exact-pinned `0.1.1-rc.2` if `alpha.2`'s types prove incompatible. Everything not derivable from the fixture is marked unconfirmed above.
