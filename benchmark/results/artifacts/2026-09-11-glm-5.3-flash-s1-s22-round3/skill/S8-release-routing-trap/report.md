# S8 · Release Routing Trap — Diagnostic Report (Read-Only Diagnosis)

Scope: static analysis of the evidence pack under `fixture/` (README.md, compat-table.md, dsh-version.txt, ls-remote-tags.txt, sync-script.sh). No files in the fixture were modified; no installs or migrations were executed. Skill mode: A · inspect (read-only) per plugin-upgrade SKILL.md.

## 1. Attempt-1 root cause — `#v0.9.5` cannot resolve

**Root cause: tag-distribution defect on the mirrors — v0.9.5 was never published as a tag, and the release sync script does not push tags at all.**

Evidence:

- `ls-remote-tags.txt` (the mirror's full tag listing, `git ls-remote --tags https://github.com/public-org/dsh-ui-progress.git`) ends with:

  ```
  refs/tags/v0.9.0
  refs/tags/v0.9.1
  refs/tags/v0.9.7
  ```

  The tags v0.9.2, v0.9.3, v0.9.4, v0.9.5, v0.9.6 are **absent**. The listing is annotated and sorted ascending, so this is not a display artifact: `#v0.9.5` simply does not exist on the mirror, and pnpm's git resolver fails immediately exactly as reported.

- `sync-script.sh` shows why: the per-mirror release sync is

  ```bash
  for remote in origin public mirror2; do
    git push --force-with-lease "$remote" HEAD:main
  done
  ```

  It pushes only `HEAD:main`. There is no `git push --tags` (and no per-tag push such as `git push "$remote" "refs/tags/v0.9.7"`). So every release's commit reaches the mirrors via `main`, but its **tag never does**. v0.9.7 appears in the listing only because someone must have pushed that one tag by hand after the attempt-1 failure — the systematic mechanism still skips tags, which is why the older tags (v0.9.2–v0.9.6) are missing while the manually pushed v0.9.7 exists.

This is a release-engineering defect on the maintainer side, not a consumer-side network, authentication, or command-typo problem: the exact command in the README points at a ref the mirror does not carry.

## 2. Attempt-2 root cause — v0.9.7 installs, then `TypeError: useConversation is not a function`

**Root cause: version-routing defect — the README's default pin was bumped to a plugin release built for a newer DSH host than the consumer runs.** The compatibility direction is: **plugin v0.9.7 targets DSH v0.1.2-alpha.1**, while the consumer's runtime is **DSH 0.1.1-rc.2** (`dsh-version.txt`).

Evidence:

- `compat-table.md`:

  ```
  | v0.9.3 | npm @deepseek-ai/dsh@0.1.1-rc.1 | rc.1 real-boot verified; rc.2 is rc.1 + image preprocessing (additive) |
  | v0.9.7 | dsh-v0.1.2-alpha.1 | Migrated to the alpha.1 client API (views/legacy projection + useConversation seat) |
  ```

- `dsh-version.txt`: `dsh --version` → `0.1.1-rc.2`.

Chain of failure: v0.9.7 was "Migrated to the alpha.1 client API", whose client surface includes the `useConversation` seat. The consumer's 0.1.1-rc.2 host predates that client API, so the browser loads the plugin bundle, the slot entry executes, and `useConversation` does not exist on the rc.2 client runtime — hence `TypeError: useConversation is not a function`. This is a client-plane API mismatch, so restarting dsh cannot help (the code that is missing lives in the host's served client runtime, not in a stale process state). Note this matches the plugin-upgrade skill's version-boundary discipline: the plugin release version (0.9.x) and the DSH host corridor (0.1.1-rc.2 → 0.1.2-alpha.1) are independent coordinates; bumping the README pin along the plugin's own release line silently crossed a DSH host corridor edge.

The consumer is under a production freeze and cannot upgrade their dsh runtime, so "upgrade to 0.1.2-alpha.1" is not an acceptable remedy.

## 3. Exact remedy for the consumer right now

Target plugin version: **v0.9.3** — per the compatibility table it runs on `@deepseek-ai/dsh@0.1.1-rc.1` (real-boot verified) and rc.2 is additive over rc.1, so rc.2 is supported.

However, `ls-remote-tags.txt` shows **`refs/tags/v0.9.3` is also missing from the mirror** (the same tag-distribution defect). So the remedy is two-step:

1. **Maintainer publishes the missing tag** (one-time, from the source repo, for each mirror):

   ```bash
   git push origin refs/tags/v0.9.3
   git push public refs/tags/v0.9.3
   git push mirror2 refs/tags/v0.9.3
   ```

   (or `git push <remote> --tags` to restore v0.9.2–v0.9.6 in one shot).

2. **Consumer installs the frozen-runtime-compatible version**:

   ```
   dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
   ```

If the maintainer cannot push the tag immediately, a workaround resolvable today is pinning the v0.9.3 **commit SHA** (the commit is reachable on `main` since the sync script pushes `HEAD:main`), e.g. `...#<v0.9.3-commit-sha>` — but the tagged ref is the clean fix. There is **no consumer-only remedy among the tags currently on the mirror**: v0.9.7 is API-incompatible with rc.2, and every older tag except v0.9.0–v0.9.1 (which predate the compat table's rc.1-verified line) is absent.

After install, verify enablement, not just install success: confirm the target profile's composition resolves to the pinned ref and cold-start/reload the web profile so the served client bundle actually mounts the plugin (per the skill's validation layers 2 and 4).

## 4. Maintainer-side fix so both defects cannot recur

**Release tooling (tag distribution):**

- In `sync-script.sh`, push tags together with `main` for every mirror, e.g.:

  ```bash
  for remote in origin public mirror2; do
    git push --force-with-lease "$remote" HEAD:main
    git push "$remote" --tags          # or: git push "$remote" "refs/tags/$RELEASE_TAG"
  done
  ```

  (The excerpt also contains a stray duplicated `done` — fix that while editing.) Add a post-sync gate asserting `git ls-remote --tags "$remote"` contains the just-released tag; fail the release if it does not. One-time backfill: push the missing v0.9.2–v0.9.6 tags.

**Docs (version routing):**

- The README must not point its default install command at "the newest tag" unconditionally. Pin the default to the plugin version whose DSH-compatibility row covers the currently **released/stable** dsh line (today: `#v0.9.3` for the 0.1.1-rc line), and ship the compatibility table next to the install command with one pinned command per supported dsh cohort, e.g. a "which tag do I use?" section keyed on `dsh --version` output.
- Establish the corridor discipline from the plugin-upgrade skill as release policy: every plugin release names the exact DSH host version it targets in its release notes/README row; a release that crosses a DSH host corridor edge (like v0.9.7 → 0.1.2-alpha.1) gets a **separate** README section/branch pin, never a replacement of the default pin.
- Optional guard: a release check that the README's default install pin (a) exists as a tag on every mirror and (b) has a compat-table row whose DSH version matches the host line advertised as stable — mechanically prevents both the missing-tag and wrong-default-pin regressions.

## Summary

| Item | Finding |
|---|---|
| Attempt-1 root cause | Tag-distribution defect: `sync-script.sh` pushes only `HEAD:main`, never tags, so `v0.9.5` (and v0.9.2–v0.9.6) are absent from `ls-remote-tags.txt`; pnpm cannot resolve a nonexistent ref |
| Attempt-2 root cause | Version-routing defect: README pin bumped to v0.9.7, which per `compat-table.md` targets DSH 0.1.2-alpha.1; consumer runs 0.1.1-rc.2 (`dsh-version.txt`) → alpha.1 client API `useConversation` missing at runtime |
| Consumer remedy | Maintainer pushes `refs/tags/v0.9.3` to the mirrors (tag also missing today); consumer installs `@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3` (rc.1-verified, rc.2 additive) |
| Maintainer fix | Push tags in the sync script + post-sync tag-verification gate; pin the README default to the dsh-stable-compatible release with a per-cohort pinned-command table |
