# S8 · Release Routing Trap — Diagnosis Report

## Evidence reviewed (read-only fixture)

- `ls-remote-tags.txt` — tag listing on the public mirror `public-org/dsh-ui-progress`: `v0.1.0 … v0.9.1`, then `v0.9.7`. **No `v0.9.2`–`v0.9.6`**, in particular no `v0.9.5` and no `v0.9.3`.
- `sync-script.sh` — the release sync script pushes only `HEAD:main` (with `--force-with-lease`) to each mirror; it never pushes tags.
- `compat-table.md` — plugin↔DSH routing: `v0.9.3` → npm `@deepseek-ai/dsh@0.1.1-rc.1` (rc.2 is rc.1 + additive image preprocessing, so v0.9.3 works on rc.2); `v0.9.7` → `dsh-v0.1.2-alpha.1` (migrated to the alpha.1 client API, "views/legacy projection + `useConversation` seat").
- `dsh-version.txt` — consumer runtime: **dsh 0.1.1-rc.2** (production freeze; cannot upgrade).

## 1. Attempt-1 root cause: why `#v0.9.5` could not resolve

This is a **tag-distribution defect in the release sync script**, not a consumer network/command problem. The sync script only rewrites install-source orgs and force-pushes `HEAD:main` to each mirror; it never runs `git push --tags` / `--follow-tags`. The mirror tag listing confirms the consequence: the tag sequence jumps from `v0.9.1` straight to `v0.9.7` — every intermediate release tag (`v0.9.2`–`v0.9.6`, including the `v0.9.5` the README pinned) exists only on the maintainer's local repo (or origin), never on the public mirrors the README tells consumers to install from. pnpm resolves `github:public-org/dsh-ui-progress#v0.9.5` against the mirror's refs; with no such ref, resolution fails immediately.

## 2. Attempt-2 root cause: why `v0.9.7` installed but crashed

The only tag the mirror *does* have beyond v0.9.1 is `v0.9.7` (evidently pushed out-of-band), so the pinned install now resolves and installs. But `v0.9.7` is **built against the newer DSH `0.1.2-alpha.1` client API** (it consumes the `useConversation` seat / views-legacy projection). The consumer runs **dsh `0.1.1-rc.2`**, whose client runtime predates that API — the hook simply doesn't exist there, so the plugin's slot entry throws `TypeError: useConversation is not a function`. Restarting dsh cannot help: the artifact's compatibility direction is wrong for the consumer's frozen runtime. The plugin version targeting the consumer's runtime is **`v0.9.3`** (built for `0.1.1-rc.1`; rc.2 differs only additively, per the compat table).

## 3. Remedy for the consumer right now (works on dsh 0.1.1-rc.2)

Preferred, if the maintainer (re)pushes the tag or it exists on any reachable remote:

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

However, the mirror tag listing shows **`v0.9.3` is also missing from the mirrors** (same tag-distribution defect). The remedy that works without any maintainer action and on the current runtime is to pin the **commit SHA of the v0.9.3 release** (from the repo history / origin), since commit refs are present on `main` even when tags are not:

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#<full-sha-of-v0.9.3-commit>'
```

The consumer must **not** stay on `v0.9.7`: it targets dsh `0.1.2-alpha.1` and will keep crashing on `0.1.1-rc.2`. Only when the production freeze lifts and dsh is upgraded to `0.1.2-alpha.1+` should `v0.9.7` be used.

## 4. Maintainer-side fixes so both defects cannot recur

**Release tooling (defect 1 — tag distribution):**
- Change `sync-script.sh` to push tags alongside the branch, e.g. `git push --force-with-lease "$remote" HEAD:main --follow-tags` (or explicitly `git push "$remote" --tags` for full history), for every mirror — and add a post-sync verification step that `git ls-remote --tags <mirror>` contains every tag in the local release history (fail loud on a missing ref).
- Gate releases: a release checklist/CI job that fails if the README-pinned version tag is absent from all published mirrors.

**Version routing / docs (defect 2 — compatibility direction):**
- Never point the README's *default* install command at the newest tag unconditionally. Default-pin to the tag targeting the **currently shipped stable dsh runtime** (here `v0.9.3` for the `0.1.1-rc.x` line), and publish the alpha-targeting builds (`v0.9.7` for `0.1.2-alpha.1`) under an explicitly labeled pre-release/cutting-edge install command.
- Keep the compat table (plugin version ↔ dsh version) in the README authoritative and add an install-command-per-DSH-version matrix so consumers on frozen runtimes can self-route.
- Optionally encode the requirement in the plugin manifest/package.json (engines-style dsh version constraint) so an incompatible install fails loud at load time instead of crashing in the browser slot.

## Summary

- Attempt 1: sync script pushes only `main`, never tags → intermediate tags (`v0.9.5`) absent from mirrors → unresolvable ref.
- Attempt 2: `v0.9.7` targets dsh `0.1.2-alpha.1`; consumer is on `0.1.1-rc.2` → `useConversation` doesn't exist there → TypeError in the slot entry.
- Consumer remedy: install `#v0.9.3` (or its commit SHA, since the tag is also missing) — compatible with `0.1.1-rc.2`; avoid `v0.9.7` until the runtime freeze lifts.
- Maintainer fix: push and verify tags in the sync script; route README install defaults by consumer DSH version with an explicit compat matrix.
