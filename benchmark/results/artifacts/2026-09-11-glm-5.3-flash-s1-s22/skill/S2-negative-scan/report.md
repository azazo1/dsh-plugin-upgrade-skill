# S2 · Negative Scan — Diagnostic Report

**Plugin**: `@demo/dsh-minimal-llm` v0.1.0 (fixture README: "Minimal touchpoint plugin") · **Target**: dsh `0.1.2-alpha.2` · **From cohort**: 0.1.1-rc.2 style (`index.js` line 2: "0.1.1-rc.2 style: injects apiProxy, dot-domain calls"; `package.json` dependency `@deepseek-ai/dsh-host-apiproxy`: `0.0.1-rc.1`).

**Corridor**: `dsh-v0.1.1-rc.2` → `dsh-v0.1.2-alpha.1` → `dsh-v0.1.2-alpha.2` (per `references/api-migration-0.1.2-alpha.2.md`). Scan scope: all 5 files (`README.md`, `cordis.patch.yml`, `index.js`, `package.json`, `src/session-notes.js`), read-only.

---

## 1. Hit / no-hit conclusion per touchpoint category

| Touchpoint | Hit | Evidence | Applicable card |
|---|---:|---|---|
| #1 source patch / monkey patch | **No** (composition only) | `cordis.patch.yml` exists but contains only a profile-composition overlay (`- insert: - id: minimal-llm, name: "@demo/dsh-minimal-llm"`). Per **API-08** ("cordis.patch.yml is composition, not a source patch"), a filename containing `patch` alone is not a hit for this class. No `patchedDependencies`/`patch-package`/monkey-patch patterns anywhere. | API-08 (classification) |
| #2 internal event names / persistent events | **No** | No `ctx.on(`, `SessionEvent`, `Session.append`, `subscribe`, or event-name literals in any file. `index.js` uses only `ctx.effect`. | — |
| #3 internal service probes / Remote | **YES** | `index.js:3` `export const inject = ["apiProxy"]`; `index.js:10` `await ctx.apiProxy.llm.providers()`. This is the host-plane APIProxy facade. Also `package.json` depends on `@deepseek-ai/dsh-host-apiproxy` `0.0.1-rc.1` — one of the 5 packages removed in rc.2 → alpha.1 (**R-05** removed-package list). | **DSH-0.1.2-A1-01**, **API-01**, **R-05**; error-flow follow-up **API-02** |
| #4 direct host directory reads/writes | **No** | No `DSH_HOME`, `.dsh`, `profiles`, `homedir(`, `readFile`/`writeFile`/`mkdir` in any file. | — |
| #5 internal UI / commands / tools | **No** | No `dsh-client-runtime`, `registerCommand`, `ctx.slots`, `useSession`/`useChat`, `dsh.client`, or `__ModuleLoader__`. `src/session-notes.js` is pure string/array utilities (`formatSessionNote`, `chunk`) — the word "session" in its name is only a naming habit (confirmed by its own header comment and the fixture README). | — |
| #6 custom HTTP / WS / RPC / DOM / CSS channels | **No** | No `createServer`, `WebSocket`, `fetch`, `/api/`, `localhost`, DOM/CSS patterns. | — |
| #7 subprocess / stdout / stderr parsing | **No** | No `child_process`/`spawn`/`exec`. The `console.error(...)` calls in `index.js` are plain logging from the plugin process, not subprocess output parsing. | — |

## 2. Hit touchpoints → change cards

**Category #3 (the only hit)** — two coupled changes:

1. **DSH-0.1.2-A1-01 / API-01** (breaking, alpha.1): the APIProxy service key `apiProxy` (type `ApiProxy`, package `@deepseek-ai/dsh-host-apiproxy`) is deleted in alpha.1; "there is no `APIProxy` identifier" at target.
   - The old call `llm.providers` maps to `llm/listProviders` + `llm/listConfigurableProviders` ("one call split into two results") — but that mapping is the **client-plane** projection.
   - **This plugin is host-plane** (an ordinary Cordis server-side plugin composed via a bundle patch, no `dsh.client` in package.json). Per the A1-01 field note: "The correct migration for host-plane apiProxy consumers is to skip the gateway and inject the domain service behind it directly (e.g. `inject: ["llm"]` and then `ctx.llm.listProviders()`)". Mechanically renaming `apiProxy` → `remote` is wrong and stalls at `pending (waiting for service: remote)`.
2. **R-05** (rollup-0.1.2): `dsh-host-apiproxy` is on the removed-package list; the `@deepseek-ai/dsh-host-apiproxy` dependency in `package.json` must be retired and the DSH cohort in dependencies/lockfile moved coherently to the 0.1.2-alpha.2 cohort ("a successful install with mixed old/new peers is not a migration").
3. **API-02 follow-up**: after migration the domain/Remote calls return `RemoteResult`; branch on `result.ok` first instead of only `try/catch`ing — the current `catch (error)` in `index.js` would treat `ok:false` as success under the new flow if a Remote-style call were used.

`cordis.patch.yml` itself needs no source-patch migration (API-08), but its enablement must be re-verified post-upgrade (the patch row must resolve to the migrated package, no duplicate/old source rows).

## 3. Do zero-hit categories prove compatibility? **No.**

**Judgment**: zero hits in categories #1, #2, #4, #5, #6, #7 only mean "not detected by the current heuristic patterns" — the pre-flight header states this verbatim: *"This is a heuristic scan, not proof of compatibility. Zero hits across the seven classes only means 'not detected by the current patterns'; you must still check dependencies/configuration and run a build, a real mount, and functional smoke tests."* The hit in #3 alone already proves this plugin is **not currently compatible** with 0.1.2-alpha.2: `ctx.apiProxy` no longer exists, and the dependency package was deleted, so on 0.1.2-alpha.2 the plugin stalls at `pending (waiting for service: apiProxy)` and its install graph references a removed package.

**What zero hits do tell us**: the migration surface is small and well-mapped — one card (A1-01) plus the dependency cohort bump — with no Web Client face, no events, no channels, no subprocess work. That makes the migration low-risk, not no-verification-needed.

**Still required before concluding compatible** (static copy here; dsh not installed — these are mandatory post-migration steps, not run in this task):

1. **Dependency/enablement resolution**: update `package.json` to the exact 0.1.2-alpha.2 cohort, scan the lockfile for the removed `dsh-host-apiproxy` and the old cohort, verify the target profile composition (`cordis.patch.yml` row) resolves and `--dump-config` shows no pending lines.
2. **Static**: build/typecheck the migrated source; close out `references/precision-checklist.md` for the alpha.2 corridor.
3. **Runtime**: cold boot an isolated real profile (e.g. `scripts/verify-runtime.mjs`) and confirm the plugin's entry activates and nothing remains `pending`.
4. **Behavior**: one functional smoke — a host-plane call `ctx.llm.listProviders()` succeeding (success branch + one failure branch + cancellation, per A1-01's verification requirement).

**Additional notes / residual risk**:

- **Baseline not collected** (Mode C step 0): the fixture is a static, non-executable copy, so the pre-migration mechanical baseline (R-06 exemption list) could not be run; it must be collected in the real repository before any migration write.
- A line-level scan cannot see data flow (pre-flight #4 caveat); here the codebase is tiny enough that manual reading substitutes, but in general this is another reason zero hits ≠ proof.
- The plugin's own version (0.1.0) is independent of the DSH host corridor; after the compatibility change, choose the plugin's own SemVer bump separately (a prerelease like `0.1.1-alpha.0` on an alpha dist-tag per rollup R-04 guidance), never reuse the dsh version number.
