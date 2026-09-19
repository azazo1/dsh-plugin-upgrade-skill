# S8 · Release Routing Trap — Diagnosis Report

Mode A (read-only inspection) per the plugin-upgrade skill. All evidence is static, from the fixture pack at `benchmark/tasks/S8-release-routing-trap/environment/fixture/`; nothing was executed, installed, or modified there.

## Evidence summary

| Artifact | Fact |
|---|---|
| `dsh-version.txt` | Consumer runtime: `dsh 0.1.1-rc.2` (production freeze — cannot upgrade) |
| `ls-remote-tags.txt` | Tags on the public mirror `public-org/dsh-ui-progress`: v0.1.0 … v0.9.0, v0.9.1, **v0.9.7** — the sequence jumps from v0.9.1 straight to v0.9.7; **v0.9.2–v0.9.6 are absent**, including the README-pinned **v0.9.5** |
| `compat-table.md` | v0.9.3 ↔ DSH 0.1.1-rc.1 (rc.2 = rc.1 + additive changes → compatible); **v0.9.7 ↔ DSH 0.1.2-alpha.1** ("Migrated to the alpha.1 client API — views/legacy projection + **useConversation** seat") |
| `sync-script.sh` | Post-release mirror sync pushes only `HEAD:main` per remote — **it never pushes tags** |
| README / brief | Default install pins `#v0.9.5`; after bump to `#v0.9.7` the install succeeded but the Web slot crashed: `TypeError: useConversation is not a function`; restart did not help |

## 1. Attempt-1 root cause — why `#v0.9.5` could not resolve

**Release-engineering defect: incomplete tag distribution to the public mirror.** The tag `v0.9.5` simply does not exist on `public-org/dsh-ui-progress` (the mirror the install URL points at), so pnpm's git resolver fails immediately when resolving `github:public-org/dsh-ui-progress#v0.9.5`. The consumer's network and command were fine.

The proximate cause is visible in `sync-script.sh`: the per-release mirror sync runs only

```bash
git push --force-with-lease "$remote" HEAD:main
```

— a branch-only push. Tags reach the mirrors only by accident (manual pushes / clone-time transfer), which is why some older tags exist but the v0.9.2–v0.9.6 window is missing while the newest v0.9.7 happens to be present. The README pins an install tag that was never distributed to the mirror the command installs from.

## 2. Attempt-2 root cause — why v0.9.7 installs but crashes

**Compatibility direction: the v0.9.7 artifact is built *forward* against the newer DSH host (0.1.2-alpha.1 client API); the consumer's runtime (0.1.1-rc.2) is *older* and does not provide that API.** Per the compat table, v0.9.7 was migrated to the alpha.1 client API, whose conversation-seat hook is `useConversation`. On the consumer's 0.1.1-rc.2 runtime that export does not exist (the alpha.1 corridor moved/renamed the conversation access — old seat gone, new `useConversation` seat not yet present), so the slot module's import yields `undefined` and calling it throws `TypeError: useConversation is not a function`.

This is a static API-version mismatch, not stale state — which is exactly why restarting dsh did not help; the crash is deterministic on every client activation of v0.9.7 under an rc.2 host. Note the inverse direction is fine: v0.9.3 (pre-migration, rc.1-era API) runs on rc.2 because rc.2 is rc.1 plus additive changes.

## 3. Remedy for the consumer right now (works on dsh 0.1.1-rc.2, no runtime upgrade)

1. Remove/disable the broken v0.9.7 entry from the profile (the `dsh plugin` remove/disable command for `@org/dsh-ui-progress` in the `web` profile), and hard-refresh the browser page so the crashed client registration is gone.
2. Install the newest plugin version that (a) targets the consumer's DSH corridor and (b) actually exists on the public mirror — that is **v0.9.3**:

```bash
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

v0.9.3 is real-boot verified on 0.1.1-rc.1 and rc.2 is additive relative to rc.1, so it is the correct pin for a frozen 0.1.1-rc.2 runtime. Everything from v0.9.7 (the only other tag ≥ v0.9.3 on the mirror) requires 0.1.2-alpha.1 and must not be used until the runtime freeze lifts.

## 4. Maintainer-side fixes

**Release tooling (defect 1 — tag distribution):**
- Change the mirror sync to distribute tags explicitly, e.g. per release tag `vX.Y.Z`:
  `git push --force-with-lease "$remote" HEAD:main` **plus** `git push "$remote" vX.Y.Z` (or `git push "$remote" --tags` after deduplicating annotated/lightweight tags).
- Add a post-sync verification gate: for each mirror, `git ls-remote --tags <mirror>` must contain the just-released tag (and ideally the full advertised tag set) before the release is announced; fail the release job otherwise. Today the script verifies nothing, which is how a missing `v0.9.5` shipped unnoticed.

**Docs / routing (defect 2 — version routing):**
- Keep the README compat matrix (plugin version ↔ required DSH version) directly adjacent to the install command, and make the default install command pin a tag that is (a) verified present on every public mirror and (b) matched to the oldest DSH line still supported — never automatically "bump to the newest tag", because newest = newest-required-DSH.
- State explicitly that versions ≥ v0.9.7 require `@deepseek-ai/dsh@0.1.2-alpha.1` or newer and that 0.1.1-rc.x consumers must stay on v0.9.3; if the community-standard manifest (`dsh-plugin.json`) supports a DSH host/version range field, declare it there so tooling can negotiate instead of crashing at runtime.
- Add a release-checklist item: "bump README install pin only after confirming the tag exists on all mirrors and the compat table names the DSH floor for that tag."

## Skipped / not applicable

- No runtime verification was possible or appropriate: the fixture is a static evidence pack and the brief forbids installs/migrations. The attempt-2 crash message is taken from the brief as quoted evidence.
- No baseline suite collected (Mode A read-only inspection; no plugin source tree was in scope).

## Residual risk

- v0.9.2–v0.9.6 content is unrecoverable from the public mirror; if any consumer needs those exact versions, they must come from the origin remote or an npm publication.
- Whether `v0.9.3` is also published to the npm-registry track is unknown from the fixture; the remedy above uses the GitHub-mirror track the consumer already uses.
