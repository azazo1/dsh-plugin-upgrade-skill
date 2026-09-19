# S2 · Negative Scan Report — `@demo/dsh-minimal-llm` 0.1.0 (0.1.1-rc.2 style → dsh 0.1.2-alpha.2)

Read-only static scan of the fixture (`/app/fixture/` in the task container; a static copy of the same files under the benchmark task directory on this host). No file under the fixture was modified, created, deleted, or renamed. The fixture is a static copy (dsh not installed, not executable), so every conclusion below is **static evidence only**; runtime verification steps are listed in §5 as mandatory post-migration work.

## 0. Configuration and dependency inventory (before the touchpoint scan)

| Item | Evidence | Note |
|---|---|---|
| Plugin | `@demo/dsh-minimal-llm` 0.1.0, `private: true`, ESM (`package.json:2-5`) | Host-side Cordis plugin (`main: index.js`, no client face) |
| Host dependency | `@deepseek-ai/dsh-host-apiproxy` `0.0.1-rc.1` (`package.json:17`) | Red flag: the apiProxy package line is exactly the surface removed in the corridor; no `peerDependencies` on `@deepseek-ai/cordis`, no `engines` declared |
| Composition | `cordis.patch.yml:1-3`: one `insert` row `id: minimal-llm`, name `@demo/dsh-minimal-llm`; wired via `dsh.bundle.patch` (`package.json:11-14`) | Official composition overlay, not a source patch (API-08) |
| Install track | registry-style npm package with in-package patch export (`package.json:7-9`) | pack-artifact check needed (API-07: the patch must actually ship in the tarball) |
| Version corridor | `dsh-v0.1.1-rc.2` → `dsh-v0.1.2-alpha.1` (28 cards, DSH-0.1.2-A1-*) → `dsh-v0.1.2-alpha.2` (8 cards, DSH-0.1.2-A2-*) | Net-state rule applied; no removed-then-restored field applies to this plugin |

## 1. Touchpoint checkup — hit / no-hit with evidence

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 source patch / monkey patch | **No** | — | — | `cordis.patch.yml` exists but is profile **composition** (an `insert` row), classified per API-08, not a source patch; no `patch-package`, no `patchedDependencies`, no host source replacement anywhere |
| #2 internal event names / persistent events | **No** | — | — | No `ctx.on(`, `SessionEvent`, `subscribe(`, no `SessionEventMap` augmentation, no `Session.append`; `ctx.effect` at `index.js:7` is a lifecycle registration, not an event subscription |
| #3 internal service probes / Remote | **YES** | `index.js:3` (`export const inject = ["apiProxy"]`), `index.js:9` (`await ctx.apiProxy.llm.providers()`), `package.json:17` | DSH-0.1.2-A1-01 (primary), A1-06/-11/-20/-21/-22/-25/-27/-30/-31/-32, A2-02/-05/-06/-08/-10; ledger API-01 | The apiProxy package/service is removed in the corridor; this plugin runs on the **Host** face |
| #4 direct host directory reads/writes | **No** | — | — | No `readFile`/`writeFile`/`mkdir`/`DSH_HOME`/`.dsh`/`homedir`; `session-notes.js` is pure in-memory string code |
| #5 internal UI / commands / tool registration | **No** | — | — | No `registerCommand`, slots, client runtime, `ctx.tools`, no `dsh.client` usage; the plugin has no client face at all |
| #6 custom HTTP / WS / RPC / DOM / CSS channels | **No** | — | — | No server/socket/router/DOM/CSS code; `console.error` at `index.js:6/10/12` is the plugin's own diagnostic output, not a channel |
| #7 subprocess / stdout / stderr parsing | **No** | — | — | No `child_process`/`spawn`/`exec`; nothing spawns or parses a dsh process. Caveat: the plugin *writes* stderr logs; if any external wrapper parses those lines, that wrapper — not this plugin — owns a #7 surface |

Suspicious-file note: `src/session-notes.js` looks host-coupled by filename ("session"), but `formatSessionNote` (`session-notes.js:2-4`) and `chunk` (`session-notes.js:7-11`) are pure string/array utilities with zero host coupling, and they are not even imported by `index.js`. Zero hits there are genuine, not missed coupling. The fixture's own `README.md` states the plugin "hits only one touchpoint category (#3)" — treated as task material; the conclusions above are derived independently from the cited source lines.

Scan scope: all 5 tracked files (`package.json`, `index.js`, `cordis.patch.yml`, `src/session-notes.js`, `README.md`). No `node_modules`, lockfile, tests, scripts, or CI exist in the fixture — those absence-of-evidence gaps are recorded in §4, not silently assumed clean.

## 2. Hit touchpoints → change-card mapping and required migration

### Hit 1 (the only hit) · `ctx.apiProxy.llm.providers()` on the Host face

- **Current evidence**: `index.js:3` injects `apiProxy`; `index.js:9` calls `ctx.apiProxy.llm.providers()` inside `ctx.effect`; `package.json:17` pins `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1`.
- **How it breaks on 0.1.2-alpha.2**: the apiProxy package/service is gone (removed in the rc.2→alpha.1 corridor, DSH-0.1.2-A1-01 / API-01). Two failure layers: (a) `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` no longer resolves as a host service — the plugin either fails install/typecheck or enters Cordis's waiting state forever on the `apiProxy` injection; (b) mechanically renaming `apiProxy` to `remote` would also hang, because `remote` is a Web-Client-face projection that does not exist for a Host plugin.
- **Target pattern (Host face, per API-01)**: skip the gateway, inject the owning domain service and call its real method:

```js
export const inject = ['llm']

export function apply(ctx) {
  ctx.effect(async () => {
    const providers = await ctx.llm.listProviders()
    console.error('[minimal-llm] llm.listProviders() ->', JSON.stringify(providers).slice(0, 160))
  })
}
```

Old→new ledger for this call: `apiProxy.llm.providers()` → the `llm` domain service's `listProviders()`. The Client-face equivalent `ctx.remote.llm.listProviders()` is **not** applicable here (wrong face). The plugin makes only this one legacy call; any other apiProxy call would need item-by-item confirmation against the `dsh-v0.1.2-alpha.2` tag.

- **Dependency change**: drop `@deepseek-ai/dsh-host-apiproxy` from `package.json:17` (packaging surfaces DSH-0.1.2-A1-24 / A2-03); declare `@deepseek-ai/cordis` as a peerDependency if the host cohort does not already provide it.
- **Composition check** (API-08; no code change expected): the `insert` row `id: minimal-llm` must remain unique across all composed layers; `config` on a matching id is whole-replacement, not deep-merge. The row carries no `config`, so it survives as-is, but verify with `--dump-config` after migration.

Action level: **required** — without this change the plugin does not activate at all on 0.1.2-alpha.2.

## 3. Do the six zero-hit categories prove 0.1.2 compatibility? — Judgment

**No, they do not. Three independent reasons:**

1. **The single hit is itself fatal, so the plugin is *not* compatible as-is.** The premise "it is tiny, so it should have no compatibility problems" fails exactly here: the one #3 hit (`apiProxy`) is a hard removal in the corridor. On 0.1.2-alpha.2 the plugin never finishes activating (stuck waiting on the `apiProxy` injection, or an install/resolution failure on the dead dependency). Zero hits in the other six classes cannot offset a breaking hit in the seventh; the scan's value is per-category evidence, not a majority vote.

2. **Zero hits means "not detected by the current patterns", not "no coupling".** A heuristic source scan over *present* files cannot see: (a) surfaces outside this source tree — the lockfile and resolved cohort (none shipped in the fixture), the actual npm tarball contents (API-07: `exports` ≠ artifact presence, and the `dsh.bundle.patch` file must really ship in the pack), install-time composition precedence over the `minimal-llm` row, and host runtime state; (b) indirect coupling — e.g. an external wrapper parsing this plugin's `console.error` diagnostics (a #7 surface owned elsewhere). Absence of a pattern match in six categories is evidence of absence only for the scanned files and patterns.

3. **A static scan of a non-executable copy cannot cover runtime planes.** The corridor documents failures that appear only at cold load, process boundary, or generation mismatch (API-05 silent-write/loud-read, API-06 process contract, ghost-host pinning). This plugin's own code hits none of them, but a compatibility verdict additionally requires the dependency/config inventory (§0) to be clean and the validation ladder (§5) to pass against the real target cohort.

**Bottom line**: the correct conclusion is *"one required migration (#3 apiProxy → `llm` domain service `listProviders()`, plus dropping the dead dependency and re-checking composition), everything else statically clean, and compatibility unproven until the §5 ladder passes"*. Anything stronger — in either direction ("no problems at all" or "fully compatible after fix #1") — is unsupported by this scan alone.

What else is needed before a compatibility verdict:

- resolved lockfile + install of the exact `dsh-v0.1.2-alpha.2` cohort, with no `0.0.1-rc.1` apiproxy residue anywhere in the tree;
- a no-scripts pack manifest (`npm pack --dry-run --ignore-scripts` or equivalent) proving `cordis.patch.yml` ships in the tarball (API-07/API-08);
- confirmation of which host process generation the plugin will mount into (ghost-host pinning is not derivable from a static copy).

## 4. No-hit notes

Scope: the 5 tracked files listed in §1; no `node_modules`, vendor, tests, CI, or lockfile exist in the fixture to scan. Dependency/configuration surfaces (§0) were checked separately from the seven classes and produced the `package.json:17` finding; it is accounted for under hit #3's dependency change and is not itself a touchpoint-class hit.

## 5. Must verify (mandatory post-migration ladder; proposed, not executed in this task)

1. **Static inventory re-run** on the migrated source: no `apiProxy` residue (inject list, call sites, dependency), corridor net-state re-checked.
2. **Typecheck/build** against the real `dsh-v0.1.2-alpha.2` cohort types — no `any` masking; run once with `skipLibCheck: false` for the migration change.
3. **Pack artifact smoke**: the pack manifest confirms `cordis.patch.yml` and `index.js` are present; resolve runtime JS and any types from the actual artifact in a clean temp install.
4. **Isolated-profile cold boot (loader/config smoke, no credentials)**: isolated `DSH_HOME`, `dsh --profile <isolated> --dump-config` — verify the `minimal-llm` row composes, the id is unique, and unmatched-target diagnostics are clean.
5. **Real mount + functional smoke**: start the isolated profile with the plugin; assert `apply()` runs, the plugin does **not** wait forever on any injection, and `ctx.llm.listProviders()` returns a provider directory (success path), plus at least one failure path so the `try/catch` branch is exercised.
6. Record the three completion states separately: *typecheck passed* ≠ *Loader mount passed* ≠ *real behavior passed*.
