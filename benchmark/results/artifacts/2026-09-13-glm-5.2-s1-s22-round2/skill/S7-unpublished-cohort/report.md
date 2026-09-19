# S7 · Unpublished Cohort — Installation / Type-Baseline Plan (Read-Only Report)

**Mode**: A · inspect (plugin-upgrade skill) — read-only analysis, no install executed, no file under the fixture touched.
**Fixture**: `dsh-cohort-bench@0.1.0` (private), `devDependencies: { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`, no lockfile present.
**Registry reality (given by the brief, closed-book)**: `@deepseek-ai/*` on npm has only `0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2`. `0.1.2-alpha.1` was never published.

---

## 1. Real consequence of `^0.1.2-alpha.1` — semver analysis

### 1.1 The range does NOT fail to install

`^0.1.2-alpha.1` desugars to `>=0.1.2-alpha.1 <0.2.0` (caret on `0.1.x` allows patch/minor within `0.1`). The decisive rule is **npm semver prerelease matching**: a version carrying a prerelease tag matches a range only if at least one comparator in the range (a) has a prerelease and (b) shares the same `[major, minor, patch]` tuple.

Evaluate each published candidate:

| Candidate | In range? | Reason |
|---|---|---|
| `0.1.1-rc.1` | no | tuple `0.1.1` ≠ `0.1.2`; also `0.1.1-rc.1 < 0.1.2-alpha.1` by semver precedence |
| `0.1.1-rc.2` | no | same as above |
| `0.1.2-alpha.1` | (would match) | tuple `0.1.2` + prerelease on both sides — **but this version does not exist on npm** |
| `0.1.2-alpha.2` | **yes** | tuple `0.1.2` matches the comparator tuple and the comparator carries a prerelease; `alpha.2 > alpha.1` |

So the naive expectation "the declared version was never published, so `npm install` fails with E404/ETARGET" is **wrong**. A version range is satisfied by *any* matching version, not by the literal text. Install succeeds and **resolves to `0.1.2-alpha.2`** — the highest published version inside the range. This mirrors the pitfall class in the skill's rollup (R-01/R-08): "the declared target is missing from the registry" and "install fails" are independent conditions; here only the first holds.

(Both npm and pnpm resolve this identically — same node-semver implementation of the prerelease-tuple rule.)

### 1.2 The README claim is silently wrong

"npm install gives you the type baseline" fails in the quietest way possible:

1. **The baseline you get is alpha.2, not alpha.1.** The author's declared intent (code written and typechecked against the alpha.1 surface) is not what lands in `node_modules`.
2. **alpha.1 → alpha.2 is a breaking edge for `dsh-llm` itself** (skill rollup R-11 ledger, alpha.1→alpha.2 rows): `deepFreeze` and `assertNever` left `@deepseek-ai/dsh-llm` for `@deepseek-ai/dsh-util-values`; `LlmModelDiscoveryError` was deleted in favor of `RemoteError<'llm/model-discovery-rejected'>`. Code that compiles against alpha.1 can fail typecheck in bulk (TS2305) against the alpha.2 that actually installs — with **zero install-time error or warning** pointing at the cause.
3. **The caret keeps drifting.** The range admits any future `0.1.2-alpha.n`, `0.1.2-rc.n`, or `0.1.2` final (a release version needs no tuple-matched prerelease comparator). A fresh install months later can silently move the baseline again. There is no lockfile in the fixture to freeze today's resolution.
4. **Peer-floor interactions (unconfirmed for this package)**: if `dsh-llm@0.1.2-alpha.2` declares peers with old-style floors like `^0.1.0-rc.8`, the same prerelease-tuple rule judges them non-matching for `0.1.2-alpha.2` and npm/pnpm emit peer warnings or refusals (rollup R-08 pitfall 3). The fixture's single devDependency cannot confirm this; mark unconfirmed.

**Bottom line**: install succeeds, `0.1.2-alpha.2` is installed, and the "type baseline" the README promises is neither alpha.1 nor stable — it is an unpinned, forward-drifting prerelease edge whose type surface differs from the author's target.

---

## 2. Installation / type-baseline plan

Ordered by preference. All paths assume the read-only constraint is lifted before any actual write (Mode B discipline: plan → confirm → execute in a dedicated branch).

### Path A — Accept alpha.2 as the baseline (recommended default)

Since install already resolves to alpha.2, make that explicit and honest:

1. Pin `"@"devDependencies": { "@deepseek-ai/dsh-llm": "0.1.2-alpha.2" }` (exact, no caret) **or** keep the caret but commit a lockfile so resolution is frozen; regenerate and audit on every intentional bump.
2. Apply the R-11 ledger's alpha.1→alpha.2 rows to the plugin source (`deepFreeze`/`assertNever` → `dsh-util-values`, now a direct dependency; `LlmModelDiscoveryError` → `RemoteError` code branching).
3. Fix the README: replace "npm install gives you the type baseline" with the actual resolved version and the pinning policy.
- **Tradeoffs**: zero infra cost; loses alpha.1 fidelity. Exit path: any time later, switch to Path B/C if alpha.1-specific behavior must be reproduced.

### Path B — Reproduce alpha.1 from the GitHub tag (R-01 recipe)

The rollup records that rc.2 → alpha.1 "can only be built from a GitHub tag" (alpha.1 never hit npm, including the `alpha` dist-tag):

```sh
git clone https://github.com/deepseek-ai/deepseek-harness.git /tmp/dsh-build
cd /tmp/dsh-build && git checkout dsh-v0.1.2-alpha.1
pnpm install && pnpm run build
mkdir -p ~/.dsh-cohorts/0.1.2-alpha.1
pnpm -r exec pnpm pack --pack-destination ~/.dsh-cohorts/0.1.2-alpha.1
```

then pin via `overrides`/`file:` tarballs, keeping the manifest range `^0.1.2-alpha.1`; delete the overrides once the cohort is officially published.
- **Tradeoffs**: true alpha.1 type baseline; but lockfiles record machine-dependent absolute paths (R-04 CI coupling — every runner must materialize the tarball store), and a single unverified field report says pnpm `11.9.0` bypasses overrides for `file:` transitive deps with third-party peers (pin `packageManager: pnpm@11.24.0`, reproduce first — unconfirmed). Must never publish a package version whose ranges resolve only via overrides.
- **Exit path**: drop overrides → registry resolution (becomes Path A).

### Path C — Verify-only lane, no install change (dsh-TUI #622/#647 pattern)

Keep the install baseline as-is (or at rc.2) and prove the type surface in CI: check out the upstream tag (`dsh-v0.1.2-alpha.1`) and run `tsc --noEmit` with `paths` mappings from its `tsconfig.base.json` pointing at the tag's source. Runtime is verified separately from the installed cohort.
- **Tradeoffs**: no registry/override machinery at all; but type-verified ≠ runtime-verified — the wire/activation contract is not exercised by `tsc` (skill: all-green static checks cannot prove the runtime contract). dsh-TUI kept this lane even after moving npm onto alpha.2, which suggests it as a durable CI complement rather than a substitute.

### Path D — Fall back to the published rc.2 baseline

Pin `0.1.1-rc.2` and treat alpha.1→alpha.2 as a later migration. Cheapest and fully registry-served, but abandons the declared cohort; reasonable only if the plugin does not need alpha-line APIs.

### Cross-cutting hygiene (any path)

- Official registry only (`npm_config_registry=https://registry.npmjs.org`) — third-party mirrors lag fresh `@deepseek-ai/*` publications (R-08 pitfall 1).
- pnpm 11 `minimumReleaseAge` can refuse day-old alphas in CI — per-scope `minimumReleaseAgeExclude: ['@deepseek-ai/*', '<plugin name>']` rather than disabling the rule (R-08 pitfall 2).
- Verify resolution: `pnpm list --depth 0 | grep @deepseek-ai` — every entry at the target version, no mixture; `npm view @deepseek-ai/dsh dist-tags` to confirm the channel.
- Validation layers per the skill: dependency resolution → typecheck/build → cold boot with one message→tool→response round. Static green alone is insufficient.

## 3. Unconfirmed / cannot verify

- **Live registry state**: closed-book brief; the three-version list is taken as given, not re-queried (no network use allowed). Later `0.1.x` publications (the skill's references mention alpha.3+ under the `alpha` tag at later dates) would change which version the caret actually resolves to today — one more reason the caret is unsafe as a "baseline" declaration.
- **Exact content of the `dsh-v0.1.2-alpha.1` git tag** (existence assumed from the skill's references; not fetched).
- **Peer-dependency floors of `dsh-llm@0.1.2-alpha.2`** and whether an ERESOLVE/peer warning fires on install (fixture has no lockfile or transitive evidence).
- **pnpm-version sensitivity of the `file:` override path** (single field report, per the skill's own "Pending confirmation").
- **The plugin's actual source** — the fixture contains only `package.json` and `README.md`, so no touchpoint inventory (pre-flight seven classes) or baseline suite (R-06) could be collected.

## 4. Skill report sections

- **pre-existing**: not collected (Mode A read-only; no mechanical suite run — the brief forbids installs and builds).
- **Completed**: fixture inspection (`package.json`, `README.md`); semver consequence analysis (§1); four-path plan with tradeoffs and exits (§2); unconfirmed list (§3).
- **Skipped**: any write to the fixture (read-only mandate); registry/network queries (closed-book); reproduction builds (forbidden); pre-flight touchpoint scan (no source files to scan).
- **Pending/residual risk**: all items in §3; plus the standing risk that a future in-range publication silently moves the caret resolution.
- **Rollback**: nothing was changed, so nothing to roll back. Future executors: record HEAD/lockfile hash before writes (Path B's overrides touch `package.json` + lockfile only).
- **Recommendations**: adopt Path A now (exact pin + committed lockfile + corrected README), keep Path C as the CI type-fidelity lane against the alpha.1 tag while the alpha.1-authored code is ported to the alpha.2 surface via the R-11 ledger; publish plugin releases adapted to an alpha cohort under an `alpha` dist-tag only.
