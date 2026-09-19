# S1 · Static Touchpoint Scan Report — legacy-plugin, dsh 0.1.1-rc.2 → 0.1.2-alpha.2

**Scan mode**: read-only static copy inspection. No file under the fixture was modified, created, deleted, or renamed; no code was executed.

**Corridor construction**: the upgrade edge dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2 is built by following the directed from → to edges of the version-corridor index (never filename order), which yields **two card sets**: v0.1.2-alpha.1.md (DSH-0.1.2-A1-*, 28 cards, rc.2 → alpha.1) and v0.1.2-alpha.2.md (DSH-0.1.2-A2-*, 8 cards, alpha.1 → alpha.2). All hits below are mapped with the **corridor net state** folded: where a field is removed in alpha.1 and restored in alpha.2, the mapping is by the final alpha.2 state, and the intermediate removal card is recorded only as cross-reference (see #2).

## 0. Configuration and dependency inventory (pre-flight step 0)

Scanned files (all fixture files, complete list):

| File | Role |
|---|---|
| `package.json` | manifest; version `0.1.1`, private, ESM |
| `cordis.patch.yml` | profile composition (+ `patch:` declaration referencing `patch.yml`) |
| `patch.yml` | source patch surface |
| `scripts/apply-patch.mjs` | patch-application script (static, do-not-execute) |
| `src/index.ts` | plugin activation source |
| `README.md` | fixture description (not plugin code) |

- `package.json` has **no peerDependencies, no engines, no `dsh.client`, no `dsh-plugin.json`** — yet `src/index.ts:10` imports `@deepseek-ai/dsh-session-view/internal`. The dependency is **undeclared**; a packaging/peer audit (the A2-03 direction: type/runtime packages actually imported must be declared directly) will flag it, and the import itself is an internal-path violation (see #5).
- `cordis.patch.yml` is ordinary profile composition (plugin row `legacy-plugin` + a `patch:` list). Per the corridor classification rule (API-08: `cordis.patch.yml` is composition, not a source patch), the composition file itself is not a #1 hit — but its `patch: [patch.yml]` declaration points at a genuine source-patch surface, which is the #1 hit.
- Install track: not installable by design (static fixture); no lockfile present.

## Touchpoint checkup table (summary)

| Touchpoint | Hit | File/line | Applicable card(s) | Confidence note |
|---|---:|---|---|---|
| #1 source patch | YES | `patch.yml:3-6`; `cordis.patch.yml:5-6`; `scripts/apply-patch.mjs:5-8` | A1-03 (primary); A1-04 (source-root/profile source of truth) | patch target is a session-view internal path split up in alpha.1 |
| #2 events | YES | `src/index.ts:15-22` | **A2-01 (net state)**, cross-ref A1-02 | ignorable removed in alpha.1, restored in alpha.2 → keep producer marker; no delete/re-add |
| #3 services/Remote | YES | `src/index.ts:25-32` | A1-01 (primary), A2-02 | host-plane apiProxy deleted in alpha.1; llm.providers splits into two |
| #4 host directory | YES | `src/index.ts:36-37` | A1-04 (primary), A1-13 (conditional) | hardcoded ~/.dsh/profiles/default; use runtime DSH_HOME |
| #5 UI/commands/tools | YES | `src/index.ts:10`, `src/index.ts:41-43` | A1-03 (primary), A1-25 (import-face relative), A1-26 (conditional) | private /internal import + registerCommand |
| #6 custom channel | YES | `src/index.ts:47-54` | A1-08 | loopback HTTP bypassing the Gateway auth model |
| #7 subprocess/output | YES | `scripts/apply-patch.mjs:12-18`; `src/index.ts:57-66` | A1-05 (primary), A1-04 (secondary), A2-04 (not applicable) | stdout-is-JSONL assumption is wrong already in rc.2 |
## Per-touchpoint detail

### #1 Source patch / monkey patch — HIT

- **Hits**:
  - `patch.yml:3-6` — patch surface targeting host source `src/session/view/SessionView.ts`, replacement `export function renderSessionView` → `renderSessionViewPatched`.
  - `cordis.patch.yml:5-6` — `patch:` list declaring `patch.yml` in the composition.
  - `scripts/apply-patch.mjs:5-9` — reads `DSH_HARNESS_SOURCE_ROOT`, loads `patch.yml`, applies the surface.
- **Coupling points**: the host-internal path `src/session/view/SessionView.ts` and the named export symbol inside it.
- **Card mapping**:
  - **DSH-0.1.2-A1-03** (Session view internals split up extensively; touchpoints #1/#5; required-if-hit). The patched path/symbol belongs to the session-view internals that alpha.1 restructured; the patch target must be re-validated against the exact alpha.2 tag compare, rebuilt per owning module, or marked "pending confirmation" — never guessed.
  - **DSH-0.1.2-A1-04** (touchpoints #4/#7): the script reliance on `DSH_HARNESS_SOURCE_ROOT` plus fixed binary/profile assumptions must be re-pinned to the runtime `DSH_HOME`, the target profile, and the official launcher at the target tag.
- Note: `cordis.patch.yml` as a composition file is classified per API-08 (composition, not a source patch); the hit is the `patch.yml` surface it declares.

### #2 Internal/persistent events — HIT

- **Hits**: `src/index.ts:15-19` — producer: `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: {...} })`, an external informational durable event. `src/index.ts:20-22` — plain observer: `ctx.on('session/event', ...)` logs `event.type` (observer role; no corridor collision by itself).
- **Corridor folding (the key point)**: `SessionEvent.ignorable` is **removed in alpha.1 (DSH-0.1.2-A1-02)** and **restored in alpha.2 (DSH-0.1.2-A2-01)**. Since the migration target is alpha.2, the net state is "marker retained": **map to DSH-0.1.2-A2-01** and do **not** follow A1-02 intermediate advice (do not delete the producer marker now to re-add it later). A1-02 applies only if an intermediate stop at exactly alpha.1 were planned.
- **Residual caution even at alpha.2 (per A2-01)**: the restore covers envelope/persistence/reload/transport retention; the public live `Session.append(...)` still has no `ignorable` parameter. A producer seam that cannot express the marker through a public API must be marked a capability gap, not faked by cast. Unknown events **without** the marker remain required-on-read. If persistence uses the SQLite provider: schema 20 only, no auto-migration from schema 19.

### #3 Internal service probes / Remote — HIT

- **Hits**: `src/index.ts:26` and `src/index.ts:30-31` — `const apiProxy = await ctx.get('apiProxy')` then `apiProxy.invoke('session.rename', ...)` and `apiProxy.invoke('llm.providers', ...)`. Two operations exercised: `session.rename`, `llm.providers`.
- **Card mapping**:
  - **DSH-0.1.2-A1-01** (APIProxy removed; breaking; required-if-hit). The `apiProxy` service key (package `@deepseek-ai/dsh-host-apiproxy`) is deleted in alpha.1. Ledger for the two hit operations:
    - `session.rename` → `session/rename` (Remote namespace `session`);
    - `llm.providers` → **splits into** `llm/listProviders` + `llm/listConfigurableProviders` (one call → two results).
  - **Plane discipline (A1-01 field note)**: this plugin calls `ctx.get('apiProxy')` inside a host-plane `activate()`. The host-plane migration is **not** `ctx.remote.*` (that is the client-plane facade) — the correct host-plane move is to inject the domain service behind the old facade (e.g. `inject: ['llm']`, `ctx.llm.listProviders()`); switching to `inject: ['remote']` on the host plane stalls with `pending (waiting for service: remote)`.
  - **DSH-0.1.2-A2-02** (required-if-hit): once calls resolve to `RemoteResult<T>` (the result shape is unchanged from rc.2), failures are `RemoteError` instances with namespaced codes (`session/not-found`, `session/agent-busy`, `gateway/cancelled`, `gateway/internal`, ...). Do not branch on old un-namespaced code strings or parse `Error.message`; `gateway/cancelled` terminates rather than errors; retry only explicitly-transient + idempotent operations.
- Also recorded: the weak `await ctx.get(...)` probe pattern itself is a corridor-relevant shape (strict inject + weak `ctx.get`), but the concrete collision is the removed `apiProxy` key.

### #4 Host directory reads/writes — HIT

- **Hits**: `src/index.ts:36-37` — `join(homedir(), '.dsh', 'profiles', 'default')` then `writeFileSync(join(profileDir, 'legacy-note.txt'), text)`. Fixed profile path + direct file write.
- **Card mapping**:
  - **DSH-0.1.2-A1-04** (touchpoints #4/#7; required-if-hit): wrappers/plugins that hardcode bins, old process trees, or fixed profile paths no longer match; use the runtime `DSH_HOME`, the target profile, and the official launcher as the source of truth; distinguish profile composition, package manifests, and resolved config.
  - **DSH-0.1.2-A1-13** (conditional): only relevant if this hardcoded path exists as a workaround for platform shell/directory-picker bugs; none is evident here, so no action unless reproduced.
- Data-flow note: the path is fully static (no variable input), so the risk is drift from the runtime home/profile location, not injection.

### #5 Internal UI / commands / tool registration — HIT

- **Hits**:
  - `src/index.ts:10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` (private Host/Web Client path; the fixture comment itself flags it as removed by UI decomposition).
  - `src/index.ts:41-43` — `ctx.contributes.registerCommand('legacy.openView', ...)` constructing `new SessionView({ enhanced: true })`.
- **Card mapping**:
  - **DSH-0.1.2-A1-03** (primary): internal session-view imports and UI registration points no longer resolve; rebuild imports by owning module against the exact-tag compare, or mark "pending confirmation".
  - **DSH-0.1.2-A1-25** (relative): `@deepseek-ai/dsh-client-runtime` removed, client symbols migrated by domain — the same class of internal-import migration; the replacement owner for a session-view symbol must be confirmed from the target tag actual exports, not assumed.
  - **DSH-0.1.2-A1-26** (conditional): client-modules registration id must equal the package.json name — only relevant if this plugin ever ships a browser client module; it currently does not (no `dsh.client`).
- Additional finding (not itself a card collision): the imported package is absent from `package.json` dependencies — an undeclared direct dependency that the corridor packaging direction (A2-03) requires declaring explicitly once the import is rebuilt.

### #6 Custom channel — HIT

- **Hits**: `src/index.ts:47-54` — `startLegacyBridge()` creates a loopback HTTP server on `127.0.0.1:43121` (comment: `http://localhost:43121/api/legacy`). The function is never invoked in the static fixture, but the coupling exists in source.
- **Card mapping**: **DSH-0.1.2-A1-08** (Web/API channels use process-scoped bootstrap tokens and signed cookies; required-if-hit). Consequences:
  - custom routes do **not** automatically inherit Connection auth, the Host/Origin fence, CORS, or TLS; a private loopback route bypassing auth is a security hole, not a safe shortcut — "listening on loopback only" is not a reason to skip authentication;
  - the bootstrap token must be used only for `GET /?token=...`; never placed into `/api`, WS URLs, or Authorization headers;
  - handlers should call `ctx.connection.requestRejection(req)` first, or move to a Connection-owned carrier/seam.
- Lifecycle note: the server handle is returned but no teardown/disposer is registered — a defect to fix during the same migration (registrations are effects).

### #7 Subprocess / output parsing — HIT

- **Hits**:
  - `scripts/apply-patch.mjs:12-18` — `execFileSync('dsh', ['--profile','headless','ping'])`, then `JSON.parse` of each stdout line expecting JSONL events with `type === 'final'`.
  - `src/index.ts:57-66` — `spawn('dsh', ['--profile','headless', prompt])`, `JSON.parse` on stdout data chunks, filter `event.type === 'final'`.
- **Card mapping**:
  - **DSH-0.1.2-A1-05** (primary; required-if-hit): headless **stdout is the final assistant text and was never JSONL — already true in rc.2** (`packages/bundle/headless/src/index.ts:129`). The fixture JSONL assumption is a pre-existing wrong wrapper assumption, not something alpha.1 introduced; the only alpha.1 change is stderr gaining a `dsh: reasoning:` segment. Migration: treat stdout as final text, judge success by exit code (0/1), do not `JSON.parse` stdout; do not treat "stderr non-empty" as failure. Both hit sites must be rewritten.
  - **DSH-0.1.2-A1-04** (secondary): the wrappers hardcode the `dsh` binary + `--profile headless`; binary/profile facts must be re-derived from the runtime (`DSH_HOME`, official launcher) at the target tag. Also note the credential failure mode: headless cold boot without a key reports `dsh: MISSING_CREDENTIAL: ...` — a profile configuration issue, not a plugin/runtime failure.
  - **DSH-0.1.2-A2-04**: reviewed and **not applicable** — it concerns `dsh web` empty client graph on Node 24.0–24.11.1 and workarounds for it; no Node-version workaround branch exists in this fixture.
- Additional parsing defect independent of the corridor: `src/index.ts:61-63` parses each `data` chunk as one JSON value; chunk boundaries do not respect line/JSON framing even under a JSONL contract.

## No-hit categories

**None.** All seven touchpoint categories have at least one hit in this fixture (by design of the S1 fixture). Accordingly, the requirement-3 no-hit evidence procedure is vacuous here; for completeness, the full scan scope was the six fixture files listed in §0 (no node_modules, no CI, no tests, no lockfile exist in the fixture), and the general caveat still applies: a static scan proves detection by these patterns, not compatibility — the migration must still be followed by build/typecheck, real profile mount, and functional smoke tests at the target tag.

## Corridor folding summary

| Field / surface | Intermediate state (alpha.1) | Net state at alpha.2 | Migration action |
|---|---|---|---|
| `SessionEvent.ignorable` | removed (A1-02) | restored (A2-01) | keep the producer marker; map to A2-01; never delete-then-re-add |
| APIProxy service | removed (A1-01) | not restored; client-plane `ctx.remote.$host` facts added (A2-06, client only) | host-plane callers inject domain services directly |
| Remote error shape | plain `{code,message,details}` | `RemoteError` + namespaced codes (A2-02) | branch on `result.error.code` namespaced values |

## Must-verify list (post-migration, beyond this static scan)

1. Patch surface (`patch.yml`) re-validated by composition against the alpha.2 tag source: every old target maps to a target-version file or states an explicit removal reason.
2. Build/typecheck with the rebuilt imports; note tsbuildinfo false positives (clean before diagnosing MISSING_EXPORT).
3. Real profile cold boot + upgrade boot; check `--dump-config` for pending entries.
4. Event reload test: unknown ignorable events survive reload; unknown required events are rejected.
5. Headless wrapper tests: plain-text success, reasoning present on stderr, empty final text, non-zero exit.
