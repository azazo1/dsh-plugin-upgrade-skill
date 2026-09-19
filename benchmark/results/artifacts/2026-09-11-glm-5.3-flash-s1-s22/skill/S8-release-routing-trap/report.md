# S8 · Release Routing Trap — Diagnostic Report

Mode: A (read-only inspect) per the dsh-plugin-upgrade skill. Evidence source: the static pack under `environment/fixture/` (untouched): `README.md`, `compat-table.md`, `dsh-version.txt`, `ls-remote-tags.txt`, `sync-script.sh`. No installs or migrations were run.

## Consumer constraint

- Consumer runtime: `dsh --version` → **0.1.1-rc.2** (`dsh-version.txt`), frozen; no host upgrade allowed.
- Install command tried: `dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.5'` (README default), then `#v0.9.7`.

## 1. Attempt-1 root cause — `#v0.9.5` cannot resolve: tag-distribution defect

`ls-remote-tags.txt` lists the mirror's full tag set: `v0.1.0, v0.2.0, v0.3.0, v0.4.0, v0.5.0, v0.5.1, v0.6.0, v0.7.0, v0.8.0, v0.9.0, v0.9.1, v0.9.7`.
**There is no `v0.9.5` tag on the remote — and in fact no `v0.9.2`–`v0.9.6` at all.**

The defect is in the release sync script (`sync-script.sh`): after every release it only runs

```bash
git push --force-with-lease "$remote" HEAD:main
```

for each mirror. It pushes the **branch head (`main`)** only and never pushes tag refs (no `git push "$remote" --tags`, no explicit per-tag push). Tags therefore exist only on the maintainer's origin where they were created; the public mirror never receives them. The lone `v0.9.7` in the list is an outlier that was evidently pushed by hand at some point — which also explains why it is the only semver-recent tag the consumer could actually switch to. This is a release-engineering defect in tag distribution, not the consumer's network or command: `#v0.9.5` cannot resolve because the ref does not exist on the mirror the URL points at.

## 2. Attempt-2 root cause — `#v0.9.7` installs but crashes: version-routing defect

`compat-table.md` (the plugin's own README table) states:

| Plugin version | DSH version |
|---|---|
| v0.9.3 | npm @deepseek-ai/dsh@0.1.1-rc.1 (rc.2 = rc.1 + additive image preprocessing) |
| v0.9.7 | dsh-v0.1.2-alpha.1 — "Migrated to the alpha.1 client API (views/legacy projection + **useConversation** seat)" |

The compatibility direction is unambiguous: **v0.9.7 is written forward, against the DSH 0.1.2-alpha.1 client API** — it expects the alpha.1 client surface where the `useConversation` hook seat exists. The consumer's frozen runtime is **0.1.1-rc.2**, which predates that API, so `useConversation` does not exist there. The plugin's slot entry calls it at mount time and the browser throws `TypeError: useConversation is not a function`. Restarting dsh cannot help: this is a static API-era mismatch between the client artifact the plugin shipped and the host's client runtime, not a transient state. "Newest tag" was routed by tag recency, not by DSH-version compatibility — the two failure stages have distinct root causes (missing ref vs. wrong-cohort artifact).

## 3. Exact remedy for the consumer right now

The consumer's compatible cohort per the compat table is the **v0.9.3** line (rc.1-verified; rc.2's image preprocessing is additive, so rc.1-compatible works on rc.2). But — per `ls-remote-tags.txt` — `v0.9.3` is **also absent from the mirror**, so no currently published ref satisfies the consumer. The remedy therefore requires one maintainer action first (no runtime upgrade, honoring the freeze):

1. Maintainer publishes the missing historical tag(s): `git push public v0.9.3` (or `git push public --tags` once the sync script is fixed).
2. Consumer installs the compatible pin:

```sh
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

If publishing tags is delayed, the interim equivalent is pinning the exact commit SHA of the v0.9.3 release commit on `main` (`...@github:public-org/dsh-ui-progress#<sha>`), since `main` is pushed — but the tag pin is the correct, reviewable target. The consumer must **not** stay on v0.9.7; every load will crash until the host reaches 0.1.2-alpha.1.

## 4. Maintainer-side fix so both defects cannot recur

1. **Fix the sync script to distribute tags** — after the branch push, add:
   ```bash
   git push --force-with-lease "$remote" HEAD:main
   git push "$remote" --tags   # or: push each release tag explicitly in the release step
   ```
   Optionally add a post-push verification: `git ls-remote --tags "$remote" | grep -qx "refs/tags/$VERSION"`, failing the release job if the just-cut tag is missing on every mirror. Backfill-push v0.9.2–v0.9.6 now.
2. **Make the README install command compatibility-routed, not recency-routed**:
   - Pin the README default to the tag matching the currently recommended DSH cohort (today, for 0.1.1-rc.x users: `#v0.9.3`), and keep a small table in the README mapping each pinned install command to its DSH version — present `compat-table.md` next to the install instructions instead of leaving them apart.
   - Add a release-checklist step that, for every new plugin tag, records its target DSH version in `compat-table.md` in the same commit; optionally publish per-cohort dist-tags/branches so "newest" and "compatible" are never conflated.
   - Optionally warn at activation when the resolved plugin's declared DSH cohort does not bracket the running host version, so the v0.9.7-on-rc.2 case fails with an attributable message instead of a browser TypeError.
