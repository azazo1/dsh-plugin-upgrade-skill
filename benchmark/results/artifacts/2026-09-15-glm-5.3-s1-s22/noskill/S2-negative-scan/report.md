# S2 · Negative Scan Report — `@demo/dsh-minimal-llm` (0.1.1-rc.2 → 0.1.2-alpha.2)

Scope: read-only static scan of the fixture at `environment/fixture/` (5 files: `README.md`, `cordis.patch.yml`, `index.js`, `package.json`, `src/session-notes.js`). The fixture is a static copy — no build, install, or execution was performed (and none is allowed under the task rules).

Version corridor: `dsh-v0.1.1-rc.2` → `dsh-v0.1.2-alpha.2` (via `dsh-v0.1.2-alpha.1`), per the migration interface ledger for this corridor.

## 1. Seven-touchpoint hit/no-hit table

| Touchpoint | Hit | Evidence | Confidence note |
|---|---:|---|---|
| #1 source patch / monkey patch | No hit | `cordis.patch.yml` exists but contains only an `insert` composition row (id `minimal-llm`, name `@demo/dsh-minimal-llm`) — it is the official Profile composition overlay (API-08), not a source patch. No `patchedDependencies`, `patch-package`, `DSH_HARNESS_SOURCE_ROOT`, or monkey-patching anywhere. | High. A filename containing `patch` alone is not a hit for this class. |
| #2 internal event names / persistent events | No hit | No `SessionEvent`, `session/event`, `ctx.on(`, `subscribe(`, no `SessionEventMap` augmentation, no `Session.append()` usage. `ctx.effect(...)` in `index.js:7` is effect lifecycle, not event subscription. | High. |
| #3 internal service probes / Remote | **HIT** | `index.js:3` `export const inject = ["apiProxy"]`; `index.js:9` `await ctx.apiProxy.llm.providers()` — the legacy APIProxy consumer pattern. Face: Host (plain Cordis plugin entry, no client facet). Additionally `package.json:17` depends on `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1`. | High. Exact legacy pattern named by API-01. |
| #4 direct host directory reads/writes | No hit | No `DSH_HOME`, `.dsh`, `profiles/`, `homedir(`, `readFile`/`writeFile`/`mkdir`/`openPath`. | High. |
| #5 internal UI / commands / tool registration | No hit | No `registerCommand`, `registerView`, `contributes`, `ctx.tools`, `commands.execute`, no `dsh-client-runtime`, `ctx.slots`, `useSession`/`useChat`, no `dsh.client.inject` declaration. | High. |
| #6 custom HTTP / WS / RPC / DOM / CSS channels | No hit | No server/WebSocket/MutationObserver/insertRule, no `router.*`, no `/api/` strings, no `127.0.0.1`/`localhost`. | High. |
| #7 subprocess / stdout / stderr parsing | No hit | No `child_process`, `spawn`, `exec`, no `headless`/`--profile` strings. | High. |

Suspicious-looking file cleared: `src/session-notes.js` ("session" in the name) contains only two pure string/array utility functions (`formatSessionNote`, `chunk`) with no host coupling, no imports, no DSH surface. Zero hits across all seven classes — the filename is a historical naming habit, not a touchpoint.

Dependency/config inventory (class 0, outside the seven): `package.json` has no `peerDependencies` and no `engines`; it declares a runtime `dependency` on `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` (see §2); `dsh.bundle.patch: ./cordis.patch.yml` plus an `exports` entry for `./cordis.patch.yml`.

## 2. Hit touchpoints → change cards

### #3 services/Remote (the single hit)

- **Card**: API-01 (APIProxy migrates by runtime plane) — `DSH-0.1.2-A1-01` cohort. Related cards listed by the pre-flight for #3 also include A1-06/A1-11/…/A2-10, but only the APIProxy-removal card intersects this plugin's actual usage.
- **Current evidence**: `index.js:3,9`; `package.json:17`.
- **Old pattern**: `inject = ["apiProxy"]` + `ctx.apiProxy.llm.providers()` (Host-side dot-domain call through the APIProxy gateway).
- **How it breaks on 0.1.2-alpha.2**: the APIProxy package/service no longer exists. `package.json` pins `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1`, which is not part of the alpha.2 cohort — install/resolution fails or the plugin enters "waiting" forever (injects a service that will never be provided). Mechanically renaming `apiProxy` to `remote` would hang, because `remote` only exists on the Web Client face.
- **Target pattern (Host face, per API-01)**: skip the gateway and inject the owning domain service confirmed at the target tag:
  ```js
  export const inject = ['llm']

  export function apply(ctx) {
    ctx.effect(async () => {
      const providers = await ctx.llm.listProviders()
    })
  }
  ```
  (Confirm the exact method name against the alpha.2 tag's `llm` service declaration before committing; the client-side projection `listProviders` must not be blindly copied to the Host face.)
- **Required config change**: remove/replace the `@deepseek-ai/dsh-host-apiproxy` dependency so all `@deepseek-ai/*` packages land on the exact alpha.2 cohort (packaging cards A1-24 / A2-03).
- **Also verify (API-08, composition)**: since the manifest declares `dsh.bundle.patch`, confirm `cordis.patch.yml` is actually present in the packed artifact (`npm pack --dry-run --json --ignore-scripts`); Node `exports` cannot replace that boundary. The row's `insert` semantics and the whole-config-replacement rule should be checked with `dsh --profile <name> --dump-config` in an isolated profile.

## 3. Do the zero-hit categories prove 0.1.2 compatibility?

**No. Judgment: this plugin is NOT compatible with 0.1.2-alpha.2 as-is** — it has one confirmed breaking hit (#3) plus a stale dependency pin — **and, independently, the six zero-hit categories would not have proven compatibility even if #3 were also clean.**

Basis:

1. **Zero hits ≠ compatible.** The seven-class scan is a heuristic pattern match ("not detected by the current patterns"), not a proof. Its own contract states that zero hits still require checking dependencies/configuration and running build, a real mount, and functional smoke tests. A static copy cannot even be typechecked here (dsh not installed), so no compile-level evidence exists at all.
2. **This fixture demonstrates it concretely**: the plugin looks tiny and clean (only one code touchpoint), yet still requires a real migration (APIProxy → `llm` domain service, dependency re-pinning) and a packaging check (`dsh.bundle.patch` in the tarball). "Tiny and mostly zero-hit" is exactly the profile where a hasty "roughly compatible" conclusion goes wrong.
3. **Coverage gaps of a static scan**: it cannot see (a) whether the resolved dependency graph satisfies the alpha.2 cohort, (b) whether the loader actually mounts the plugin (assembly/inject faults surface only at runtime), (c) behavioral drift (e.g., changed return shapes of `llm.listProviders()`), (d) pack-artifact presence of declared files.

What is still needed before any compatibility conclusion (mandatory post-migration verification ladder, not run in this task):

1. **Build/typecheck** against the alpha.2 cohort with the real `Context` (no `any` masking) — the plugin is plain JS, so at minimum a loader-level syntax/resolution check plus reviewing the new inject surface.
2. **Isolated-profile cold boot / config smoke**: `DSH_HOME` isolated, `dsh --profile <name> --dump-config` to check the composition overlay layers and the `insert` row; no credentials needed.
3. **Real mount + functional smoke**: boot an isolated profile with the migrated plugin, confirm it does not stay in "waiting" (i.e., `llm` is actually provided), and observe `ctx.llm.listProviders()` succeed/fail explicitly.
4. **Artifact smoke**: pack and confirm `cordis.patch.yml` ships in the tarball alongside `index.js`.

## 4. Final summary table

| Hit location | Old interface | Typical symptom | Target interface | Change | Verification status |
|---|---|---|---|---|---|
| `index.js:3` | `inject = ["apiProxy"]` | Plugin waits forever; service never provided | `inject = ['llm']` | Required | Static scan only |
| `index.js:9` | `ctx.apiProxy.llm.providers()` | Runtime TypeError / hang; gateway gone | `ctx.llm.listProviders()` (confirm at target tag) | Required | Static scan only |
| `package.json:17` | `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` | Install/resolution failure against alpha.2 cohort | Remove; align `@deepseek-ai/*` deps to alpha.2 | Required | Static scan only |
| `cordis.patch.yml` + `dsh.bundle.patch` | Composition overlay (not a source patch) | Missing patch file in tarball | Keep as composition; verify pack manifest | Conditional | Unverified (needs pack smoke) |

No fixture files were modified; this report is the only file written.
