# S1 · Static Touchpoint Scan Report — legacy-plugin (dsh 0.1.1 era → 0.1.2-alpha.2)

- **Mode**: Mode A · inspect (read-only). No file under the fixture was modified, created, or deleted; no build, install, or execution was performed. The fixture's own README states it is a static, non-installable, non-compilable test fixture.
- **Scan scope** (every file in the fixture, 6 files, full text): `README.md`, `package.json`, `patch.yml`, `cordis.patch.yml`, `scripts/apply-patch.mjs` (19 lines), `src/index.ts` (68 lines).
- **Corridor**: per the corridor index, `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2` comprises two edges: `v0.1.2-alpha.1.md` (cards `DSH-0.1.2-A1-01…32`) and `v0.1.2-alpha.2.md` (cards `DSH-0.1.2-A2-01…10`). Interface coordinates come from `api-migration-0.1.2-alpha.2.md` (API-01…API-10). Because the fixture self-identifies as "written in the dsh 0.1.1 era" (`package.json` `"version": "0.1.1"`), earlier-edge cards (`DSH-0.1.1-R1-*`, `DSH-0.1.1-R2-*`) are cited only where the fixture's coupling demonstrably intersects them; they are outside the requested rc.2→alpha.2 mapping and flagged as such.

## 0. Configuration and dependency inventory (pre-flight step 0)

| Item | Value | Note |
|---|---|---|
| Identity | `legacy-plugin` v0.1.1, `"private": true`, `"type": "module"` | registry-external static fixture; not an installable npm package |
| peerDependencies / engines / `@deepseek-ai/*` deps | **none declared** in `package.json` | the DSH dependency cohort is entirely implicit — the source import at `src/index.ts:10` is an undeclared phantom dependency (see A2-03 packaging direction) |
| Manifest `dsh-plugin.json` / `dshClient` / `dsh.client` | absent | no client half is declared; Web-Client-roster cards (A1-25/A1-26) are non-hits by construction |
| Profile composition | `cordis.patch.yml` — a single insert row `{id: legacy-plugin, name: legacy-plugin, config: {}}` plus a `patch:` list referencing `patch.yml` | the row itself is composition (API-08); the `patch:` entry is a source-patch declaration → touchpoint #1 |
| Lockfile / resolved versions | none present | dependency-resolution layer cannot be verified statically; noted as residual risk |
| Scripts | `apply-patch` → `node scripts/apply-patch.mjs` | package script exists; never executed per read-only discipline |

## Summary table

| Touchpoint | Hit | File/line | Applicable card(s) | Confidence |
|---|---:|---|---|---|
| #1 source patch | YES | `patch.yml:2-6`; `cordis.patch.yml:5-6`; `scripts/apply-patch.mjs:5-9` | **DSH-0.1.2-A1-03** (+ API-08 classification) | high — patch target path names the split-up session-view module |
| #2 events | YES | `src/index.ts:15-19` (producer), `:20-22` (observer) | **DSH-0.1.2-A2-01** folded with DSH-0.1.2-A1-02 | high — the fixture is the exact producer shape both cards describe |
| #3 services/Remote | YES | `src/index.ts:26-27, 30-31` (`ctx.get('apiProxy')`, `session.rename`, `llm.providers`) | **DSH-0.1.2-A1-01**, **DSH-0.1.2-A2-02** (on migration); (DSH-0.1.1-R1-04, earlier edge) | high — exact old identifiers from the A1-01 table |
| #4 host directory | YES | `src/index.ts:36-37` (`~/.dsh/profiles/default` hardcoded) | **DSH-0.1.2-A1-04** | high |
| #5 UI/commands/tools | YES | `src/index.ts:10` (`@deepseek-ai/dsh-session-view/internal`), `:41-43` (`registerCommand` + `new SessionView`) | **DSH-0.1.2-A1-03** | high — import is a private internal path |
| #6 custom channel | YES | `src/index.ts:47-54` (loopback HTTP :43121, unauthenticated) | **DSH-0.1.2-A1-08** | high |
| #7 subprocess/output | YES | `scripts/apply-patch.mjs:12-18`; `src/index.ts:57-66` (JSON.parse of headless stdout) | **DSH-0.1.2-A1-05** (+ API-06; A1-04 shared with #4) | high — the fixture's own comment admits the wrong assumption |

All seven categories hit; there is no no-hit category (requirement 3 is answered in "No-hit sub-checks" below instead).

## #1 Source patch / monkey patch — HIT

**Evidence**

- `patch.yml:2-6` — patch surface with `target: src/session/view/SessionView.ts` and a find/replace renaming `export function renderSessionView` → `…Patched`.
- `cordis.patch.yml:5-6` — the composition file carries a `patch:` list referencing `patch.yml`.
- `scripts/apply-patch.mjs:5-9` — requires `DSH_HARNESS_SOURCE_ROOT`, reads `patch.yml`, prints the surface (the applier itself is classified under #7).

**Mapping**

- **DSH-0.1.2-A1-03** (`Session view internals split up extensively`, touchpoints #1/#5, required-if-hit): the patch target `src/session/view/SessionView.ts` is exactly the "session view internals" module the card says was split up in alpha.1. The recipe applies verbatim: check each host path against an exact-tag compare (`dsh-v0.1.1-rc.2...dsh-v0.1.2-alpha.2`), rebuild by owning module, and mark targets with no stable public seam "pending confirmation" rather than guessing new paths. The find-string `export function renderSessionView` must be re-validated even if a file of that name survives.
- **API-08** (`cordis.patch.yml is composition, not a source patch`): classification rule — the insert row in `cordis.patch.yml` is composition and must not be reported as a patch hit by itself; the hit here is the `patch:` declaration plus `patch.yml` + the applier script. A filename containing "patch" alone is not a hit for this class; here the content is a genuine source-patch surface.
- (Earlier edge, outside the requested corridor: pre-flight lists DSH-0.1.2-A1-03 as the #1 card; no R1 card covers patch surfaces. DSH-0.1.2-A1-03's field note — pointing `DSH_HARNESS_SOURCE_ROOT` at the target tag and validating each path by composition — describes precisely what `apply-patch.mjs:5-6` sets up.)

## #2 Internal event names and persistent events — HIT

**Evidence**

- `src/index.ts:15-19` — producer: `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: {…} })`. A third-party informational durable SessionEvent.
- `src/index.ts:20-22` — observer: `ctx.on('session/event', …)` reading `event.type`.

**Mapping — corridor folding (the point requirement 2 asks to think through)**

- The marker `ignorable: true` is **removed in alpha.1** (DSH-0.1.2-A1-02, `SessionEvent.ignorable` temporarily removed) and **restored in alpha.2** (DSH-0.1.2-A2-01, restore for third-party persisted events). Per the corridor rule (README: "if a field is removed in alpha.1 and restored in alpha.2, do not delete and re-add it"), the **final net state for the rc.2→alpha.2 corridor keeps the producer writing `ignorable: true`** — the correct mapping card is **DSH-0.1.2-A2-01**, with **DSH-0.1.2-A1-02** recorded as the folded intermediate edge that matters only if the plugin ever stops at exactly alpha.1. A naive edge-by-edge migration that deleted the marker for alpha.1 would have to re-add it; the folded plan never touches it.
- DSH-0.1.2-A2-01's recipe also carries obligations the fixture currently ignores: write `ignorable: true` **only** for informational events an old reader can omit; the public live `Session.append(...)` has no `ignorable` parameter, so a plugin limited to that API must mark the producer seam a capability gap rather than faking an entry by cast — relevant here because `ctx.emit('session/event', …)` at `:15` is exactly such a producer seam.
- The observer at `:20-22` already reads `event.type` (not `event.kind`), so the earlier-edge contract fix DSH-0.1.1-R1-06 is satisfied; noted only because the fixture predates rc.2 certainty.

## #3 Internal service probes / Remote — HIT

**Evidence**

- `src/index.ts:26-27` — `const apiProxy = await ctx.get('apiProxy')`; `apiProxy.invoke('session.rename', { id, title })`.
- `src/index.ts:30-31` — `apiProxy.invoke('llm.providers')`.
- Face: the calls live in `activate(ctx)` in a Node-side module — a **host-plane (ordinary server plugin)** consumer, not a Web Client.

**Mapping**

- **DSH-0.1.2-A1-01** (`APIProxy removed`, touchpoint #3, required-if-hit): rc.2's service key `apiProxy` (package `@deepseek-ai/dsh-host-apiproxy`) is deleted in alpha.1; both `invoke` calls stop resolving. Per the card's field note, the correct migration for a **host-plane** consumer is *not* `ctx.remote.*` (that is the client-plane facade; swapping names yields `pending (waiting for service: remote)`), but to inject the owning domain service directly behind the gateway:
  - `session.rename` → the session-domain service (Remote projection `session/rename` exists only for the client plane; the host plane goes through the owning service);
  - `llm.providers` → per the A1-01 table the old call **splits into two**: `llm/listProviders` + `llm/listConfigurableProviders` (host plane: `inject: ['llm']`, then the two service methods). A one-to-one rename would silently lose half the result.
- **DSH-0.1.2-A2-02** (`RemoteError`, namespaced codes, required-if-hit on migration): if any call is moved to the Remote plane, failures are `RemoteResult<T>` branches with `RemoteError` codes like `session/not-found`, `gateway/cancelled`; the fixture has no error handling today, so the migration must add `result.ok` branching rather than try/catch.
- API-01 in `api-migration-0.1.2-alpha.2.md` is the precise plane-split ledger for both operations above.
- Earlier edge (outside the requested corridor, flagged): `ctx.get('apiProxy')` on a plugin with no `inject` declaration would also collide with strict injection (DSH-0.1.1-R1-04, rc.8→rc.1); the fixture declares no `inject` at all, so whichever service replaces apiProxy must be declared.

## #4 Direct host directory reads/writes — HIT

**Evidence**

- `src/index.ts:36-37` — `join(homedir(), '.dsh', 'profiles', 'default')` hardcoded, then `writeFileSync(join(profileDir, 'legacy-note.txt'), text)`. Fixed user-directory write assuming the profile is literally `default` under `~/.dsh`.

**Mapping**

- **DSH-0.1.2-A1-04** (touchpoints #4/#7, required-if-hit): wrappers that hardcode "old process trees, or fixed profile paths no longer match"; the recipe is to use the runtime `DSH_HOME`, the target profile, and the official launcher as the source of truth and "not hardcode user directories". The fixture hardcodes both the home (`~/.dsh`) and the profile name (`default`) and additionally performs an unguarded `writeFileSync` with no ownership of the directory's existence. Pre-flight's note applies: the line-level hit is the path construction; the data flow (text → file) was traced and confirmed.
- DSH-0.1.2-A1-21 (preset `roots` paths) and A1-13 (shell/directory-picker workarounds) were checked and are not hit: no `roots` config, no `resolveSessionPreset`, no platform-shell workaround code exists in the fixture.

## #5 Internal UI / commands / tool registration — HIT

**Evidence**

- `src/index.ts:10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` (the file's own comment: "private Host/Web Client path removed by UI decomposition"). Undeclared in `package.json` (phantom dependency).
- `src/index.ts:41-43` — `ctx.contributes.registerCommand('legacy.openView', …)` returning `new SessionView({ enhanced: true })`.

**Mapping**

- **DSH-0.1.2-A1-03** (touchpoints #1/#5): the private `/internal` import path of the session-view package is removed by the alpha.1 split-up. Recipe: rebuild imports by owning module against the exact tag; a capability with no stable public seam (constructing the host's own view object inside a command handler) is "pending confirmation" — do not guess the new owning package. Ordinary plugins should migrate to public facets/services instead of internal imports.
- Packaging corollary: when the import is rebuilt, the owning package must become a declared dependency — today it is a phantom (`package.json` declares nothing), which after the cohort move surfaces under **DSH-0.1.2-A2-03** (declare the type/runtime packages actually imported).
- Non-hits verified: no `dsh-client-runtime` import or `dsh.client.inject` (A1-25 non-hit), no `dsh.client` declaration so the roster-scan contract (A1-26) does not apply, no `useSession`/`useChat`/`MarkdownText`/composer DOM (A1-28/A1-29 non-hits), no PTC/code-mode strings (A1-06 non-hit), no `userQuestions.registerProvider` (A1-20 non-hit), no `settingsNamespace` (A2-10 non-hit).

## #6 Custom HTTP / WS / RPC / DOM / CSS channels — HIT

**Evidence**

- `src/index.ts:47-54` — `createServer(…)` + `server.listen(43121, '127.0.0.1')` with a comment marking the endpoint `http://localhost:43121/api/legacy`; the handler answers unconditionally (`response.end('legacy')`) with no authentication, Host/Origin check, or teardown (the server is created by `startLegacyBridge`, never invoked, and never disposed). Fixed port, no ownership of EADDRINUSE.

**Mapping**

- **DSH-0.1.2-A1-08** (process-scoped bootstrap tokens and signed cookies, touchpoint #6, required-if-hit): the card explicitly rejects "listening on loopback only" as a reason to skip authentication, and the fixture's own comment concedes it "bypasses the Host Gateway authentication model". Migration direction per the card: either retire the private bridge in favor of Connection-owned carriers/routes, or wire custom routes through `ctx.connection.requestRejection(req)` first; the bootstrap token must never appear in `/api`, WS URLs, or Authorization headers. Teardown/port lifecycle must become reversible (disposer), which the fixture lacks entirely.

## #7 Subprocess / stdout / stderr parsing — HIT

**Evidence**

- `scripts/apply-patch.mjs:12-18` — `execFileSync('dsh', ['--profile', 'headless', 'ping'])`, then `JSON.parse` of every stdout line expecting `{type:'final', text}` events.
- `src/index.ts:57-66` — `spawn('dsh', ['--profile', 'headless', prompt])`; `child.stdout.on('data', …)` JSON-parses **each chunk** and captures `event.text` when `event.type === 'final'`; resolves on close with no exit-code inspection, no stderr consumption, no cancellation, no error rejection.

**Mapping**

- **DSH-0.1.2-A1-05** (Headless stdout/stderr contract, touchpoint #7, required-if-hit): rc.2's headless stdout was **already the final assistant text and never JSONL** — so the fixture's JSONL assumption is wrong even at the corridor's *from* edge; alpha.1's only change is that stderr gains a `dsh: reasoning:` segment. The fixture violates the card's recipe on every axis: it `JSON.parse`s stdout (will throw on plain text), treats presence of structured events as the success signal instead of the exit code (0 success / 1 failure), and ignores stderr entirely (loses reasoning; the `dsh: <code>: <message>` error channel). The `src/index.ts` variant is doubly wrong: parsing per-`data` chunk ignores stream fragmentation. Both call sites need: read stdout as final text (or use a documented structured entrypoint), consume stderr, branch on exit code, and add cancellation/teardown.
- **API-06** (`api-migration-0.1.2-alpha.2.md`) pins the exact argv/output contract; the fixture's positional form `dsh --profile headless <text>` is a valid shape per that ledger — the breakage is purely in output interpretation, not argv.
- **DSH-0.1.2-A1-04** (shared with #4): the wrapper hardcodes profile assumptions; use runtime `DSH_HOME`/profile as source of truth.
- DSH-0.1.2-A2-04 (Node 24.0–24.11.1 loader workaround) checked: no Node-version workaround branch exists in the fixture — non-hit.

## No-hit sub-checks (per card), and why "no hit ≠ no problem"

All seven touchpoint classes hit, so there is no no-hit *category*; the following card-level non-hits were still verified by scanning all six fixture files:

- **DSH-0.1.1-R1-01/02/03** (repository-plugins, `dshClient`→`dsh.client`): no repository rows, no `dshClient`/`dsh.client` field, no `dsh-plugin.json` — but this is partly vacuous: the fixture declares *no* packaging metadata at all, which itself blocks any Web-side enablement and cannot be validated statically.
- **DSH-0.1.1-R1-08/09, A1-06** (`tasks.peek`, `httpServer`→`webServer`/`tasks`→`jobs`, PTC rename): zero occurrences of `tasks`, `httpServer`, `webServer`, `jobs`, `code-dispatch`, `tools.mode`.
- **A1-07, A1-09…A1-12, A1-14, A1-19…A1-23, A1-27…A1-32, A2-05/06/08/10**: no matching identifiers/imports (`web_fetch`, `isTokenDelta`, `resolveSessionPreset`, `pi-ai`, `connection.api`, `connectWorkspace`, `pluginInventory`, `$host`, `sessionProjections`, `settingsNamespace`, …).
- **Why no-hit cannot be trusted**: the skill's pre-flight states zero hits only mean "not detected by the current patterns". This fixture has no lockfile, no declared dependency cohort, and no test/build entry point, so dependency resolution, enablement resolution, and runtime behavior are **unverifiable statically**; the corridor cards are also a curated list, not a complete API diff. Mandatory follow-up before any real migration: baseline build/typecheck, exact-tag compare of the patch target, cold-boot of a real profile with entry activation, and one message → tool → response flow (per the skill's validation ladder).

## Consolidated migration implications (read-only findings, no changes made)

1. **A1-03 dominates**: the patch surface (`patch.yml`) and the private import (`src/index.ts:10`) both point into the session-view internals that alpha.1 split up; both need exact-tag re-validation, and the `SessionView`-in-command capability is "pending confirmation".
2. **A1-01 + A2-02**: both `apiProxy` call sites are dead on alpha.1+; host-plane fix is direct domain-service injection, with `llm.providers` splitting into two calls and Remote-plane results needing `RemoteResult` branching.
3. **A2-01 folded with A1-02**: keep `ignorable: true` on the informational event producer — net corridor state restores it; only an alpha.1 intermediate stop would require suspending the producer.
4. **A1-08**: the loopback bridge is unauthenticated by design and must be retired or gated.
5. **A1-05/API-06**: both headless stdout JSONL parsers are wrong for the whole corridor (including its from-edge) and must move to final-text stdout + exit-code + stderr handling.
6. **A1-04**: hardcoded `~/.dsh/profiles/default` write must move to runtime `DSH_HOME`/profile resolution.

## Rollback / discipline record

- Baseline: fixture untouched (task grades fixture-vs-git-HEAD identity; no writes performed inside it or anywhere in the benchmark repository). Only this report file was written, to the designated output directory.
- No installs, no lifecycle scripts, no version fetches, no executions of fixture code.
