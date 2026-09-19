# S8 · Release Routing Trap — Diagnostic Report

Scope: read-only analysis of the evidence pack (fixture files `README.md`, `compat-table.md`, `dsh-version.txt`, `ls-remote-tags.txt`, `sync-script.sh`). Nothing in the fixture was modified; no installs or migrations were executed. Report prepared per the plugin-upgrade skill (Mode A · inspect).

## 1. Attempt-1 root cause — why `#v0.9.5` could not resolve

**Defect: the release sync script distributes code but never distributes tags.**

Evidence:

- `ls-remote-tags.txt` (the mirror’s actual tag listing) shows the tag sequence ending in a jump from v0.9.1 straight to v0.9.7:
  ```
  refs/tags/v0.9.0
  refs/tags/v0.9.1
  refs/tags/v0.9.7
  ```
  Tags **v0.9.2 through v0.9.6 are absent**, including the README-recommended `v0.9.5`. A git-source install resolves `#v0.9.5` to a tag ref; with no such ref on the mirror, pnpm fails immediately — exactly attempt 1. This is a distribution defect on the maintainer side, not a consumer network or command problem.
- `sync-script.sh` shows why the tags are missing. The entire push loop is:
  ```bash
  for remote in origin public mirror2; do
    git push --force-with-lease "$remote" HEAD:main
  done
  ```
  It pushes only `HEAD:main`. There is **no `git push --tags` (or any tag refspec)** anywhere in the script. Whatever tags do exist on the mirror arrived via ad-hoc manual pushes (the old run up to v0.9.1, and evidently one manual push of v0.9.7), while the routine release pipeline silently skips tag publication for every release in between.

Conclusion: `v0.9.5` was released on `origin` but never published to the public mirrors because the release tooling has no tag-distribution step; the README’s pinned install command referenced a tag the public mirrors do not carry.

## 2. Attempt-2 root cause — why the newest tag installed but crashes

**Defect: compatibility-direction mismatch — the `v0.9.7` artifact targets a *newer* DSH host than the consumer runs.**

Evidence:

- `dsh-version.txt`: the consumer’s runtime is
  ```
  $ dsh --version
  0.1.1-rc.2
  ```
- `compat-table.md` (from the plugin README) declares:
  ```
  | v0.9.3 | npm @deepseek-ai/dsh@0.1.1-rc.1 | rc.1 real-boot verified; rc.2 is rc.1 + image preprocessing (additive) |
  | v0.9.7 | dsh-v0.1.2-alpha.1 | Migrated to the alpha.1 client API (views/legacy projection + useConversation seat) |
  ```

`v0.9.7` is built against the **DSH 0.1.2-alpha.1 Web Client API**, where `useConversation` exists as a client seat. The consumer’s host is **0.1.1-rc.2**, one full cohort earlier; that API (the alpha.1 client migration: views/legacy projection + the `useConversation` seat) does not exist there. Hence the install succeeds — `v0.9.7` *is* a real tag on the mirror — but the plugin’s slot entry crashes in the browser with `TypeError: useConversation is not a function`: the hook is simply absent from the rc.2 client runtime. Restarting dsh cannot help; this is a static API-cohort mismatch, not a stale process or cache. A successful dependency installation does not mean compatibility — the resolved cohort must match the host.

Compatibility direction: **plugin v0.9.7 → host 0.1.2-alpha.1** (forward-looking), while the consumer needs a plugin targeting **host 0.1.1-rc.x** (backward). The maintainer bumped the README to "the newest tag" without consulting the compat table, routing the consumer to an artifact for a host cohort they cannot run (production freeze).

## 3. Exact remedy for the consumer right now (works on the frozen runtime)

Target the plugin version whose declared host row covers the consumer’s runtime:

- Per `compat-table.md`, **plugin v0.9.3 ↔ DSH 0.1.1-rc.1**, and the table itself states `rc.2 is rc.1 + image preprocessing (additive)` — i.e. v0.9.3 is compatible with the consumer’s 0.1.1-rc.2 host. `v0.9.7` is ruled out (targets 0.1.2-alpha.1); no other tag has a compat row.

One blocker remains: **v0.9.3 is also missing from the public mirrors** (item 1 — tags v0.9.2–v0.9.6 were never pushed). The consumer cannot fetch a ref that does not exist, so the fix has two steps:

1. **Maintainer, one-time tag backfill** (from the origin checkout):
   ```bash
   git push public refs/tags/v0.9.3
   git push mirror2 refs/tags/v0.9.3
   ```
2. **Consumer install command** (their current runtime, no DSH upgrade needed):
   ```
   dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
   ```

If the maintainer cannot push the tag promptly, the only consumer-side substitute is pinning the exact v0.9.3 **commit SHA** (`@github:public-org/dsh-ui-progress#<sha>`); branch `main` content is not guaranteed to be the v0.9.3 state, so a SHA pin requires first confirming on `origin` which commit carries the v0.9.3 tag. Pinning `main` or staying on `v0.9.7` is not acceptable: both risk shipping alpha.1-API code to an rc.2 host.

## 4. Maintainer-side fix so both defects cannot recur

**Release tooling (fixes defect 1 — tag distribution):**

- Add tag publication to `sync-script.sh` so every release pushes its annotated tag to every mirror, e.g. inside the loop:
  ```bash
  git push --force-with-lease "$remote" HEAD:main
  git push "$remote" "refs/tags/v$VERSION"   # the release tag, explicit refspec
  ```
  (Push the specific release tag, not a blanket `--tags`, and never force-push tags.)
- Add a release gate that fails the release when a required ref is absent from a mirror: after the sync loop, run `git ls-remote --tags <mirror>` for each remote and assert `refs/tags/v$VERSION` is listed. This converts "tag silently missing" into a loud release failure instead of a silent skip.

**Compatibility routing + docs (fixes defect 2 — version routing):**

- Make `compat-table.md` the single routing authority: the README’s default install command must pin the newest tag whose host row covers a *currently supported* DSH cohort, and each release must add the table row for its plugin version (the plugin release version and the DSH host corridor are independent coordinates — never derive one from the other).
- Add a release gate that cross-checks the pushed tag against the table: refuse to publish tag vX.Y.Z (or refuse to move the README default pin to it) unless a `vX.Y.Z` row exists declaring the exact DSH cohort it targets.
- Document the pin-and-table discipline in the README: "if install of the default tag fails, or the plugin crashes after install, check the compat table against your `dsh --version` before changing anything else," and keep an installable, mirror-published fallback pin for each still-supported host cohort (as v0.9.3 is for 0.1.1-rc.x).

## Summary

| Item | Finding |
|---|---|
| Attempt 1 | `v0.9.5` absent from mirror tags (`ls-remote-tags.txt`: jump v0.9.1 → v0.9.7); `sync-script.sh` pushes only `HEAD:main`, never tags — release-tooling defect, not consumer error |
| Attempt 2 | `v0.9.7` targets DSH 0.1.2-alpha.1 (`compat-table.md`), consumer runs 0.1.1-rc.2 (`dsh-version.txt`) — forward-cohort mismatch; `useConversation` exists only in the alpha.1 client API |
| Remedy | Maintainer pushes `refs/tags/v0.9.3` to both mirrors; consumer installs `@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3` (v0.9.3 ↔ rc.1; rc.2 = rc.1 + additive) — no host upgrade required |
| Prevention | Sync script publishes the release tag per mirror; CI gate asserts tag presence on mirrors and that the README default pin resolves to a tag whose compat-table row covers a supported DSH cohort |
