# S7 · Unpublished Cohort — Installation / Type-Baseline Plan (Read-Only Report)

**Task**: analyze, without modifying the fixture or running any install, the consequences of a plugin declaring
`devDependencies: { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }` when — per the task brief — the npm reality for
`@deepseek-ai/*` is that only `0.1.1-rc.1`, `0.1.1-rc.2`, and `0.1.2-alpha.2` exist; `0.1.2-alpha.1` was never published.

**Evidence inspected (read-only)**

- `fixture/package.json` — `"private": true`, single devDependency `@deepseek-ai/dsh-llm: ^0.1.2-alpha.1`.
- `fixture/README.md` — claims "npm install gives you the type baseline" and marks the fixture as test material.

No files were modified; no install was executed.

---

## 1. Real consequence of the declaration

### 1.1 Semver resolution of `^0.1.2-alpha.1`

Under node-semver, the caret range on a 0.x version with a prerelease lower bound expands to:

`^0.1.2-alpha.1` ≡ `>=0.1.2-alpha.1 <0.2.0`

Two rules matter here:

1. **The lower bound is inclusive of the prerelease itself**, and any version ≥ it that is not a prerelease (e.g. a
   future `0.1.2` stable or `0.1.3`) also satisfies the range.
2. **Prerelease versions only satisfy a range if at least one comparator has the same [major, minor, patch] tuple.**
   `0.1.2-alpha.2` shares the `0.1.2` tuple with the `>=0.1.2-alpha.1` comparator, and `alpha.2 > alpha.1`
   lexicographically/by identifier precedence — so it **does** satisfy the range.
   `0.1.1-rc.1` / `0.1.1-rc.2` are below the lower bound and are **excluded** regardless of the prerelease rule.

### 1.2 Will install fail?

**No.** `npm install` will not fail with ENOTFOUND/ETARGET, because the range is satisfiable. npm resolves the range to
the **highest published version that satisfies it**, which is:

> **`@deepseek-ai/dsh-llm@0.1.2-alpha.2` will actually be installed.**

So the failure mode of this fixture is **not** a hard install error — it is a **silent version substitution**:

- The maintainer declared `0.1.2-alpha.1` as the intended type baseline, but that artifact never existed on the registry.
- Every fresh install (and every `package-lock.json`-less CI run) silently gets `0.1.2-alpha.2` instead.
- The README claim "npm install gives you the type baseline" is therefore **only accidentally true**: you get *a*
  type baseline, but not the one named in `package.json`, and it is one prerelease identifier ahead of the declared
  baseline. Any type changes shipped between alpha.1 and alpha.2 land in consumers' editors without any signal in the
  manifest. (Whether alpha.2 actually differs in types from alpha.1 is **unconfirmed** — alpha.1 was never published,
  so no diff is possible from the registry.)

### 1.3 Caveats / unconfirmed items

- **Unconfirmed — registry contents.** This is a closed-book brief; the set {0.1.1-rc.1, 0.1.1-rc.2, 0.1.2-alpha.2} is
  taken from the task statement and could not be verified against the live npm registry (no network use allowed).
- **Unconfirmed — dist-tags.** If `0.1.2-alpha.2` were somehow unpublished or a `latest`/dist-tag constraint applied,
  resolution could differ; plain `npm install <pkg>@^0.1.2-alpha.1` ignores dist-tags except for tag specifiers, so
  this only matters if the version list above is wrong.
- **Unconfirmed — type surface delta between alpha.1 and alpha.2.** Not verifiable; alpha.1 does not exist.

---

## 2. Installation / type-baseline plan

Multiple paths, with tradeoffs and exit paths. All are manifest/lockfile-level actions; none require touching the
fixture for this read-only analysis.

### Path A — Accept the resolver's choice, make it visible (minimal change)

**Action**: keep `^0.1.2-alpha.1`, commit a `package-lock.json` (or `npm shrinkwrap` for a published package) that
pins the resolved version, and update the README to name the *actual* baseline (`0.1.2-alpha.2`).

- **Tradeoff**: zero manifest churn; the lockfile freezes the silent substitution so all machines/CI get the identical
  baseline. Downside: the declared range still advertises a nonexistent version, which is misleading to readers and
  fragile if alpha.2 is ever unpublished.
- **Exit path**: switch to Path B the moment types drift, or drop the lockfile once a stable `0.1.2` ships (stable
  releases satisfy the caret range and become the resolved version automatically).

### Path B — Pin the real baseline exactly (recommended for reproducibility)

**Action**: change the devDependency to the exact published version that the resolver would pick anyway:

```json
"devDependencies": { "@deepseek-ai/dsh-llm": "0.1.2-alpha.2" }
```

- **Consequence**: `npm install` installs exactly `0.1.2-alpha.2`; no silent substitution; README claim becomes
  literally true. Exact prerelease pins fail loudly (ETARGET) if that version is unpublished later, which is the
  correct signal for a type baseline.
- **Tradeoff**: manual bumps for every baseline move; no automatic pickup of `0.1.2` stable.
- **Exit path**: relax to `^0.1.2` (or `~0.1.2`) once the stable `0.1.2` is published, restoring caret semantics
  without the nonexistent-prerelease trap.

### Path C — Downgrade to the published 0.1.1 line

**Action**: pin `"0.1.1-rc.2"` (an exact pin is required — `^0.1.1-rc.2` would not match `0.1.2-alpha.2` anyway,
and rc.2 is the newest 0.1.1 prerelease).

- **Tradeoff**: only sensible if the plugin's code compiles against the 0.1.1 type surface; a downgrade below the
  declared baseline risks type errors against APIs introduced in 0.1.2. Highest risk of the three.
- **Exit path**: upgrade to Path B as soon as 0.1.2-line compatibility is confirmed.

### Path D — Escalate upstream (no manifest change yet)

**Action**: file an issue with `@deepseek-ai/dsh-llm` maintainers asking either to publish `0.1.2-alpha.1`
(retroactive publish is possible for a never-used version, though unusual) or to confirm `0.1.2-alpha.2` as the
intended baseline; keep Path A's lockfile in the interim.

- **Tradeoff**: correct root-cause fix; slowest. **Exit path**: adopt the maintainer's answer via Path A or B.

### Recommended sequence

1. **Verify** what actually resolves today: `npm view @deepseek-ai/dsh-llm versions` (read-only; not run here —
   **unconfirmed** per the closed-book constraint).
2. Adopt **Path B** (exact `0.1.2-alpha.2` pin) + README wording fix, keeping a lockfile.
3. Relax to a caret on the stable `0.1.2` when it publishes; remove the pin.

---

## 3. Summary

- `npm install` does **not** fail: `^0.1.2-alpha.1` is satisfied by `0.1.2-alpha.2`, which is what gets installed.
- The bug class is a **silent baseline substitution**: the declared version never existed, so the README's "npm install
  gives you the type baseline" is true only by accident of the resolver picking alpha.2.
- Fix of choice: pin the real published version (`0.1.2-alpha.2`), fix the README, keep a lockfile, and relax to a
  stable caret once `0.1.2` ships. Registry facts and the alpha.1→alpha.2 type delta remain **unconfirmed** under the
  closed-book constraint.
