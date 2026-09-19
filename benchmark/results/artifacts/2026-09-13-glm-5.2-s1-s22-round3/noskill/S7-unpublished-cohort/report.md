# S7 · Unpublished Cohort Install Plan (Read-Only Report)

Task: analyze, read-only, the fixture plugin at `benchmark/tasks/S7-unpublished-cohort/environment/fixture` whose `package.json` declares `devDependencies: { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }` while its README claims "npm install gives you the type baseline". npm reality (per the brief): `@deepseek-ai/*` has only 0.1.1-rc.1, 0.1.1-rc.2, and 0.1.2-alpha.2 published — 0.1.2-alpha.1 was never published. No install was executed; the fixture was not modified.

## 1. Real consequence of `^0.1.2-alpha.1`

**Install will NOT fail.** Semver caret semantics on a prerelease base:

- `^0.1.2-alpha.1` desugars to `>=0.1.2-alpha.1 <0.1.3-0` (for 0.x ranges the upper bound is the next patch bump, i.e. `0.1.3`; the ` -0` suffix excludes `0.1.3-0`-style prereleases of the boundary).
- npm's prerelease-matching rule: a prerelease version can only satisfy a comparator range if at least one comparator with the same `[major, minor, patch]` tuple has a prerelease. Here the tuple is `0.1.2`, so **prereleases of exactly 0.1.2 may match; prereleases of other tuples (0.1.1-rc.x) cannot**.
- Checking each published version:
  - `0.1.1-rc.1`, `0.1.1-rc.2`: wrong tuple `0.1.1` and lower than the lower bound → excluded.
  - `0.1.2-alpha.2`: same tuple, and `0.1.2-alpha.2 > 0.1.2-alpha.1` (prerelease identifiers compare numerically/alphabetically: `2` > `1`) → **satisfies the range**.
  - A hypothetical final `0.1.2` would also satisfy (release > any prerelease of the same version) and win as newer, but per the brief it is not published.

**Therefore `npm install` (or `pnpm install`) will silently install `@deepseek-ai/dsh-llm@0.1.2-alpha.2`.** The failure mode is not a hard error but a silent one-version drift from what the declaration literally names: the pin-looking `alpha.1` in the manifest is not what lands in `node_modules` or the lockfile. Consequences:

- The "type baseline" is whatever `alpha.2` ships, which may differ from `alpha.1` API/type surface (unconfirmed — the fixture contains no source that consumes the types, and alpha.1 was never published so its contents cannot be compared).
- CI reproducibility is still achieved via the lockfile (which will record `0.1.2-alpha.2`), so builds are stable — just not on the version the author believed they declared.
- If npm ever publishes `0.1.2-alpha.3`, `0.1.2-beta.1`, or final `0.1.2`, fresh unlocked installs jump again; only the lockfile pins.

Note on lockfile edge: on a registry where literally nothing in the range existed, npm would fail with `ETARGET` "No matching version found". That is not this case, but it is the failure the README's wording implicitly assumes ("install gives you the type baseline") — the assumption is only accidentally true because alpha.2 happens to exist.

## 2. Installation / type-baseline plan (paths, tradeoffs, exits)

**Path A — accept alpha.2 (zero-change, recommended default).**
Run `npm install` (in a copy, not the fixture); let the range resolve to `0.1.2-alpha.2`; commit the resulting lockfile as the baseline.
- Tradeoff: no fixture edits needed; drift is documented and locked.
- Exit: if `alpha.2` turns out to break the plugin's types, move to B or C.

**Path B — pin the exact version that actually resolved.**
Change the declaration to the exact `"0.1.2-alpha.2"` (or keep the range and rely on `npm install --save-exact` / lockfile-only updates).
- Tradeoff: manifest now tells the truth about what is installed; no silent future jumps within 0.1.2 prereleases.
- Exit: requires a fixture/package edit — **not permitted in this read-only task**; it is the follow-up recommendation for the maintainer.

**Path C — deliberately downgrade to the 0.1.1-rc.x cohort.**
`0.1.1-rc.1/rc.2` can never satisfy `^0.1.2-alpha.1`; selecting one requires changing the range (e.g. `^0.1.1-rc.2` or exact `0.1.1-rc.2`).
- Tradeoff: only sensible if the plugin's code was actually written against the rc API surface (unconfirmed — no consuming source in the fixture). Same edit restriction as B.

**Path D — local/vendored type baseline (no registry dependency).**
If the registry versions are all unsuitable and installs must not reach the network: alias a local tarball/directory, e.g. `"@deepseek-ai/dsh-llm": "file:../vendor/dsh-llm-0.1.2-alpha.2.tgz"`, or use `overrides`/`pnpm.overrides` to force a version.
- Tradeoff: fully reproducible offline; but this fabricates a baseline that may diverge from any published artifact and complicates upstream upgrades. Mark any such artifact "unconfirmed" relative to real alpha.1 content.

**Verification steps after any install (read-only checks):**
1. `npm ls @deepseek-ai/dsh-llm` (or inspect the lockfile) — confirm which version actually landed.
2. `node -e "console.log(require('./node_modules/@deepseek-ai/dsh-llm/package.json').version)"`.
3. Type-check the plugin against the installed `lib/types` (e.g. `tsc --noEmit`) to confirm the baseline is usable.

## 3. Unconfirmed items

- The actual npm registry state (existence of exactly 0.1.1-rc.1/rc.2 and 0.1.2-alpha.2, absence of 0.1.2-alpha.1 and of any final 0.1.2) is taken from the task brief; no network/registry query was performed (**unconfirmed by direct observation**).
- Whether `0.1.2-alpha.2`'s exported types differ from what `alpha.1` would have shipped (**unconfirmed** — alpha.1 never existed, so there is nothing to compare).
- Whether the plugin's source compiles against `alpha.2` at all (**unconfirmed** — the fixture contains only `package.json` and `README.md`, no TypeScript source that imports `@deepseek-ai/dsh-llm`).
- Which package manager and lockfile format the maintainer uses (**unconfirmed**; npm assumed from README wording).

## Constraint compliance

- Fixture directory untouched (read-only reads of `package.json` and `README.md` only).
- No install, build, dependency download, or registry access performed.
- No modification to skill/verifier/reference solutions; no git operations; no external services.
