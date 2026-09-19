# S2 · Negative Scan Report — `@demo/dsh-minimal-llm` (0.1.1-rc.2 → 0.1.2-alpha.2)

Mode A · inspect (read-only). The fixture at `…/S2-negative-scan/environment/fixture` was scanned read-only; nothing inside it was modified.

## 0. Identity and dependency inventory

| Item | Value | Evidence |
|---|---|---|
| Plugin | `@demo/dsh-minimal-llm` v0.1.0, private, ESM, host-side Cordis plugin (`main: index.js`) | `package.json:2-6` |
| Profile composition | `cordis.patch.yml` exports a single `insert` row for the plugin itself; no `dsh-plugin.json` manifest | `cordis.patch.yml:1-3`, `package.json:7-15` |
| DSH dependency cohort | `dependencies: { "@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1" }` — **the entire cohort is one removed package** | `package.json:16-18` |
| Corridor `from` | Source comments self-declare "0.1.1-rc.2 style"; the corridor is **rc.2 → alpha.1 → alpha.2** via cards `DSH-0.1.2-A1-01` then the alpha.2 API ledger `API-01` | `index.js:2`; skill corridor index |
| Files scanned | `README.md`, `package.json`, `cordis.patch.yml`, `index.js`, `src/session-notes.js` (5 files, full tree) | glob result |

## Touchpoint checkup (@demo/dsh-minimal-llm, 0.1.1-rc.2 → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 source patch / monkey patch | **No** | — | (API-08 note) | `cordis.patch.yml` is profile composition, not a source patch; no `patch-package`, `patchedDependencies`, `DSH_HARNESS_SOURCE_ROOT`, or monkey-patching anywhere |
| #2 internal event names / persistent events | **No** | — | — | No `ctx.on(`, `SessionEvent`, `subscribe(`, or the listed event names; the plugin only registers an `ctx.effect` cleanup |
| #3 internal service probes / Remote | **YES** | `index.js:3` `export const inject = ["apiProxy"]`; `index.js:9` `await ctx.apiProxy.llm.providers()` | **DSH-0.1.2-A1-01** (alpha.1 deletes `@deepseek-ai/dsh-host-apiproxy`; service key `apiProxy` gone) + **API-01** of `api-migration-0.1.2-alpha.2.md` (plane-aware migration) | High confidence — exact identifier match |
| #4 direct host directory reads/writes | **No** | — | — | No `DSH_HOME`, `.dsh`, `homedir()`, `readFile/writeFile` in any file |
| #5 internal UI / commands / tool registration | **No** | — | — | No `registerCommand`, slots, `dsh-client-runtime`, `useSession/useChat`; plugin is Host-plane only |
| #6 custom HTTP / WS / RPC / DOM / CSS channels | **No** | — | — | No `createServer`, WebSocket, router/`/api/` strings, DOM/CSS injection |
| #7 subprocess / stdout / stderr parsing | **No** | — | — | No `child_process`, `spawn`, `execa`, `headless`/`--profile` strings |

Suspicious-looking file cleared: `src/session-notes.js` ("session" in the name) contains only pure string/array utilities (`formatSessionNote`, `chunk`) with zero host coupling and, notably, is not even imported by `index.js` — dead code, no touchpoint.

No-hit notes: scan covered the full 5-file fixture tree (no tests/scripts/CI/config beyond `package.json` + `cordis.patch.yml`); dependency and composition surfaces were checked separately per pre-flight step 0 — and the dependency surface **is** where the breakage lives.

## 1. Hit touchpoint → card mapping and required change

**#3 — `apiProxy` injection and dotted-domain call (breaking).**

- `index.js:3` `inject: ["apiProxy"]` + `index.js:9` `ctx.apiProxy.llm.providers()` is exactly the rc.2-era Host APIProxy facade.
- Card **DSH-0.1.2-A1-01**: alpha.1 deletes the package `@deepseek-ai/dsh-host-apiproxy` and the `apiProxy` service key; rc.2's dotted facade no longer exists.
- Card/ledger **API-01** (alpha.2): migration is **plane-aware**. This is a Host plugin (no `dsh.client` in `package.json`), so the correct target is **not** `inject: ["remote"]` — that is the Client-plane facade and would leave the host fiber stuck at `pending (waiting for service: remote)` (troubleshooting.md documents the `waiting for service: apiProxy` variant of the same failure). The Host-side best practice is to skip the gateway and inject the owning domain service directly, e.g. `inject: ["llm"]` then `ctx.llm.listProviders()` — with the exact method name **confirmed against the target tag's generated declarations**, not reverse-engineered from the Client Remote table.
- Companion change in `package.json`: drop `@deepseek-ai/dsh-host-apiproxy` (removed package) and, if needed for typing, add the concrete domain-service package that owns the confirmed contract. Per the skill, the alpha.2 cohort in `package.json` must stay exact and coherent.
- Behavioral note: the current `try/catch` prints a failure and continues, so a naive "drop-in" would look alive while the provider list never loads; on alpha.2 also prefer branching on `result.ok` for unary Remote-style calls (API ledger "Unary failure" row) — though after moving to a direct domain service this is ordinary service-call semantics.

## 2. Do the six no-hit categories prove compatibility with 0.1.2-alpha.2?

**No. Zero hits across the seven touchpoint classes is "not detected by the current patterns", not compatibility.** Basis:

1. **The one category that did hit already breaks the plugin.** `waiting for service: apiProxy` / a deleted dependency package means this plugin will not even activate on 0.1.2-alpha.2. "Tiny and mostly zero-hit" is exactly the false-comfort case this scan exists to catch.
2. **The touchpoint scan is heuristic by construction.** pre-flight.md states it explicitly: a heuristic scan is not proof of compatibility; zero hits only means "not detected by the current patterns". The scan also cannot see data flow, dead code that a later edit revives (`src/session-notes.js` is currently unreferenced), or indirect coupling arriving through dependencies.
3. **The scan does not cover the dependency/configuration surface.** Those are checked separately (step 0), and here that separate check is what finds the removed `@deepseek-ai/dsh-host-apiproxy` dependency. A touchpoint-only read would have missed packaging-level breakage.
4. **Even a true zero-hit-everywhere plugin still needs runtime proof**: corridor cards are a curated list, not a complete API diff; missing edges must be marked unsupported, and only a build + real mount + functional smoke can close the question.

**What is still needed before concluding compatibility (mandatory post-migration verification, per the brief listed here but not executed):**

- Implement the API-01/A1-01 Host-side change (`inject: ["llm"]`, `ctx.llm.listProviders()`, method confirmed against the alpha.2 tag declarations) and fix the dependency cohort.
- Static: install with the exact alpha.2 cohort, build/typecheck the plugin.
- Enablement: confirm the profile composition actually resolves to this package (no stale rows).
- Runtime: isolated-profile cold boot (skill's `verify-runtime.mjs`) — verify the entry activates and no required/provided Cordis service stays pending.
- Behavior: execute the provider-list path once; assert it returns data rather than a swallowed error (the current catch-and-log pattern can mask failure).
- Wrapper: exit code, stdout/stderr, teardown of the `ctx.effect`.

## Summary

- **Completed**: read-only scan of the full fixture; per-category hit/no-hit table with evidence; hit mapped to **DSH-0.1.2-A1-01 + API-01**; compatibility judgment with basis; verification plan recorded.
- **Skipped**: categories #1, #2, #4, #5, #6, #7 — no pattern hits (evidence above); `src/session-notes.js` cleared as pure utility/dead code.
- **Pending/residual risk**: the exact alpha.2 `llm` service method name must be confirmed against the target tag's generated declarations before writing the migration; `cordis.patch.yml` composition syntax should be re-validated against alpha.2 profile loading during cold boot; no runtime verification was possible (static copy, dsh not installed).
- **Rollback**: not applicable — no files were modified (read-only scan; fixture untouched).
