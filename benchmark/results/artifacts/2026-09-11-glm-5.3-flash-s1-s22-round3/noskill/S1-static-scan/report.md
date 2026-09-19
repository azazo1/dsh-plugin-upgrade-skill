# S1 · Static Touchpoint Scan Report — legacy-plugin (dsh 0.1.1 → 0.1.2-alpha.2)

- **Scope**: read-only static scan of `environment/fixture` (verbatim copy of `skills/plugin-upgrade/examples/legacy-plugin/`). No file under the fixture was modified, created, or deleted; no migrations or installs were executed.
- **Corridor**: dsh 0.1.1-rc.2 → 0.1.2-alpha.1 (card set `DSH-0.1.2-A1`) → 0.1.2-alpha.2 (card set `DSH-0.1.2-A2`). Edges were connected by the `from → to` fields of the version card sets (v0.1.2-alpha.1.md: `from: dsh-v0.1.1-rc.2, to: dsh-v0.1.2-alpha.1`; v0.1.2-alpha.2.md: `from: dsh-v0.1.2-alpha.1, to: dsh-v0.1.2-alpha.2`), never by filename order, and net changes were folded before mapping.
- **Files scanned (complete inventory, 6 files)**: `README.md`, `cordis.patch.yml`, `patch.yml`, `package.json`, `scripts/apply-patch.mjs`, `src/index.ts`.

**Corridor folding rule applied.** Where a field/behavior is removed in an intermediate corridor version and restored in the target, it is judged by the **final net state**, not the intermediate removal. One folding case exists in this corridor: `SessionEvent.ignorable` (removed by `DSH-0.1.2-A1-02`, restored by `DSH-0.1.2-A2-01`). Details under touchpoint #2.

---

## Touchpoint #1 — Source patch / monkey patch: **HIT**

**Hit files / lines**
- `patch.yml:2-6` — declares a `surface` patching `src/session/view/SessionView.ts`, replacing `export function renderSessionView` with `export function renderSessionViewPatched`.
- `cordis.patch.yml:5-6` — profile composition mounts the patch via `patch: [- patch.yml]`.
- `scripts/apply-patch.mjs:5-8` — reads `patch.yml` and resolves the host source via `DSH_HARNESS_SOURCE_ROOT` (the same composition-validation seam cited by card A1-03's field note).

**Coupling points**
1. Patch **target path** `src/session/view/SessionView.ts` is a host-internal session-view source path. Card **DSH-0.1.2-A1-03** ("Session view internals split up extensively", Type: breaking, Touchpoints **#1, #5**, action required-if-hit): "Patch target paths, internal imports, or UI registration points no longer work"; every old target must map to a target-version file or an explicit removal reason via an exact-tag compare.
2. Patched **symbol** `renderSessionView` is host-internal; the alpha.1 view split gives no guarantee it survives.

**Card mapping**: **DSH-0.1.2-A1-03** (primary; net hit in alpha.2 — no alpha.2 card restores these internals, so the removal stands in the net state).

## Touchpoint #2 — Internal/persistent events: **HIT** (with corridor folding)

**Hit files / lines**
- `src/index.ts:13-19` — `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: ... })`: producer of a **third-party persisted informational SessionEvent** carrying the `ignorable: true` marker.
- `src/index.ts:20-22` — `ctx.on('session/event', ...)`: an internal event-name listener.

**Coupling points and card mapping (folding)**
- **DSH-0.1.2-A1-02** ("`SessionEvent.ignorable` temporarily removed", Touchpoints **#2**, action required-if-target-is-alpha.1): on alpha.1, first-party readers would reject the persisted `legacy/informational-note` event on reload.
- **DSH-0.1.2-A2-01** ("Restore `SessionEvent.ignorable` for third-party persisted events", Type: fix, Touchpoints **#2**, action required-if-hit) explicitly reverts A1-02 and is its listed revert target.
- **Net state for the alpha.2 target**: the `ignorable` marker is **retained**, so the correct action is **no removal and no re-add churn** — keep `ignorable: true`; do not delete the producer marker and then restore it (exactly the anti-pattern A1-02's recipe warns against: "first read DSH-0.1.2-A2-01 to compute the corridor net state; do not delete the producer marker and then restore it"). Residual alpha.2 obligations from A2-01: the marker must be preserved as-is by JSONL/SQLite/API transports and the generated catalog; the SQLite provider accepts only schema 20 and rejects schema 19 (back up/rebuild before upgrading); the public live `Session.append(...)` still has no `ignorable` parameter — if this producer seam only exists via that API, record a capability gap rather than faking the field with a cast. The fixture's own comment (`src/index.ts:14`: "alpha.1 removed the ignorable marker; alpha.2 restored its producer/persistence contract") already encodes the folded conclusion.

## Touchpoint #3 — Internal service / Remote: **HIT**

**Hit files / lines**
- `src/index.ts:25-28` — `ctx.register('rename-session', ...)` → `await ctx.get('apiProxy')` → `apiProxy.invoke('session.rename', { id, title })`.
- `src/index.ts:29-32` — `ctx.register('list-providers', ...)` → `ctx.get('apiProxy')` → `apiProxy.invoke('llm.providers')`.

**Coupling points**
1. The **service key `apiProxy`** (type `ApiProxy`, package `@deepseek-ai/dsh-host-apiproxy`) — card **DSH-0.1.2-A1-01** ("APIProxy removed, Host/Web Client calls moved to `@Remote`", Type: breaking, Touchpoints **#3**; indirectly #1, required-if-hit): alpha.1 deletes that package; there is no `APIProxy` identifier. Net state: still removed in alpha.2 (no restore card).
2. Old operation `session.rename` → new Remote `session/rename` (`ctx.remote.session.rename`), per A1-01's migration table.
3. Old operation `llm.providers` → split into `llm/listProviders` **+** `llm/listConfigurableProviders` (one call becomes two results), per A1-01's table.
4. Plane caveat from A1-01's field note: this fixture is a **host-plane** (server-side) plugin, so the correct migration injects the domain service behind the proxy directly (e.g. `inject: ["llm"]`, `ctx.llm.listProviders()`; session rename via the session domain service), **not** `inject: ["remote"]` — that yields `pending (waiting for service: remote)`. Only browser-plane plugins use `ctx.remote.*`.
5. Downstream alpha.2 coupling: **DSH-0.1.2-A2-02** ("Remote failures become `RemoteError` instances; error codes gain namespaces", Touchpoints **#3**) applies to whatever replaces these calls once they cross a Remote seam — branch on `result.ok` / `result.error.code` with namespaced codes (e.g. `session/not-found`), never on old plain-code strings or `instanceof`.

**Card mapping**: **DSH-0.1.2-A1-01** (primary), **DSH-0.1.2-A2-02** (downstream error-model change on the migrated seam).

## Touchpoint #4 — Direct host directory reads/writes: **HIT**

**Hit files / lines**
- `src/index.ts:34-38` — `ctx.register('write-note', ...)` computes `join(homedir(), '.dsh', 'profiles', 'default')` and `writeFileSync`es `legacy-note.txt` into it.

**Coupling points**
- Hard-coded **fixed profile path** `~/.dsh/profiles/default` assumed to be the Host profile directory. Card **DSH-0.1.2-A1-04** ("ACP/SDK examples merged into the `dsh` profile, standalone demo bins and packages removed", Touchpoints **#4, #7**, required-if-hit): "Wrappers that hardcode these bins, old process trees, or **fixed profile paths** no longer match"; recipe: use the runtime `DSH_HOME`, the target profile, and the official launcher as the source of truth, and "do not hardcode user directories". (Its 2026-08-30 alpha.2 container field note confirms profiles live under `$DSH_HOME/profiles`.)

**Card mapping**: **DSH-0.1.2-A1-04** (touchpoint #4 leg).

## Touchpoint #5 — Internal UI / commands / tool registration: **HIT**

**Hit files / lines**
- `src/index.ts:9-10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` (private internal subpath import).
- `src/index.ts:40-43` — `ctx.contributes.registerCommand('legacy.openView', () => new SessionView({ enhanced: true }))` (private UI/command registration instantiating the internal view).

**Coupling points**
1. The `/internal` export path of `dsh-session-view` — card **DSH-0.1.2-A1-03** (Touchpoints **#1, #5**): "internal imports, or UI registration points no longer work"; recipe: rebuild imports by owning module against an exact-tag compare; capabilities without a stable public seam must be marked "pending confirmation", not guessed. Net state in alpha.2: still removed (no restore card).
2. The command contribution surface wiring an internal component — same card, plus A1-03's guidance to prefer public facets/services.
3. Ruled out but adjacent: **DSH-0.1.2-A1-25** (`dsh-client-runtime` removal) — `package.json` has no `dsh.client` block and no `@deepseek-ai/dsh-client-runtime` import anywhere, so **not hit**. The rc.2-era image cards (DSH-0.1.1-R2-01/02) have no touchpoint here (no `read_image` / `ImageAttachmentRef` use), and the corridor starts at rc.2 so the DSH-0.1.1-R2-* set is not part of this migration anyway.

**Card mapping**: **DSH-0.1.2-A1-03** (both the import and the command hit).

## Touchpoint #6 — Custom HTTP / WS / RPC channels: **HIT**

**Hit files / lines**
- `src/index.ts:45-54` — `startLegacyBridge()` creates a raw `node:http` server and `server.listen(43121, '127.0.0.1')` (comment: `http://localhost:43121/api/legacy`), described in-source as "Private loopback HTTP bridge that bypasses the Host Gateway authentication model". Currently dead code (`void startLegacyBridge` at line 54), but the coupling is statically present and becomes a live hole the moment it is invoked.

**Coupling points**
- A **custom loopback HTTP route** outside the Host Gateway auth gate. Card **DSH-0.1.2-A1-08** ("Web/API channels use process-scoped bootstrap tokens and signed cookies", Type: security, Touchpoints **#6**, required-if-hit): "private routes that bypass auth become security holes"; custom routes outside the Connection gate "do not automatically inherit auth, the Host/Origin fence, CORS, or TLS; handlers should call `ctx.connection.requestRejection(req)` first, or switch to a Connection-owned carrier/seam". Net state: alpha.2 keeps the token/cookie model (A1-08 has no revert card).

**Card mapping**: **DSH-0.1.2-A1-08**.

## Touchpoint #7 — Subprocess / stdout / stderr parsing: **HIT** (two independent sites)

**Hit files / lines**
1. `src/index.ts:56-67` — `ctx.register('headless-ask', ...)` spawns `dsh --profile headless <prompt>` and `JSON.parse`s every stdout chunk, expecting `event.type === 'final'`.
2. `scripts/apply-patch.mjs:11-18` — same wrong assumption, with the in-file comment "Deliberately wrong expectation: target headless stdout is final text, not JSONL": `execFileSync('dsh', ['--profile','headless','ping'])` then `output.split('\n')` → `JSON.parse(line)` per line.

**Coupling points**
- Both sites treat headless **stdout as JSONL**. Card **DSH-0.1.2-A1-05** ("Headless: stderr gains a `dsh: reasoning:` segment; stdout remains the final text", Touchpoints **#7**, required-if-hit): rc.2 stdout "was already the final assistant text ... it was never JSONL"; recipe: treat stdout as the final assistant-text channel, receive `dsh: reasoning:` / `dsh: <code>: <message>` on stderr, judge success by exit code, and "do not `JSON.parse` stdout by default". This is a **pre-existing latent bug** (broken even on rc.2), sharpened by alpha.1's new stderr segment — ignoring stderr now also loses reasoning, and "stderr has output" must not be treated as failure.
- Secondary: **DSH-0.1.2-A1-04** (Touchpoints **#4, #7**) applies to the launch lane itself — both sites hardcode the `dsh` invocation without honoring the `DSH_HOME`/profile-resolution rules A1-04 makes authoritative.

**Card mapping**: **DSH-0.1.2-A1-05** (primary, both sites), **DSH-0.1.2-A1-04** (#7 leg, launch wrapper).

---

## Summary table

| # | Touchpoint | Hit? | Files:lines | Card(s) |
|---|---|---|---|---|
| 1 | Source patch | HIT | patch.yml:2-6; cordis.patch.yml:5-6; scripts/apply-patch.mjs:5-8 | DSH-0.1.2-A1-03 |
| 2 | Events | HIT (folded) | src/index.ts:13-22 | DSH-0.1.2-A1-02 → folded by DSH-0.1.2-A2-01 (net: keep `ignorable: true`; schema-20 + transport-retention caveats) |
| 3 | Service/Remote | HIT | src/index.ts:25-32 | DSH-0.1.2-A1-01, DSH-0.1.2-A2-02 |
| 4 | Host directory | HIT | src/index.ts:34-38 | DSH-0.1.2-A1-04 |
| 5 | UI/commands | HIT | src/index.ts:9-10, 40-43 | DSH-0.1.2-A1-03 |
| 6 | Custom channel | HIT | src/index.ts:45-54 | DSH-0.1.2-A1-08 |
| 7 | Subprocess/output | HIT | src/index.ts:56-67; scripts/apply-patch.mjs:11-18 | DSH-0.1.2-A1-05, DSH-0.1.2-A1-04 |

All seven touchpoint categories hit; no negative-category finding was required for this fixture. Cards deliberately **not** mapped (no matching code): A1-06 (no `tools.mode: code` / PTC identifiers), A1-07 (no approval/WebFetch policy code), A1-20 (no `userQuestions.registerProvider`), A1-21/22 (no `resolveSessionPreset` / `isTokenDelta`), A1-25 (no `dsh-client-runtime` references), A2-03/04/05/06/08/10 (no matching surfaces: no peer-dependency graph to trim, no Node-24 loader workaround, no `pluginInventory/list` consumer, no `host.describe` caller, no tool-package peer composition, no `settingsNamespace` import).

## Why "no hit ≠ no problem" (limits of this static scan)

This fixture hit all seven categories, so the required negative-category statement is generalized to the scan's limits:

1. **Files scanned and what was ruled out**: all 6 files listed above. `package.json` was checked for `peerDependencies`, `engines`, `@deepseek-ai/*` imports, and a `dsh.client` block (none present — hence A1-25/A1-26 ruled out). `cordis.patch.yml` was checked for legacy `cordis.yml` naming, `!!js` vs `!js` usage, and unknown fields. `README.md` is documentation only and was not treated as code evidence.
2. **Static-only scope**: the scan greps source against curated card sets, not a complete API diff — every card file itself warns it is "a curated list of plugin-relevant changes, not a complete API diff". Runtime-only behavior (event reload on a real SQLite store, auth gates on the loopback bridge, actual headless byte streams) cannot be confirmed statically; this fixture is additionally not installable by design ("do not execute").
3. **Dead code still counts; invisible coupling does not**: `startLegacyBridge` is never invoked, yet its coupling is reported; conversely, coupling living in dependencies (a transitive `@deepseek-ai/*` package resolved at install time) is invisible here because the fixture has no lockfile and no `node_modules` to resolve against.
4. **Card coverage gap is possible**: upstream changes without a card are possible by construction (card files state that undeclared host UI changes "do not prove the absence of API or behavior impact"). A clean scan therefore means "no *known-card* collision found"; unsupported gaps must be reported and researched against primary sources, not treated as safety.
5. **Corridor folding must precede planning**: as finding #2 shows, reading only the intermediate alpha.1 card set would recommend deleting the `ignorable` marker — the wrong action for the alpha.2 target. The same folding risk applies in reverse to negative conclusions in shorter corridors (an intermediate removal misread as final).
