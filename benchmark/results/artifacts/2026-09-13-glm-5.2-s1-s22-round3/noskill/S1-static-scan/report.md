# S1 · Static Touchpoint Scan Report — legacy-plugin (dsh 0.1.1 era → 0.1.2-alpha.2)

**Scope**: read-only static scan of the fixture at `environment/fixture/` (files inspected: `README.md`, `package.json`, `patch.yml`, `cordis.patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts`). No file under the fixture (or anywhere in the benchmark repository) was modified, created, deleted, or renamed; nothing was executed. Corridor mapped: **0.1.1-rc.2 → 0.1.2-alpha.1 → 0.1.2-alpha.2**, folded to its **net state** per the corridor rule (the canonical fold pair being `ignorable`, removed by A1-02 and restored by A2-01).

**Fixture identity**: `package.json:1-9` — name `legacy-plugin`, version `0.1.1`, private, ESM. The plugin is host-plane (no `dsh.client` field, no client bundle), which matters for the A1-01 plane distinction below.

---

## Summary matrix

| # | Touchpoint | Hit | Files / lines (fixture-relative) | Change cards (net-state mapped) |
|---|---|---|---|---|
| 1 | Source patch | **Yes** | `patch.yml:3-6`, `cordis.patch.yml:2-6`, `scripts/apply-patch.mjs:5-9` | **A1-03** (primary); A1-04 (launcher/env coupling of the patch runner) |
| 2 | Events / persistent events | **Yes** | `src/index.ts:15-19` (producer), `src/index.ts:20-22` (consumer) | **A1-02 → A2-01 fold** (net: keep `ignorable`), A1-27 (adjacent, verify-only) |
| 3 | Internal service / Remote | **Yes** | `src/index.ts:26-27`, `src/index.ts:30-31` | **A1-01** (primary), **A2-02** (error model at the new call sites), A1-25 (removed-package inventory), R-05 |
| 4 | Host directory read/write | **Yes** | `src/index.ts:36-37` | **A1-04** (primary), A1-13 (conditional), A1-21 (ruled out — see notes) |
| 5 | UI / commands / tools | **Yes** | `src/index.ts:10`, `src/index.ts:41-43` | **A1-03** (primary), **A1-26** (conditional, id alignment), A1-25 (removed `dsh-client-runtime`-family internals) |
| 6 | Custom HTTP/WS channel | **Yes** | `src/index.ts:47-53` | **A1-08** (primary), A1-19 (acceptance-side, #6/#7) |
| 7 | Subprocess / stdout parsing | **Yes** | `scripts/apply-patch.mjs:12-18`, `src/index.ts:57-67` | **A1-05** (primary), A1-04 (profile/launcher coupling), A1-19 (startup-log/URL format coupling) |

All seven categories hit. Detail per category follows.

---

## #1 · Source patch — HIT

**Evidence**
- `patch.yml:3-6`: patch surface targets host source file `src/session/view/SessionView.ts` with a textual replacement (`renderSessionView` → `renderSessionViewPatched`).
- `cordis.patch.yml:2-6`: profile composition row (`id: legacy-plugin`, `name: legacy-plugin`, `config: {}`) plus a `patch:` section declaring `patch.yml`.
- `scripts/apply-patch.mjs:5-9`: reads `DSH_HARNESS_SOURCE_ROOT` from the environment and loads `patch.yml` to apply the surface against host source.

**Coupling points & card mapping**
- **DSH-0.1.2-A1-03 (Session view internals split up extensively; touchpoints #1/#5, required-if-hit).** The patch target `src/session/view/SessionView.ts` is exactly the internal session-view surface this card splits in alpha.1. The patch target path and the textual anchors (`export function renderSessionView`) must be re-validated one-by-one against the exact target tag; every old target must map to a target-version file or record an explicit removal reason. The card's field-note practice (point `DSH_HARNESS_SOURCE_ROOT` at the target tag and validate each patch-surface path by composition) is what `apply-patch.mjs` already structurally supports — the *paths* it feeds in are what rot.
- **DSH-0.1.2-A1-04 (secondary):** the patch runner is also a launcher-coupled wrapper (see #7); profile/launcher reorganization means its assumptions about how to reach a host checkout/profile must come from runtime `DSH_HOME`/target profile, not hardcoded layout.

**Migration implication (static):** re-base `patch.yml` against the alpha.2 tag's session-view package layout; expect the flat path to have moved; mark capabilities without a stable public seam "pending confirmation" rather than guessing new internal paths.

---

## #2 · Internal / persistent events — HIT

**Evidence**
- `src/index.ts:15-19`: `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: {...} })` — a producer of an **external informational durable SessionEvent** carrying the `ignorable: true` marker.
- `src/index.ts:20-22`: `ctx.on('session/event', ...)` — a consumer logging event types.

**Coupling points & card mapping — the corridor-fold case**
- **DSH-0.1.2-A1-02 → DSH-0.1.2-A2-01 (fold; net state, do not migrate stepwise).** alpha.1 temporarily removed the ability to retain `ignorable` on third-party persisted events (unknown persisted events then fail reload as required events); **alpha.2 restored the producer/persistence/reload/transport retention semantics** (it is the revert of A1-02). Because the target is **0.1.2-alpha.2**, the net state is: **keep writing `ignorable: true` on informational events exactly as the fixture does — do not delete the marker for alpha.1 and re-add it**, and remove any old-version defensive adaptation rather than keeping it. Two net-state caveats from A2-01:
  1. the public live `Session.append(...)` still has **no `ignorable` parameter`; a plugin whose only seam is that API should mark the producer seam as a capability gap, not fake a public entry via cast;
  2. the SQLite provider accepts **only schema 20** (no auto-migration from 19) — relevant if this producer feeds a persisted store during upgrade.
- **DSH-0.1.2-A1-27 (adjacent, verify-only):** session content reads now go through the SessionBinding durable event window. The fixture's `ctx.on('session/event')` listener is a raw event consumer, not a session-content reader, so no source change is indicated statically — but the read-path contract should be re-verified at runtime for any code that reconstructs content from the stream.

---

## #3 · Internal service / Remote — HIT

**Evidence**
- `src/index.ts:26-27`: `const apiProxy = await ctx.get('apiProxy')` then `apiProxy.invoke('session.rename', { id, title })`.
- `src/index.ts:30-31`: same acquisition, `apiProxy.invoke('llm.providers')`.

**Coupling points & card mapping**
- **DSH-0.1.2-A1-01 (APIProxy removed; touchpoint #3, required-if-hit).** rc.2's service key `apiProxy` (package `@deepseek-ai/dsh-host-apiproxy`) is **deleted in alpha.1** — `ctx.get('apiProxy')` can never resolve; symptoms: the entry stays `pending (waiting for service: apiProxy)` / `web boot: N entries did not activate`. Both fixture operations are in the card's migration table:
  - `session.rename` → `session/rename` (Remote namespace `session`, i.e. `ctx.remote.session.rename` on the **client plane**);
  - `llm.providers` → **split into two results**: `llm/listProviders` + `llm/listConfigurableProviders` (also moved domain for `llm.models` → `session/modelCatalog`, not used here).
  - **Plane discipline (card field note):** this fixture is a **host-plane** plugin, and the old `apiProxy` is the host-plane facade while `ctx.remote.*` is the client-plane facade — they are not swappable one-to-one. The correct host-plane migration is to **skip the gateway and inject the domain service directly** (e.g. `inject: ['llm']`, `ctx.llm.listProviders()`); naively switching to `inject: ['remote']` on the host plane reproduces the permanently-pending symptom.
- **DSH-0.1.2-A2-02 (Remote failures become `RemoteError`; namespaced codes).** Wherever the migrated call sites end up returning `RemoteResult<T>`: `RemoteResult`'s `{ ok, value } | { ok: false, error }` shape is unchanged from rc.2, but `error` is now a `RemoteError` instance and codes are namespaced (`session-not-found` → `session/not-found`, `internal` → `gateway/internal`, etc.). Do not branch on old code strings, parse `Error.message`, wrap calls in defensive catches, or use `instanceof` across realms; use `isRemoteFailure` only on explicitly thrown `result.error`.
- **DSH-0.1.2-A1-25 / rollup R-05 (inventory):** `dsh-host-apiproxy` is one of the five packages removed at the rc.2 → alpha.1 edge — the pre-migration grep list should include it for this plugin's dependency graph.

---

## #4 · Host filesystem — HIT

**Evidence**
- `src/index.ts:36`: `join(homedir(), '.dsh', 'profiles', 'default')` — hardcoded host/profile directory.
- `src/index.ts:37`: `writeFileSync(join(profileDir, 'legacy-note.txt'), text)` — direct synchronous write into the profile directory.

**Coupling points & card mapping**
- **DSH-0.1.2-A1-04 (ACP/SDK examples merged into the `dsh` profile; touchpoints #4/#7).** Wrappers/plugins that read profile files directly or hardcode fixed profile paths no longer match: profiles live under the runtime **`DSH_HOME`** (`$DSH_HOME/profiles`), and the profile set changed (new `acp`/`sdk`/`sdk-minimal` profiles; standalone demo bins/packages removed). Migration: use runtime `DSH_HOME`, the target profile, and the official launcher as the source of truth; distinguish profile composition (`cordis.patch.yml` / `agent.cordis.yml`), package manifests, and resolved config; do not hardcode user directories.
- **DSH-0.1.2-A1-13 (conditional).** Platform shell/directory-picker fixes may obsolete directory-related workarounds — only relevant if this hardcoded path was itself a workaround; verify on the target platform before keeping or deleting the branch.

**Ruled out within #4:** **A1-21** touches #4 only through agent-preset `roots` config pointing at the old CLI `config/agent-presets/` directory; this fixture's `cordis.patch.yml` sets no `roots` and never references agent presets — no hit, but see "why no-hit ≠ no problem" below.

---

## #5 · Internal UI / commands / tools — HIT

**Evidence**
- `src/index.ts:10`: `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` — a **private/internal subpath import** of the session-view package.
- `src/index.ts:41-43`: `ctx.contributes.registerCommand('legacy.openView', ...)` returning `new SessionView({ enhanced: true })` — private command registration constructing the internal view.

**Coupling points & card mapping**
- **DSH-0.1.2-A1-03 (primary; #1/#5).** The same session-view decomposition card: the `/internal` entry and the `SessionView` constructor shape are internal surface that was split extensively. Import must be rebuilt by owning module against the exact tag; capabilities without a stable public seam get "pending confirmation", and ordinary plugins should migrate to public facets/services instead of adding more internal imports.
- **DSH-0.1.2-A1-25 (removed `dsh-client-runtime`, symbols migrated by domain).** The fixture imports `dsh-session-view/internal`, a sibling private client-plane surface dismantled in the same edge; the symbol-by-domain mapping table (Context from `@deepseek-ai/cordis`, conversation types from `dsh-client-ui-conversation/client`, etc.) is the reference for rebuilding. A leftover reference to a removed package leaves the assembly row pending / out of the boot graph, often silently.
- **DSH-0.1.2-A1-26 (conditional).** If this plugin ever ships a Web Client half, the client-modules scan contract requires the registration id, assembly-row `name`, and `package.json#name` to agree (bare package name). Statically the names happen to align (`legacy-plugin` in both `package.json:2` and `cordis.patch.yml:2-3`), and no client bundle exists today — conditional only.

**Ruled out within #5:** A1-09/A1-10/A1-11 (optional new capabilities — no provider-login, language, or subagent-selector code), A1-28 (composer `<textarea>` → contenteditable; no composer/DOM code), A1-29 (`MarkdownText` nested label shape; no ui-primitives usage), A1-20 (`userQuestions.registerProvider`; no structured-question code), A1-32 (`IWorkspaces` → `ctx.uiWorkspace`; no workspace navigation code).

---

## #6 · Custom channel — HIT

**Evidence**
- `src/index.ts:47-53`: `startLegacyBridge()` creates a loopback HTTP server (`node:http`) and `server.listen(43121, '127.0.0.1')` (comment: `http://localhost:43121/api/legacy`), answering with a plain `'legacy'` body. Never invoked in the fixture, but statically present.

**Coupling points & card mapping**
- **DSH-0.1.2-A1-08 (Web/API channels use process-scoped bootstrap tokens and signed cookies; touchpoint #6, required-if-hit).** This is precisely the card's target shape: a custom loopback HTTP route that **bypasses the Host Gateway authentication model**. In alpha.1/alpha.2 the official `/api` Remote/RPC/exact-Fetch routes and `/api/remote.mux` go through the Connection auth gate; a private unauthenticated route becomes a **security hole** (the card's words), and old direct-`/api` callers get 401/403. Migration options per the card: fold the route into a Connection-owned carrier/seam, or for custom routes registered via `ctx.webServer.register()`/`registerUpgrade()` call `ctx.connection.requestRejection(req)` first (these do not automatically inherit auth, Host/Origin fence, CORS, or TLS).
- **DSH-0.1.2-A1-19 (acceptance-side; #6/#7).** Any wrapper/acceptance script that probes this channel by concatenating URLs or checking HTTP 200 must instead honor the token-carrying root URL, cookie exchange, and the `window.__DSH_BOOT__` boot manifest (relevant if the bridge is verified during migration).

**Ruled out within #6:** A1-28 (composer DOM change; no DOM/CSS manipulation).

---

## #7 · Subprocess / output parsing — HIT

**Evidence**
- `scripts/apply-patch.mjs:12-18`: `execFileSync('dsh', ['--profile', 'headless', 'ping'])` then **`JSON.parse` each stdout line** looking for `event.type === 'final'`. The file's own comment marks the assumption "Deliberately wrong expectation: target headless stdout is final text, not JSONL."
- `src/index.ts:57-67`: the `headless-ask` registration spawns `dsh ['--profile', 'headless', prompt]` and in `child.stdout.on('data')` **`JSON.parse`s each stdout chunk** (additionally chunk-wise, not even line-wise) looking for `event.type === 'final'`.

**Coupling points & card mapping**
- **DSH-0.1.2-A1-05 (Headless: stderr gains a `dsh: reasoning:` segment; stdout remains the final text; touchpoint #7, required-if-hit).** Key corridor fact: **rc.2's stdout was already the final assistant text — it was never JSONL**; the fixture's parsing assumption is wrong on the *from*-version too, and stays wrong at the target. The only alpha.1 change is stderr gaining `dsh: reasoning:` (rc.2 stderr was empty on success), so "stderr has output" must not be read as failure. Migration: treat stdout as the final assistant-text channel; receive `dsh: reasoning:` / `dsh: <code>: <message>` on stderr; **judge success by exit code** (0 completion, 1 failure/abort/no completed turn); do not `JSON.parse` stdout by default. Both fixture call sites (`apply-patch.mjs:15-18`, `src/index.ts:61-64`) must be rewritten from JSONL event-scraping to text-plus-exit-code. Bonus static bug to fix while there: the `data` handler parses arbitrary buffer chunks, not lines.
- **DSH-0.1.2-A1-04 (secondary; #4/#7).** The wrappers hardcode the `dsh` launcher and profile names; removed bins (`dsh-acp-demo`, `dsh-jsonrpc-agent`) are not used here (good), but launcher/profile resolution should move to runtime `DSH_HOME` + official launcher. Field-note triage: a keyless cold boot reports `dsh: MISSING_CREDENTIAL: ...` — a profile-configuration issue, not a plugin/runtime failure.
- **DSH-0.1.2-A1-19 (secondary; #6/#7).** Startup-log format coupling: any acceptance logic reading the readiness line must parse the full whitespace-delimited token URL.

**Ruled out within #7:** **A1-06 (Code Mode → PTC rename)** — the rename ledger's identifiers (`tools.mode: 'code'`, preset id `code`, `tools/code-dispatch-log`, `CodeDispatch*`, `tools:code-only`, "Code Mode" copy) appear nowhere in the fixture, and the fixture's `run_code`-adjacent identifiers are absent too; no hit. **A2-04** (Node 24 `dsh web` empty client graph) — the fixture spawns headless, not `dsh web`, and pins no Node version; no hit.

---

## No-hit statement and why "no hit ≠ no problem"

All seven touchpoint categories hit, so there is no fully-empty category; the meaningful negative results are the per-category card exclusions listed above. Files scanned in full: `README.md`, `package.json`, `patch.yml`, `cordis.patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts` (the entire fixture tree — no other source exists).

Why a static zero cannot be trusted as "no problem" for this codebase:

1. **Static green ≠ wire green (A1-01 field note / rollup layer-2 caveat).** All-green typecheck+build cannot prove the wire contract; descriptor-layer parameter drift is silent at the static layer (e.g. wrapper-key mismatches such as `request` vs `_request` surface only at the gateway, and dotted endpoints 404 in favor of slash-form `POST /api/<ns>/<method>`). Only card-level unit tests with descriptor-encoding doubles and a real cold boot close this.
2. **Silent runtime exclusion (A1-25/A1-26).** A removed package left in `inject`, or a registration-id mismatch, produces *no error*: the row simply stays pending or drops out of the boot graph and the UI silently disappears. Absence of a static marker does not mean absence of the failure.
3. **Locale-silent breakage (rollup R-13).** Any UI anchoring by displayed text fails silently after the client-locale rollout; a static English-only scan cannot see it.
4. **This scan is copy-only.** The fixture is explicitly non-executable; conclusions are grounded in the corridor's card set (a curated list, "not a complete API diff" per the card files' own headers). Unlisted type-surface drift (rollup R-11 ledger) and unpublished-cohort install pitfalls (R-01/R-02/R-08) can still bite during the actual migration and are process-level, not scan-detectable, risks.
5. **Negative evidence is version-relative.** Cards ruled out here (e.g. A1-06, A1-21, A1-28) were checked against this fixture's current text; any future edit that introduces composer DOM, preset `roots`, or PTC identifiers re-opens them.

## Suggested verification once migration starts (beyond this static scan)

Per the corridor's layered checklist: baseline first (R-06), dependency-resolution check, then per-hit-touchpoint unit assertions (Remote call sites covering `ok:false` business codes, cancellation, unknown codes per A2-02), a real cold boot watching for `missed the module table` / `service-unavailable` loops / pending rows, and — because #7 is hit — headless exit-code + stdout/stderr classification per A1-05.
