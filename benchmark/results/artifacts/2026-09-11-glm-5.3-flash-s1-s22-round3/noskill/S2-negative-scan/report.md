# S2 · Negative Scan — Compatibility Report for `@demo/dsh-minimal-llm` → dsh `0.1.2-alpha.2`

Scope: read-only static scan of the fixture (files: `README.md`, `package.json`, `cordis.patch.yml`, `index.js`, `src/session-notes.js`). Target corridor: `0.1.1-rc.2 → 0.1.2-alpha.2` (through the `0.1.2-alpha.1` edge). Nothing under the fixture was modified; no installs or migrations were executed.

## 1. Hit / no-hit conclusion per touchpoint category

Touchpoint classes per the seven-class pre-flight: (1) source patches, (2) events / persistent events, (3) services / Remote, (4) host directory read/write, (5) UI / commands / tools, (6) custom HTTP/WS/RPC/DOM/CSS channels, (7) subprocess / stdout / stderr.

| # | Category | Verdict | Evidence |
|---|---|---|---|
| 1 | Source patches (`cordis.patch.yml` / profile composition) | **No hit** (one adjacent caveat) | `cordis.patch.yml` contains only `- insert: - id: minimal-llm, name: "@demo/dsh-minimal-llm"` — a plain insert with no `require`, no removed manifest fields, no `dshClient`/client-merge keys. Caveat: if this row ever gains `require: ['apiProxy']` it would hang forever on 0.1.2 ("pending (waiting for service: apiProxy)", troubleshooting → cards A1-01/A1-25) — it does not today. |
| 2 | Events / persistent events | **No hit** | No `ctx.on`, no event names, no `SessionEventMap` usage anywhere in `index.js` or `src/session-notes.js`. |
| 3 | Services / Remote | **HIT — the only real hit** | `index.js:3`: `export const inject = ["apiProxy"]`; `index.js:9`: `await ctx.apiProxy.llm.providers()`. Also `package.json:17`: dependency `"@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1"` — the very package the corridor deletes. |
| 4 | Host directory read/write | **No hit** | No `fs`, no path handling, no host directory APIs in any file. |
| 5 | UI / commands / tools | **No hit** | No tool/command registration, no client face, no `dsh.client` in `package.json`, no client entry file. |
| 6 | Custom HTTP/WS/RPC/DOM/CSS channels | **No hit** | No fetch/WebSocket/RPC/DOM/CSS usage; only `console.error` logging of the plugin's own state. |
| 7 | Subprocess / stdout / stderr | **No hit** | No child-process or stream APIs. `console.error` is the plugin's own logging, not a subprocess touchpoint. |

Decoy check: `src/session-notes.js` looks suspicious by filename ("session") but contains only pure utility functions (`formatSessionNote`, `chunk`) with no host coupling — **zero hits**, confirmed. Its own comment states: "Pure utility functions; they touch no host coupling surface."

## 2. Mapping hits to change cards

The single hit maps to:

- **DSH-0.1.2-A1-01 · "APIProxy removed, Host/Web Client calls moved to `@Remote`"** (breaking; touchpoints #3, indirectly #1; action level required-if-hit). Identifiers section: "rc.2's service key is `apiProxy` (type `ApiProxy`, package `@deepseek-ai/dsh-host-apiproxy`); alpha.1 deletes that package; there is no `APIProxy` identifier." The fixture depends on exactly that deleted package at `0.0.1-rc.1` and calls `llm.providers`.
  - Table row for this exact call: `llm.providers` → `llm/listProviders` + `llm/listConfigurableProviders` — "One call split into two results."
  - **Plane matters**: the fixture is a Host-plane (server-side) Cordis plugin (`inject` / `apply(ctx)` in `index.js`, no `dsh.client`). Per the card's field note, the correct host-plane migration is to **skip the gateway and inject the domain service directly**: `inject: ["llm"]`, then `ctx.llm.listProviders()` / `ctx.llm.listConfigurableProviders()`. Mechanically renaming to `inject: ["remote"]` hangs forever ("pending (waiting for service: remote)").
- **Corollary obligations** raised by the same hit:
  - The deleted `@deepseek-ai/dsh-host-apiproxy` dependency row must be removed from `package.json` **and** the lockfile (corridor-level rule: scan the full lockfile for the old DSH cohort and removed packages, not only top-level dependencies; "a plugin that builds only because it depends on a removed SDK package" fails mid-migration).
  - **DSH-0.1.2-A2-02** (Remote error flow): if any call migrates to a Remote plane, unary calls return `RemoteResult<T>` with `ok` / `error.code`; the fixture's current `try/catch → error.message` pattern must become checking `result.ok` and preserving `code`/`details` rather than blind-retrying.

## 3. Do the zero-hit categories prove compatibility? — No.

**Judgment: zero hits in six of seven categories does NOT establish compatibility with 0.1.2.** Basis:

1. **Zero hits are negative evidence about a heuristic scan, not positive proof.** The pre-flight scan is explicitly heuristic; the skill states "zero hits still require checking dependencies/imports and running build plus a real mount." A grep-class scan cannot see parameter drift, changed callback shapes, or descriptor-level wire changes ("all-green static checks cannot prove the wire contract" — rollup note on A1-01).
2. **The plugin already has one confirmed breaking hit (#3).** It is definitively *not* compatible as-is: on 0.1.2-alpha.2, `inject: ["apiProxy"]` stays pending forever and the `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` package no longer exists. "Everything else is clean" cannot offset a required-if-hit card.
3. **Cards are a curated list, not a complete API diff** — absence of a card is itself not proof; corridor edges with missing API coordinates must be marked unsupported/pending rather than assumed fine.
4. **The plugin is tiny, which lowers risk but does not zero it** — e.g. a hosted-dependency version conflict or a profile-composition issue surfaces only at mount time.

**What is still required before concluding (mandatory post-migration verification steps; not run here — static scan only):**

1. **Baseline first**: in the plugin's own dependency state, run build/typecheck/tests and record pre-existing failures as an exemption list (R-06); the migration must not add or worsen failures.
2. **Dependency resolution**: apply the A1-01 recipe (`inject: ["llm"]`, split `llm.providers` into `listProviders` + `listConfigurableProviders`), remove the `@deepseek-ai/dsh-host-apiproxy` row, and confirm the lockfile holds no old-cohort/removed-package residue; keep the DSH cohort exact and coherent in `package.json` and lockfile.
3. **Static layer**: typecheck + build of the migrated plugin; the migrated `inject: ['llm']` must resolve against the target tag's actual service name.
4. **Runtime layer**: cold-start an isolated real DSH profile (dedicated profile / `verify-runtime.mjs`) and verify the entry activates and no required service remains pending — the classic failure here is `pending (waiting for service: …)` from a wrong injection name.
5. **Behavior layer**: one core path — trigger the provider-listing effect and confirm the success branch logs providers; per A1-01's verification requirement, cover the success branch, one business failure code, and cancellation for each migrated call.
6. **Composition check**: confirm the target profile's composition resolves to the migrated package identity (`cordis.patch.yml` insert present, no duplicate or old rows).

Only after these layers pass can "compatible with 0.1.2-alpha.2" be stated. Until then the honest conclusion is: **one required breaking change (DSH-0.1.2-A1-01), six categories zero-hit, compatibility unproven pending the verification steps above.**
