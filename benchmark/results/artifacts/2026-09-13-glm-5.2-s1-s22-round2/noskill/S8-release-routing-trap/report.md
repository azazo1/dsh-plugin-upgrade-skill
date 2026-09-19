# S8 · Release Routing Trap — Diagnosis Report

## Evidence reviewed (fixture, read-only)

- `ls-remote-tags.txt` — tag listing on the public mirror `public-org/dsh-ui-progress`: `v0.1.0 … v0.9.1, v0.9.7`. Notably **`v0.9.5` is absent**, and there is a gap `v0.9.1 → v0.9.7` (v0.9.2–v0.9.6 missing).
- `sync-script.sh` — the post-release mirror sync script pushes **only the branch**: `git push --force-with-lease "$remote" HEAD:main` for each of `origin public mirror2`. It never pushes tag refs.
- `compat-table.md` — plugin↔DSH compatibility:
  - `v0.9.3` ↔ `npm @deepseek-ai/dsh@0.1.1-rc.1` (rc.1 real-boot verified; rc.2 is rc.1 + additive image preprocessing)
  - `v0.9.7` ↔ `dsh-v0.1.2-alpha.1` (migrated to the alpha.1 client API: views/legacy projection + `useConversation` seat)
- `dsh-version.txt` — the consumer's actual runtime: **`dsh 0.1.1-rc.2`**.
- README default install pins `#v0.9.5`.

## 1. Attempt-1 root cause — why `#v0.9.5` could not resolve

This is a **tag-distribution defect in the release tooling, not a consumer problem**. The consumer's command targeted the public mirror (`github:public-org/dsh-ui-progress`), and the mirror's tag list does not contain `v0.9.5` (it jumps v0.9.1 → v0.9.7). The sync script is the cause: after every release it pushes only `HEAD:main` to each mirror and **never pushes `refs/tags/*`** (no `--tags`, no `--follow-tags`, no explicit tag-ref push). Tags reach mirrors only accidentally/manually — which is also why the mirror happens to have `v0.9.7` but is missing the intermediate tags. pnpm therefore cannot resolve the pinned `#v0.9.5` ref on that remote and fails immediately.

## 2. Attempt-2 root cause — why `v0.9.7` installs but crashes

The compatibility direction is **plugin artifact → DSH runtime** (each plugin build targets a specific DSH client API generation). `v0.9.7` was migrated to the **`dsh-v0.1.2-alpha.1` client API** (views/legacy projection + the `useConversation` hook). The consumer runs **`0.1.1-rc.2`**, an older client API generation whose bundle does not export `useConversation`. So the newest tag is *newer than the runtime supports*: the plugin's client half calls an API that does not exist on 0.1.1-rc.2, producing `TypeError: useConversation is not a function` in the slot entry. Restarting dsh cannot help — it is a static API mismatch, not a stale-load problem. This is a **version-routing failure**: "newest tag" ≠ "compatible tag".

## 3. Remedy for the consumer right now (runtime frozen at 0.1.1-rc.2)

Pin the plugin to the release line verified against 0.1.1-rc.x — **`v0.9.3`** (rc.1 real-boot verified; rc.2 is additive on top of rc.1, so it remains compatible):

```
dsh plugin --profile web add '@org/dsh-ui-progress@github:public-org/dsh-ui-progress#v0.9.3'
```

(`v0.9.3` is present on the mirror per `ls-remote-tags.txt`, so this resolves.) Then restart dsh / reload the Web client so the old crashed slot registration is replaced. Do **not** use `#v0.9.7` until the runtime is upgraded to `dsh-v0.1.2-alpha.1`+.

## 4. Maintainer-side fixes

**Release tooling (`sync-script.sh`):**
- Push tags to every mirror alongside the branch, e.g. `git push --force-with-lease "$remote" HEAD:main --follow-tags` (or explicitly `git push "$remote" --tags` / the specific released tag ref).
- Add a post-sync verification step that fails the release if `git ls-remote --tags <mirror>` does not contain the just-released tag on **each** mirror — this turns silent tag skew into a loud failure instead of a consumer-facing pnpm resolution error.

**Docs / routing:**
- The README's default install command must pin a version chosen from the compatibility table, not blindly the newest tag; better, document per-runtime install lines, e.g. "on dsh 0.1.1-rc.x use `#v0.9.3`; on dsh-v0.1.2-alpha.1+ use `#v0.9.7`".
- Keep the compat table (`dsh-version ↔ plugin tag`) mandatory in every release checklist, and stop publishing client-API migrations (like the `useConversation` alpha.1 migration) as patch-level bumps on the same line consumers auto-pin — either cut a minor/major line per supported DSH API generation or ship dual-built artifacts so the installer can route by runtime version.
