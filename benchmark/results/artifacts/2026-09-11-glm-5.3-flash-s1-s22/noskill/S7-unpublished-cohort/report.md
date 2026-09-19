# S7 · Unpublished Cohort — Installation / Type-Baseline Diagnostic Report

Fixture inspected (read-only, nothing executed, nothing modified):
- `fixture/package.json` — `"name": "dsh-cohort-bench"`, `"version": "0.1.0"`, `"private": true`, `"devDependencies": { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }`
- `fixture/README.md` — states the plugin declares `@deepseek-ai/dsh-llm: ^0.1.2-alpha.1` while the README claims "npm install gives you the type baseline"; npm reality is only `0.1.1-rc.1 / 0.1.1-rc.2 / 0.1.2-alpha.2`, and **alpha.1 was never published**.

Published-version context is taken from the brief and fixture README (closed-book: no network or registry query was performed — see section 3, "Unconfirmed").

---

## 1. Real consequence of the declaration

### 1.1 Will the install actually fail? — No.

The instinctive reading ("the exact version named in the range was never published, so install fails") is wrong. npm resolves a **range**, not a literal version. Under standard semver caret semantics applied to a prerelease base:

- `^0.1.2-alpha.1` expands to `>=0.1.2-alpha.1 <0.2.0` (caret on `0.x.y` pins the leftmost non-zero component, here the **minor**: `0.1`).
- npm's prerelease rule: a version with a prerelease tag satisfies a range only if at least one comparator in the range has the **same `[major, minor, patch]` tuple and a prerelease**. The lower bound comparator here is `0.1.2-alpha.1` — tuple `(0,1,2)` with a prerelease — so the "prerelease gate" is **open** for that tuple.
- `0.1.2-alpha.2` (published, per the brief) satisfies both conditions: `0.1.2-alpha.2 >= 0.1.2-alpha.1` (prerelease identifiers compare lexically/numerically: `alpha.2 > alpha.1`) and `0.1.2-alpha.2 < 0.2.0`.

### 1.2 Which version will actually be installed?

`@deepseek-ai/dsh-llm@0.1.2-alpha.2` — the only published version inside the range.

Why the other published versions do not match:
- `0.1.1-rc.1` and `0.1.1-rc.2`: `0.1.1.x < 0.1.2-alpha.1`, below the range floor. (Excluded twice over: even ignoring ordering, their tuple `(0,1,1)` has no prerelease comparator in the range.)
- No `0.1.2` stable exists per the brief, so npm cannot "upgrade out" of the prerelease tuple.

### 1.3 Subtle consequences worth noting

1. **Silent lock to the alpha line.** The declaration looks like "alpha.1" but installs "alpha.2". A maintainer reading the manifest and the README will expect a different version than what the lockfile records — a documentation/reality drift already present in the fixture.
2. **Future drift in both directions.** If `0.1.3-beta.0` were ever published, it would **not** satisfy the range (different tuple, no matching prerelease comparator). But `0.1.2-alpha.3` or a `0.1.2` stable would, and would be auto-selected on any fresh resolve. The pin is less pinned than it looks, and more pinned where it looks loose.
3. **The README's claim is half-true.** "npm install gives you the type baseline" does succeed — but it yields an **alpha.2 baseline, not the alpha.1 baseline the README narrative implies**. If alpha.1→alpha.2 changed any types, the documented baseline and the installed baseline diverge. That is the real defect: not install failure, but an unverifiable type contract.
4. **`private: true`** (confirmed in `fixture/package.json`) prevents accidental publication of the fixture itself; it does not affect dependency resolution.

---

## 2. Workable installation / type-baseline plans

All paths are **plans only — nothing was executed** (per brief). Ordered by preference.

### Path A — Accept and pin the reality: declare `0.1.2-alpha.2` explicitly (recommended)

- Change the declaration to `"@deepseek-ai/dsh-llm": "0.1.2-alpha.2"` (exact pin, no caret), commit the resulting lockfile.
- **Why**: makes the manifest say what actually installs, removes silent prerelease drift, and makes the README's "type baseline" claim verifiable — the baseline *is* alpha.2, stated in writing.
- **Tradeoff**: you are consciously on an alpha line; you must move again when a stable or blessed RC appears.
- **Exit path**: when `0.1.2` stable (or a later RC the team blesses) is published, bump the exact pin in one small PR; the lockfile diff is the entire migration.

### Path B — Re-anchor to the last non-alpha line: exact `0.1.1-rc.2`

- Declare `"@deepseek-ai/dsh-llm": "0.1.1-rc.2"` (exact) and commit the lockfile.
- **Why**: RC builds are usually closer to stable intent than alphas; if the plugin only needs the 0.1.1-rc type surface, this is the most defensible baseline.
- **Tradeoff / verification gate (unconfirmed)**: whether alpha.2 contains type changes the plugin code actually requires **cannot be verified offline** — no source or `*.d.ts` of any version is present in the fixture and no install was run. If alpha.2 added types the plugin uses, this path fails at typecheck, which is itself a cheap, safe detector.
- **Exit path**: if typecheck fails, fall back to Path A; the failing typecheck output names exactly which symbols are missing from rc.2.

### Path C — Keep the caret, raise the floor to a published anchor: `^0.1.2-alpha.2`

- Behavior: same open prerelease gate on tuple `(0,1,2)`, floor moved to the actually-published version; still resolves to alpha.2 today.
- **Tradeoff**: still permits `0.1.2-alpha.3+` silently on fresh resolves — keeps the drift problem, only moves the floor. Choose only if the team wants auto-pickup of later alphas.
- **Exit path**: superseded by Path A whenever a stable appears; no additional work.

### Path D — Vendored / local type shim (last resort)

- If the needed type baseline exists **only** in the unpublished alpha.1 and neither alpha.2 nor rc.2 is acceptable (*unconfirmed, cannot be verified offline*): vendor the required type declarations locally (a local `types/` shim, or a `file:`-scoped local copy of the alpha.1 declarations if the team possesses them).
- **Tradeoff**: hand-maintained types rot; repo policy prefers maintained dependencies over hand-rolling. Use only as a bridge.
- **Exit path**: delete the shim the moment any published version carries the needed types; typecheck is the trigger.

### Cross-cutting recommendations

- Whatever path is chosen, **commit the lockfile** so every install is reproducible and the README claim becomes checkable against it.
- **Fix the README** to name the concrete baseline version (e.g. "npm install resolves @deepseek-ai/dsh-llm 0.1.2-alpha.2 as the type baseline"). The current sentence is the root cause of the maintainer confusion.
- Add a lightweight CI assertion (`npm view @deepseek-ai/dsh-llm versions` in a networked job, or simply lockfile-resolve verification) so a future "declared-but-unpublished" floor fails loudly instead of drifting silently.

---

## 3. Unconfirmed items

Marked explicitly per the brief's closed-book rules; none of the below was verifiable from the fixture:

1. **The exact published-version list** (`0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2`) is taken from the brief and `fixture/README.md`, not queried from the npm registry (no network permitted). **Unconfirmed (registry state).**
2. **That alpha.1 was never published** — likewise from the brief/README only. Consistent with the range analysis (the analysis holds whether or not alpha.1 exists, since alpha.2 outranks it), but the publication fact itself is **unconfirmed**.
3. **Type-level differences between 0.1.1-rc.2, 0.1.2-alpha.1, and 0.1.2-alpha.2** — no tarballs or `.d.ts` files exist in the fixture and no install was run. Whether Path B would typecheck is **unconfirmed**; the typecheck itself is the proposed detector.
4. **The consumer package manager's exact prerelease semantics** (npm vs pnpm vs yarn). The analysis follows standard node-semver (npm) rules, which pnpm and yarn use by default; exotic settings (`legacy-peer-deps`, custom resolution modes) were not observable from the fixture. **Unconfirmed (toolchain settings).**
5. **Whether `0.1.2` stable exists or is imminent** — no information available; affects only the timing of the Path A exit.

## Verdict

The declaration `^0.1.2-alpha.1` **does not fail to install**: it silently resolves to `@deepseek-ai/dsh-llm@0.1.2-alpha.2`. The genuine problem is that the README's "type baseline" claim is fiction at the version level. Recommended plan: **Path A** (exact-pin `0.1.2-alpha.2`, commit the lockfile, rewrite the README claim), with **Path B** (exact `0.1.1-rc.2`) as fallback if a typecheck proves alpha.2 unnecessary.
