# S8 · Release Routing Trap — Diagnostic Report

Evidence pack: `fixture/` (README.md, compat-table.md, dsh-version.txt, ls-remote-tags.txt, sync-script.sh). All findings below are grounded in those files.

## 1. Attempt-1 root cause: `#v0.9.5` cannot resolve — the tag was never distributed

The consumer pinned the exact tag from the README (`@github:public-org/dsh-ui-progress#v0.9.5`), so this is not a command or network problem. The defect is in the release tooling, visible in two fixtures:

- `ls-remote-tags.txt` lists the tags that actually exist on the public mirror: v0.1.0 … v0.9.1, then **v0.9.7**. The sequence jumps straight from `v0.9.1` to `v0.9.7` — **the `v0.9.5` tag (and `v0.9.3`, which the compat table also references) was never pushed to the mirror at all**. The README advertised a tag that does not exist on the install source, so pnpm's ref resolution fails immediately.
- `sync-script.sh` shows why: the post-release mirror sync only does
  ```bash
  git push --force-with-lease "$remote" HEAD:main
  ```
  This pushes the **branch head only; it never pushes tags** (`refs/tags/*` is absent from the command). The v0.9.7 tag evidently reached the mirror through some other/older path (it appears in `ls-remote-tags.txt`), but the current release script cannot distribute any new tag — so each future release would repeat this gap. The release-engineering defect is **tag distribution**: the sync script does not mirror tags, leaving the README's pinned install commands pointing at nonexistent refs.

## 2. Attempt-2 root cause: v0.9.7 targets a newer DSH than the consumer runs — forward incompatibility

- `dsh-version.txt`: the consumer's runtime is `dsh --version → 0.1.1-rc.2`.
- `compat-table.md`: **v0.9.7 requires `dsh-v0.1.2-alpha.1`** — "Migrated to the alpha.1 client API (views/legacy projection + useConversation seat)". The last release verified on the consumer's line is **v0.9.3 ↔ npm @deepseek-ai/dsh@0.1.1-rc.1**, with the note that rc.2 is rc.1 plus additive image preprocessing — i.e. rc.2 is on the same compatibility line.

So the compatibility direction is: **plugin v0.9.7 is written against the newer dsh 0.1.2-alpha.1 client API** (the `useConversation` seat exists only there), while the consumer's runtime is the older 0.1.1-rc.2. Installing a plugin compiled for a newer host onto an older runtime is a forward-incompatible mismatch: the alpha-1-only export `useConversation` does not exist in the rc.2 client surface, which is exactly the crash `TypeError: useConversation is not a function` when the slot entry mounts in the browser. Restarting dsh cannot help — the mismatch is in the shipped artifact, not in runtime state. The README bump to "newest tag" made the version routing worse: it moved the consumer from a (nominally) rc-compatible line to an alpha-only build.

## 3. Exact remedy for the consumer right now (no runtime upgrade)

Constraints: the consumer must stay on dsh 0.1.1-rc.2, and the install source is the public mirror whose available tags are fixed by `ls-remote-tags.txt`.

- v0.9.7 is out (requires 0.1.2-alpha.1).
- v0.9.3 would be the right rc-line release per `compat-table.md` (verified against rc.1, rc.2 additive), **but the v0.9.3 tag does not exist on the mirror** (defect #1) — pinning it would reproduce attempt-1's resolution failure.
- Therefore the newest tag on the mirror that is compatible with the rc line is **v0.9.1** (last tag before the alpha-API migration; the compat table's rc-compatible entries are v0.9.x pre-0.9.7, and everything from v0.9.1 and earlier predates the alpha.1 migration).

Concrete command:

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.1'
```

This is the best remedy available under the production freeze until the maintainer pushes the missing rc-line tag (see §4).

## 4. Maintainer-side fix so both defects cannot recur

**Release tooling (fixes tag distribution):** in the mirror sync script, push tags together with the branch head, e.g.

```bash
for remote in origin public mirror2; do
  git push --force-with-lease "$remote" HEAD:main
  git push "$remote" --tags          # or push the specific release tag: git push "$remote" "refs/tags/vX.Y.Z"
done
```

Better: make tag publication a mandatory, verified step of the release pipeline — after each release, assert with `git ls-remote --tags` that the tag named by the README actually resolves on every mirror, and fail the release otherwise. That turns the attempt-1 silent gap into a loud CI failure (misconfiguration fails loud). Backfill now: push the missing `v0.9.5` and `v0.9.3` tags (or retag/republish a rc-line release) to both mirrors.

**Docs (fixes version routing):** the README must not point at "the newest tag". Change it to:

1. Pin the default install command to the newest release that is verified against the **published/stable dsh line** (per `compat-table.md`: the rc-compatible line, e.g. v0.9.3 once its tag is distributed), not the newest tag overall.
2. Keep the compatibility table adjacent to the install command and state the direction explicitly: "v0.9.7 requires dsh v0.1.2-alpha.1 or newer; dsh 0.1.1-rc.x users must install vX.Y.Z".
3. Add a release checklist gate that cross-checks the README's pinned tag against (a) the tag's existence on every mirror and (b) the compat table's minimum dsh version, so a doc bump can never again route rc-line users onto an alpha-only artifact.
