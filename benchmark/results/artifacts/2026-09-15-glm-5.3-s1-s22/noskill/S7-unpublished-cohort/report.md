# S7 · Unpublished Cohort — Installation / Type-Baseline Plan (Read-Only Report)

Fixture: `dsh-cohort-bench@0.1.0` (private), declaring `devDependencies: { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`; README claims "npm install gives you the type baseline". Per the brief, the npm registry for `@deepseek-ai/*` contains only `0.1.1-rc.1`, `0.1.1-rc.2`, and `0.1.2-alpha.2` — `0.1.2-alpha.1` was never published. No install was run; nothing under the fixture was modified (registry state is taken from the brief; **unconfirmed** by direct query — closed-book).

## 1. Real consequence of `^0.1.2-alpha.1`

### 1.1 Semver mechanics of the caret range with a prerelease lower bound

- For `0.x.y` versions, `^0.1.2` behaves like `>=0.1.2 <0.2.0` (caret on 0.x allows only patch-level drift within the same minor: `0.1.x` with `x >= 2`).
- npm's prerelease-range rule: a comparator with a prerelease tag (here `0.1.2-alpha.1`) admits other **prerelease** versions only when they share the same `(major, minor, patch)` tuple — i.e. `0.1.2-alpha.2`, `0.1.2-beta.1`, etc. — and their prerelease identifier sorts **greater than or equal to** `alpha.1`.
- Release (non-prerelease) versions in the range `0.1.2 … 0.1.x` also satisfy it (a plain release outranks any prerelease of the same tuple).

### 1.2 Will install fail? — **No**

`npm install` will **not** fail with ENOTFOUND/ETARGET, because `0.1.2-alpha.2` satisfies `^0.1.2-alpha.1`:

- `0.1.2-alpha.2`: same tuple (0.1.2), `alpha.2 > alpha.1` → **matches** (this is what gets installed).
- `0.1.1-rc.1` / `0.1.1-rc.2`: different tuple (0.1.1) and below the range floor → correctly excluded.

So the range is *satisfiable* even though its exact lower bound was never published. The failure mode is **not** install failure but **silent baseline drift**: the README's promise "npm install gives you the type baseline" is only true if the types the plugin was developed against are byte-identical in `alpha.2`. The resolved baseline is `0.1.2-alpha.2`, not `0.1.2-alpha.1`.

### 1.3 Consequences for the type baseline

- `@deepseek-ai/dsh-llm` is a devDependency, so its exported types flow into `tsc` typechecking of this plugin. Whatever `alpha.2` exports *is* the de-facto baseline.
- Additional drift risk: the caret range leaves the door open to any future `0.1.2-*` prerelease published later (`alpha.3`, `beta.0`, `0.1.2` final). A fresh install on another machine or in CI after such a publication silently changes the baseline. Unpinned prerelease ranges make builds non-reproducible across time.
- Nothing in the fixture (only `package.json` + README, no lockfile, no tsconfig, no source) pins or verifies the types, so today there is no guard at all. *(No lockfile present in the fixture — confirmed by inspection.)*

## 2. Installation / type-baseline plan (paths, tradeoffs, exit paths)

### Path A — Accept `0.1.2-alpha.2` as the baseline (minimal change, recommended first step)

1. Run `npm install` (or `pnpm install` if the workspace uses pnpm — **unconfirmed** which package manager the maintainer intends; the fixture gives no `packageManager` field or lockfile).
2. Record the resolved version (`npm ls @deepseek-ai/dsh-llm`) and verify the plugin typechecks against `alpha.2`'s `.d.ts` (`tsc --noEmit`).
3. Commit a lockfile so the baseline is reproducible.

- **Tradeoff:** zero friction; baseline becomes whatever `alpha.2` ships. If types changed between the never-published `alpha.1` and `alpha.2`, compile errors surface here (which is exactly what you want to learn).
- **Exit path:** if typecheck fails against `alpha.2`, move to Path B or C; the diff between the two tarballs' `types`/`lib/*.d.ts` tells you what drifted.

### Path B — Pin the exact published version (reproducibility-first)

Change the declaration to `"@deepseek-ai/dsh-llm": "0.1.2-alpha.2"` (exact, no caret), or keep the caret plus a lockfile.

- **Tradeoff:** exact pin gives bit-reproducible installs and an honest README ("type baseline = 0.1.2-alpha.2"); you lose automatic pickup of fixes. Prerelease pins should be considered disposable anyway.
- **Exit path:** when `0.1.2` stable is published, switch to `^0.1.2` (stable range, no prerelease semantics) and update the lockfile.

### Path C — Recover the intended `alpha.1` baseline locally (fidelity-first)

If the plugin genuinely depends on `alpha.1`-era types:

1. Obtain the `alpha.1` tarball/source — e.g. the maintainer's local build of the `dsh-llm` workspace at the `alpha.1` tag/commit (**unconfirmed** whether such a tag exists; the registry does not have it per the brief).
2. Install it without publishing: `file:` dependency, `npm link`, or a pnpm workspace override pointing at the local path.
3. Typecheck against it, then re-run against `alpha.2` to enumerate the drift.

- **Tradeoff:** most faithful to the original baseline, but it is a local, unpublished artifact — every collaborator/CI needs the same local copy or the setup breaks; it also reintroduces "phantom dependency on an unpublished version".
- **Exit path:** once drift is understood, converge on Path A or B and delete the local override.

### Path D — Defer to a published stable baseline (process-first)

Treat the cohort's `0.1.2-alpha.1` gap as a publishing-process bug: file it upstream, wait for `0.1.2` (stable) or `0.1.2-alpha.3` to be published, and only then baseline.

- **Tradeoff:** cleanest long-term answer; blocks work now. Suitable only if the plugin has no immediate consumers.
- **Exit path:** switch the range to `^0.1.2` (stable) as soon as it exists.

### Cross-path recommendation

Do A immediately (it works today), harden with B (lockfile and/or exact pin), use C only if typecheck reveals drift you must attribute precisely, and keep D as the upstream tracking item. Also fix the README wording: "npm install gives you the type baseline" should name the concrete resolved version, because the declared `alpha.1` is unpublishable-by-definition absent and never what install resolves.

## 3. Unconfirmed items

- Registry contents (`0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2`) are taken from the task brief; no network query was performed (closed-book rule) — **unconfirmed by direct observation**.
- Which package manager is intended (no lockfile/`packageManager` field in the fixture) — **unconfirmed**.
- Whether `0.1.2-alpha.1`'s types differ from `0.1.2-alpha.2`'s (no source or tarball available to diff) — **unconfirmed**; Path A step 2 is the check.
- Whether an `alpha.1` git tag/source snapshot exists locally for Path C — **unconfirmed**.
- No `tsconfig.json` or source files exist in the fixture, so the plugin's actual type surface cannot be exercised read-only — **unconfirmed** how much of `dsh-llm`'s API it consumes.

## 4. Fixture integrity

Read-only honored: only the two fixture files were read; no file under the fixture (or anywhere in the benchmark repository) was created, modified, deleted, or renamed; no install was executed. Sole output is this report in the designated output directory.
