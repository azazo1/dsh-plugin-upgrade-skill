# S7 · Unpublished Cohort Install Plan (Read-Only Report)

**Mode**: A · inspect (read-only) per the `plugin-upgrade` skill. No file under the fixture was modified; no install, build, or migration was executed. This report is written under the designated output directory only.

**Fixture identity** (recorded, not changed):

- Path: `benchmark/tasks/S7-unpublished-cohort/environment/fixture`
- `package.json`: `"name": "dsh-cohort-bench"`, `"version": "0.1.0"`, `"private": true`, `devDependencies: { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`
- `README.md` claim: "npm install gives you the type baseline"; states npm reality for `@deepseek-ai/*`: only `0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2` exist; **alpha.1 was never published**.
- No lockfile, no `pnpm-workspace.yaml`, no source files — the fixture is a manifest-level scenario only.

---

## 1. Real consequence of `^0.1.2-alpha.1` under npm semver

### 1.1 The caret range does NOT mean "install exactly alpha.1"

`^0.1.2-alpha.1` desugars to `>=0.1.2-alpha.1 <0.2.0` (caret over a 0.x version keeps the same minor). npm's prerelease-matching rule adds one gate: a prerelease version only satisfies a range if at least one comparator shares its `[major, minor, patch]` tuple **and** carries a prerelease tag. Applying that to the published set:

| Published version | Satisfies `^0.1.2-alpha.1`? | Why |
|---|---|---|
| `0.1.1-rc.1` / `0.1.1-rc.2` | **No** | Fails `>=0.1.2-alpha.1` outright (lower tuple), and the prerelease-tuple rule also excludes it |
| `0.1.2-alpha.2` | **Yes** | Same tuple `0.1.2`, prerelease `alpha.2` sorts above `alpha.1`, and below `0.2.0` |

### 1.2 So: install will NOT fail — and it will NOT install alpha.1

- `npm install` / `pnpm install` resolves `@deepseek-ai/dsh-llm@^0.1.2-alpha.1` to the **highest published satisfying version: `0.1.2-alpha.2`**. No E404/ETARGET occurs against the official registry for this specifier (registry-side pitfalls are separate, see §2.4).
- The failure the maintainer might expect ("declared an unpublished version, so install breaks") does not happen. Instead the install **silently succeeds with a different version than the one declared**, which is the actual hazard: the README's "npm install gives you the type baseline" is true only in the sense that *a* type baseline appears — but it is the **alpha.2 surface, not the alpha.1 surface the manifest names**.
- Consequence for the type baseline: the alpha.1 → alpha.2 edge carries documented type-surface drift that will surface as compile errors (TS2305-class) in code written against alpha.1. From the R-11 ledger (rollup-0.1.2.md), the drift items touching `dsh-llm` consumers directly:
  - `deepFreeze`, `assertNever` leave `@deepseek-ai/dsh-llm` → `@deepseek-ai/dsh-util-values` (must be added as a **direct dependency**, DSH-0.1.2-A2-03);
  - `LlmModelDiscoveryError` → `RemoteError<'llm/model-discovery-rejected'>`;
  - community measurement (dsh-TUI #647) reports `settingsNamespace` as the only compile break on this edge for one real repository — for this fixture the break set is code-dependent and **unconfirmed** (the fixture ships no source to typecheck).
- Secondary effect: alpha.1 is the corridor edge where `dsh-client-runtime` was removed and `CallId` → `ToolCallId` (rc.2 → alpha.1, R-11). If any consumer code was written against **rc.2 types** and never adapted for alpha.1, the jump straight to alpha.2 folds two edges of drift into one install.

### 1.3 Verdict

The declaration is misleading but functional: the real baseline users get from `npm install` is `0.1.2-alpha.2`. The honest manifest for "the npm-reachable baseline" is `^0.1.2-alpha.2` (see Path D). Getting an actual **alpha.1** baseline requires non-registry work (Paths B/C).

---

## 2. Installation / type-baseline plan (multiple paths, tradeoffs, exit paths)

### Path A (recommended default) — accept alpha.2 as the de-facto baseline

Keep `^0.1.2-alpha.1` as-is or (better) rewrite to `^0.1.2-alpha.2`; let the registry resolve to `0.1.2-alpha.2`; adapt code to the alpha.2 surface using the R-11 ledger and the alpha.1→alpha.2 cards (v0.1.2-alpha.2.md).

- **When**: you have no hard requirement to match an alpha.1-running host; you just want a green, reproducible type baseline.
- **Tradeoffs**: zero build machinery; but the manifest's stated intent and the resolved version diverge (if kept as `^0.1.2-alpha.1`), and you inherit alpha.1→alpha.2 breaking type changes.
- **Exit path**: once the 0.1.2 final ships, the range already admits it; re-verify and re-pin.

### Path B — materialize the true alpha.1 cohort from the git tag (R-01 recipe)

Only when something genuinely requires alpha.1 (e.g. matching a host that runs an unpublished alpha.1 build). Build from the official tag in an isolated worktree and pin via `file:` tarball overrides:

```sh
git clone https://github.com/deepseek-ai/deepseek-harness.git /tmp/dsh-build
cd /tmp/dsh-build && git checkout dsh-v0.1.2-alpha.1   # exact tag name: see "Unconfirmed"
pnpm install && pnpm run build
mkdir -p ~/.dsh-cohorts/0.1.2-alpha.1
pnpm -r exec pnpm pack --pack-destination ~/.dsh-cohorts/0.1.2-alpha.1
```

Then in the plugin's manifest keep the range `^0.1.2-alpha.1` and add `overrides` pointing at the tarballs.

- **Tradeoffs / risks**:
  - the frozen lockfile records machine-dependent absolute tarball paths → CI needs a tarball-store materialization script + actions cache keyed by the manifest hash, and `packageManager` as the single pnpm version source (R-04);
  - **pending-confirmation** pnpm sensitivity: a single field report says `pnpm@11.9.0` bypasses overrides for `file:` transitive deps when third-party peers are present; `packageManager: pnpm@11.24.0` was reported correct — reproduce minimally before adopting;
  - **do not publish** plugin versions whose `@deepseek-ai/*` ranges cannot resolve from the registry (irreversible for that version); if you must release, gate with `NPM_PUBLISH_ENABLED` and/or publish under the `alpha` dist-tag only (R-04).
- **Exit path**: once the cohort ships officially, delete the `overrides` section and regenerate the lockfile to return to registry resolution.

### Path C — verify-only type lane (no install at all)

The dsh-TUI #622 practice: keep the install baseline elsewhere (or absent); CI checks out the upstream alpha.1 tag and runs `tsc --noEmit` with `paths` mappings from its `tsconfig.base.json` pointing at the source. This proves the alpha.1 type surface without ever installing it; runtime is verified separately. dsh-TUI #647 even kept this lane after going npm on alpha.2.

- **When**: you want CI proof against the exact declared version with zero dependency-graph surgery, and runtime compatibility is handled independently (e.g. R-02 runtime probes).
- **Tradeoffs**: proves types only — wire/parameter drift stays invisible at this layer; requires the upstream checkout in CI; no `node_modules` usable for local dev against alpha.1.
- **Exit path**: when alpha.1 stops mattering, delete the lane; or promote it to the published-cohort equivalent by pointing `paths` at registry-installed alpha.2.

### Path D — make the manifest honest

Bump the devDependency to `^0.1.2-alpha.2` (or later published cohort lines — the skill records `0.1.2-alpha.3`/`alpha.4`/`alpha.5` and `0.1.2-rc.1` as published under `alpha`/`next` dist-tags) and update the README wording to name the actual version users get. This is a one-line write in the plugin repo (not this read-only fixture).

- **When**: combined with Path A; the cheapest durable fix.
- **Tradeoffs**: abandons the alpha.1 target; requires the alpha.1→alpha.2 code adaptation anyway.
- **Exit path**: none needed; normal corridor maintenance afterwards.

### 2.4 Cross-cutting install-channel pitfalls (apply to every path that installs)

Per R-08, even *published* cohort versions can fail to install cleanly through three independent mechanisms — check all three before concluding "version missing":

1. **Mirror lag**: force the official registry (`npm_config_registry=https://registry.npmjs.org`); third-party mirrors lag fresh `@deepseek-ai/*` publications by hours+.
2. **pnpm 11 `minimumReleaseAge`** (24h supply-chain rule): on the day a cohort version ships, installs are refused; prefer per-scope exemption `minimumReleaseAgeExclude: ['@deepseek-ai/*', '<plugin name>]` over `minimumReleaseAge: 0`.
3. **Peer-floor prerelease semantics**: an old peer floor like `^0.1.0-rc.8` does **not** match `0.1.2-alpha.2` under npm semver (comparator must share tuple + carry prerelease) → install-time peer warnings/refusals despite actual compatibility; rewrite the floor to `^0.1.2-alpha.2`. Note the same semantics that bites here is what *saves* the fixture's own range in §1.

**Verification after any install** (layer 1 of the skill's checklist): `pnpm list --depth 0 | grep @deepseek-ai` shows a single coherent target version with no mixture; full-lockfile scan finds no old-cohort or removed-package residue; `npm view @deepseek-ai/dsh-llm dist-tags` confirms the channel; install log free of peer warnings.

---

## Report sections per skill convention

- **pre-existing**: not collected (Mode A read-only; fixture ships no source, no lockfile, no test suite to baseline).
- **Completed**: fixture identity recorded; semver consequence analyzed (install succeeds → `0.1.2-alpha.2`, alpha.1 unreachable from the registry); four install/baseline paths with tradeoffs and exit paths; channel pitfalls mapped.
- **Skipped**: touchpoint-class pre-flight scan — no plugin source exists in the fixture to scan; runtime/mount validation layers — out of scope for a read-only plan and explicitly disallowed by the brief.
- **Pending/residual risk / Unconfirmed**:
  - npm registry state is taken from the fixture README + skill references (measured 2026-08-31/2026-09-04); this closed-book brief forbids network queries, so current dist-tags are **unconfirmed**;
  - exact git tag name `dsh-v0.1.2-alpha.1` is inferred from the documented tag convention (`dsh-v0.1.2-alpha.4` etc.) — **unconfirmed** for alpha.1 specifically;
  - the alpha.1→alpha.2 compile-break set for this plugin is **unconfirmed** (no source in the fixture);
  - the pnpm 11.9.0/11.24.0 override-bypass report remains single-source **pending confirmation** in the skill itself;
  - R-06-style baseline attribution was not run (nothing to baseline).
- **Rollback**: nothing was changed; no rollback owed. For future executions: record HEAD/lockfile hash before writes; Path B rollback = delete the `overrides` section and regenerate the lockfile.
- **Recommendations**: adopt Path D + A as the default; keep a Path C verify-only CI lane if alpha.1 fidelity ever matters; never publish plugin versions whose `@deepseek-ai/*` ranges are registry-unresolvable (use `NPM_PUBLISH_ENABLED` gating and the `alpha` dist-tag per R-04).
