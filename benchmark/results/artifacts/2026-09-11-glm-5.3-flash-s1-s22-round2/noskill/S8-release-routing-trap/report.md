# S8 · Release Routing Trap — Diagnostic Report

Evidence base (read-only fixture): `README.md`, `compat-table.md`, `dsh-version.txt`, `ls-remote-tags.txt`, `sync-script.sh`.

## 1. Attempt-1 root cause: tag `#v0.9.5` never existed on the mirror

The consumer's command was correct; the tag is absent from the public mirror:

- `ls-remote-tags.txt` lists the mirror's tags: `...`, `v0.9.0`, `v0.9.1`, `v0.9.7`. The sequence jumps **from v0.9.1 straight to v0.9.7** — tags `v0.9.2` through `v0.9.6` (including the README-pinned `v0.9.5`) were never pushed to the mirror.
- The release tooling explains why: `sync-script.sh` runs, per mirror, only
  `git push --force-with-lease "$remote" HEAD:main`
  — it pushes the **branch head only and never pushes tags**. Any release done by tagging (e.g. `v0.9.5`) therefore never propagates to the mirrors; `v0.9.7` reaching the mirror is inconsistent residue (pushed manually or by an earlier script revision), not evidence the script handles tags.
- Conclusion: a **tag-distribution defect in release tooling** (tags not part of mirror sync), not a consumer network or command problem. pnpm failed immediately because the git ref `#v0.9.5` does not resolve on `public-org/dsh-ui-progress`.

## 2. Attempt-2 root cause: `v0.9.7` targets a newer DSH than the consumer runs

- Consumer runtime (`dsh-version.txt`): `dsh --version` → **0.1.1-rc.2**.
- Compat table (`compat-table.md`): **v0.9.7 ↔ dsh-v0.1.2-alpha.1**, noted as "Migrated to the alpha.1 client API (views/legacy projection + useConversation seat)".
- The compatibility direction is **forward-only**: plugin v0.9.7 requires the newer client API of DSH 0.1.2-alpha.1, while the consumer's 0.1.1-rc.2 predates it. Installing v0.9.7 routes the consumer to the alpha.1-targeted build on an rc.2 runtime; the slot entry then calls the alpha.1-only API seat and crashes in the browser with `TypeError: useConversation is not a function`. Restarting dsh cannot help — it is a version-routing mismatch, not a transient state: the plugin must not be routed to a DSH newer than the runtime.
- Note `compat-table.md` itself documents that **v0.9.3 ↔ npm @deepseek-ai/dsh@0.1.1-rc.1**, and rc.2 is "rc.1 + image preprocessing (additive)" — i.e. the pre-alpha line is compatible with the consumer's runtime, but `v0.9.3`'s tag is (per §1) not on the mirror either.

## 3. Remedy for the consumer right now (no runtime upgrade)

Pin the newest tag that **both exists on the mirror** and **predates the alpha.1 client-API migration**:

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.1'
```

- `v0.9.1` is the latest tag actually present on the mirror below the v0.9.7 alpha.1 cut, so it installs (attempt-1 failure avoided) and targets the rc-era client API (attempt-2 failure avoided).
- Caveat to flag to the consumer: `compat-table.md` does not list a row for v0.9.1; the maintainer should confirm/add it. Once the maintainer re-pushes the missing tags (§4), the better-supported pin is `#v0.9.3` (compat row: DSH 0.1.1-rc.1, rc.2 additive-safe).
- Do **not** use the README default `#v0.9.7` on this runtime; it requires dsh 0.1.2-alpha.1.

## 4. Maintainer-side fix so both defects cannot recur

Release tooling:

1. **Push tags in the mirror sync.** In `sync-script.sh`, add tag propagation next to the branch push, e.g.
   `git push --force-with-lease "$remote" HEAD:main` **plus** `git push "$remote" --tags` (or `git push --follow-tags "$remote" HEAD:main` if only annotated release tags are wanted). This eliminates the v0.9.2–v0.9.6 class of "released here, absent on the mirror" gaps.
2. **Add a post-sync verification gate**: after each mirror sync, run `git ls-remote --tags <mirror>` and assert every tag reachable from the pushed HEAD exists on the mirror; fail the release loudly on any gap (fail-loud misconfiguration/distribution rather than silent drift).

Docs:

3. **Correct the README install pin to a tag that exists and matches a compat-table row.** Today the default `#v0.9.5` fails outright and the updated `#v0.9.7` crashes on pre-alpha.1 runtimes. Publish a matrix of install commands per DSH line (rc.x users → `#v0.9.3` once tags are pushed; 0.1.2-alpha.1 users → `#v0.9.7`), or have the install docs state the minimum DSH version prominently.
4. **Complete the compat table**: add rows for every published tag (at minimum v0.9.1) so consumers can always pick a safe pin from the table, and note the forward-only direction (a plugin built for DSH X will not run on DSH < X — the useConversation crash is the symptom).
