# S7 · Unpublished Cohort — Installation / Type-Baseline Plan (Read-Only Report)

Task: analyze `dsh-cohort-bench` (fixture, read-only) whose `package.json` declares
`devDependencies: { "@deepseek-ai/dsh-llm": "^0.1.2-alpha.1" }` while its README claims
"npm install gives you the type baseline". Published npm reality for `@deepseek-ai/*`:
only `0.1.1-rc.1`, `0.1.1-rc.2`, `0.1.2-alpha.2` — **0.1.2-alpha.1 was never published**.
No install was run; nothing under the fixture was modified.

## 1. Real consequence of the declaration

### Semver semantics of `^0.1.2-alpha.1`

- For `0.x.y` versions the caret range keeps the minor: `^0.1.2-alpha.1` means
  `>=0.1.2-alpha.1 <0.2.0`.
- npm's prerelease rule: a prerelease tag only satisfies a range if the comparator's
  \`[major, minor, patch]\` tuple matches. So prereleases of `0.1.2\` (like
  `0.1.2-alpha.2\`) can match; prereleases of other tuples (`0.1.1-rc.*\`) cannot.

### Will install fail?

**No.** `npm install` will not fail and will not fall back to `0.1.1-rc.*\`.
Resolution picks the highest version satisfying the range, i.e.
**`@deepseek-ai/dsh-llm@0.1.2-alpha.2`** — a version that was never named in the
declaration. So the failure mode is not an error; it is a **silent baseline drift**:
the README's "npm install gives you the type baseline" is only accidentally true, and
the maintainer never reviewed the version actually installed.

Consequences:

- Type-checking against alpha.2 is a *different, unreviewed* contract than the declared
  alpha.1. If alpha.1→alpha.2 changed exported types (likely for adjacent prereleases,
  but **unconfirmed** — alpha.1 does not exist anywhere and cannot be inspected),
  compile errors or, worse, silently accepted drift appear only on other machines.
- Non-determinism risk: if `0.1.2-beta.1` or `0.1.2-alpha.3` were later published, a
  fresh `npm install` would pick the new version with no local change — the "type
  baseline" is whatever npm's registry happened to have that day.
- `0.1.1-rc.1/rc.2` are unreachable from this range under either reading; they matter
  only as the only other published cohort members.

### Verified vs unconfirmed

- Verified from the fixture: the declaration, the README claim, `"private": true`.
- Given by the brief (registry state, alpha.1 never published): treated as ground truth
  for this closed-book task.
- **Unconfirmed:** the API/type surface of `0.1.2-alpha.1` (unpublishable to inspect),
  the diff between alpha.1 and alpha.2, whether alpha.2 was cut from the same commit
  lineage as intended alpha.1, and whether a `package-lock.json` exists anywhere
  (none in the fixture).

## 2. Installation / type-baseline plan

All paths are plans only; nothing was executed.

### Path A — Pin to the published cohort member (recommended default)

- Change `devDependencies` to the exact published version: `"@deepseek-ai/dsh-llm": "0.1.2-alpha.2"` (no caret), commit a `package-lock.json`.
- **Tradeoff:** deterministic, honest baseline; loses nothing real since alpha.1 never
  existed. **Exit path:** when a stable `0.1.2` (or later) ships, repin deliberately.

### Path B — Keep the range, lock the resolution

- Leave `^0.1.2-alpha.1` but add/commit `package-lock.json` so CI and contributors
  resolve `0.1.2-alpha.2` reproducibly.
- **Tradeoff:** declaration still names a nonexistent version (misleading archaeology;
  ranges can drift again on fresh lockfile regeneration). **Exit path:** any
  `npm update` reopens the drift; migrate to Path A when convenient.

### Path C — Vendored/workspace type baseline

- Copy the intended type surface (from the harness checkout's `packages/llm/dsh-llm`
  sources, or a `file:`/workspace dependency) as the baseline, decoupling the plugin
  from the npm cohort entirely.
- **Tradeoff:** full determinism and access to the "alpha.1-era" intent; cost is
  maintaining the vendored copy and losing registry updates. **Exit path:** swap back
  to a pinned registry version once `0.1.2` stable exists.

### Path D — Downgrade to the rc cohort

- Pin `0.1.1-rc.2` if the plugin's code actually compiles against the older rc API.
- **Tradeoff:** only viable if the code predates the 0.1.2 line (unconfirmed);
  otherwise introduces real type errors. Treat as last resort.

### Recommended sequence

1. `npm view @deepseek-ai/dsh-llm versions` to re-confirm the published set (not run
   here — read-only, closed-book).
2. `npm install` once with Path A pinning; record the resolved version in the README
   ("type baseline = 0.1.2-alpha.2") so the claim stops being implicit.
3. Type-check; any errors are alpha.1→alpha.2 drift — fix against alpha.2's real API
   rather than guessing at alpha.1.
4. Commit lockfile; CI installs with `npm ci`.

## 3. Honesty notes / blockers

- Nothing under the fixture was modified; no install, build, or registry access was
  performed (task rules).
- The single unresolvable unknown is the intended `0.1.2-alpha.1` type surface; every
  statement about it above is marked unconfirmed. All other analysis follows from
  standard npm semver prerelease resolution semantics.
