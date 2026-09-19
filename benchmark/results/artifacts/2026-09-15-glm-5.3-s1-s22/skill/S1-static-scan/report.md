# S1 · Static Touchpoint Scan Report — legacy-plugin (dsh 0.1.1 era → dsh 0.1.2-alpha.2)

Read-only scan performed per the `plugin-upgrade` skill (Mode A · inspect) using the
seven-class touchpoint methodology of `references/pre-flight.md`. No file under the fixture
was modified, created, deleted, or renamed; nothing was executed; no install or migration was performed.

## 0 · Configuration and dependency inventory (pre-flight step 0)

Scanned files (complete fixture tree, 6 files, no `node_modules`/vendor/generated artifacts present):

| File | Role |
|---|---|
| `package.json` | package manifest — `legacy-plugin` v0.1.1, `private: true`, ESM, script `apply-patch` |
| `cordis.patch.yml` | profile composition; **also declares a `patch:` source-patch surface** (see #1) |
| `patch.yml` | patch-surface declaration against host source |
| `scripts/apply-patch.mjs` | patch-apply script (also #7) |
| `src/index.ts` | plugin entry (touchpoints #2–#7) |
| `README.md` | fixture documentation |

Findings:

- **Plugin version** `0.1.1` (this is the plugin's own version, not a DSH host pin). The task brief pins the
  corridor as **0.1.1-rc.2 → 0.1.2-alpha.2** (edges: `v0.1.2-alpha.1.md` rc.2→alpha.1, then `v0.1.2-alpha.2.md`
  alpha.1→alpha.2, connected via the corridor index's `from → to` chain, not filename order).
- **No lockfile, no `dsh-plugin.json`, no `peerDependencies`, no `engines`** in `package.json`.
- **Undeclared internal dependency**: `src/index.ts:10` imports `@deepseek-ai/dsh-session-view/internal`
  but `package.json` declares no `@deepseek-ai/*` dependency at all. Already a packaging defect in 0.1.1;
  on 0.1.2 it additionally intersects the removed/split session-view internals (see #5) and the alpha.2
  peer-trimming direction (`DSH-0.1.2-A2-03`: consumers referencing moved type packages must declare them
  directly — informational here, `conditional`).
- The fixture is a static, deliberately non-compiling test fixture; this scan is a static copy review only.

## Corridor folding note (required by the brief)

One removed-then-restored field exists in this corridor: `SessionEvent.ignorable` was **removed in
alpha.1** (`DSH-0.1.2-A1-02`) and **restored in alpha.2** (`DSH-0.1.2-A2-01), which reverts A1-02.
Net state at the target 0.1.2-alpha.2: the producer/persistence/reload/transport retention of
`ignorable: true` for third-party informational events is **available again** — the correct migration is
to **keep the producer marker**, not delete-then-re-add it. A1-02 applies only if an intermediate stop at
exactly alpha.1 were planned (it is not).

## Touchpoint checkup (legacy-plugin, dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 source patch | YES | `cordis.patch.yml:5-6`; `patch.yml:2-6`; `scripts/apply-patch.mjs:5-9` | DSH-0.1.2-A1-03 (required-if-hit) | Patch target is host session-view source, the exact subsystem A1-03 splits up |
| #2 events | YES | `src/index.ts:15-22` | DSH-0.1.2-A2-01 (folds DSH-0.1.2-A1-02) | Producer + observer of third-party informational session event with `ignorable: true` |
| #3 services/Remote | YES | `src/index.ts:25-32` | DSH-0.1.2-A1-01 (required-if-hit); DSH-0.1.2-A2-02 when moving to Remote | Host-plane `ctx.get('apiProxy')` with `session.rename` and `llm.providers` — both in A1-01's ledger |
| #4 host filesystem | YES | `src/index.ts:36-37`; `scripts/apply-patch.mjs:5-6` | DSH-0.1.2-A1-04 (required-if-hit) | Hardcoded `~/.dsh/profiles/default` and `DSH_HARNESS_SOURCE_ROOT`; profiles live under runtime `$DSH_HOME` in 0.1.2 |
| #5 UI/commands/tools | YES | `src/index.ts:10`, `41-43` | DSH-0.1.2-A1-03 (required-if-hit) | Internal import `@deepseek-ai/dsh-session-view/internal` + `registerCommand` returning a `SessionView` |
| #6 custom channel | YES | `src/index.ts:47-53` | DSH-0.1.2-A1-08 (required-if-hit) | Unauthenticated loopback HTTP bridge on 127.0.0.1:43121 bypassing the Connection auth gate |
| #7 subprocess/output | YES | `src/index.ts:57-67`; `scripts/apply-patch.mjs:12-18` | DSH-0.1.2-A1-05 (required-if-hit); DSH-0.1.2-A2-04 (conditional) | Both sites `JSON.parse` headless stdout as JSONL; stdout was already final text in rc.2 and stays final text |

All seven categories hit — there are no no-hit categories for requirement 3. Nevertheless the scope/limits
are recorded below ("Scan scope and limits").

---

## #1 · Source patch / monkey patch — HIT

**Evidence**

- `cordis.patch.yml:5-6` — the composition file declares a `patch:` list pointing at `patch.yml`.
  Note the classification nuance: an *ordinary* `cordis.patch.yml` is profile composition, not a source
  patch (API-08); here it additionally carries an explicit `patch:` surface declaration, which is the hit.
- `patch.yml:2-6` — patch surface targeting host file `src/session/view/SessionView.ts`, replacing
  `export function renderSessionView` with `export function renderSessionViewPatched`.
- `scripts/apply-patch.mjs:5-9` — reads `patch.yml` and is driven by `DSH_HARNESS_SOURCE_ROOT`,
  i.e. a host-checkout patching workflow.

**Card mapping**

- **DSH-0.1.2-A1-03 · "Session view internals split up extensively"** (breaking, touchpoints #1/#5,
  required-if-hit). The patch target (`SessionView.ts`, `renderSessionView`) is inside the session-view
  subsystem that alpha.1 split up extensively; the target path and symbol are not guaranteed to exist in
  the target tag. Recipe: check each host path against an exact-tag compare (`dsh-v0.1.1-rc.2...dsh-v0.1.2-alpha.1`),
  rebuild by owning module, mark unmatched capabilities "pending confirmation" — do not guess new paths.
- **DSH-0.1.2-A1-03 field note precedent**: point `DSH_HARNESS_SOURCE_ROOT` at the target tag and validate
  every patch-surface path by composition.

**Coupling points**: host source path `src/session/view/SessionView.ts`; exported symbol
`renderSessionView`; env var `DSH_HARNESS_SOURCE_ROOT`.

## #2 · Internal/persistent events — HIT

**Evidence**: `src/index.ts:15-19` — producer of a third-party persisted session event
(`type: 'legacy/informational-note'`, `ignorable: true`, payload). `src/index.ts:20-22` — a plain
`ctx.on('session/event', …)` observer (observer role only; no persistence/transport role in this fixture).

**Card mapping (with corridor folding)**

- **Removed in alpha.1**: `DSH-0.1.2-A1-02` — alpha.1 cannot retain the `ignorable` marker on external
  informational events; unknown persisted events are treated as required and reload is rejected.
- **Restored in alpha.2**: `DSH-0.1.2-A2-01` (revert of A1-02) — retention semantics for
  envelope/persistence/reload/transport are back.
- **Net state at target (0.1.2-alpha.2)**: map this hit to **A2-01**. Do **not** delete the producer's
  `ignorable: true` marker and re-add it later (explicitly warned against by A1-02's recipe). A1-02 would
  apply only for an intermediate alpha.1 target, which is not planned.
- A2-01 precision constraints worth planning for: the marker is a *producer/persistence* concern, not a
  consumer-side filter; the public live `Session.append(...)` still has no `ignorable` parameter, so a
  producer seam relying only on that public API is a **capability gap** to mark "pending review" rather than
  faking an entry via cast; unknown events without the marker remain required-on-read (fail closed).
- SQLite note from A2-01 (informational): the SQLite session provider accepts only schema 20 and rejects
  schema 19 without auto-migration — relevant only if this plugin's events live in such a store.

**Coupling points**: `ctx.emit('session/event', { type, ignorable, payload })`; event vocabulary
`legacy/informational-note`; `ctx.on('session/event')` observer.

## #3 · Internal service probes / Remote — HIT

**Evidence**: `src/index.ts:26-27` — `await ctx.get('apiProxy')` then `apiProxy.invoke('session.rename', …)`;
`src/index.ts:30-31` — `apiProxy.invoke('llm.providers')`. This is a **host-plane (server-side)**
consumer (ordinary Cordis plugin shape, `activate(ctx)`).

**Card mapping**

- **DSH-0.1.2-A1-01 · "APIProxy removed, Host/Web Client calls moved to `@Remote`"** (breaking,
  required-if-hit). The `apiProxy` service (rc.2 key `apiProxy`, package `@deepseek-ai/dsh-host-apiproxy`)
  is deleted in alpha.1; both operations are in the card's ledger:
  - `session.rename` → `session/rename`;
  - `llm.providers` → **split into** `llm/listProviders` + `llm/listConfigurableProviders` (one call becomes two results).
- **Plane discipline (A1-01 field notes)**: this plugin is host-plane, so the correct migration is **not**
  `ctx.remote.*` — inject the domain service behind the old facade directly (e.g. `inject: ["llm"]`,
  `ctx.llm.listProviders()`); switching to `inject: ["remote"]` on the host plane stalls with
  `pending (waiting for service: remote)`. `ctx.remote.<ns>.<method>` is the client-plane (browser) face
  and requires a `dsh.client` manifest declaration.
- **DSH-0.1.2-A2-02 · "Remote failures become `RemoteError`; codes gain namespaces"** (breaking,
  required-if-hit on the Remote path): applies to whichever call sites end up on `ctx.remote` after A1-01 —
  handle `RemoteResult<T>` branches, do not branch on old code strings (`session-not-found` →
  `session/not-found`, `cancelled` → `gateway/cancelled`, …), no `instanceof` across realms.
- Not hit in this fixture: A1-20 (`userQuestions.registerProvider`), A1-21 (`resolveSessionPreset`),
  A1-22 (`isTokenDelta`), A2-05 (pluginInventory), A2-06 (`$host` facts), A2-08 (`sessionProjections` peer) —
  no corresponding identifiers appear anywhere in the fixture.

**Coupling points**: service key `apiProxy`; wire operations `session.rename`, `llm.providers`;
dynamic `ctx.get(...)` (no `inject` declaration at all — also a lifecycle defect independent of the corridor).

## #4 · Direct host directory reads/writes — HIT

**Evidence**: `src/index.ts:36-37` — hard-coded `join(homedir(), '.dsh', 'profiles', 'default')` and
`writeFileSync` of `legacy-note.txt` into it. `scripts/apply-patch.mjs:5-6` — `DSH_HARNESS_SOURCE_ROOT`
env-driven host-checkout access.

**Card mapping**

- **DSH-0.1.2-A1-04 · "ACP/SDK examples merged into the `dsh` profile…"** (behavior, touchpoints #4/#7,
  required-if-hit): profiles are composed under the runtime `DSH_HOME` (`$DSH_HOME/profiles`); wrappers
  that "hardcode … fixed profile paths no longer match". Recipe: use the runtime `DSH_HOME`, the target
  profile, and the official launcher as the source of truth; distinguish profile composition from package
  manifests and resolved config; do not hardcode user directories. The fixed `~/.dsh/profiles/default`
  assumption breaks when `DSH_HOME` is redirected (the field note's alpha.2 container test confirms
  profiles resolve under `$DSH_HOME`).
- **DSH-0.1.2-A1-13** (shell/directory-picker workaround fixes): scanned for — no PowerShell/Bash
  persistent-shell or directory-picker workaround code exists in the fixture; **not hit**.
- **DSH-0.1.2-A1-21** (`roots` for agent-presets / CLI preset directory): no `roots` config or
  `resolveSessionPreset` usage; **not hit**.

**Coupling points**: `homedir()/.dsh/profiles/default` path construction; unconditional `writeFileSync`
(no mkdir/ownership handling); `DSH_HARNESS_SOURCE_ROOT`.

## #5 · Internal UI / commands / tool registration — HIT

**Evidence**: `src/index.ts:10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'`
(private Host/Web Client path removed by UI decomposition). `src/index.ts:41-43` —
`ctx.contributes.registerCommand('legacy.openView', …)` returning `new SessionView({ enhanced: true })`.

**Card mapping**

- **DSH-0.1.2-A1-03** (same card as #1; its declared touchpoints are #1 **and** #5): the internal
  session-view import path and the construction of `SessionView` no longer resolve after the split.
  Recipe: rebuild imports by owning module against the exact target tag; if no stable public seam exists for
  what the command returns, mark "pending confirmation" — do not guess; prefer public facets/services.
- Related but **not hit** here (checked): A1-25 (`@deepseek-ai/dsh-client-runtime` removal — no such import),
  A1-26 (registration-id ≠ package name — `cordis.patch.yml` id `legacy-plugin` equals `package.json#name`),
  A1-28/A1-29 (composer/MarkdownText client surfaces — no client code), A1-06 PTC rename (no `tools.mode:
  'code'`, preset id, or `CodeDispatch*` identifiers anywhere), A1-09/A1-10/A1-11 (optional capabilities —
  not applicable).

**Coupling points**: subpath import `@deepseek-ai/dsh-session-view/internal`; symbol `SessionView`;
`ctx.contributes.registerCommand` with a UI-returning handler; undeclared dependency in `package.json`.

## #6 · Custom HTTP/WS/RPC/DOM/CSS channel — HIT

**Evidence**: `src/index.ts:47-53` — `createServer` + `server.listen(43121, '127.0.0.1')`, comment
`http://localhost:43121/api/legacy`; an unauthenticated plain-`200` loopback bridge that "bypasses the
Host Gateway authentication model". The function is never invoked in the static fixture, but the coupling
is present in source.

**Card mapping**

- **DSH-0.1.2-A1-08 · "Web/API channels use process-scoped bootstrap tokens and signed cookies"**
  (security, required-if-hit): 0.1.2 gates the official `/api` Remote/RPC/Fetch routes behind the Connection
  auth gate; private routes that bypass auth become security holes, and "listening on loopback only" is
  explicitly **not** a reason to skip authentication. Custom routes registered with
  `ctx.webServer.register()`/`registerUpgrade()` do not inherit auth/Host-Origin/CORS/TLS; handlers must
  call `ctx.connection.requestRejection(req)` first or move to a Connection-owned carrier/seam.
- **DSH-0.1.2-A1-19** (web-plugin acceptance via boot manifest): no acceptance script, hardcoded bundle
  path, or startup-log parsing exists in the fixture; **not hit** (would matter for the wrapper/e2e lane if
  one is added during migration).

**Coupling points**: `node:http` `createServer`; fixed port `43121`; loopback bind `127.0.0.1`;
route named `/api/legacy` (collides with the now-authenticated `/api` namespace by convention);
no teardown/disposer lifecycle for the server.

## #7 · Subprocess / stdout / stderr parsing — HIT

**Evidence**

- `src/index.ts:57-67` — `spawn('dsh', ['--profile', 'headless', prompt])`; `child.stdout.on('data')`
  `JSON.parse`s each chunk and looks for `event.type === 'final'`. Wrong on two axes: (a) headless stdout
  is the final assistant text, not JSONL — and was already so in rc.2; (b) a `'data'` chunk is an arbitrary
  buffer boundary, not a line, so even a JSONL assumption would mis-split. Success is also never judged by
  exit code.
- `scripts/apply-patch.mjs:12-18` — `execFileSync('dsh', ['--profile', 'headless', 'ping'])` then
  `JSON.parse` per line with the same `event.type === 'final'` expectation (comment in the fixture itself
  admits the expectation is wrong).

**Card mapping**

- **DSH-0.1.2-A1-05 · "Headless: stderr gains a `dsh: reasoning:` segment; stdout remains the final text"**
  (behavior, required-if-hit): treat stdout as the final assistant-text channel; receive
  `dsh: reasoning:` / `dsh: <code>: <message>` on stderr; judge success by exit code (0 complete / 1
  failure-abort-no-completed-turn); **do not `JSON.parse` stdout by default**. The JSONL assumption was
  already wrong for rc.2 — this is a pre-existing wrapper bug the migration must fix, not a 0.1.2 regression.
- **DSH-0.1.2-A2-04 · "Fix empty client graph for `dsh web` on Node.js 24.0–24.11.1"** (fix, conditional,
  touchpoint #7): applies to the wrapper/CI environment rather than these code lines — remove only branches
  with evidence they existed to bypass that Node defect (forcing Node 22, skipping `dsh web`); none exist in
  this fixture, so no action beyond keeping it in the verification matrix (Node 22 LTS + 24.x tiers).
- **DSH-0.1.2-A1-04** also touches #7 (launcher/profile surface of the spawned `dsh` binary): the wrapper
  hardcodes the `dsh` bin and `--profile headless` argv, which remains valid, but cwd/env/DSH_HOME
  assumptions should be re-verified per its recipe (cold-boot + upgrade-boot once each).
- Not hit: A1-13 (no shell/platform workaround parsing), A1-06 (no PTC/code-mode identifiers in argv or
  parsing — the persisted `tool/code-dispatch*` event names are explicitly unchanged by the rename anyway).

**Coupling points**: `spawn`/`execFileSync` of `dsh --profile headless`; per-chunk and per-line
`JSON.parse` of stdout; `event.type === 'final'` protocol assumption; no exit-code handling; stderr
ignored entirely.

---

## Scan scope and limits (requirement 3)

- **Files scanned**: all 6 fixture files listed in section 0 — `package.json`, `cordis.patch.yml`,
  `patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts`, `README.md`. No other source, test, CI, or
  configuration files exist in the fixture; there is no lockfile, no `dsh-plugin.json`, no
  `agent.cordis.yml`/legacy `cordis.yml`, and no `node_modules`/vendor/generated artifacts to exclude.
- **No-hit categories**: none — every one of the seven classes has at least one concrete hit (table above).
  For completeness, within hit classes I ruled out these card couplings with concrete absence evidence:
  A1-06 (no code-mode/PTC identifiers), A1-13 (no shell/directory-picker workarounds), A1-19 (no web
  acceptance script), A1-20/A1-21/A1-22/A2-05/A2-06/A2-08/A2-10 (none of their identifiers —
  `registerProvider`, `resolveSessionPreset`, `isTokenDelta`, `pluginInventory/list`, `$host`,
  `sessionProjections`, `settingsNamespace` — appear anywhere in the fixture), A1-25 (no
  `dsh-client-runtime` import), A1-26 (composition id matches `package.json#name`).
- **Why "no hit ≠ no problem" generally** (and the residual limits of this scan): the pre-flight patterns
  are heuristic regexes over a static copy — line-level search cannot reveal data flow (e.g. where a path
  variable originates) or dynamic service resolution (`ctx.get('apiProxy')` resolves only at runtime);
  the corridor cards are a **curated** list, not a complete API diff, so uncatalogued changes can exist;
  and the fixture itself is non-executable by design. Zero hits in any class would still require checking
  dependencies/configuration and running build, typecheck, a real profile mount, and a functional smoke
  path before claiming compatibility. Here, additionally: the undeclared `@deepseek-ai/*` internal import,
  the missing `inject` declarations, and the absent lockfile mean dependency-resolution and
  enablement-resolution layers cannot be verified from the static copy at all.

## Recommended next steps (planning only — nothing executed)

1. Fix the two pre-existing wrapper bugs regardless of corridor position: headless stdout is final text
   (A1-05) and the loopback bridge needs the Connection auth gate or removal (A1-08).
2. A1-01: replace `apiProxy` with host-plane domain-service injection (not `ctx.remote`); split
   `llm.providers` into the two `llm/*` calls; plan `RemoteResult` error branches (A2-02) for any
   client-plane calls that appear later.
3. A1-03: re-derive the patch surface and the `SessionView` import against the exact
   `dsh-v0.1.2-alpha.2` tag (exact-tag compare + composition validation), marking unmatched seams
   "pending confirmation".
4. A1-04: replace `~/.dsh/profiles/default` with runtime `DSH_HOME` resolution.
5. Events (#2): keep the `ignorable: true` producer per the folded net state (A2-01 over A1-02), and
   record the `Session.append` capability gap for review instead of casting.
6. Validate per the skill's layered checklist: dependency resolution → enablement resolution →
   build/typecheck → real profile cold mount (no pending services) → one functional path → wrapper
   exit-code/stdout/stderr/cancellation behavior.

*Report generated read-only; fixture untouched.*
