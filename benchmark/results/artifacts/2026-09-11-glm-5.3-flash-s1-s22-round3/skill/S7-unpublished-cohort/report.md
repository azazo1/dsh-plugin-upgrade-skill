# S7 · Unpublished Cohort Install Plan (Read-Only Diagnostic Report)

Mode: A · inspect (read-only), per the dsh-plugin-upgrade skill. No file under the fixture was modified and no install was executed (per brief: closed-book, no registry queries, no reproduction environment). Fixture inspected: `environment/fixture/package.json` and `environment/fixture/README.md`. This report corresponds to `/app/fixture/` in the original brief.

## Evidence collected

- `package.json`: `"name": "dsh-cohort-bench"`, `"version": "0.1.0"`, `"private": true`, `"devDependencies": { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`.
- `README.md`: "A plugin whose type baseline declares `@deepseek-ai/dsh-llm: ^0.1.2-alpha.1` while the README claims \"npm install gives you the type baseline\". npm reality: `@deepseek-ai/*` has only 0.1.1-rc.1 / 0.1.1-rc.2 / 0.1.2-alpha.2 — **alpha.1 was never published**." Also: "Test material only — do not execute or publish (`private: true`)."
- No lockfile exists in the fixture, so the package manager is not pinned; the plan below treats npm and pnpm separately.
- Skill reference `references/rollup-0.1.2.md`, section R-01 ("Target cohort dependency packages not fully published to npm") confirms the same registry fact verbatim: "on npm, the `@deepseek-ai/dsh-*` packages only have `0.1.1-rc.1`, `0.1.1-rc.2`, and `0.1.2-alpha.2`; alpha.1 was never published."

## 1. Real consequence of `"devDependencies": { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`

**The install does NOT fail.** Two semver facts decide this:

1. **Prerelease matching rule.** npm's semver implementation only lets a range containing a prerelease comparator match prerelease versions of the same `[major, minor, patch]` tuple. `^0.1.2-alpha.1` desugars to `>=0.1.2-alpha.1 <0.2.0` with the prerelease comparator pinned to the `0.1.2` tuple. Therefore:
   - `0.1.1-rc.1` / `0.1.1-rc.2` — **not matched** (different tuple, `0.1.1`), even though they exist on npm. The old cohort cannot satisfy the range.
   - `0.1.2-alpha.2` — **matched** (same `0.1.2` tuple, prerelease, `>= alpha.1`, and the caret upper bound `<0.2.0` does not exclude it).
2. **Caret semantics on `0.x`.** For `0.1.2-alpha.1`, the caret upper bound is `0.2.0` (caret with a leading `0.x.y` locks the minor). The upper bound is irrelevant here since no `0.1.x`/higher version besides alpha.2 is published.

**What actually gets installed: `@deepseek-ai/dsh-llm@0.1.2-alpha.2`** — the highest published version satisfying the range. npm skips the unpublished `0.1.2-alpha.1` exactly as it skips any version absent from the registry; it does not error because a *referenced* version is missing, only if *no* version satisfies the range. Since alpha.2 satisfies it, resolution succeeds.

**The real problem is semantic, not resolution:** the README's claim "npm install gives you the type baseline" is wrong in a specific way. The declared baseline is alpha.1, but the installed type surface is alpha.2. Per the skill's rollup R-11 ("0.1.2 type-surface export drift"), the alpha.1 → alpha.2 edge of `@deepseek-ai/dsh-llm` itself carries breaking type changes, e.g.:

- `deepFreeze` / `assertNever` exported from `@deepseek-ai/dsh-llm` at alpha.1 are **gone** by alpha.2 (moved to the new package `@deepseek-ai/dsh-util-values`, which is not in the fixture's devDependencies).
- `LlmModelDiscoveryError` (code `model-discovery-failed`) is deleted; replaced by `RemoteError<'llm/model-discovery-rejected'>` (alpha.2 `packages/llm/llm/src/types.ts:261`).

So a plugin authored against the alpha.1 type baseline will typecheck against alpha.2 **only if** it touches none of the drifted exports; if it does, `pnpm install` / `npm install` succeed and the failure appears later, at `tsc`, as TS2305 ("has no exported member") — a silent version skew, not an install error. Conversely, `^0.1.2-alpha.1` is *open-ended upward* within the tuple: any future `0.1.2-alpha.3`, `-rc.1`, or final `0.1.2` will silently replace alpha.2 on a fresh install, so the "baseline" is not reproducible without a lockfile (which this fixture does not have). One related install-channel hazard from rollup R-08 does apply at execution time even though resolution succeeds: if the machine's registry is a lagging mirror (npmmirror etc.) that has not synced alpha.2, the install reports E404/ETARGET — use `registry.npmjs.org` explicitly; and pnpm 11's `minimumReleaseAge` supply-chain rule can refuse a freshly published alpha (fix: `minimumReleaseAgeExclude: ['@deepseek-ai/*']`).

Unconfirmed (closed-book, no registry access): the exact current npm version list and dist-tags beyond what the brief and the skill's R-01 entry (measured 2026-08-31) state; whether a lockfile was ever generated for this plugin; whether the plugin source actually imports any R-11-drifted export (no source files exist in the fixture beyond the two listed files).

## 2. Workable installation / type-baseline plan

Multiple paths, ordered by preference. All are plans only — none executed, per the brief.

### Path A (recommended if the plugin must stay on the exact alpha.1 baseline): pin + file: tarball built from the official tag

Per rollup R-01's recipe:

1. Record the missing coordinate: `@deepseek-ai/dsh-llm@0.1.2-alpha.1` (registry-absent).
2. In an isolated worktree, build the official tag and pack:
   `git clone https://github.com/deepseek-ai/deepseek-harness.git /tmp/dsh-build` → `git checkout dsh-v0.1.2-alpha.1` → `pnpm install && pnpm run build` → `pnpm -r exec pnpm pack --pack-destination ~/.dsh-cohorts/0.1.2-alpha.1`.
3. Pin via overrides to the local tarball, keeping the declared range unchanged: dependency stays `"^0.1.2-alpha.1"`, with an `overrides`/`pnpm.overrides` entry `"@deepseek-ai/dsh-llm": "file:<tarball>"` (npm) or the pnpm equivalent.
4. Exit path: "once the final release ships, deleting the overrides section returns to registry resolution" (R-01 verbatim). Rollback = delete the overrides entry and regenerate the lockfile; only those two paths are owned by this change.
- Tradeoffs: exact baseline, reproducible; but machine-dependent tarball paths poison frozen-lockfile CI (R-04 — needs a tarball-materialization script + CI cache), and the pnpm 11 overrides/file:-tarball transitive pitfall noted in R-01 is explicitly "pending confirmation" (single field report, un-reproduced — verify with a minimal repro before adopting, and consider `packageManager: pnpm@11.24.0` if it reproduces).

### Path B (recommended if alpha.2 types are acceptable): accept the resolved alpha.2 and re-baseline the declaration

1. Change the declared range to the exact resolved intent: `"@deepseek-ai/dsh-llm": "0.1.2-alpha.2"` (or `"^0.1.2-alpha.2"`), and commit a lockfile so installs are reproducible.
2. Run a typecheck with `skipLibCheck: false` (skill Mode C step 5: do this whenever a selector or callback unexpectedly becomes `any`) and fix any R-11 drift hits: `deepFreeze`/`assertNever` → `@deepseek-ai/dsh-util-values` (add as a direct devDependency), `LlmModelDiscoveryError` → `RemoteError<'llm/model-discovery-rejected'>` code branching.
3. Exit path: none needed — the dependency is registry-resolvable; the corridor's later tags (alpha.3/alpha.4 on the `alpha` dist-tag per R-01's update note) are a straightforward future bump.
- Tradeoffs: no build-from-source, CI-friendly, lockfile-reproducible; but it concedes the type baseline is alpha.2, not alpha.1, so it must be paired with the small drift fix above. This also fixes the README contradiction at the root (declare the baseline that npm actually provides).

### Path C (verify-only, no dependency install): source-plane typecheck against the tag

Per R-01's "Verify-only, no install" lane (dsh-TUI #622): keep the install baseline as-is (or on rc.2 for runtime), check out the upstream `dsh-v0.1.2-alpha.1` tag, and run `tsc --noEmit` with `paths` mappings from the tag's `tsconfig.base.json` pointing at the alpha.1 sources. This proves the type surface without installing the unpublished version; runtime is verified separately.
- Tradeoffs: zero artifact maintenance and works while alpha.1 remains unpublished; but it is a CI-side proof, not an installable baseline — a local `npm install` still resolves alpha.2, so the README's "npm install gives you the type baseline" sentence must be corrected regardless.

### Path D (if the real intent was "latest of the 0.1.2 cohort"): jump to a fully published cohort

The registry lacks only alpha.1; alpha.2 is published, and per rollup R-01's update "`0.1.2-alpha.3` and `0.1.2-alpha.4` are published under the `alpha` dist-tag". Declaring `^0.1.2-alpha.2` (R-08's peer-floor rewrite pattern) with the official registry gives an entirely registry-resolvable install. Requires reading the alpha.1→alpha.2 (and beyond) version cards before bumping — per the skill, never treat a resolved install as a migration.

### Validation plan (applies to whichever path is chosen)

Layered, per the rollup checklist: (1) dependency resolution — `pnpm list --depth 0 | grep @deepseek-ai` shows one consistent version, full lockfile scan shows no old-cohort `0.1.1-rc.*` row; (2) static — typecheck + build, all green without `@ts-ignore`; (3) real cold boot of one profile with the plugin mounted, no pending entries; (4) one functional message → tool → reply round. Before any change, record the rollback baseline: current `package.json` content (quoted above), absence of a lockfile, and no git-tracked changes to the fixture.

## 3. Unconfirmed items

- Current npm dist-tags/version list (no network allowed): stated registry facts are taken from the brief and the skill's R-01 measurements (2026-08-31 / 2026-09-02 / 2026-09-07) and may have moved since.
- Whether the pnpm 11.9.0 overrides/file:-tarball defect (R-01 note) reproduces — single field report, flagged "pending confirmation" in the skill itself.
- Retry parameters in R-07 and the R-06 baseline pipeline are likewise single-source per the skill's "Pending confirmation" section; not load-bearing for this plan.
- Any plugin source-level usage of drifted alpha.1 exports: no source files are present in the fixture, so the R-11 drift is a *risk*, not a confirmed break.

## Bottom line

`^0.1.2-alpha.1` resolves successfully to `@deepseek-ai/dsh-llm@0.1.2-alpha.2` — the install will not fail, and the missing alpha.1 is silently skipped. The defect is the false "npm install gives you the type baseline" claim: you get alpha.2 types, with R-11-documented breaking surface drift from alpha.1, and a non-reproducible floating baseline (no lockfile). Preferred fix is Path B (declare `0.1.2-alpha.2` explicitly + commit a lockfile + drift typecheck); Path A (tag-built tarball + overrides) preserves the literal alpha.1 baseline when that is mandatory; Path C is the zero-install verification lane; Path D if the intent was cohort-latest.
