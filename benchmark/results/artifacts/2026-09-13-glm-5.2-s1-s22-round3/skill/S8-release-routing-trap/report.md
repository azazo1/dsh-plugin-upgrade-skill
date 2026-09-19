# S8 · Release Routing Trap — Diagnosis Report

Mode: **A · inspect** (read-only; per plugin-upgrade skill and the benchmark brief, no writes
outside this report, no installs, no migrations).

Evidence reviewed (fixture, unchanged): `README.md`, `compat-table.md`, `dsh-version.txt`,
`ls-remote-tags.txt`, `sync-script.sh`, plus the two failure symptoms quoted in the task brief.

## 0. Identity baseline

| Coordinate | Value |
|---|---|
| Consumer dsh runtime | `0.1.1-rc.2` (`dsh-version.txt`) — **cannot upgrade** (production freeze) |
| Plugin package (install name) | `@org/dsh-ui-progress` |
| Consumer's install source | GitHub mirror `github:public-org/dsh-ui-progress` (org rewritten per mirror) |
| Mirrors maintained | `origin`, `public`, `mirror2` (`sync-script.sh`) |
| Plugin↔DSH compat (README table) | v0.9.3 → dsh `0.1.1-rc.1` (rc.2 additive, compatible); v0.9.7 → dsh `0.1.2-alpha.1` |

## 1. Attempt-1 root cause — why `#v0.9.5` could not resolve

**The release sync script never pushes tags.** `sync-script.sh` performs, for each of the three
mirrors, only:

```bash
git push --force-with-lease "$remote" HEAD:main
```

It distributes the `main` branch only; there is no `--tags`, no `--follow-tags`, and no
post-push tag verification. Tag distribution to the mirrors is therefore whatever leaked through
manual pushes, and it is demonstrably inconsistent: `git ls-remote --tags` on the consumer's
mirror (`public-org`) lists `v0.9.0`, `v0.9.1`, then jumps straight to `v0.9.7` —
**`v0.9.5` (and v0.9.2–v0.9.4) do not exist on that mirror**, even though the README pins
`#v0.9.5` as the default install. pnpm resolving `github:public-org/dsh-ui-progress#v0.9.5`
fails immediately because `refs/tags/v0.9.5` is absent from the only remote the consumer can
see. This is a release-engineering defect (tag distribution gap between mirrors), not a
consumer network or command problem.

## 2. Attempt-2 root cause — why `v0.9.7` installed but crashed

**Compatibility direction:** the plugin's *client artifact* is built against the **DSH
0.1.2-alpha.1** client API; the consumer's *host/client runtime* is **0.1.1-rc.2**. The plugin
is ahead of the runtime, and client-plugin APIs are not forward-compatible in that direction —
a plugin compiled against a newer client API surface calls seats that do not exist on an older
runtime.

Per `compat-table.md`, v0.9.7 was "migrated to the alpha.1 client API (views/legacy projection
+ `useConversation` seat)". The `useConversation` seat exists only from the alpha-line client
runtime; on 0.1.1-rc.2 the hook is undefined, so the plugin's slot entry throws
`TypeError: useConversation is not a function` at registration/mount time. Restarting dsh
cannot help — the failure is a static API mismatch, not stale state (the plugin is served into
every page load and crashes on each mount).

The maintainer's README bump from `#v0.9.5` → `#v0.9.7` made the *resolution* problem go
away (v0.9.7 is the one later tag that does exist on the mirror) but routed the consumer onto
an artifact built for a runtime corridor he does not have — the "routing trap": tag
availability was fixed by choosing a tag whose *DSH version target* is wrong for the consumer.

## 3. Remedy for the consumer (works on dsh 0.1.1-rc.2, no runtime upgrade)

Install the plugin version whose DSH corridor matches the frozen runtime: **v0.9.3**
(verified against `0.1.1-rc.1`; rc.2 is rc.1 plus additive image preprocessing, per the
compat table), and **v0.9.3 exists on the consumer's mirror** per `ls-remote-tags.txt`:

```bash
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

Then restart dsh / hard-refresh the browser so the old crashing v0.9.7 client artifact is
replaced, and verify the slot entry mounts without the `useConversation` error. (If v0.9.3
also failed to resolve on that mirror in practice, the same tag-distribution defect of §1
would be the first suspect; the evidence here shows v0.9.3 present, so it should resolve.)

Do **not** install v0.9.7 until the runtime is upgraded to `>= 0.1.2-alpha.1`.

## 4. Maintainer-side fixes

### 4.1 Release tooling (prevents attempt 1 — tag distribution gap)

- The sync script must distribute tags to every mirror, explicitly and verifiably, e.g. after
  the branch push add a tag push for the release tag:

```bash
for remote in origin public mirror2; do
  # rewrite install-source orgs for the target mirror, then:
  git push --force-with-lease "$remote" HEAD:main
  git push "$remote" "refs/tags/$RELEASE_TAG"
done
```

- Add a post-sync gate per release that fails the release (not just warns) when any mirror is
  missing the tag: `git ls-remote --tags "$remote" "refs/tags/$RELEASE_TAG"` must return
  exactly the expected object hash on **all** mirrors. The current state (v0.9.7 present,
  v0.9.2–v0.9.5 absent on `public-org`) shows partial/manual tag pushes already happened;
  CI should own tag distribution end-to-end so it cannot drift per mirror again.
- Treat tags as immutable release artifacts: never rewrite or skip them per-mirror; verify
  org-rewritten install sources still point at the intended tag object after rewriting.

### 4.2 Docs / routing (prevents attempt 2 — version misrouting)

- Stop pinning a single "newest tag" as the README's default install command. The README's
  default must be chosen by **DSH host corridor**, not by tag recency, and must be updated in
  lockstep with the compat table: consumers on `0.1.1-rc.x` should be told to install
  `#v0.9.3`; only consumers on `>= 0.1.2-alpha.1` should be told `#v0.9.7`.
- Put the plugin-version ↔ dsh-version compatibility table at the top of the README with an
  explicit instruction: run `dsh --version` first, then pick the plugin tag from the table.
  Mark v0.9.7's row with a hard warning: "requires dsh ≥ 0.1.2-alpha.1; on older runtimes
  the client slot crashes with `TypeError: useConversation is not a function`".
- Longer term, make routing structural rather than prose: publish per-corridor release lines
  (e.g. a branch/tag scheme or registry dist-tags per DSH corridor) so "newest tag" is never
  ambiguously wrong, and have the release checklist verify that the README's pinned tag exists
  on all mirrors *and* matches the corridor the release notes claim.
- Keep the plugin's own release version (v0.9.x) and the DSH host corridor (0.1.x-alpha/rc)
  as separate coordinates in all docs and release notes; never imply one from the other.

## 5. Skipped / not applicable

- No dependency, lockfile, enablement-resolution, or runtime-mount validation was run: the
  fixture is a static evidence pack and the brief forbids installs/migrations. Findings rest on
  the fixture documents and the symptoms quoted in the brief.
- Rollback: not applicable — nothing was modified; the fixture was only read and remains
  unchanged.

## 6. Summary

1. **Attempt 1**: `#v0.9.5` failed because the mirror-sync script pushes only `HEAD:main` and
   never tags — `refs/tags/v0.9.5` is absent from `public-org`, so pnpm cannot resolve the
   GitHub ref. Release-engineering defect: incomplete tag distribution across mirrors.
2. **Attempt 2**: v0.9.7 exists on the mirror but its client artifact targets the DSH
   `0.1.2-alpha.1` API (`useConversation` seat), which the consumer's frozen
   `0.1.1-rc.2` runtime does not provide → the slot entry crashes on mount; restart cannot
   fix an API mismatch.
3. **Consumer remedy**: `dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'`.
4. **Maintainer fixes**: push and verify tags on all mirrors in the sync script (fail the
   release otherwise); route README install pins by DSH-host corridor from the compat table
   instead of newest tag.
