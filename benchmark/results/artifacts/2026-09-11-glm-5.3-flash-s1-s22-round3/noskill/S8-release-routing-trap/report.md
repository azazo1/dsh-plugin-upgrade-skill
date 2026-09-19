# S8 · Release Routing Trap — Diagnostic Report

Evidence pack: `fixture/` (read-only): `ls-remote-tags.txt`, `dsh-version.txt`, `compat-table.md`, `sync-script.sh`, `README.md`. Consumer runtime: **dsh 0.1.1-rc.2**.

## 1. Attempt-1 root cause — tag never published to the mirror (tag distribution defect)

The README's default install command pins `@github:public-org/dsh-ui-progress#v0.9.5`, but `ls-remote-tags.txt` — the actual tag listing of `https://github.com/public-org/dsh-ui-progress.git` — shows the mirror's tags jump straight from `v0.9.1` to `v0.9.7`:

```
refs/tags/v0.9.1
refs/tags/v0.9.7
```

There is **no `v0.9.5` ref on the mirror at all**, so pnpm cannot resolve the pinned tag and fails immediately. This is a release-engineering defect, not a consumer-side problem. The cause is visible in `sync-script.sh`: after every release it pushes only the branch to each mirror —

```bash
git push --force-with-lease "$remote" HEAD:main
```

— it never runs `git push --tags` (nor pushes any refspec). Tags exist only on the primary repo; the mirrors, which the README's install command targets, never receive them. Any tag-pinned install against the mirror can only resolve by accident (an old tag pushed before this script existed, such as up to `v0.9.1`, or a future manually pushed one).

Note the trap: the maintainer "fixed" attempt 1 by bumping the README to the newest tag `#v0.9.7` — the one tag that does exist on the mirror — but that tag is the wrong artifact for this consumer (item 2).

## 2. Attempt-2 root cause — version routing mismatch (artifact targets a newer DSH than the runtime)

`compat-table.md` is explicit:

- `v0.9.3` → npm `@deepseek-ai/dsh@0.1.1-rc.1` ("rc.2 is rc.1 + image preprocessing (additive)") — i.e. built for the **0.1.1-rc line**.
- `v0.9.7` → `dsh-v0.1.2-alpha.1` ("Migrated to the alpha.1 client API (views/legacy projection + **useConversation seat**)").

`dsh-version.txt` shows the consumer runs **`dsh --version` → `0.1.1-rc.2`**. Installing `#v0.9.7` therefore put a **dsh v0.1.2-alpha.1-targeted plugin** onto a **dsh 0.1.1-rc.2 runtime**: v0.9.7 imports the `useConversation` client API seat that exists only in alpha.1's client API, which rc.2 does not provide. At slot render time the import resolves to a non-function, producing exactly the reported `TypeError: useConversation is not a function` in the browser. Restarting dsh cannot help — this is a static version mismatch, not a stale process.

Compatibility direction: **v0.9.7 targets DSH v0.1.2-alpha.1 (newer); the consumer's runtime is DSH 0.1.1-rc.2 (older)**. The consumer needs the rc-line plugin artifact, which per the table is **v0.9.3** (rc.2 being additive over rc.1, v0.9.3 runs on rc.2).

## 3. Exact remedy for the consumer right now

The correct install ref is `#v0.9.3` — but per `ls-remote-tags.txt` the mirror also lacks `v0.9.3` (everything between `v0.9.1` and `v0.9.7` is missing). So a bare retry would fail exactly like attempt 1. The remedy is two steps:

1. Maintainer publishes the missing tags to the mirror once (see item 4), e.g. `git push public --tags` (at minimum `v0.9.3`).
2. Consumer then runs:

```sh
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

v0.9.3 is verified against `0.1.1-rc.1` and rc.2 is additive over rc.1, so it works on the frozen `0.1.1-rc.2` runtime. Pinning `#v0.9.7` (or any later tag) is not an option until the consumer's production freeze lifts and they upgrade to dsh ≥ v0.1.2-alpha.1. No tag between `v0.9.1` and `v0.9.3` has a documented compatibility row, so do not fall back to `#v0.9.1` blindly.

## 4. Maintainer-side fix so both defects cannot recur

**Release tooling — publish tags to every mirror.** `sync-script.sh` syncs only `HEAD:main`. Add an explicit tag sync to the same loop (do not force-push tags):

```bash
for remote in origin public mirror2; do
  git push --force-with-lease "$remote" HEAD:main
  git push "$remote" --tags   # publish release tags; add explicit refspecs if only release tags should propagate
done
```

Ideally verify sync succeeded as a release gate: after the loop, run `git ls-remote --tags "$remote"` and fail the release if the just-cut tag is absent from any mirror — that check would have caught the missing `v0.9.5`/`v0.9.3` immediately. Backfill now: push the missing historical tags (`v0.9.2`–`v0.9.6`, at minimum `v0.9.3`) to both mirrors.

**Version routing — make compatibility machine-checkable and install-command-driven.** The README currently forces maintainers to hand-pick tags, which is how `#v0.9.7` (alpha.1-only) got recommended to an rc.2 user. Fixes:

- Record each release's required DSH range in the plugin package itself (e.g. a `peerDependencies`/`engines`-style field on `@org/dsh-ui-progress` or the plugin manifest) so the installer can refuse a mismatched runtime with a clear message instead of crashing at slot render with `useConversation is not a function`.
- Update `compat-table.md` for every release (v0.9.4–v0.9.6 rows are missing too) and link it from the install section.
- Change the README default install command from a hardcoded tag to the compatibility-compatible ref (or an install command that resolves the newest compatible tag for the consumer's `dsh --version`), and add a release checklist step: "bump README pin only to a tag whose DSH range covers the currently recommended dsh release, then re-verify the pinned tag exists on every mirror (`git ls-remote --tags`)".

These two fixes close the distinct failure classes: tag distribution (mirror missing refs) and version routing (artifact/runtime mismatch silently installed).
