# S8 · Release Routing Trap — Diagnosis Report

**Task type:** Mode A · inspect (read-only release-engineering diagnosis)
**Fixture:** `benchmark/tasks/S8-release-routing-trap/environment/fixture/` (read-only, unchanged)
**Skill:** plugin-upgrade (references consulted: SKILL.md corridor rules; v0.1.1-rc.1 / v0.1.2-alpha.1 card summaries)

## Evidence summary

| Artifact | Key fact |
|---|---|
| `ls-remote-tags.txt` (mirror `public-org/dsh-ui-progress`) | Tags ascend `v0.9.0, v0.9.1, …` then jump straight to `v0.9.7`. **`v0.9.5` is absent** from the mirror, as are v0.9.2–v0.9.6. |
| `sync-script.sh` | The post-release mirror sync pushes only `git push --force-with-lease <remote> HEAD:main` for each of `origin public mirror2`. **It never pushes `refs/tags/*`.** |
| `dsh-version.txt` | Consumer runtime: `dsh 0.1.1-rc.2` (production freeze — cannot upgrade). |
| `compat-table.md` | `v0.9.3` ↔ `dsh@0.1.1-rc.1` (rc.1 real-boot verified; rc.2 noted as additive). `v0.9.7` ↔ `dsh-v0.1.2-alpha.1` ("migrated to the alpha.1 client API — views/legacy projection + **useConversation** seat"). |

## 1. Attempt-1 root cause — why `#v0.9.5` could not resolve

**Release-engineering defect: the mirror sync script distributes only the `main` branch, never tags.** The consumer's install source is the GitHub mirror `github:public-org/dsh-ui-progress#v0.9.5`; pnpm resolves a `#<tag>` Git selector against the refs actually present on that remote. The mirror's tag list (`ls-remote-tags.txt`) contains `v0.9.1` then `v0.9.7` — `v0.9.5` exists (or existed) only on the primary remote and was never replicated, because `sync-script.sh` pushes exclusively `HEAD:main` with no `--tags` / `refs/tags/*` push. The tag `v0.9.7` is present presumably because it was pushed out-of-band (or re-pushed) after the README bump, which is why the failure looked "flaky" but is in fact deterministic per tag.

This is not a network or command error on the consumer's side: any consumer following the README against that mirror at that time would hit the same resolution failure for every tag in the v0.9.2–v0.9.6 gap.

## 2. Attempt-2 root cause — why `v0.9.7` installs but crashes

**Compatibility direction: the newest plugin artifact targets a *newer* DSH than the consumer runs.** Per the compat table, `v0.9.7` was migrated to the **0.1.2-alpha.1 client API** (the rc.2→alpha.1 corridor in the skill's references), which includes the `useConversation` seat. The consumer's runtime is **0.1.1-rc.2**, which predates that API — so the client-side slot entry calls a function that does not exist on that host and throws `TypeError: useConversation is not a function`. Restarting dsh cannot help: the mismatch is between the artifact's compiled client API expectation and the frozen host's exported client runtime, not a stale process.

In short:

- Attempt 1 = **tag distribution defect** (missing tag on the install mirror).
- Attempt 2 = **version routing defect** (README's "newest tag" advice routes a consumer on an older host corridor to an artifact built for a newer corridor).

## 3. Remedy for the consumer (works on frozen runtime 0.1.1-rc.2)

Install the plugin version whose corridor matches the runtime: **`v0.9.3`** — real-boot verified on 0.1.1-rc.1, and rc.2 is documented as additive relative to rc.1, so it is the correct pick for 0.1.1-rc.2. Its tag is present on the mirror:

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

Do **not** stay on `v0.9.7`; no configuration can make an alpha.1-API artifact run on an rc.2 host.

## 4. Maintainer-side fixes (tooling + docs)

**Release tooling — make tag distribution complete and verified:**

1. Change the sync loop to distribute tags as well as the branch, e.g.:
   ```bash
   git push --force-with-lease "$remote" HEAD:main
   git push "$remote" --tags   # or: git push "$remote" 'refs/tags/*:refs/tags/*'
   ```
2. Add a post-sync verification step that, for **each** mirror, runs `git ls-remote --tags <mirror>` and asserts every released tag (and in particular the tag the README currently pins) is present — failing the release if any mirror is missing it. The absence of this check is why v0.9.2–v0.9.6 silently never reached the mirrors.

**Docs / routing:**

3. Stop advising "install the newest tag." Make the README's default install command pin the version resolved from the compatibility matrix, and render the compat table with a per-row install command (e.g. "on dsh 0.1.1-rc.x → `…#v0.9.3`; on dsh 0.1.2-alpha.1+ → `…#v0.9.7`"), so a consumer on a frozen runtime is routed by their DSH version, not by tag recency.
4. Optionally declare a peer/runtime compatibility range for the DSH host in the plugin manifest/package metadata so an incompatible runtime fails loudly at install time (misconfiguration fails loud) rather than as a `TypeError` in the browser.

## Completed / Skipped / Pending

- **Completed:** static evidence read (all five fixture files); both root causes identified and tied to evidence; consumer remedy (`#v0.9.3`) given; maintainer tooling + docs fixes specified.
- **Skipped:** runtime verification, installs, and any repository mutation — read-only task by design (Mode A); fixture untouched.
- **Pending/residual risk:** none identified for the diagnosis; the inferred out-of-band push of `v0.9.7` to the mirror is consistent with, but not directly proven by, the static evidence.
- **Rollback:** not applicable — no writes outside this report.

*Output: `benchmark-runs/glm-5.3-r1/skill/S8-release-routing-trap/report.md` (the designated agent-output location for this run).*
