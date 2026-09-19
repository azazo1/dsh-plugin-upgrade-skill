# S2 · Negative Scan Report — @demo/dsh-minimal-llm (0.1.1-rc.2 era → 0.1.2-alpha.2)

Task: read-only touchpoint scan of the fixture plugin source; hit/no-hit verdict per the seven
touchpoint classes of `plugin-upgrade` pre-flight.md,
card mapping for hits, and a judgment on whether "no hits" proves compatibility.

- **Mode**: A (inspect, read-only). No file under the fixture was modified; no install, migration, or package script was run.
- **Fixture scanned**: `README.md`, `package.json`, `cordis.patch.yml`, `index.js`, `src/session-notes.js` (5 files, complete tree).
- **Corridor**: `from` pinned by evidence in the source itself — `index.js` carries the comment "0.1.1-rc.2 style", `package.json` depends on `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` (the rc.2 host-plane package). Corridor edges per `references/README.md`: **rc.2 → 0.1.2-alpha.1 → 0.1.2-alpha.2** (cards `DSH-0.1.2-A1-*`, then `DSH-0.1.2-A2-*`; plus the `api-migration-0.1.2-alpha.2.md` ledger). No ghost-host check applies: the fixture is a static copy, no host process is running from it.

## 0. Configuration / dependency inventory

| Item | Value | Note |
|---|---|---|
| Package | `@demo/dsh-minimal-llm` v0.1.0, `private: true`, ESM | test fixture, never publish |
| Entry | `main: index.js`, exports `.` and `./cordis.patch.yml` | plain Cordis plugin, Host face only (no `dsh.client`) |
| DSH dependency | `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` | **removed package**: rc.2 → alpha.1 deletes `dsh-host-apiproxy` (rollup-0.1.2.md removed-package list) |
| peerDependencies / engines | none declared | no explicit host corridor pin — a risk in itself |
| `dsh-plugin.json` | absent | community manifest not adopted |
| Profile composition | `cordis.patch.yml`: one `insert` row (`id: minimal-llm`, `name: "@demo/dsh-minimal-llm"`) | composition overlay, **not** a source patch (API-08) |
| Lockfile / install track | none; static copied source | resolved cohort cannot be verified from the fixture |

## Touchpoint checkup (@demo/dsh-minimal-llm, 0.1.1-rc.2 → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 source patch / monkey patch | No | — | — | The only "patch" hit is the filename `cordis.patch.yml`, which is profile composition and must **not** be classified as a source patch (API-08; pre-flight #1 explicitly warns a filename containing `patch` alone is not a hit) |
| #2 internal events / persistent events | No | — | — | No `ctx.on(`, `SessionEvent`, `session/event`, `subscribe(` anywhere; plugin only observes nothing and produces no persisted events (A1-02/A2-01 therefore inapplicable) |
| #3 internal service probes / Remote | **Yes** | `index.js:2` `export const inject = ["apiProxy"]`; `index.js:9` `await ctx.apiProxy.llm.providers()`; `package.json` dep `@deepseek-ai/dsh-host-apiproxy` | **DSH-0.1.2-A1-01** (primary), **API-01** ledger in `api-migration-0.1.2-alpha.2.md`, rollup-0.1.2 removed-package list, troubleshooting "waiting for service: apiProxy" → A1-01/A1-25 | Definite hit: the `apiProxy` service and its owning package are deleted in alpha.1 and never restored through alpha.2 |
| #4 direct host directory reads/writes | No | — | — | No `DSH_HOME`, `.dsh`, `homedir()`, `readFile"/`writeFile` etc. The plugin performs no filesystem access |
| #5 internal UI / commands / tool registration | No | — | — | No `registerCommand`, slots, `dsh-client-runtime`, client face at all (Host-only plugin; A1-09/A1-10/API-10 inapplicable) |
| #6 custom HTTP / WS / RPC / DOM / CSS channel | No | — | — | No server/WebSocket/DOM; `console.error` logging only (A1-08 auth gate inapplicable) |
| #7 subprocess / stdout/stderr parsing | No | — | — | No `child_process`/`spawn`/`execa`; nothing launches or parses `dsh`. The headless JSONL stdout/stderr card targets headless wrapper layers, not in-host plugins |

**Net: exactly one hit — #3, and it is fatal without migration.**

### Hit detail and required change (#3)

- **How it breaks on 0.1.2-alpha.2**: the `apiProxy` Host-plane facade and the package
  `@deepseek-ai/dsh-host-apiproxy` were removed in alpha.1. The `inject: ["apiProxy"]` row
  stays **pending forever** (`waiting for service: apiProxy`, troubleshooting.md symptom
  table); `ctx.apiProxy.llm.providers()` never resolves. The plugin's `catch` swallows the
  failure into a `console.error` line, so a smoke test that only asserts "no crash" would
  wrongly pass — this matches the A1-01 field note about silently-swallowed errors.
- **Correct migration (Host plane, per A1-01 field note and API-01)**: skip the gateway and
  inject the owning domain service directly — `export const inject = ['llm']` and call
  `ctx.llm.listProviders()` (confirm the exact method contract against the alpha.2 tag's
  generated declarations; the old dotted `llm.providers` key must not be reverse-engineered
  from the Client Remote table). **Do not** mechanically change `apiProxy` → `remote`: `remote`
  exists only on the Client face; on the Host plane it hangs with
  `pending (waiting for service: remote)`.
- **Dependency change**: drop `@deepseek-ai/dsh-host-apiproxy` from `dependencies` (removed
  package; verify the full dependency graph after migration, not just top-level). Keep the
  DSH cohort exact and coherent.
- **Composition**: the `cordis.patch.yml` `insert` row itself needs no change for this card
  (API-08: it is composition); only confirm it still resolves to the migrated package identity.

## Q3: Do the six no-hit categories prove compatibility with 0.1.2?

**No — and for this plugin the conclusion is the opposite of "compatible".**

1. **Zero hits ≠ compatible by construction of the method.** pre-flight.md states explicitly:
   "This is a heuristic scan, not proof of compatibility. Zero hits across the seven classes
   only means 'not detected by the current patterns'; you must still check
   dependencies/configuration and run a build, a real mount, and functional smoke tests."
   The scan is line-pattern based; it cannot reveal data flow, declaration-level drift, or
   dependency-graph breakage.
2. **This fixture is a live demonstration of that**: six of seven categories are clean, yet the
   single #3 hit is a hard breaker — a removed service in `inject` plus a removed dependency
   package. The plugin will not activate at all on 0.1.2-alpha.2, despite looking "tiny and
   surely fine". A "roughly compatible" verdict from the no-hit majority would be wrong.
3. **No-hit categories were checked, not skipped**: each row above records the patterns run and
   why the class is inapplicable (e.g. #1's `cordis.patch.yml` is composition per API-08, not a
   false positive; `src/session-notes.js` is pure string/array utility with zero host coupling —
   the "session" in its filename is historical naming, not an event/persistence touchpoint).

### What is still needed before any compatibility conclusion (mandatory post-migration steps)

Per the brief these are recorded, not executed:

1. **Dependency resolution**: after removing `dsh-host-apiproxy`, scan the full dependency
   graph/lockfile for the old DSH cohort and removed packages (rollup validation layer 1).
   Note the fixture declares **no peerDependencies/engines**, so the host corridor is unpinned —
   recommend adding an explicit `@deepseek-ai/cordis` peer + host compatibility statement.
2. **Static**: build + typecheck against the 0.1.2-alpha.2 cohort (here trivial, but the
   `inject`/call-signature change must compile against real declarations, and the exact
   `llm.listProviders()` contract must be confirmed at the target tag).
3. **Runtime**: cold-boot an isolated profile with the migrated plugin; verify the entry
   activates and no required/provided Cordis service stays pending
   (`skills/plugin-upgrade/scripts/verify-runtime.mjs` runs this end-to-end with failure
   attribution). The pre-migration symptom to watch: `waiting for service: apiProxy`.
4. **Behavior/functional smoke**: assert the providers call **succeeds and returns data** — not
   merely "no crash". The current `catch`-and-log pattern would mask a permanently pending
   service as a clean boot (A1-01 field note).
5. **Wrapper**: exit code, stdout/stderr, teardown of the profile boot.

## Summary

- **Completed**: full read-only scan of all 5 fixture files; corridor pinned rc.2 → alpha.1 →
  alpha.2; one definite hit (#3 internal service/Remote → DSH-0.1.2-A1-01 / API-01) with the
  exact Host-plane migration recipe (`inject: ['llm']`, `ctx.llm.listProviders()`, drop
  `dsh-host-apiproxy`); the six no-hit categories each carry evidence and an inapplicability
  reason.
- **Skipped**: client-face cards (API-10, A2 client cards) — the plugin is Host-face only;
  ghost-host check — static fixture, no running host; baseline build/test — source is a static
  copy, not executable (dsh not installed).
- **Pending/residual risk**: exact `llm` domain-service method contract at alpha.2 must be
  confirmed against generated declarations before implementing; no lockfile/install track in the
  fixture, so the resolved DSH cohort is unverifiable from evidence alone.
- **Rollback**: nothing was changed; no rollback needed. Post-migration work should record the
  baseline (`package.json`, composition row) before editing.
- **Recommendation**: the plugin is **not compatible as-is** with 0.1.2-alpha.2 despite being
  "tiny"; apply the #3 migration, pin the host corridor in `package.json`, and run the
  four-layer validation above before calling it compatible.
