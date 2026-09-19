# S7 · Unpublished Cohort Install Plan — Diagnostic Report

Mode: **A · inspect (read-only)** per the plugin-upgrade skill. No file under the fixture was modified, no install was run, no network was queried (closed-book).

## Fixture identity (skill "shared read-only preparation" step 2)

- Files inspected: `README.md`, `package.json` (the complete evidence pack).
- `package.json`: `"name": "dsh-cohort-bench"`, `"version": "0.1.0"`, `"private": true` (README: "Test material only — do not execute or publish"), and exactly one dependency row: `"devDependencies": { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`.
- `README.md` claim: "npm install gives you the type baseline", while also stating the npm reality: `@deepseek-ai/*` has only `0.1.1-rc.1` / `0.1.1-rc.2` / `0.1.2-alpha.2` — **alpha.1 was never published**.
- No lockfile, no source files, no `cordis.yml`/`dsh-plugin.json` present — package-manager choice is unconstrained by a lockfile (see Unconfirmed).

## Item 1 · Real consequence of the caret declaration

**The install does NOT fail.** Under npm/node-semver rules:

- `^0.1.2-alpha.1` expands to `>=0.1.2-alpha.1 <0.2.0` (caret on a `0.x` line freezes the minor: `<0.2.0`, not `<1.0.0`).
- Prerelease versions satisfy a range only when at least one comparator shares the same `[major,minor,patch]` tuple **and** carries a prerelease. The comparator `>=0.1.2-alpha.1` shares the `0.1.2` tuple and carries `-alpha.1`, so published prereleases of the `0.1.2` tuple above `alpha.1` **do** match.
- Given the registry reality (only `0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2`): `0.1.1-rc.2` is below the lower bound (0.1.1 < 0.1.2, and its tuple has no matching prerelease comparator), so the only satisfier is `0.1.2-alpha.2`.
- **Net result: a plain `npm install` succeeds and silently resolves `@deepseek-ai/dsh-llm@0.1.2-alpha.2`** — the declared floor `alpha.1` never exists anywhere on disk. Only an **exact** pin (`"0.1.2-alpha.1"` with no caret) would hard-fail with ETARGET/404; the caret is precisely what makes this fail soft.

**The real problem is the README's type-baseline claim.** "npm install gives you the type baseline" is false in two directions:

1. You get `alpha.2`, not the declared `alpha.1` floor — a different cohort than the declaration names.
2. `alpha.1 → alpha.2` has real type-surface drift in exactly this package. Per the skill's rollup R-11 ("0.1.2 type-surface export drift"): `deepFreeze` and `assertNever` move **out of `@deepseek-ai/dsh-llm`** to the new `@deepseek-ai/dsh-util-values`; `LlmModelDiscoveryError` is replaced by `RemoteError<'llm/model-discovery-rejected'>`; and on the rc.2 → alpha.1 edge `CallId` becomes `ToolCallId`. A plugin written against the assumed alpha.1 surface may typecheck (or fail) against alpha.2 unpredictably — the "baseline" is whatever the registry's highest satisfier happens to be on install day, which is exactly the hazard R-11 documents (bulk TS2305/TS2614 with runtime unaffected).

The skill's R-08 pitfall 3 confirms the mirror-image rule: a caret prerelease floor is also how peer floors silently stop matching — here it works in the opposite direction (it silently *upgrades*), but both are the same "prerelease caret semantics" trap.

## Item 2 · Workable installation / type-baseline plan

### Path 1 (recommended): accept the resolution, but make it explicit — pin `0.1.2-alpha.2` and migrate the surface

- Change the declaration to `"@deepseek-ai/dsh-llm": "^0.1.2-alpha.2"` (or exact `"0.1.2-alpha.2"`) and regenerate the lockfile. This is the skill's R-08 remedy written for the dependency instead of a peer floor: "when bumping cohorts, explicitly rewrite it to `^0.1.2-alpha.2`"; the disappearing install-time peer warning is the landed signal.
- Audit the code against the R-11 ledger for the `dsh-llm` rows (`CallId`→`ToolCallId`, `deepFreeze`/`assertNever`→`dsh-util-values` + add `@deepseek-ai/dsh-util-values` as a direct dependency per card DSH-0.1.2-A2-03, `LlmModelDiscoveryError`→`RemoteError` code branching).
- **Tradeoff**: requires a small source migration; **exit path**: the caret keeps future `0.1.2`-tuple prereleases flowing, and rolling back is a one-line dependency revert plus lockfile regen.
- Verify (layered checklist layer 1): `pnpm list --depth 0 | grep @deepseek-ai` all points at one version with no mixture.

### Path 2: if you truly need the alpha.1 floor — build the tarball from the tag (R-01 recipe)

- Record the exact missing package/version (`@deepseek-ai/dsh-llm@0.1.2-alpha.1`), then build from the official tag in an isolated worktree: `git clone … && git checkout dsh-v0.1.2-alpha.1 && pnpm install && pnpm run build`, `pnpm -r exec pnpm pack --pack-destination ~/.dsh-cohorts/0.1.2-alpha.1`, and pin via `overrides` to `file:` tarballs, keeping the range written as `^0.1.2-alpha.1`.
- **Tradeoff** (R-04): frozen lockfiles then record machine-dependent absolute paths and every CI runner needs the tarball store materialized; publish must be gated (`NPM_PUBLISH_ENABLED` off) while the cohort is unpublished, or that plugin version becomes permanently unresolvable. R-01 also flags an **unconfirmed** pnpm-version sensitivity (`11.9.0` bypassing `file:` overrides for transitive deps; pin `packageManager: pnpm@11.24.0` — single field report, reproduce before adopting).
- **Exit path**: once the cohort publishes (or you accept Path 1's alpha.2), delete the `overrides` section and registry resolution returns.

### Path 3: verify-only, zero install (R-01 / dsh-TUI #622 recipe)

- Keep the install baseline at the last published stable line (`0.1.1-rc.2`) and prove the **type surface** only: CI checks out the upstream `dsh-v0.1.2-alpha.1` tag and runs `tsc --noEmit` with `paths` mapped at that tag's `tsconfig.base.json`. Runtime is verified separately (dsh-TUI #647 kept this lane even after moving to npm on alpha.2).
- **Tradeoff**: no runtime verification of the target cohort in this lane; dual bookkeeping between the install tree and the typecheck tree. **Exit path**: fold into Path 1 when the migration lands.

### Path 4 (orthogonal, always do it): fix the documentation contract

- Whichever path wins, the README line "npm install gives you the type baseline" must state the *actual* resolved version and the prerelease-caret semantics ("installs the newest published `0.1.2-alpha.*`, currently `0.1.2-alpha.2`"), or pin the exact version so the claim becomes true. The R-06-style attribution point: today a green install proves nothing about the declared floor — make the declaration, the lockfile, and the README agree on one cohort.

Not recommended: exact-pinning `0.1.2-alpha.1` (guaranteed ETARGET/404 — that version does not exist), or mixing package managers against a lockfile (skill Mode B rule 1).

## Item 3 · Unconfirmed items

- **Registry state**: taken from the brief/fixture README as given ("only 0.1.1-rc.1 / 0.1.1-rc.2 / 0.1.2-alpha.2"; alpha.1 never published). Not verified against npm — the brief forbids network access. Note the tension: the skill's rollup R-01 records that `0.1.2-alpha.3` and `alpha.4` later appeared under the `alpha` dist-tag (as of 2026-09-02/09-07 `alpha` → `0.1.3-alpha.2`); if any of those exist, the caret resolves to the *highest* satisfier, not necessarily `alpha.2`. Confirm with `npm view @deepseek-ai/dsh-llm versions` and `npm view @deepseek-ai/dsh-llm dist-tags` before executing any path.
- **Which package manager**: no lockfile in the fixture; commands above assume pnpm (the skill's default); under npm the same resolution applies but `overrides`/`minimumReleaseAgeExclude` syntax differs (R-08's supply-chain and mirror-lag pitfalls apply per channel).
- **Exact type drift hit-list for this plugin**: the fixture contains no source, so which R-11 ledger rows actually bite cannot be determined — run a typecheck with `skipLibCheck: false` against the resolved tarball to find out (skill Mode C step 5 guidance).
- **Published dates / mirror state**: nothing in the fixture dates the README claim; mirror lag (R-08 pitfall 1) cannot be assessed offline.

## Skill-structure reporting sections

- **Pre-existing**: not collected (Mode A; no baseline run performed — and none may be run: no install allowed).
- **Completed**: fixture identity recorded; caret-resolution analysis (resolves `0.1.2-alpha.2`, install succeeds); four-path plan with tradeoffs and exit paths.
- **Skipped**: no touchpoint scan, runtime validation, or registry queries — read-only, closed-book, no install authorized; no source files exist to scan.
- **Pending/residual risk**: unconfirmed registry/dist-tag state above; silent caret drift will recur for every future `0.1.2`-tuple prerelease until the range is pinned or the cohort goes final.
- **Rollback**: none needed — no writes performed; fixture untouched (grading requires it unchanged vs git HEAD).
- **Recommendations**: execute Path 1 + Path 4 together; use Path 2 only if alpha.1-faithful typing is a hard requirement; keep Path 3 in CI as the keyless type lane.
