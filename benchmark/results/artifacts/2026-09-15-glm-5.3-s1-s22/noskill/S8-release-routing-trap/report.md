# S8 · Release Routing Trap — Diagnosis Report

## Summary

Two independent release-engineering defects, one per attempt:

1. **Attempt 1 (`#v0.9.5` fails to resolve):** the release sync script pushes only the
   `main` branch to the mirrors — it never pushes tags. The public mirror's tag set is
   therefore incomplete and divergent from origin: `git ls-remote --tags` on
   `public-org/dsh-ui-progress` shows `v0.9.1` then `v0.9.7`, with **no `v0.9.5`**.
   The README's default install command pinned a tag that was never distributed to the
   mirror the command installs from, so pnpm's git-resolver could not resolve the ref and
   failed immediately. This is a tag-distribution defect, not a consumer network/command
   problem.
2. **Attempt 2 (`#v0.9.7` installs but crashes):** v0.9.7 was migrated to the
   **dsh-v0.1.2-alpha.1 client API** (compat table: "views/legacy projection +
   `useConversation` seat"). The consumer's runtime is **dsh 0.1.1-rc.2** (`dsh
   --version`), which predates the alpha.1 client API — so the hook the plugin calls does
   not exist on that runtime and the slot entry throws
   `TypeError: useConversation is not a function`. Compatibility direction: the newest
   plugin artifact targets a **newer** DSH than the consumer runs; the plugin is
   forward-compatible only with 0.1.2-alpha.1+. Restarting dsh cannot help because the
   failure is a static API mismatch between plugin artifact and client runtime, not stale
   state. Per the compat table, the **v0.9.3** line targets npm
   `@deepseek-ai/dsh@0.1.1-rc.1`, and rc.2 is rc.1 plus additive image preprocessing —
   so v0.9.3 is the correct artifact for the consumer's frozen runtime.

## Remedy for the consumer (works on dsh 0.1.1-rc.2, no runtime upgrade)

Install the tag whose compatibility line matches the frozen runtime — v0.9.3 — which does
exist on the public mirror:

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

Then fully restart dsh (or reload the Web client) so the previously crashed v0.9.7 slot
registration is replaced by the v0.9.3 one.

## Maintainer-side fixes

### Release tooling (`sync-script.sh`)

- **Distribute tags to every mirror.** The loop currently runs only
  `git push --force-with-lease "$remote" HEAD:main`. It must also push the release tags,
  e.g. `git push "$remote" --tags` (or push the specific `refs/tags/<version>` being
  released) inside the same per-remote loop.
- **Verify distribution after sync.** After each push, run a read-only
  `git ls-remote --tags "$remote"` and assert that the tag being released (and every tag
  the README currently pins) is present on **each** mirror; fail the release loudly on a
  missing tag ("misconfiguration fails loud") instead of letting mirrors silently diverge.
- **Order the release correctly:** create and push the tag to all mirrors **before**
  bumping the README's pinned version, so the documented install command can never
  reference an undistributed ref.

### Docs

- **State runtime requirements per tag.** The README's compatibility table must be part of
  the release checklist: each tagged release declares the minimum DSH runtime it targets
  (v0.9.3 → 0.1.1-rc.x; v0.9.7 → 0.1.2-alpha.1+), and the default install command must
  pin a tag compatible with the oldest DSH version still in support — or ship two
  documented commands (one per runtime line).
- **Warn on the breaking line:** mark v0.9.4–v0.9.7 as requiring the 0.1.2-alpha client
  API so consumers on frozen rc.x runtimes are routed to `#v0.9.3` explicitly.
- Longer term, consider publishing versioned artifacts to a registry instead of relying on
  per-mirror git-tag distribution, which removes the mirror-divergence class of failure.

## Evidence trail

| Fact | Source |
|---|---|
| Public mirror tags jump v0.9.1 → v0.9.7; no v0.9.5 | `fixture/ls-remote-tags.txt` |
| Sync script pushes only `HEAD:main`, never tags | `fixture/sync-script.sh` |
| README default install pins `#v0.9.5` from the public mirror | task brief |
| v0.9.7 targets dsh-v0.1.2-alpha.1 (`useConversation` seat) | `fixture/compat-table.md` |
| v0.9.3 targets 0.1.1-rc.1; rc.2 = rc.1 + additive image preprocessing | `fixture/compat-table.md` |
| Consumer runtime is 0.1.1-rc.2 | `fixture/dsh-version.txt` |
