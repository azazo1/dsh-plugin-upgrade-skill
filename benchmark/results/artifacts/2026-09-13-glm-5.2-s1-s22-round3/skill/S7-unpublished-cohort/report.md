# S7 · Unpublished Cohort Install / Type-Baseline Plan (Read-Only Report)

Task: analyze `dsh-cohort-bench` (fixture) whose `devDependencies` declares
`"@deepseek-ai/dsh-llm": "^0.1.2-alpha.1"` while the README claims "npm install gives you the
type baseline". npm reality per the brief: the `@deepseek-ai/*` scope has only
**0.1.1-rc.1 / 0.1.1-rc.2 / 0.1.2-alpha.2** published — **0.1.2-alpha.1 was never published**.

Skill mode: **A · inspect** (read-only; no install, no file changes, no environment built).
Per the benchmark authorization, the fixture was only read; no install was executed.

## Evidence collected

| Item | Value |
|---|---|
| Fixture package | `dsh-cohort-bench@0.1.0`, `"private": true` |
| Declared devDependency | `@deepseek-ai/dsh-llm: ^0.1.2-alpha.1` |
| README claim | "npm install gives you the type baseline" |
| Published cohort (per brief; not independently verifiable offline) | 0.1.1-rc.1, 0.1.1-rc.2, 0.1.2-alpha.2 |
| Files in fixture | `package.json`, `README.md` only (no lockfile, no source, no tsconfig) |
| Registry check | **Unconfirmed** — closed-book brief, no network allowed; the published-version list is taken from the task statement |

## 1. Real consequence of the declaration

### 1.1 Semver semantics of the caret on a prerelease

`^0.1.2-alpha.1` desugars to the range `>=0.1.2-alpha.1 <0.1.3`. Two npm/node-semver rules
matter here:

1. **Prerelease versions only satisfy a range if the comparator's `[major, minor, patch]` tuple
   matches.** A prerelease like `0.1.1-rc.2` does **not** satisfy `^0.1.2-alpha.1` (different
   tuple), and no `0.1.3-*` prerelease ever will either.
2. **Prerelease identifiers compare dot/lexically left to right**: `alpha.1 < alpha.2`
   (`alpha` equal, then numeric `1 < 2`), and any `0.1.2-alpha.X` sorts below the final
   `0.1.2`. So the range admits: `0.1.2-alpha.1`, `0.1.2-alpha.2`, …, and the final
   `0.1.2` (once published), nothing else.

### 1.2 Will install fail? No.

- **Install does not fail.** `0.1.2-alpha.2` is inside the range (same 0.1.2 tuple,
  `alpha.2 > alpha.1`, and `0.1.2-alpha.2 < 0.1.3`). npm resolves
  `^0.1.2-alpha.1` → **`0.1.2-alpha.2`** (the highest satisfying published version).
- npm only errors (ETARGET / "No matching version found") if *no* published version satisfies
  the range — not when the exact written version is missing. Caret/range declarations name a
  *corridor*, not a pin.

### 1.3 The actual gap: silent baseline drift, not install failure

- The **declared** baseline (alpha.1) does not exist on npm; the **effective** baseline is
  alpha.2 — one corridor edge *ahead* of what the author wrote and what the README promises.
- The plugin gets the alpha.2 type surface, which includes the alpha.1→alpha.2 breaking edge
  (skill card set `DSH-0.1.2-A2-*`, see `references/v0.1.2-alpha.2.md`: removed client
  runtime, keyed chat snapshots, command execution signature, Workspace navigation, etc.).
  Any code written against the alpha.1 surface may type-fail or silently diverge against the
  alpha.2 declarations — the README's "npm install gives you the type baseline" is therefore
  **misleading**: the install gives you *a later* baseline, and which one depends on the
  registry state at install time (a future `0.1.2` final would also satisfy the range and
  shift the baseline again without any change to `package.json`).
- Because the dependency is a **devDependency** and the package is `private`, there is no
  consumer-facing peer-cohort incoherence from this repo itself; the risk is confined to the
  type baseline and any local build/typecheck/test that compiles against it.

Attribution per the skill's failure classes: this is **dependency-resolution drift** (an
unpublished cohort member inside a satisfiable range), not a plugin-code or profile-config
defect.

## 2. Installation / type-baseline plan (multiple paths, tradeoffs, exit paths)

### Path A · Accept the drift, pin the resolved version (recommended first step)

- Action: keep the range but record what it resolves to; for reproducibility, generate a
  lockfile (`npm install --package-lock-only` — no lifecycle scripts, no node_modules) so the
  baseline is fixed at `0.1.2-alpha.2` and future `0.1.2` final cannot silently shift it.
- Then compile/typecheck the plugin against alpha.2 and apply the alpha.1→alpha.2 corridor
  cards (`references/v0.1.2-alpha.2.md` + `references/api-migration-0.1.2-alpha.2.md` for
  exact API coordinates) to any touchpoints that broke.
- Tradeoff: smallest change; honest about reality. Risk: you migrate to alpha.2 without ever
  seeing the alpha.1 surface the code was written against — some alpha.1-only assumptions may
  be masked rather than checked.
- Exit path: if alpha.2 breakage is too large, fall back to Path B or C.

### Path B · Correct the declaration to the corridor you actually mean

- If the author's intent was "the alpha.1 era surface": that surface is unreachable from npm;
  the closest *published* earlier point is `0.1.1-rc.2`. If the code actually compiles
  against rc.2 semantics, declare `^0.1.1-rc.2` explicitly (prerelease-caret note: this
  range's tuple is 0.1.1, so it will *not* pick up 0.1.2-alpha.2 — verify that is what you
  want) and follow the rc.2→alpha.2 corridor cards for the eventual jump.
- If the intent is "track the 0.1.2 alphas", declare `^0.1.2-alpha.2` (or pin
  `0.1.2-alpha.2` exactly for the type baseline) so the written declaration matches the
  installable truth and the README claim becomes accurate.
- Tradeoff: requires a one-line edit to `package.json` (needs the maintainer's write
  confirmation per skill safety boundaries — **not performed** in this read-only run) plus a
  README update.
- Exit path: none needed once the declaration is truthful; revert the one line to roll back.

### Path C · Git/source baseline instead of registry

- If an exact alpha.1 type surface is genuinely required (e.g. to reproduce a bug against the
  alpha.1 declarations), install from the DSH monorepo at the alpha.1 tag via a
  `git+https`-style dependency or a pnpm override pointing at the tag/SHA for
  `@deepseek-ai/dsh-llm`.
- Tradeoff: exact surface, but it is a non-registry install track (skill Mode B rule: single
  mechanism, no mixing), drags the whole DSH workspace-cohort question with it
  (`@deepseek-ai/cordis` peer etc.), and alpha.1's tag existence is **unconfirmed** in this
  closed-book environment. Only justified when Paths A/B cannot answer the question.
- Exit path: remove the override / dependency line to return to the registry track.

### Cross-cutting recommendations

1. **Do not trust the caret to "give the type baseline"**: for a *type baseline* specifically,
   prefer an exact pin (`"0.1.2-alpha.2"`, no caret) or a lockfile; ranges are for runtime
   deps, not for declaration surfaces that compile your code.
2. Keep the DSH cohort coherent: if other `@deepseek-ai/*` devDependencies are added later,
   they must resolve to the same corridor edge (skill rule: "a successful install with mixed
   old/new peers is not a migration"); scan the full lockfile for stray versions.
3. Update the README wording to name the actual baseline version, or the claim will keep
   silently rotting as the registry moves.
4. Validation once a write is authorized: dependency-resolution layer (lockfile diff shows only
   `@deepseek-ai/dsh-llm@0.1.2-alpha.2`), static layer (typecheck/build against the resolved
   declarations), and — if the plugin is ever mounted — the runtime layer via
   `verify-runtime.mjs`. None were run here (read-only task).

## 3. Verification status

| Claim | Status |
|---|---|
| `^0.1.2-alpha.1` range admits `0.1.2-alpha.2` and excludes `0.1.1-rc.x` | Confirmed by node-semver prerelease rules (mechanical) |
| Install fails | **Disproven by analysis** — range is satisfiable; resolution lands on alpha.2 |
| Registry contents (only rc.1/rc.2/alpha.2 published) | **Unconfirmed** — taken from the task brief; no network access permitted |
| Which exact file npm would write / lockfile contents | **Unconfirmed** — no install executed (task rule) |
| alpha.1→alpha.2 card applicability to this fixture's code | **Not assessable** — the fixture contains no source code, only `package.json` + `README.md`; there are no touchpoints to scan |
| Existence of an alpha.1 git tag for Path C | **Unconfirmed** |

## Rollback / safety record

- No files under the fixture were read-modified, created, deleted, or renamed; fixture untouched.
- No install, no package-manager invocation, no lifecycle scripts, no network access.
- Only output written: this report file in the designated output directory.

*Skill structure note — pre-existing baseline failures: not collected (no build/test environment
exists in the fixture and the task forbids creating one).*
