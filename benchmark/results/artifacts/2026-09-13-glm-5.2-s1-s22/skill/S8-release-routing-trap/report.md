# S8 · Release Routing Trap — Diagnosis Report

Task: release-engineering diagnosis of a two-stage install failure for the community plugin
`@org/dsh-ui-progress` (GitHub mirrors: `public-org/dsh-ui-progress`). Mode A (read-only
inspection) per the plugin-upgrade skill. Evidence: static pack in the fixture directory
(`ls-remote-tags.txt`, `dsh-version.txt`, `compat-table.md`, `sync-script.sh`, `README.md`).

## 1. Attempt-1 root cause — why `#v0.9.5` could not resolve

**Defect: the release sync script distributes branches but never distributes tags, so the
mirror the consumer installs from does not have the `v0.9.5` tag.**

Evidence chain:

- `sync-script.sh` runs, for each mirror (`origin public mirror2`):
  `git push --force-with-lease "$remote" HEAD:main` — and nothing else. There is no
  `git push --tags` / `git push <remote> <tag>` anywhere in the excerpt.
- `ls-remote-tags.txt` (tags on the consumer-facing mirror `public-org/dsh-ui-progress`)
  confirms the consequence: the tag series jumps `v0.9.0, v0.9.1, … v0.9.7`. Tags
  `v0.9.2`–`v0.9.6` — including the `v0.9.5` the README pinned — exist only on the
  maintainer's primary remote and were never mirrored. (`v0.9.7` evidently reached this
  mirror by some out-of-band push, which is why attempt 2 got further.)
- The consumer's command used the Git-resolver form
  `@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.5`. With a `#<ref>` pin,
  pnpm must resolve that ref to a commit **on that remote**; an absent tag cannot resolve,
  so pnpm fails immediately. This is a tag-distribution defect on the maintainer side —
  not a network problem and not a command error on the consumer side.

This matches the known "mirror lag / incomplete install channel" pitfall from the skill's
rollup reference: mirrors are independent distribution channels and must be verified
per-remote after each release.

## 2. Attempt-2 root cause — why `v0.9.7` installed but crashed

**Defect: version routing. The newest artifact targets a NEWER DSH client API than the
consumer's runtime; the README bump advertised it as the default for everyone.**

Compatibility direction, tied to the consumer's actual runtime (`dsh --version` →
**0.1.1-rc.2`):

- `compat-table.md`:
  - `v0.9.3` → targets `@deepseek-ai/dsh@0.1.1-rc.1` (real-boot verified; rc.2 is noted
    as rc.1 + additive image preprocessing). So **v0.9.3 is the artifact line for the
    consumer's 0.1.1-rc.x runtime**.
  - `v0.9.7` → targets `dsh-v0.1.2-alpha.1`, "migrated to the alpha.1 client API
    (views/legacy projection + **useConversation seat**)". `useConversation` is part of
    the 0.1.2-alpha client conversation-slot API and does not exist in the 0.1.1-rc.2
    client runtime the consumer runs.
- Therefore `v0.9.7`'s slot entry calls a client API that the consumer's older runtime
  simply does not export → `TypeError: useConversation is not a function` at registration
  time. Restarting dsh cannot help: it is a static API-cohort mismatch (plugin built
  against a newer host/client corridor), not a stale-state or boot-race problem.

Note the two independent version coordinates the skill calls out: the plugin's release
version (0.9.x) is **not** the DSH host corridor (0.1.1-rc.x vs 0.1.2-alpha.x). The
maintainer treated "newest plugin tag" as "the default install", which is exactly the
routing error.

## 3. Remedy for the consumer right now (runtime frozen at 0.1.1-rc.2)

The consumer must run the plugin line built for the 0.1.1 corridor: **v0.9.3** (rc.1-built,
rc.2-compatible per the compat table's additive note). Because the mirror lacks the
`v0.9.3` tag (same sync defect), the pin must come from a remote that has it. Two
equivalent paths:

1. Preferred (no maintainer action needed): install from the primary `origin` repository
   at the `v0.9.3` tag:

   ```
   dsh plugin --profile web add '@org/dsh-ui-progress@github:<origin-org>/dsh-ui-progress#v0.9.3'
   ```

   (substitute the origin org; the consumer can find it in the repo's "official mirror"
   links — the fixture only names the mirror org `public-org`).

2. Or, after the maintainer performs the one-line remediation `git push public --tags`
   (or `git push public v0.9.3`), the mirror command works:

   ```
   dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
   ```

Either way: **downgrade the plugin pin to v0.9.3, not the runtime upgrade to 0.1.2-alpha.1
that v0.9.7 would require** — the production freeze forbids the latter. After install,
verify enablement: the profile composition resolves to the v0.9.3 package identity and the
slot entry mounts without the TypeError (per the skill's validation layers: enablement
resolution + runtime registration, not just install exit code).

## 4. Maintainer-side fixes so both defects cannot recur

**Release tooling (defect 1 — tag distribution):**

- Extend `sync-script.sh` to distribute tags to every mirror, e.g.:

  ```bash
  for remote in origin public mirror2; do
    git push --force-with-lease "$remote" HEAD:main
    git push "$remote" --tags
  done
  ```

- Add a post-sync verification step per mirror — `git ls-remote --tags <remote>` must
  contain every tag in the just-cut release (fail the release job loudly on a hole).
  Misconfiguration fails loud rather than silently shipping an incomplete channel.
- Audit and backfill the missing historical tags (`v0.9.2`–`v0.9.6`) to all mirrors once.

**Docs / routing (defect 2 — version routing):**

- The README's single "default install command" must become a **version-selection table**
  keyed by the consumer's `dsh --version`: "0.1.1-rc.x → pin `#v0.9.3`";
  "0.1.2-alpha.1+ → pin `#v0.9.7`". Never advertise only the newest tag as the universal
  default — plugin SemVer (0.9.x) is independent of the DSH host corridor (0.1.x).
- Consider per-corridor distribution channels (e.g. release lines/tags like
  `dsh-0.1.1`/`dsh-0.1.2-alpha` or a moving branch per corridor) so consumers can pin a
  channel instead of a hand-checked tag.
- Optionally add a client-entry runtime guard: on registration, check the injected client
  API for the required exports (e.g. `useConversation`) and fail with an explicit
  "this build requires dsh ≥ 0.1.2-alpha.1; on 0.1.1-rc.x use v0.9.3" message instead of
  a raw `TypeError`.

## Summary

| Stage | Root cause | Class |
|---|---|---|
| Attempt 1 (`#v0.9.5` pnpm failure) | Sync script pushes only `HEAD:main`, never tags → tag absent on the consumer-facing mirror | Tag distribution (release tooling) |
| Attempt 2 (`v0.9.7` crashes) | v0.9.7 is built for dsh 0.1.2-alpha.1 client API (`useConversation`); consumer runs 0.1.1-rc.2 | Version routing (compat direction: artifact targets a newer host than the runtime) |
| Consumer remedy | Pin `#v0.9.3` from a remote that has the tag (origin, or mirror after `git push public --tags`) | Works under the 0.1.1-rc.2 freeze |
| Maintainer fix | Push + verify tags on every mirror; README install commands keyed by dsh version; optional runtime guard | Prevents both recurrences |

Fixture was treated strictly read-only; no migrations, installs, or external access were
performed.
