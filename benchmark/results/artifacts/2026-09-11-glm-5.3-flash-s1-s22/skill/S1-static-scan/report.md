# S1 · Static Touchpoint Scan — legacy-plugin, dsh 0.1.1 → 0.1.2-alpha.2

- **Mode**: A · inspect (read-only). No file under the fixture was modified, created, or deleted.
- **Corridor**: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (built from the `from → to` edges in `references/README.md`, not filename order). The full corridor was read first and net states folded before mapping.
- **Face**: Host-plane ordinary Cordis plugin (`src/index.ts` uses `ctx.register`, `node:child_process`, `node:http`) plus two Node wrapper scripts (`scripts/apply-patch.mjs`) and profile/patch YAML. No Web Client plugin face is declared (no `dsh.client` in `package.json`), so client-plane cards (A1-25/A1-26/A1-30/A1-32, API-10) are recorded as checked-and-ruled-out.

## Touchpoint checkup (legacy-plugin, 0.1.1 → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 patch | Yes | `cordis.patch.yml:5-6`, `patch.yml:2-5`, `scripts/apply-patch.mjs:5` | DSH-0.1.2-A1-03; API-08 (classification) | Two distinct sub-hits; see below |
| #2 events | Yes | `src/index.ts:15-19` (producer), `src/index.ts:20-22` (observer) | DSH-0.1.2-A2-01 (net); DSH-0.1.2-A1-02 superseded | Corridor folding applied — see below |
| #3 services/Remote | Yes | `src/index.ts:26-27`, `src/index.ts:30-31` | DSH-0.1.2-A1-01 + DSH-0.1.2-A2-02 | Host-plane apiProxy consumer |
| #4 filesystem | Yes | `src/index.ts:36-37` | DSH-0.1.2-A1-13 (primary), A1-04/A1-21 cross-checked | Hard-coded fixed profile path |
| #5 UI/commands/tools | Yes | `src/index.ts:10`, `src/index.ts:41-43` | DSH-0.1.2-A1-03 | Internal session-view import + registerCommand |
| #6 custom channel | Yes | `src/index.ts:47-53` (esp. 48, 51) | DSH-0.1.2-A1-08 | Unauthenticated loopback HTTP |
| #7 subprocess/output | Yes | `src/index.ts:57-67`; `scripts/apply-patch.mjs:12-18` | DSH-0.1.2-A1-05 + API ledger API-06 | JSONL assumption wrong on both tags |

All seven touchpoint categories hit. Details per category follow.

---

## #1 Source patch / monkey patch — HIT

**Evidence:**
- `patch.yml:1-5` — a genuine source-patch surface: `surface: - target: src/session/view/SessionView.ts` with `replacements: - find: export function renderSessionView / replace: export function renderSessionViewPatched`. This rewrites a Host source file by string replacement.
- `cordis.patch.yml:5-6` — declares `patch: - patch.yml`, wiring that source patch into profile composition.
- `scripts/apply-patch.mjs:5-6` — `const sourceRoot = process.env.DSH_HARNESS_SOURCE_ROOT`, confirming the patch is applied against a DSH source checkout.

**Coupling:** the patch target path `src/session/view/SessionView.ts` and the symbol `renderSessionView` are Host internals that the corridor reorganizes.

**Card mapping — DSH-0.1.2-A1-03** (Session view internals split up extensively; Touchpoints #1, #5; required-if-hit). The internal session-view module is split up in alpha.1, so the patch target path and the `renderSessionView` export can no longer be assumed to exist; per the card, check each target against an exact-tag compare and mark capabilities with no stable public seam "pending confirmation" — do not guess new paths.

**Classification guard (API-08, api-migration-0.1.2-alpha.2.md):** the file `cordis.patch.yml` itself is **composition, not a source patch** — a filename containing `patch` alone is not a #1 hit. The hit here is the *nested* `patch: [patch.yml]` row plus `patch.yml`'s source-replacement content; those migrate as a source patch under A1-03, while the composition rows (`id: legacy-plugin`, `config: {}`) migrate as ordinary Loader composition. The two use different verification paths and must not be conflated.

## #2 Internal event names / persistent events — HIT

**Evidence:** `src/index.ts:15-19`: the plugin emits `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: { text: 'fixture' } })` — it is a **producer of a third-party persisted informational SessionEvent** carrying `ignorable: true`. `src/index.ts:20-22` is a plain observer (`ctx.on('session/event', ...)`) — no persistence/reload/transport role.

**Card mapping — corridor folding is decisive here:**
- DSH-0.1.2-A1-02 (`SessionEvent.ignorable` temporarily removed) applies only "if the target is exactly alpha.1" (`Action level: required-if-target-is-alpha.1`).
- DSH-0.1.2-A2-01 restores the marker in alpha.2; A1-02 itself instructs: "If the final target is alpha.2 or later, first read A2-01 to compute the corridor net state; **do not delete the producer marker and then restore it**."

**Net state for target alpha.2: keep `ignorable: true` as-is.** Do not remove it — applying A1-02 against the folded corridor would be a migration error even though both cards exist. Residual obligation from A2-01: what alpha.2 restores is the envelope/persistence/reload/transport retention semantics; the public live `Session.append(...)` still has no `ignorable` parameter, so a producer seam needing the marker through a supported public API remains a recorded capability gap, not something to fake via casts. (This fixture uses `ctx.emit` and is static-only, so no live append path exists to verify.)

## #3 Internal service probes / Remote — HIT

**Evidence:** `src/index.ts:26-27` and `src/index.ts:30-31`: `const apiProxy = await ctx.get('apiProxy')` followed by `apiProxy.invoke('session.rename', { id, title })` and `apiProxy.invoke('llm.providers')`.

**Coupling:** the rc.2 service key `apiProxy` (type `ApiProxy`, package `@deepseek-ai/dsh-host-apiproxy`) and two old wire operations: `session.rename` and `llm.providers`.

**Card mapping — DSH-0.1.2-A1-01** (APIProxy removed, Host/Web Client calls moved to `@Remote`; Touchpoint #3; required-if-hit). alpha.1 deletes `@deepseek-ai/dsh-host-apiproxy`; there is no `APIProxy` identifier afterwards. Exact ledger entries hit:
- `session.rename` → `session/rename` (generated declaration, `ctx.remote.session.rename`).
- `llm.providers` → `llm/listProviders` + `llm/listConfigurableProviders` (one call split into two).

**Face correction from the A1-01 field note (important):** this is a **host-plane** plugin, so the ledger's `ctx.remote.*` facade does not apply — `ctx.remote` is the browser-plane facade. The correct host-plane migration is to skip the gateway and inject the domain service behind the proxy directly (e.g. `inject: ['session']` and call the session rename capability; the llm domain service for provider listing). Mistakenly injecting `remote` on the host plane stalls with `pending (waiting for service: remote)`.

**Second-edge card — DSH-0.1.2-A2-02** (Remote failures become `RemoteError` instances; error codes gain namespaces; Touchpoint #3; required-if-hit). Once the calls are migrated to Remote, failure handling must move to the `RemoteResult<T>` branch with namespaced codes (`session/not-found`, `gateway/cancelled`, ...); branching on old code strings, parsing `Error.message`, or `instanceof RemoteError` across realms misclassifies. No such handling exists in the fixture, so this lands together with the A1-01 rewrite.

## #4 Direct host directory reads/writes — HIT

**Evidence:** `src/index.ts:36-37`: `const profileDir = join(homedir(), '.dsh', 'profiles', 'default')` then `writeFileSync(join(profileDir, 'legacy-note.txt'), text)`.

**Coupling:** hard-coded Host home layout (`~/.dsh/profiles/default`) with a direct write into the Host's profile directory — bypasses every ownership and directory-resolution seam; breaks under any non-default `DSH_HOME` or profile name.

**Card mapping — DSH-0.1.2-A1-13** (platform shell and directory picker fixes may obsolete old workarounds; pre-flight lists A1-04/A1-13/A1-21 for class #4). Applicable direction: the corridor's supported substitutes are the directory-picker/host-directory seams (`directoryPicker/pick`, `host.openPath` → `session/openWorkspacePath` per A1-01's table); the fixed `~/.dsh` construction is exactly the kind of workaround the card flags for retirement. A1-04/A1-21 were cross-checked and found non-intersecting (no ACP/SDK demo-bin usage, no `dsh-agent-presets` usage). Per pre-flight's warning, the line-level hit was traced through its data flow: the path is constructed from `homedir()` alone, never from a host-provided handle, so no `DSH_HOME` override is honored.

## #5 Internal UI / commands / tool registration — HIT

**Evidence:**
- `src/index.ts:10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` (private Host/Web path).
- `src/index.ts:41-43` — `ctx.contributes.registerCommand('legacy.openView', () => new SessionView({ enhanced: true }))`.

**Coupling:** an internal `/internal` subpath import of a session-view symbol, consumed by a command registration.

**Card mapping — DSH-0.1.2-A1-03** (same card as #1; Touchpoints #1, #5; required-if-hit): the internal session-view paths are split up in alpha.1, so both the `@deepseek-ai/dsh-session-view/internal` import and the `SessionView` constructor use break. Recipe: rebuild the import by owning module against the exact target tag; if no stable public seam exists, mark "pending confirmation" — do not invent a replacement path from memory. The `registerCommand` call itself is not hit by the corridor's command changes (the API-10 `ctx.commands.execute` signature change adds an attachments parameter to *execution*, which this fixture never calls).

**Ruled out within this class:** no `dsh-client-runtime` import (→ A1-25 not hit), no `useSession`/`useChat`/`ctx.slots`/`__ModuleLoader__` (→ A1-26/A1-28/API-10 keyed-snapshot surface not hit), no `IWorkspaces`/`connectWorkspace`/`pickDirectory` (→ A1-32 not hit), no image/tool output schemas (→ rc.2 cards R2-01/02/03 not hit).

## #6 Custom HTTP / WS / RPC / DOM / CSS channels — HIT

**Evidence:** `src/index.ts:47-53`: `createServer((_request, response) => { response.end('legacy') })` and `server.listen(43121, '127.0.0.1') // http://localhost:43121/api/legacy`. (The function is never invoked — the fixture is static-only — but the coupling is present in source.)

**Coupling:** a private loopback HTTP channel with a `/api/...` route and **no authentication, no Host/Origin fence, no token/cookie redemption**.

**Card mapping — DSH-0.1.2-A1-08** (Web/API channels use process-scoped bootstrap tokens and signed cookies; Type: security; Touchpoint #6; required-if-hit). After alpha.1, anything speaking `/api` must go through the Connection auth gate; custom routes registered outside it do **not** automatically inherit auth, the Host/Origin fence, CORS, or TLS — handlers must call `ctx.connection.requestRejection(req)` first or move to a Connection-owned carrier. Pre-flight's rule applies verbatim: "listening on loopback only is not a reason to skip authentication." Verifying the process starts is not enough; the card's verification matrix (403 on wrong Host/Origin, 401 on missing/bad cookie, token→cookie redemption) is the acceptance path.

## #7 Subprocess / stdout / stderr parsing — HIT (two sites)

**Evidence:**
- `src/index.ts:57-67` — `spawn('dsh', ['--profile', 'headless', prompt])`, then per-chunk `JSON.parse(line.toString())` looking for `{type:'final'}`; the comment at line 56 admits the "deliberately wrong wrapper assumption".
- `scripts/apply-patch.mjs:12-18` — `execFileSync('dsh', ['--profile', 'headless', 'ping'], ...)` then splitting stdout on newlines and `JSON.parse`-ing each line for `event.type === 'final'`; the comment at line 11: "Deliberately wrong expectation: target headless stdout is final text, not JSONL."

**Coupling:** both call sites treat headless stdout as JSONL events; neither reads the exit code; neither handles stderr.

**Card mapping — DSH-0.1.2-A1-05** + **API-06** (api-migration-0.1.2-alpha.2.md, the Headless argv/output contract):
- stdout was **already final assistant text in rc.2** (never JSONL) — so both wrappers are broken on the `from` version too, not just the target; `JSON.parse` on stdout fails on ordinary final text.
- alpha.1/alpha.2 change: stderr gains a `dsh: reasoning:` segment (failures take the form `dsh: <code>: <message>`), so "any stderr output = failure" also misjudges; success is judged by **exit code** (0 completed, 1 abort/error/no completed turn; SIGINT→130).
- API-06's invocation rules are hit as well: argv arrays are used and launcher flags precede the task, but `ping`/`prompt` as bare task text is not a verified command shape of either tag, and ignoring the exit code treats startup failures as success.
- DSH-0.1.2-A2-04 was cross-checked: conditional, applies only to wrappers that added Node 24.0–24.11.1 workarounds (forcing Node 22, skipping `dsh web`); this fixture contains none — recorded as a non-hit with the reason stated.

---

## Corridor folding note (explicit)

The brief's folding case is realized by touchpoint #2: `SessionEvent.ignorable` is **removed in alpha.1** (DSH-0.1.2-A1-02) and **restored in alpha.2** (DSH-0.1.2-A2-01). Per the pre-flight rule ("read the full corridor first and fold net changes such as 'removed then restored' before producing the change plan") and the explicit instruction in both cards, the final net state at alpha.2 is "marker retained with its envelope/persistence semantics" — the governing card is **DSH-0.1.2-A2-01**, and **DSH-0.1.2-A1-02 is superseded** (it would have required deleting the marker only if the target were exactly alpha.1). Writing the migration as "remove then re-add" would be a folding error even though both cards exist.

## No-hit / ruled-out notes (scope, and why "no hit ≠ no problem")

**Scan scope:** all six fixture files — `README.md`, `package.json`, `cordis.patch.yml`, `patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts` (68 lines, read in full). No generated artifacts, vendor, or `node_modules` exist to exclude. `package.json` declares no `peerDependencies`, no `engines`, and no `@deepseek-ai/*` dependency (the only `@deepseek-ai/*` import in the tree is `src/index.ts:10`); no `dsh-plugin.json` manifest is present.

**Explicitly checked and ruled out (with reasons):**
- **A1-06 (Code Mode → PTC)**: no `tools.mode`, `code` preset id, `CodeDispatch*`, `tools:code-only`, or `tools/code-dispatch-log` tokens anywhere.
- **A1-25 / API-10 (`dsh-client-runtime`, keyed chat snapshots, command execute signature)**: no such import; the only `@deepseek-ai/*` import is `dsh-session-view/internal`.
- **A1-32 (`IWorkspaces` → `ctx.uiWorkspace`)**: no workspace navigation calls.
- **A1-26 (client-modules registration id = package name)**: no `dsh.client` block, no client module registration.
- **rc.2 cards R2-01/02/03 (image attachments, `read_image`, Files API)**: no image handling of any kind.
- **A2-03/A2-08 (peer trims / `sessionProjections` peer)**: no peer dependencies declared and none of the listed tool packages appear — but see caveat 2 below.
- **A2-05/A2-10, A1-20/21/22/24/27/30/31, A1-04/07/09–12/14/19/23/28/29, A2-06**: no matching imports, service keys, settings usage, or client faces.

**Why zero-hit (or card-ruled-out) cannot be read as "no problem":**
1. The pre-flight scan is explicitly *heuristic*: "Zero hits across the seven classes only means 'not detected by the current patterns'; you must still check dependencies/configuration and run a build, a real mount, and functional smoke tests."
2. Card sets are **curated, not a complete API diff** (stated in every card-set header): an unlisted plugin-facing change can still bite. A2-08 shows peers can be *added* in alpha.2 and surface as a runtime `pending`, not a typecheck error — the fixture's empty `peerDependencies` cannot prove safety; the resolved dependency graph must be re-checked after any dependency change.
3. This fixture **cannot compile by design** (its own README says so), so no build/typecheck evidence exists; every conclusion here is static and unverified by any executable layer.
4. Corridor edges with missing cards must be treated as unsupported gaps, and the alpha.2 precision checklist (peer floors, runtime module composition vs type declarations, channel auth with protocol preservation) still applies to whatever the migration touches.

## Must verify before touching anything (per pre-flight / Mode C step 0)

- Baseline mechanical run in the plugin's own dependency state (expected to fail here — record as the pre-existing exemption list); build/typecheck against exact `dsh-v0.1.2-alpha.2` declarations; a real isolated-profile mount; for #6, the A1-08 auth verification matrix; for #7, the API-06 stdout/stderr/exit-code stub matrix; for #1/#5, an exact-tag check of `src/session/view/SessionView.ts` and `renderSessionView` (currently pending confirmation — the corridor does not state the symbol's fate).

## Summary of card applicability

| Card | Verdict |
|---|---|
| DSH-0.1.2-A1-03 | Hit — via #1 (`patch.yml` target) and #5 (internal import) |
| DSH-0.1.2-A2-01 | Hit — via #2; supersedes DSH-0.1.2-A1-02 (folded net state: keep `ignorable: true`) |
| DSH-0.1.2-A1-01 | Hit — via #3 (`apiProxy` key, `session.rename`, `llm.providers`); host-plane recipe applies |
| DSH-0.1.2-A2-02 | Hit (conditional on the A1-01 rewrite) — Remote failure vocabulary |
| DSH-0.1.2-A1-13 | Hit — via #4 (hard-coded `~/.dsh/profiles/default` workaround) |
| DSH-0.1.2-A1-08 | Hit — via #6 (unauthenticated loopback `/api/legacy` channel) |
| DSH-0.1.2-A1-05 + API-06 | Hit — via #7 (both subprocess sites; wrong on the `from` version too) |
| DSH-0.1.2-A1-02 | Superseded by corridor folding — do not apply against an alpha.2 target |
| DSH-0.1.2-A2-04 | Non-hit — no Node-version workaround present (conditional card) |
| All other A1-/A2-/R2- cards | Non-hit with reasons recorded above |
