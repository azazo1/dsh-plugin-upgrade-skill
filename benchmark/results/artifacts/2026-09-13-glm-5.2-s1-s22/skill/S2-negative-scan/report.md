# S2 · Negative Scan — @demo/dsh-minimal-llm → dsh 0.1.2-alpha.2

Task type: plugin-upgrade **Mode A · inspect (read-only)**. The fixture was scanned read-only; nothing under the fixture directory was modified, and no migration, installation, or package script was executed.

## 0. Configuration and dependency inventory (pre-flight step 0)

| Item | Value | Evidence |
|---|---|---|
| Plugin identity | `@demo/dsh-minimal-llm` v0.1.0, private, ESM (`type: module`), `main: index.js` | `package.json` |
| Source identity | static local copy (fixture), not a Git checkout, not installed; no lockfile present | fixture directory listing |
| Face | Host Cordis plugin (no client code, no `dsh.client`) | `index.js`, `package.json` |
| DSH dependency | `dependencies: { "@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1" }` — the only `@deepseek-ai/*` entry | `package.json` |
| Manifest | no `dsh-plugin.json` | absent |
| Profile composition | `dsh.bundle.patch: ./cordis.patch.yml` → an `insert` row for the plugin itself | `package.json`, `cordis.patch.yml` |
| Corridor | from = rc-era (service key `apiProxy`, package `@deepseek-ai/dsh-host-apiproxy`) → to = `dsh-v0.1.2-alpha.2`; edges rc.2→alpha.1→alpha.2 per `references/README.md` | cards below |

**Key finding before any touchpoint scan:** the single declared DSH dependency, `@deepseek-ai/dsh-host-apiproxy`, is **deleted in alpha.1** — "alpha.1 deletes that package; there is no `APIProxy` identifier" (v0.1.2-alpha.1.md, DSH-0.1.2-A1-01). This alone makes the plugin **not installable/assemblable on 0.1.2-alpha.2 as-is**, independent of the touchpoint verdicts.

## Touchpoint checkup (@demo/dsh-minimal-llm, rc-era → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 patch | no | — | API-08 (classification note) | `cordis.patch.yml` is profile composition (an `insert` row), not a source patch; a filename containing "patch" alone is not a hit. No `patchedDependencies`/`patch-package`/monkey-patch patterns anywhere. |
| #2 events | no | — | — | No `ctx.on(`, `SessionEvent`, `subscribe(`, or known renamed event keys in `index.js` or `src/session-notes.js`. |
| #3 services/Remote | **yes** | `index.js` lines 2–16: `inject = ["apiProxy"]`, `ctx.apiProxy.llm.providers()` | **DSH-0.1.2-A1-01** (APIProxy removed → Remote; package deleted), **DSH-0.1.2-A2-02** (RemoteError vocabulary for any replacement call), **API-01 ledger** in api-migration-0.1.2-alpha.2.md | The `apiProxy` dot-domain call is the exact rc.2 pattern A1-01 removes. Also note the dependency row in `package.json` is the same break. |
| #4 filesystem | no | — | — | No `DSH_HOME`, `.dsh`, `homedir(`, `readFile`/`writeFile`/`mkdir` calls. |
| #5 UI/commands/tools | no | — | — | No `registerCommand`, `ctx.tools`, `ctx.slots`, `dsh-client-runtime`, or selector use. `src/session-notes.js` exports two pure string/array utilities with no host coupling — the "session" in its filename is a naming habit, not a touchpoint. |
| #6 custom channel | no | — | — | No server/WebSocket/router/DOM/CSS-channel code; no `127.0.0.1`/`localhost`/`/api/` literals. |
| #7 subprocess/output | no (weak) | `index.js` uses `console.error` only | — | No `spawn`/`exec`/`child_process`. Self-emitted stderr log strings only; nobody else's stdout is parsed. |

No-hit notes: scan scope = all 5 fixture files (README.md, package.json, cordis.patch.yml, index.js, src/session-notes.js); no node_modules, tests, scripts, or CI exist in the fixture. Dependency/configuration was inventoried separately (step 0 above) and **does** surface a break the seven classes alone would not flag.

## Hit mapping to change cards

1. **DSH-0.1.2-A1-01 · APIProxy → Remote migration (breaking)** — v0.1.2-alpha.1.md
   - The `apiProxy` service and the `@deepseek-ai/dsh-host-apiproxy` package are gone at the target tag.
   - **Face-specific rule (do not get this wrong):** this is a **Host plugin**, so the correct migration is *not* `ctx.remote` — "the old `apiProxy` is the host-plane facade, `ctx.remote` is the client-plane"; "the correct migration for host-plane apiProxy consumers is to skip the gateway and inject the domain service behind it directly" (A1-01), confirmed by api-migration-0.1.2-alpha.2.md, API-01: a Host plugin that mechanically switches to `remote` **hangs forever**.
   - Concretely for this call: drop `inject: ["apiProxy"]` and the `dsh-host-apiproxy` dependency; `inject: ["llm"]` and call the owning domain service confirmed at the target tag — the ledger's worked example is exactly `llm`/`listProviders()` (API-01 "Current Remote owner pattern" section). Every other legacy APIProxy call must be re-confirmed item by item against the target tag; here there is only this one call.
   - Secondary effect: with strict injection semantics, keeping `inject: ["apiProxy"]` on alpha.2 leaves the plugin **waiting forever** on a service that never appears — a silent no-op, not a crash.
2. **DSH-0.1.2-A2-02 · Remote failures become `RemoteError` (applies to the replacement code)** — v0.1.2-alpha.2.md
   - The current `try/catch` that logs `error.message` is a defensive catch around a service call. After migration, ordinary failures of the successor call must be handled in the result branch (`result.ok` first, then `result.error.code` with `<domain>/<reason>` codes), and assembly faults should surface rather than be swallowed — otherwise a mis-migration renders as "apply() ran but silently did nothing".
3. **API-08 (classification only)** — `cordis.patch.yml` is composition, not a source patch; after migration the `insert` row must still resolve to the (unchanged) package identity `@demo/dsh-minimal-llm`.

## Does "six of seven categories show no hits" mean compatible? **No.**

Judgment: **the zero-hit categories do not establish compatibility with 0.1.2-alpha.2**, for four independent reasons:

1. **The one category that hit is fatal by itself.** #3 hits the single largest breaking change of the corridor (A1-01: APIProxy package and service deleted), and the same break also lives in `package.json`'s dependency list. The plugin as written is neither installable (dependency on a deleted package) nor, even if installed, activatable (strict `inject: ["apiProxy"]` waits forever). "Tiny and only one touchpoint" is exactly the shape that hides a corridor-fatal hit.
2. **A line-level scan cannot see dependency/cohort state.** The dependency break was found in pre-flight step 0 (package.json), not by the seven classes. Per the skill: zero hits only means "not detected by the current patterns"; the dependency graph, lockfile, and cohort coherence must be checked separately, and here they fail.
3. **Cards are a curated list, not a complete API diff.** The corridor edges must still be read end-to-end (rc.2→alpha.1→alpha.2, folded to net state); when a card's API coordinates are missing, the item is marked unsupported/pending rather than assumed safe.
4. **No executable verification has run.** The fixture is a static copy with no dsh host, no build, no typecheck, and no mount. Per the skill's validation layers, compatibility is only proven by: dependency resolution, enablement resolution (composition resolves to the expected package identity), static build/typecheck, a real isolated-profile cold boot with the entry active and no pending required services (`verify-runtime.mjs`), one functional path (here: the providers listing actually returning data), and teardown.

### What is still needed before a compatibility conclusion

- Item-by-item confirmation at the `dsh-v0.1.2-alpha.2` tag that the `llm` domain service exposes the successor to `apiProxy.llm.providers()` (the ledger gives `llm`/`listProviders()` as the Host-side example — confirm against the tag source, not from memory).
- Decide the dependency replacement: the `@deepseek-ai/dsh-host-apiproxy` row must be removed and, if the successor needs one, an exact-cohort `@deepseek-ai/*` peer declared (cohort must be exact and coherent; mixed old/new peers are not a migration).
- Mandatory post-migration verification (not run here, per task rules): build + typecheck; isolated-profile cold boot proving entry activation and that no required/provided service stays pending; one functional smoke test of the providers listing path, asserting it returns data rather than merely "no crash" (the catch-and-log pattern can mask a silent failure); wrapper/teardown check.

## Report per skill structure

- **pre-existing (baseline failures)**: not collected — the fixture is a static read-only copy, not executable; no baseline run was possible or permitted.
- **Completed**: read-only seven-class touchpoint scan with per-class verdicts and evidence; dependency/config inventory; hit→card mapping (A1-01 primary, A2-02 secondary, API-08 classification); corridor determination rc.2-era → alpha.1 → alpha.2; the zero-hits-≠-compatible judgment with basis.
- **Skipped**: no migration implementation, no installs, no builds, no runtime verification — Mode A read-only and the task brief forbid writes outside the report; all verification items are listed as mandatory post-migration steps instead.
- **Pending/residual risk**: (a) successor call for `llm.providers()` confirmed only from the card ledger, not from tag source in this environment; (b) target host cohort/lockfile unknown (no lockfile in fixture); (c) untested on a real alpha.2 host — strict-inject "wait forever" failure mode is inferred from cards, not reproduced.
- **Rollback**: not applicable — no files were changed anywhere in the fixture or benchmark repository; the only write is this report in the designated output directory.
- **Recommendations**: after migration, prefer the owning domain service injection pattern over any gateway round-trip; replace the blanket `try/catch` with `RemoteResult`-style branch handling appropriate to the successor call's return shape; keep `cordis.patch.yml` patched by path with unknown fields preserved; run the skill's full validation ladder before declaring success.

---
*Scan performed with the plugin-upgrade skill (Mode A). Fixture path: benchmark/tasks/S2-negative-scan/environment/fixture (read-only). Report path: test-lhh010/benchmark-runs/glm-5.2-r1/skill/S2-negative-scan/report.md.*
