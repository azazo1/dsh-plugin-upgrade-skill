# S2 · Negative Scan — Diagnostic Report

Plugin: `@demo/dsh-minimal-llm` 0.1.0 (static copy at `fixture/`, read-only)
Corridor: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2` (the source is 0.1.1-rc.2-style; target is dsh 0.1.2-alpha.2)
Method: read-only scan of all 5 fixture files against the seven touchpoint classes (pre-flight.md) and the corridor change cards (v0.1.2-alpha.1.md, v0.1.2-alpha.2.md).

## Scan scope

Files scanned: `README.md`, `cordis.patch.yml`, `package.json`, `index.js`, `src/session-notes.js`. No `node_modules`, no lockfile, no tests present. Source identity: private npm-style package, main entry `index.js`, ESM (`"type": "module"`), Host-plane ordinary Cordis plugin (no `client.js`, no `dsh.client` key).

## 1) Touchpoint-by-touchpoint verdicts

| # | Class | Verdict | Evidence |
|---|---|---|---|
| 1 | Source patch / monkey patch | **No hit** (composition only) | `cordis.patch.yml` exists, but it contains only `- insert: - id: minimal-llm, name: "@demo/dsh-minimal-llm"` — profile composition, not a source patch. Per API-08 ("cordis.patch.yml is composition, not a source patch"), a filename containing `patch` alone is not a hit for this class. No `patchedDependencies`, `patch-package`, `DSH_HARNESS_SOURCE_ROOT`, or monkey-patch patterns anywhere. |
| 2 | Internal event names / persistent events | **No hit** | No `ctx.on(`, `SessionEvent`, `subscribe(`, `session/event`, `connection/reset`, `tool/code-dispatch` in any file. `index.js` registers only `ctx.effect(...)`. |
| 3 | Internal service probes / Remote | **HIT** | `index.js` line 3: `export const inject = ["apiProxy"]`; line 9: `await ctx.apiProxy.llm.providers()`. `package.json`: `"dependencies": { "@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1" }`. Face: Host-plane ordinary plugin (comment in file says "0.1.1-rc.2 style: injects apiProxy, dot-domain calls"). |
| 4 | Direct host directory reads/writes | **No hit** | No `readFile`/`writeFile`/`mkdir`/`openPath`, no `DSH_HOME`, `.dsh/`, `profiles/`, `homedir(` anywhere. |
| 5 | Internal UI / commands / tool registration | **No hit** | No `registerCommand`, `registerView`, `contributes`, `ctx.tools`, `ctx.slots`, `useSession`/`useChat`, `dsh-client-runtime`, `__ModuleLoader__`; no client bundle at all (no `client.js`, no `dsh.client` in `package.json`). |
| 6 | Custom HTTP / WS / RPC / DOM / CSS channels | **No hit** | No `createServer(`, `WebSocket`, `router.`, `/api/`, `localhost`/`127.0.0.1`, DOM/CSS hooks in any file. |
| 7 | Subprocess / stdout / stderr parsing | **No hit** | No `node:child_process`, `spawn(`, `execSync`, `execa`, `--profile`/`headless` argv handling. The `console.error(...)` lines in `index.js` are plugin-side logging, not subprocess output ownership. |

False-positive note: `src/session-notes.js` looks suspicious by name but has zero hits — it exports pure utilities (`formatSessionNote`, `chunk`) with no host coupling surface; the "session" in the filename is only historical naming. Do not map it to any session/event card.

## 2) Hit touchpoints → change cards

Class #3 maps to the rc.2 → 0.1.2-alpha.2 corridor:

- **DSH-0.1.2-A1-01** (breaking, touchpoint #3, required-if-hit): "APIProxy removed, Host/Web Client calls moved to `@Remote`". The card's identifier note states exactly this plugin's coordinates: "rc.2's service key is `apiProxy` (type `ApiProxy`, package `@deepseek-ai/dsh-host-apiproxy`); alpha.1 deletes that package; there is no `APIProxy` identifier." Both the injected service key (`inject: ["apiProxy"]`) and the dependency (`@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1`) therefore break at alpha.1+.
  - Migration for this plugin (host-plane, per the card's field note): do **not** switch to `inject: ["remote"]` — that is client-plane only and would hang as `pending (waiting for service: remote)`. Instead inject the owning domain service directly: `inject: ["llm"]` and call `ctx.llm.listProviders()`. Note the old `llm.providers` call was split: `llm.providers` → `llm/listProviders` + `llm/listConfigurableProviders` ("One call split into two results") — decide which of the two (or both) the plugin actually needs.
  - `package.json`: remove `@deepseek-ai/dsh-host-apiproxy` from dependencies (the package no longer exists in the target cohort) and align the DSH cohort exactly.
- **DSH-0.1.2-A2-02** (breaking, touchpoint #3, required-if-hit) applies **only conditionally** here: if any migrated call ends up going through the Remote/`RemoteResult` surface, error handling must use the namespaced `RemoteError` codes (e.g. `gateway/cancelled`, `gateway/internal`), never `instanceof` or parsed messages. Since the recommended host-plane fix injects `llm` directly and skips the gateway, this card is a watch item, not a required edit.
- Composition check (adjacent to class #1): keep `cordis.patch.yml` as composition per API-08 and verify it still resolves against the 0.1.2-alpha.2 profile; no card removes the `insert` operation, so no edit is implied, only verification.

## 3) Do the zero-hit categories prove compatibility with 0.1.2? — No.

**Judgment: zero hits ≠ compatible. The static scan alone cannot clear this plugin for 0.1.2-alpha.2.** Basis:

1. The pre-flight doc says so itself, in its header: "This is a heuristic scan, not proof of compatibility. Zero hits across the seven classes only means 'not detected by the current patterns'; you must still check dependencies/configuration and run a build, a real mount, and functional smoke tests."
2. The corridor cards say the same thing: the card sets are "a curated list, not a complete API diff". Zero hits only means no *known, card-covered* surface was touched.
3. This very plugin demonstrates why: it has exactly **one** hit, and that hit is fatal — the entire host plane it injects (`apiProxy` / `@deepseek-ai/dsh-host-apiproxy`) was deleted in alpha.1. A scan that stopped at "five of seven categories are clean" would have shipped a plugin that never activates.
4. Un-scanned surfaces remain: no lockfile exists in the fixture, so cohort coherence (`@deepseek-ai/*` versions after the dependency swap) is unverified; the Cordis plugin protocol surface (`inject`/`apply`/`ctx.effect`) is assumed stable but only a real mount proves the service key `llm` resolves in the target cohort.

**What is still required before concluding (mandatory post-migration verification, not run here):**

- Dependency resolution: after replacing `@deepseek-ai/dsh-host-apiproxy` with the correct direct dependency, install in an isolated directory and scan the full lockfile for the removed package and any old-cohort leftovers (rollup R-06 baseline discipline; A2-03 pitfalls — no mixed old/new peers).
- Static: build/typecheck the migrated source; confirm `inject: ["llm"]` against the target tag's generated declarations.
- Runtime: cold-boot a real, isolated dsh 0.1.2-alpha.2 profile with this plugin mounted; verify the entry activates and `llm` does not remain pending (e.g. via `verify-runtime.mjs`).
- Functional smoke: execute the plugin's one core path — a successful `ctx.llm.listProviders()` (plus, if needed, `listConfigurableProviders()`), covering the success branch and one failure branch (A1-01 verification requirements).
- Enablement: confirm the target profile's composition points at `@demo/dsh-minimal-llm` via `cordis.patch.yml` with no duplicate/old rows.

Bottom line: the plugin is **small and its migration is well-defined by a single card (DSH-0.1.2-A1-01)**, which is favorable — but "no compatibility problems" is only provable after the dependency swap plus build, real mount, and functional smoke all pass, not from the scan.
