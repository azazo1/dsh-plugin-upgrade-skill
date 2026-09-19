# S8 · Release Routing Trap — Diagnosis Report

## Evidence base

Static fixture pack read-only: `ls-remote-tags.txt` (actual tags on the public mirror), `dsh-version.txt` (consumer runtime `0.1.1-rc.2`), `compat-table.md` (plugin↔DSH version matrix), `sync-script.sh` (per-mirror release sync excerpt), `README.md`.

## 1. Attempt-1 root cause: why `#v0.9.5` could not resolve

**The tag `v0.9.5` does not exist on the mirror the consumer installs from.** `git ls-remote --tags` on `public-org/dsh-ui-progress` lists `v0.9.0, v0.9.1`, then jumps straight to `v0.9.7` — `v0.9.2…v0.9.6` (including the README-pinned `v0.9.5`) are absent.

This is a **tag-distribution defect in the release sync script**, not a consumer/network/command problem. The excerpt pushes, for each mirror:

```bash
git push --force-with-lease "$remote" HEAD:main
```

That refspec pushes **only the branch `main`** — it never transports tags (no `--tags`, no `--follow-tags`, no explicit `refs/tags/*:refs/tags/*` refspec). Commits reach the mirrors; the tags cut on those commits mostly do not. The few tags that do exist on the mirror (`v0.9.1` and below) predate this script or were pushed by some other path; everything cut since is missing. So pnpm resolving `github:public-org/dsh-ui-progress#v0.9.5` fails immediately: the pinned ref is simply not there.

## 2. Attempt-2 root cause: why `v0.9.7` installs but crashes

**Version-routing mismatch: the newest artifact targets a *newer, pre-release* DSH than the consumer runs.**

From `compat-table.md`:

| Plugin | Targets DSH | Notes |
|---|---|---|
| v0.9.3 | `0.1.1-rc.1` | rc.1-verified; **rc.2 is rc.1 + additive image preprocessing, so v0.9.3 is safe on rc.2** |
| v0.9.7 | `v0.1.2-alpha.1` | Migrated to the alpha.1 client API (views/legacy projection + `useConversation` seat) |

The consumer's runtime is `0.1.1-rc.2` (`dsh-version.txt`). `v0.9.7` was rebuilt against the `0.1.2-alpha.1` client API, whose `useConversation` hook does not exist in the `0.1.1-rc.x` client. On load the slot entry calls `useConversation(...)` and gets `undefined` → `TypeError: useConversation is not a function`. Restarting cannot help: the incompatibility is between the shipped artifact and the runtime's client API, not transient state. The "newest tag" is the right answer to attempt 1's resolution failure but the wrong answer to the runtime — that is the trap.

## 3. Remedy for the consumer right now (runtime frozen at `0.1.1-rc.2`)

The compatible plugin version is **v0.9.3** (targets rc.1; rc.2 is additive-only over rc.1, per the plugin's own compat table). The catch: the public mirror **also lacks the `v0.9.3` tag** (same sync-script defect — its tags stop at `v0.9.1`). So the working install must come from a remote that actually has the tag — the primary origin the mirrors are synced *from*:

```bash
dsh plugin --profile web add '@org/dsh-ui-progress@github:<primary-org>/dsh-ui-progress#v0.9.3'
```

(Use the upstream/origin GitHub org in place of `<primary-org>`; the mirror rewrite in the sync script means the README's `public-org` spelling cannot serve `v0.9.3` today.)

If policy forbids non-mirror sources, the fallback is to ask the maintainer to run a one-off `git push <mirror> refs/tags/v0.9.3` — still no runtime upgrade required for the consumer. What the consumer must **not** do is stay on `v0.9.7` or any `0.1.2-alpha.x`-targeted build.

## 4. Maintainer-side fixes

**Release tooling — distribute tags:**
- Change the sync script to transport tags explicitly, e.g.:
  ```bash
  git push --force-with-lease "$remote" HEAD:main
  git push "$remote" --tags            # or: --follow-tags after annotated-tagged releases
  ```
- Add a post-release verification step that runs `git ls-remote --tags <mirror>` against the intended release tag set (the same evidence as `ls-remote-tags.txt`) and fails the release if any mirror is missing a tag — catches the `v0.9.2–v0.9.6` gap class automatically.

**Docs — route versions to runtimes:**
- Stop pinning a single "newest" tag in the README's default install command. Replace it with a compatibility matrix (the table already exists) plus per-DSH-version install commands, e.g. "on dsh 0.1.1-rc.x → `#v0.9.3`; on dsh 0.1.2-alpha.1+ → `#v0.9.7`".
- Optionally add `peerDependencies`-style/runtime check so a plugin built for `0.1.2-alpha.1` refuses to load on older clients with a clear message instead of `TypeError: useConversation is not a function`.

**CI guard:** run the exact README install command against each supported DSH runtime in CI, so a tag that can't resolve from the documented source, or an artifact that crashes on a documented-compatible runtime, fails the build rather than the consumer.
