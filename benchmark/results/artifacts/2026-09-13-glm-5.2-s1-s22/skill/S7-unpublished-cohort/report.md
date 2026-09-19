# S7 · Unpublished Cohort — Installation / Type-Baseline Plan (Read-Only Report)

- **Task**: analyze `dsh-cohort-bench` (fixture) declaring `@deepseek-ai/dsh-llm: ^0.1.2-alpha.1` while `0.1.2-alpha.1` was never published on npm; produce an installation/type-baseline plan. Read-only; no install executed; fixture untouched.
- **Mode**: plugin-upgrade skill, **Mode A · inspect** (read-only investigation and report).
- **Evidence inspected**: fixture `package.json` + `README.md`; skill references `rollup-0.1.2.md` (R-01 npm-reality note, R-02/R-04), `v0.1.2-alpha.2.md` (alpha.1→alpha.2 card set), `v0.1.2-alpha.1.md`; local `semver` behavior check (see §1).
- **Baseline attribution**: not collected (Mode A; no build/test run permitted or performed).

---

## 1. Real consequence of `^0.1.2-alpha.1`

**Install does NOT fail. It silently installs `0.1.2-alpha.2` — a different version than the declared/intended one.**

### 1.1 Semver mechanics (verified locally)

Caret-prerelease desugaring and prerelease-tuple matching were verified with the real `semver` library (read-only, local to this machine, no network):

- `^0.1.2-alpha.1` desugars to `>=0.1.2-alpha.1 <0.2.0-0`.
- Prerelease versions only satisfy a range if their `[major, minor, patch]` tuple equals a comparator that itself carries a prerelease.

| candidate | satisfies `^0.1.2-alpha.1`? |
|---|---|
| 0.1.1-rc.1 / 0.1.1-rc.2 | **false** (below the floor) |
| 0.1.2-alpha.1 | true (never published — unreachable) |
| **0.1.2-alpha.2** | **true** ← what actually resolves |
| 0.1.2 (final, if published later) | true |
| 0.1.3-alpha.1 | false (prerelease on a different tuple) |
| 0.2.0-alpha.1 | false |

`maxSatisfying([0.1.1-rc.1, 0.1.1-rc.2, 0.1.2-alpha.2]) = 0.1.2-alpha.2`.

### 1.2 Consequences

1. `npm install` succeeds and yields `@deepseek-ai/dsh-llm@0.1.2-alpha.2`. There is no `ETARGET`/`ERESOLVE` failure, so nothing warns the maintainer that the declared version does not exist.
2. The README claim "npm install gives you the type baseline" is therefore **subtly wrong**: the type baseline obtained is **alpha.2**, not the alpha.1 the declaration names. If the code was written/validated against alpha.1-era declarations, type-checking now runs against a shifted surface.
3. alpha.1 → alpha.2 is **not a no-op edge**: the skill's card set for that corridor (`DSH-0.1.2-A2`, 8 cards) includes breaking/behavioral items relevant to a type baseline — `RemoteError` instances with namespaced error codes (`session/not-found` etc., removal of `RpcError`/`RpcErrorCode` etc. from `dsh-client-connection`), restored `SessionEvent.ignorable` retention, trimmed peer dependencies, `sessionProjections` becoming a required inject/peer for tool packages, optional preset grouping, fixed client Host facts `$host.home/isLoopback`. Code or types written against alpha.1 may fail or — worse — silently change meaning under alpha.2.
4. **Forward drift risk**: the range also admits any future `0.1.2` final and `0.1.x` (x≥2) final releases (finals match without the tuple restriction). The fixture ships **no lockfile**, so every fresh install floats to whatever is newest in-range — the "baseline" is not reproducible across time or machines.
5. Per `rollup-0.1.2.md` R-01 npm-reality note: on npm the `@deepseek-ai/dsh-*` cohort has `0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2` (and later `alpha.3`/`alpha.4` under the `alpha` dist-tag); **alpha.1 was never published** and can only be obtained from the GitHub tag `dsh-v0.1.2-alpha.1`. *(Registry state as recorded in the skill; not re-queried here — closed-book, see §4.)*

---

## 2. Installation / type-baseline plan (paths with tradeoffs and exits)

### Path A — Accept alpha.2 as the real baseline, pin it (recommended default)

1. Decide the effective baseline is `0.1.2-alpha.2` (what the range already resolves to).
2. Replace the range with an exact pin `"@deepseek-ai/dsh-llm": "0.1.2-alpha.2"` **and/or** commit a lockfile so the baseline is reproducible; a bare caret with no lockfile floats.
3. Fix the README wording: name the actual version ("type baseline: `0.1.2-alpha.2`"), not "npm install gives you the type baseline".
4. Run typecheck against alpha.2; triage failures against the `DSH-0.1.2-A2` card set (especially A2-02 Remote error codes, A2-08 `sessionProjections` inject/peer) and the api-migration-0.1.2-alpha.2.md (reference file) ledger.
- **Tradeoff**: cheapest, fully registry-backed; but you migrate your source one corridor edge forward (alpha.1→alpha.2) rather than keeping the version you declared.
- **Exit path**: if alpha.2 breakage is too large right now, fall to Path B or C.

### Path B — Obtain the true alpha.1 baseline via the unpublished-cohort recipe (R-01)

Only if the code genuinely must typecheck against alpha.1:

1. Record the exact missing package/version (`@deepseek-ai/dsh-llm@0.1.2-alpha.1`); confirm the registry truly lacks it (query `npm view` — see §4 unconfirmed).
2. Clone the official repo into an isolated worktree, `git checkout dsh-v0.1.2-alpha.1`, `pnpm install && pnpm run build`, `pnpm -r exec pnpm pack` into a local store (`~/.dsh-cohorts/0.1.2-alpha.1`), and pin via `file:` tarballs under `overrides`; keep the manifest range as-is per R-01.
- **Tradeoffs**: exact intended baseline, no source migration needed — but machine-dependent tarball paths land in the lockfile (`--frozen-lockfile` breaks on other runners unless the store is materialized + cached, R-04); a pnpm-11 overrides bypass for `file:` transitive deps is a single unverified field report (pin `packageManager`, treat as pending confirmation); publishing your plugin while ranges cannot resolve from the registry is **irreversible** for that version — gate publishes (`NPM_PUBLISH_ENABLED`) and use an `alpha` dist-tag for prerelease plugin versions.
- **Exit path**: once the registry covers the cohort, delete the `overrides` section and return to registry resolution (R-04).

### Path C — Verify-only, no install (the `dsh-TUI #622` lane)

1. Keep the install baseline wherever it is (even rc.2); in CI, check out upstream tag `dsh-v0.1.2-alpha.1` and run `tsc --noEmit` with `paths` mappings from its `tsconfig.base.json` pointing at the tag's sources.
2. This proves the alpha.1 type surface without any registry tarball. Runtime is verified separately (a second lane).
- **Tradeoff**: zero registry dependency and no lockfile pollution; but it proves types only, requires the upstream checkout in CI, and splits type vs runtime verification.
- **Exit path**: switch to Path A once you adopt alpha.2 (dsh-TUI kept this lane even after going npm on alpha.2 — it can coexist).

### Shared verification (any path)

- `pnpm list --depth 0` (or `npm ls`) shows every `@deepseek-ai/*` entry at the intended single version, no mixture (R-01 verification).
- Full lockfile scan for stale cohort versions, not just top-level deps.
- One typecheck (all paths) + one runtime smoke (Paths A/B) of the plugin's core path.

---

## 3. Skipped (with evidence)

- **No migration executed, no install run, no build/tests**: prohibited by the brief (read-only analysis; fixture must remain unchanged; no reproduction environment). Baseline failures: not collected.
- **Registry / dist-tag live queries**: closed-book brief forbids network lookups; registry state is taken from the skill's recorded npm-reality note and marked unconfirmed where relevant.
- **Mode B/C write actions**: out of scope; this task is explicitly a read-only plan (Mode A).

## 4. Pending / residual risk · unconfirmed items

- **Current npm registry state** (versions and dist-tags of `@deepseek-ai/dsh-llm`) — **unconfirmed**; taken from `rollup-0.1.2.md` (dated 2026-08-31/09-02). Re-query with `npm view @deepseek-ai/dsh-llm versions --json` and `dist-tags` before acting.
- **Existence/reachability of the git tag `dsh-v0.1.2-alpha.1`** — unconfirmed here (no network); Path B depends on it.
- **Transitive cohort resolution at alpha.2**: whether every other `@deepseek-ai/*` package that `dsh-llm@0.1.2-alpha.2` needs as peer/dependency is itself published at a compatible version — unconfirmed (A2-03 trimmed peers, which helps but does not prove it).
- **Exact resolver behavior of the maintainer's npm/pnpm version** for caret-prerelease — verified here only against the `semver` library bundled in the local DSH checkout; ancient resolver quirks are out of scope.
- The pnpm-11 `overrides` bypass note (Path B) is a single field report marked "pending confirmation" in the skill itself.
- **Semver floor subtlety worth flagging**: even a hypothetical future `0.1.2-alpha.1` publication changes nothing for drift — the range still admits every newer same-tuple prerelease and later finals; only an exact pin or lockfile gives a stable baseline.

## 5. Rollback

No changes were made (read-only task): fixture untouched, nothing installed, no lockfile, no configuration writes. Rollback baseline = current state of the fixture directory (git HEAD per the fixture README's grading note). For the *future* execution of Paths A/B: record HEAD + lockfile hash before editing; Path B's recoverable path is deleting the `overrides` section and the local tarball store; Path A's is restoring the previous dependency line + lockfile.

## 6. Recommendations

1. Adopt **Path A** unless there is a concrete reason the source must compile against alpha.1 exactly; pin exactly and commit a lockfile — a floating caret over a partially published prerelease cohort is the root cause here.
2. Fix the README sentence to name the concrete version; "npm install gives you the type baseline" is exactly the assumption this incident falsifies.
3. When the corridor moves again, run the corridor edges (`v0.1.2-alpha.2` card set → later cards) rather than trusting the range to stay put; prerelease tuples outside the comparator tuple do **not** match, so e.g. `0.1.3-alpha.1` will not silently arrive, but `0.1.2` final and `0.1.3` final will.
4. If dual-cohort runtime support (rc.2 hosts + alpha hosts) matters, apply the R-02 recipe (runtime cohort probing, no hard `inject` on new-only services) rather than hard-coding either cohort.
