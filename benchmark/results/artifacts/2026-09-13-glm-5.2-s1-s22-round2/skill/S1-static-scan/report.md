# S1 · Static Touchpoint Scan Report — legacy-plugin (dsh 0.1.1 → 0.1.2-alpha.2)

**Mode**: read-only inspection (Mode A / pre-flight scan). No file under the fixture was modified, created, deleted, or renamed; no command was executed from the fixture; nothing was installed.

- **Fixture scanned**: `benchmark/tasks/S1-static-scan/environment/fixture/` (verbatim copy of `skills/plugin-upgrade/examples/legacy-plugin/`, 6 files + this README):
  `README.md`, `package.json`, `patch.yml`, `cordis.patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts`.
- **Corridor**: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2`, connected by the corridor index as two edges:
  rc.2 → alpha.1 (v0.1.2-alpha.1.md, prefix `DSH-0.1.2-A1`) and
  alpha.1 → alpha.2 (v0.1.2-alpha.2.md, prefix `DSH-0.1.2-A2`),
  plus the exact rc.2→alpha.2 interface ledger api-migration-0.1.2-alpha.2.md.
- **Plugin identity**: `legacy-plugin@0.1.1`, private, ESM (`"type": "module"`), no `peerDependencies`, no `engines`, no `@deepseek-ai/*` entries in `package.json` (but `src/index.ts` imports one — see #5). Fixture is explicitly non-installable / non-executable by design.

## Summary

| Touchpoint | Hit | File/line | Applicable cards | Confidence |
|---|---:|---|---|---|
| #1 source patch | YES | patch.yml:3–6; scripts/apply-patch.mjs:5–9; cordis.patch.yml:5–6 | DSH-0.1.2-A1-03; API-08 (classification) | high |
| #2 events | YES | src/index.ts:15–22 | A1-02 + A2-01 folded → net: field **retained** in alpha.2; A2-01 governs | high |
| #3 service/Remote | YES | src/index.ts:26–32 (`ctx.get('apiProxy')`) | DSH-0.1.2-A1-01 (primary); DSH-0.1.2-A2-02 (error flow) | high |
| #4 host directory | YES | src/index.ts:36–37 (`~/.dsh/profiles/default`) | DSH-0.1.2-A1-04 | high |
| #5 UI/commands/tools | YES | src/index.ts:10 (`@deepseek-ai/dsh-session-view/internal`), 41–43 (`registerCommand`) | DSH-0.1.2-A1-03; API-10 / A1-25 context | high |
| #6 custom channel | YES | src/index.ts:47–54 (loopback HTTP :43121) | DSH-0.1.2-A1-08 | high |
| #7 subprocess/output | YES | scripts/apply-patch.mjs:12–18; src/index.ts:57–67 | DSH-0.1.2-A1-05 (primary — wrong JSONL assumption); A1-04; A2-04 (conditional) | high |

All seven classes hit; there is no no-hit category for this fixture (this matches the fixture's own README table, which I used only as cross-validation — every hit below was independently located in source).

---

## #1 · Source patch / monkey patch — HIT

**Evidence**

- `patch.yml:1–6` — a real replacement surface: target `src/session/view/SessionView.ts`, `find: export function renderSessionView` → `replace: export function renderSessionViewPatched`.
- `scripts/apply-patch.mjs:5–9` — reads `patch.yml` and requires `DSH_HARNESS_SOURCE_ROOT`; comment marks it as the patch-surface fixture.
- `cordis.patch.yml:1–6` — profile composition declaring `patch: [patch.yml]`.

**Coupling points & card mapping**

- The `patch.yml` surface patches a host-internal file under the session-view tree → **DSH-0.1.2-A1-03** ("Session view internals split up extensively", touchpoints #1/#5): the target path and the symbol `renderSessionView` must be re-validated against the exact `dsh-v0.1.2-alpha.2` tag compare; there is no guaranteed equivalent owning module. Per the card: mark unmatched targets "pending confirmation", do not guess new paths.
- **API-08** governs classification: `cordis.patch.yml` here is the Loader composition overlay (an ordinary `patch:` row list), **not** itself a source patch — a filename containing `patch` alone is not a hit for this class. The actual source-patch hit is `patch.yml` + `apply-patch.mjs` (real find/replace evidence). Composition rows and the replacement surface need different verification paths (dump-config layering vs. exact-tag apply).

## #2 · Internal events / persistent events — HIT

**Evidence**: `src/index.ts:15–19` produces an external informational durable event:

`ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: {...} })`

and `src/index.ts:20–22` observes `session/event` (plain observer role, no migration action).

**Coupling points & card mapping — corridor folding applies**

- alpha.1 removed `SessionEvent.ignorable` (**DSH-0.1.2-A1-02**); alpha.2 restored it (**DSH-0.1.2-A2-01**, explicitly the revert of A1-02). **Net state at target 0.1.2-alpha.2: the `ignorable` producer/persistence contract is retained.** Therefore the producer code should *not* be changed to drop the marker (do not "delete then re-add"); map this hit to **A2-01** only, and treat A1-02 as superseded intermediate state.
- Residual coupling under A2-01: the public `Session.append(...)` still has no `ignorable` parameter — a plugin restricted to that API must mark the producer seam a capability gap, not fake an envelope cast. Unknown events *without* the marker remain required-on-read (fail-closed). Also note the alpha.2 SQLite provider accepts only schema 20 (relevant if persistence is exercised later).

## #3 · Internal service probes / Remote — HIT

**Evidence**: `src/index.ts:26–32` — two host-plane registrations resolve the legacy service by key and invoke dotted RPC names:

- `await ctx.get('apiProxy')` → `apiProxy.invoke('session.rename', ...)` (line 27)
- `apiProxy.invoke('llm.providers')` (line 31)

**Coupling points & card mapping**

- **DSH-0.1.2-A1-01** (primary): the `apiProxy` service key / `@deepseek-ai/dsh-host-apiproxy` package is deleted in alpha.1. This is a **host-plane** call site (server-side plugin, no `dsh.client` declaration), so per the card's field note the correct migration is to skip the gateway and inject the domain service directly (e.g. `inject: ["llm"]` → `ctx.llm.listProviders()`); switching to `inject: ["remote"]` on the host plane stalls at `pending (waiting for service: remote)`. Wire-name mapping if the client plane is ever needed: `session.rename` → `session/rename`; `llm.providers` → `llm/listProviders` + `llm/listConfigurableProviders` (one call splits into two).
- **DSH-0.1.2-A2-02**: migrated Remote calls return `RemoteResult<T>` whose `error` is a `RemoteError` instance with namespaced codes (`session/not-found`, `gateway/cancelled`, ...); the migrated call sites must branch on `result.ok`/`result.error.code` instead of throwing/defensive catch.

## #4 · Host filesystem — HIT

**Evidence**: `src/index.ts:36–37` — `join(homedir(), '.dsh', 'profiles', 'default')` then `writeFileSync(join(profileDir, 'legacy-note.txt'), text)`.

**Coupling points & card mapping**

- **DSH-0.1.2-A1-04** (touchpoints #4/#7): profiles live under the runtime `DSH_HOME` (`$DSH_HOME/profiles/<name>`); hardcoding `~/.dsh/profiles/default` no longer matches the source of truth. Migration: resolve the home/profile from the runtime environment and the official launcher; do not hardcode user directories.
- Static-scan caveat honored: line search cannot reveal data flow, but here the path is constructed entirely from literals, so the coupling is confirmed at the hit lines.

## #5 · Internal UI / commands / tools — HIT

**Evidence**

- `src/index.ts:10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` (private Host/Web Client internal path; the inline comment itself says "removed by UI decomposition").
- `src/index.ts:41–43` — `ctx.contributes.registerCommand('legacy.openView', ...)` constructing `new SessionView({ enhanced: true })`.

**Coupling points & card mapping**

- **DSH-0.1.2-A1-03**: the session-view internals were split up extensively; both the internal import path and the registration point that consumes it must be rebuilt against owning modules at the exact tag. Per the card, ordinary plugins should migrate to public facets/services; capabilities with no stable public seam are "pending confirmation".
- Context cards (not direct hits, but the same seam): **A1-25** (`@deepseek-ai/dsh-client-runtime` removed; symbols moved per-domain) and **API-10** (client runtime unbundling, keyed chat snapshots, command attachment parameters) apply if this plugin ever declares `dsh.client`; its `package.json` currently declares neither `dsh.client` nor any `@deepseek-ai/*` dependency, so the internal import is also an undeclared-dependency defect independent of the corridor.
- No `dsh-client-runtime`, `PropsRuntime`, `ctx.slots`, `useSession`/`useChat`, `__ModuleLoader__`, or `PLUGIN_ID` usage elsewhere in the fixture (checked `src/index.ts`, `scripts/apply-patch.mjs`, `package.json`).

## #6 · Custom channel — HIT

**Evidence**: `src/index.ts:47–54` — `startLegacyBridge()` creates a loopback HTTP server on `127.0.0.1:43121` (comment: `http://localhost:43121/api/legacy`), bypassing the Host Gateway authentication model. The function is never invoked (`void startLegacyBridge`), but the coupling exists in source.

**Coupling points & card mapping**

- **DSH-0.1.2-A1-08** (security, touchpoint #6): web/API channels now use process-scoped bootstrap tokens and signed cookies; loopback is **not** exempt from authentication. A private unauthenticated route is a security hole even on 127.0.0.1. Migration: route through a Connection-owned carrier/seam, or gate custom routes with `ctx.connection.requestRejection(req)` first (Host/Origin fence, CORS, TLS are not inherited automatically). Port lifecycle/teardown of the raw `createServer` is also unowned today (no disposer), an independent defect.

## #7 · Subprocess / output parsing — HIT

**Evidence**

- `scripts/apply-patch.mjs:12–18` — `execFileSync('dsh', ['--profile','headless','ping'])` then `JSON.parse` each stdout line expecting JSONL events with `type === 'final'`. The file's own comment flags this as "deliberately wrong expectation".
- `src/index.ts:57–67` — `spawn('dsh', ['--profile','headless', prompt])` with `child.stdout.on('data')` → `JSON.parse(line)` filtering `event.type === 'final'`; no exit-code, stderr, or cancellation handling.

**Coupling points & card mapping**

- **DSH-0.1.2-A1-05** (primary): headless stdout is the **final assistant text**, not JSONL — and it was already so in rc.2; alpha.1 additionally adds a `dsh: reasoning:` segment on stderr. Both JSONL parsers are wrong for the whole corridor, not just the target. Migration: read stdout as final text, receive reasoning/`dsh: <code>: <message>` on stderr, judge success by exit code (0/1); never `JSON.parse` stdout by default.
- **DSH-0.1.2-A1-04** (touchpoints #4/#7): wrappers hardcoding bins/old process trees/fixed profile paths no longer match the merged profile layout.
- **DSH-0.1.2-A2-04** (conditional): applies only if this wrapper carries Node-24.0–24.11.1 workarounds (forcing Node 22 / skipping `dsh web`); none are present in the fixture, so no action — recorded for completeness.
- Not hit: **A1-06** (Code Mode → PTC rename) — no `tools.mode: 'code'`, preset id, or `tools/code-dispatch` identifiers appear anywhere in the fixture.

---

## No-hit statement

There is **no no-hit touchpoint category** in this fixture — all seven classes have concrete hits, independently located in the source (the fixture README's table was used only as a cross-check). Accordingly requirement 3 reduces to the scan-scope statement: I scanned all six fixture files in full (source, scripts, both YAML manifests, package.json); excluded nothing except the README itself (documentation). Dependencies/configuration were checked (`package.json` has no peers, engines, or `@deepseek-ai/*` declarations — itself a finding under #5).

Even with seven hits, "hit map complete" cannot be concluded: this is a heuristic static scan of a curated card list, not a proof of compatibility — per the pre-flight preamble, zero (or full) hits still require dependency/lockfile checks, build + typecheck, a real profile mount, and functional smoke tests on the exact target tag before the migration can be called safe. The plugin also cannot be compiled or executed as-is (by design), so no runtime layer was collected.

## Recommended corridor actions (ordered)

1. **A1-05/#7**: drop both JSONL stdout parsers; use stdout-as-final-text + stderr + exit code.
2. **A1-01 + A2-02/#3**: replace `ctx.get('apiProxy')` with direct host-plane domain-service injection; handle `RemoteResult`/`RemoteError` codes if any Remote surface remains.
3. **A1-08/#6**: delete or gate the loopback 43121 bridge behind the Connection auth gate.
4. **A1-04/#4**: replace the hardcoded `~/.dsh/profiles/default` with runtime `DSH_HOME` resolution.
5. **A1-03/#1/#5**: re-validate the `patch.yml` surface and the `@deepseek-ai/dsh-session-view/internal` import against the exact `dsh-v0.1.2-alpha.2` tag; mark unmatched targets "pending confirmation".
6. **A2-01 (folded with A1-02)/#2**: keep the `ignorable: true` producer as-is at the alpha.2 target; do not remove-and-restore.

*Report generated read-only; fixture and benchmark repository untouched.*
