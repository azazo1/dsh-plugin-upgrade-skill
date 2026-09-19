# S1 · Static Touchpoint Scan — legacy-plugin (dsh 0.1.1-era → 0.1.2-alpha.2)

**Mode**: A · inspect (read-only static scan; no file under the fixture was modified, created, or deleted; no installs, migrations, or network access).
**Corridor**: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (edges taken from the skill's version-corridor index, connected by `from → to`, not filename order).
**Scan scope**: every file in the fixture pack — `README.md`, `package.json`, `patch.yml`, `cordis.patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts` (6 files, all read line-by-line).
**Face**: ordinary Host-plane Cordis plugin (no `dsh.client` manifest, no browser bundle in `package.json`).

## 0. Configuration and dependency inventory

- `package.json`: `name: legacy-plugin`, `version: 0.1.1`, `private: true`, `type: module`, one script `apply-patch`. **No** `peerDependencies`, `engines`, or `@deepseek-ai/*` dependencies declared — so the packaging cards DSH-0.1.2-A2-03 (peer trimming) and DSH-0.1.2-A2-08 (added `sessionProjections` peer) have nothing to act on at the manifest level, and DSH-0.1.2-A1-24 (pi-ai double instance) is not hit (no `@earendil-works/pi-ai` import).
- No lockfile, no `dsh-plugin.json`.
- `cordis.patch.yml`: one plugin row `legacy-plugin` **plus a `patch:` block pointing at `patch.yml`** — this is not a plain composition file; see #1.
- No resolved config available (fixture is not installable, by design).

## Touchpoint checkup (legacy-plugin, 0.1.1-rc.2 → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card(s) |
|---|---:|---|---|
| #1 source patch | **YES** | `cordis.patch.yml:5-6`; `patch.yml:1-6`; `scripts/apply-patch.mjs:5,8` | DSH-0.1.2-A1-03 (+ API-08 classification) |
| #2 events | **YES** | `src/index.ts:13-22` | DSH-0.1.2-A2-01 (net state; DSH-0.1.2-A1-02 folded away) |
| #3 services/Remote | **YES** | `src/index.ts:24-32` | DSH-0.1.2-A1-01 + DSH-0.1.2-A2-02 |
| #4 host filesystem | **YES** | `src/index.ts:34-38` | DSH-0.1.2-A1-04 |
| #5 UI/commands/tools | **YES** | `src/index.ts:9-10,40-43` | DSH-0.1.2-A1-03 (+ API-10 note) |
| #6 custom channel | **YES** | `src/index.ts:45-54` | DSH-0.1.2-A1-08 |
| #7 subprocess/output | **YES** | `src/index.ts:56-67`; `scripts/apply-patch.mjs:11-19` | DSH-0.1.2-A1-05 (+ DSH-0.1.2-A1-04, DSH-0.1.2-A2-04 conditional) |

All seven classes hit. Details per class follow.

### #1 Source patch / monkey patch — HIT

- `cordis.patch.yml:5-6` declares a source patch inside profile composition:
  ```yaml
  patch:
    - patch.yml
  ```
- `patch.yml:2-6` patches **host source** `src/session/view/SessionView.ts`, replacing `export function renderSessionView` with `renderSessionViewPatched`.
- `scripts/apply-patch.mjs:5-8` reads `process.env.DSH_HARNESS_SOURCE_ROOT` and applies that surface — the exact patch-surface pattern of the pre-flight #1 patterns (`patch\.yml`, `DSH_HARNESS_SOURCE_ROOT`).

**Classification (API-08)**: `cordis.patch.yml` is by default Loader composition, not a source patch; a filename containing `patch` alone is not a hit. Here it **is** a hit because the content carries a real patch declaration with a host target path and a replacement intent — it enters the source-patch migration path, not the composition path.

**Card mapping — DSH-0.1.2-A1-03** (Session view internals split extensively; Touchpoints #1/#5, required-if-hit): the patch target `src/session/view/SessionView.ts` is a pre-split session-view internal path that no longer matches the alpha.1/alpha.2 tree. Action: check the target path one-by-one against an exact-tag compare; when no owning module exists at the target tag, mark it **"pending confirmation" — do not guess a new path**. Until a stable public seam exists, the patch surface is obsolete/conflicting.

### #2 Internal event names / persistent events — HIT

- `src/index.ts:15-19`: producer of an external informational durable event — `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: … })`.
- `src/index.ts:20-22`: observer — `ctx.on('session/event', …)` logging `event.type`.

**Corridor folding (the required net-state reasoning)**:

- DSH-0.1.2-A1-02 (`SessionEvent.ignorable` **temporarily removed**, Touchpoints #2, action level `required-if-target-is-alpha.1`) would demand stopping the write of this unknown persisted event — but only if the target were exactly alpha.1.
- DSH-0.1.2-A2-01 (**restores** `SessionEvent.ignorable` for third-party persisted events, Touchpoints #2, required-if-hit) reverts it at the target.

Per the corridor rule ("if a field is removed in alpha.1 and restored in alpha.2, do not delete and re-add it"), the **final net state is: the `ignorable: true` marker's producer/persistence semantics are valid at alpha.2 — keep the marker, do not remove the producer, do not add a consumer whitelist**. A1-02 is therefore recorded as folded/superseded; the applicable card at the target is **DSH-0.1.2-A2-01**, whose verification applies: envelope/persistence/reload/transport must preserve `ignorable: true` on `legacy/informational-note` across reload; unknown events *without* the marker remain required-on-read (fail closed); note A2-01's caveat that the public live `Session.append(...)` still has no `ignorable` parameter, and its SQLite note (schema 19 rejected, schema 20 only) if any persistence seam is exercised.

### #3 Internal service probes / Remote — HIT

- `src/index.ts:26-27`: `const apiProxy = await ctx.get('apiProxy')` then `apiProxy.invoke('session.rename', { id, title })`.
- `src/index.ts:30-31`: `ctx.get('apiProxy')` then `apiProxy.invoke('llm.providers')`.

**Cards**:

- **DSH-0.1.2-A1-01** (APIProxy removed, calls moved to `@Remote`; Touchpoints #3, required-if-hit): the service key `apiProxy` (package `@deepseek-ai/dsh-host-apiproxy`) is deleted in alpha.1; both `invoke` targets are in the card's migration table:
  - `session.rename` → `session/rename` (generated declaration `ctx.remote.session.rename`);
  - `llm.providers` → split into `llm/listProviders` **+** `llm/listConfigurableProviders` (one call becomes two results).
- **Face pitfall (A1-01 field note)**: this plugin is **host-plane** (ordinary Cordis plugin, server side). The correct migration is to skip the gateway and **inject the owning domain service directly** (e.g. `inject: ['llm']` → `ctx.llm.listProviders()`; the session domain service for rename); mechanically switching to `inject: ['remote']` on the host plane leaves the entry `pending (waiting for service: remote)`. The `ctx.remote.*` table applies only to browser-plane plugins.
- **DSH-0.1.2-A2-02** (Remote failures become `RemoteError` instances; error codes gain namespaces; Touchpoints #3, required-if-hit): once migrated, failure handling must branch on `result.ok` / namespaced `result.error.code` (`session/not-found`, `gateway/internal`, …), never parse `Error.message` or use `instanceof` across realms. The fixture currently does no error handling at all, so the card is mapped as a required follow-on for the migrated call sites.
- Not hit in this class: `@Remote`, `ctx.remote`, `APIProxy` type imports, `/internal` package entries beyond the #5 import — no other lines match. A2-05/A2-06/A2-08/A2-10 have no corresponding consumption in the fixture.

### #4 Direct host directory reads/writes — HIT

- `src/index.ts:36-37`: `const profileDir = join(homedir(), '.dsh', 'profiles', 'default')`; `writeFileSync(join(profileDir, 'legacy-note.txt'), text)` — a hard-coded user-home/profile path, written directly.

**Card — DSH-0.1.2-A1-04** (ACP/SDK profiles merged; standalone demo bins/packages removed; Touchpoints #4/#7, required-if-hit): the recipe says to use the runtime `DSH_HOME`, the target profile, and the official launcher as the source of truth and "do not hardcode user directories". The fixed `~/.dsh/profiles/default` construction is exactly that anti-pattern; under the target host the profile layout is resolved via `DSH_HOME`, and any fixed path can silently point at the wrong home after upgrade. Conditional corollary DSH-0.1.2-A1-13 (#4) was checked and is **not** applicable: the fixture contains no platform-shell/directory-picker workaround branches to retire. Data flow note (pre-flight #4): the written value comes straight from the caller's `{ text }` argument — no credentials or logs are touched.

### #5 Internal UI / commands / tool registration — HIT

- `src/index.ts:10`: `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` — a private Host/Web Client internal path (the file's own comment at line 9: "private Host/Web Client path removed by UI decomposition").
- `src/index.ts:41-43`: `ctx.contributes.registerCommand('legacy.openView', () => new SessionView({ enhanced: true }))` — internal command registration bound to that internal view.

**Card — DSH-0.1.2-A1-03** (Touchpoints #1/#5, required-if-hit): the internal import and the UI registration point both stop working after the session-view decomposition. Per the recipe: check host paths against an exact-tag compare, rebuild imports by owning module; capabilities with no stable public seam are marked **"pending confirmation"** — do not guess a replacement path. Ordinary plugins should migrate to public facets/services and drop the internal import.
Command-surface note: `command.list`/`command.execute` were already Remote in rc.2 (not part of this migration per A1-01); if the command handler ever gains caller arguments, the attachment-parameter rules of **API-10** in the alpha.2 ledger apply. No slot augmentation, `dsh-client-runtime` import, `useSession`/`useChat`, `__ModuleLoader__`, or `dsh.client.inject` is present — so A1-25/A1-26/A1-27/A1-29/A1-30/A1-32 (Web Client face) are out of scope for this plugin's current face.

### #6 Custom HTTP / WS / RPC / DOM / CSS channels — HIT

- `src/index.ts:47-53`: `createServer(...)` with `server.listen(43121, '127.0.0.1')` (comment: `http://localhost:43121/api/legacy`) — a private loopback HTTP bridge that bypasses the Host Gateway authentication model. The function is defined but never invoked (`void startLegacyBridge`, line 54) — static-only, as the fixture intends.

**Card — DSH-0.1.2-A1-08** (Web/API channels use process-scoped bootstrap tokens and signed cookies; Touchpoints #6, required-if-hit): after alpha.1, private routes that bypass auth are security holes, and "listening on loopback only" is explicitly not a reason to skip authentication. If this bridge is ever enabled, the handler must call `ctx.connection.requestRejection(req)` first (or move to a Connection-owned carrier), and it must not inherit a false sense of protection from the Host's gate. Being dead code does not clear the finding — it removes runtime exposure but the coupling point remains in source.

### #7 Subprocess / stdout / stderr parsing — HIT (two sites, same wrong assumption)

- `src/index.ts:56-67`: `spawn('dsh', ['--profile', 'headless', prompt])`, then per-chunk `JSON.parse(line.toString())` expecting `{ type: 'final', text }` events — i.e. treats headless stdout as JSONL. No env/cwd control, no cancellation, no exit-code check, no stderr consumption.
- `scripts/apply-patch.mjs:12-18`: `execFileSync('dsh', ['--profile', 'headless', 'ping'])`, then splits stdout and `JSON.parse`s each line — the file itself admits "Deliberately wrong expectation: target headless stdout is final text, not JSONL."

**Card — DSH-0.1.2-A1-05** (Headless: stderr gains `dsh: reasoning:`; stdout remains the final text; Touchpoints #7, required-if-hit): rc.2's stdout was **already** the final assistant text (never JSONL), and alpha.1 adds a `dsh: reasoning:` segment on stderr. Both call sites break: `JSON.parse` on the final-text stdout throws on the first line, and ignoring stderr loses reasoning while risking "stderr has output = failure" misjudgment. Migration: treat stdout as final assistant text (unless a specific entrypoint has its own structured contract), receive `dsh: reasoning:` / `dsh: <code>: <message>` on stderr, judge success by exit code (0/1), never `JSON.parse` stdout by default; also record argv/cwd/env/cancellation/teardown, which both wrappers currently leave undefined.

Secondary #7 mappings:

- **DSH-0.1.2-A1-04** (#7): the wrappers invoke `dsh --profile headless` — the profile mechanism itself exists since rc.2 and the removed bins (`dsh-acp-demo`, `dsh-jsonrpc-agent`) are not referenced, so the launch target survives; the hit is the fixed assumptions around it, covered by A1-05 above.
- **DSH-0.1.2-A2-04** (#7, conditional): relevant only if these wrappers (or their CI) carried Node 24.0–24.11.1 workarounds — none are present in the fixture, so no action.

## Corridor folding summary

| Change | Intermediate state | Final net state at alpha.2 | Action for this plugin |
|---|---|---|---|
| `SessionEvent.ignorable` | removed in alpha.1 (A1-02) | restored in alpha.2 (A2-01) | **Keep** the `ignorable: true` producer marker in `src/index.ts:17`; do not delete-and-re-add. Map to A2-01 verification only. A1-02's "stop writing the event" action does **not** apply because the target is not alpha.1. |

All other mapped cards are single-edge and carry over unchanged. Cards in the corridor checked and **not** hit (with the evidence checked): R2-01/02/03 (no image/`read_image`/attachment use), A1-06 (no `code`-mode identifiers), A1-07 (no approval/permission hooks), A1-12/A1-14/A1-23 (privacy/composition — plugin publishes no such rows), A1-20/21/22/31 (no user-questions, agent-presets, `isTokenDelta`, or subagent descriptor usage), A1-24 (no pi-ai), A1-25–A1-30/A1-32 (Web Client face absent), A2-03/A2-08 (no peers declared), A2-05/A2-06/A2-10 (no inventory/`$host`/settings-namespace consumption).

## No-hit analysis and the limits of "no hit = no problem"

In this fixture **all seven classes hit**, so there is no fully clean category; for completeness, the scan scope and exclusions were: the full six-file pack, patterns from pre-flight #1–#7 (`patch\.yml`, `patchedDependencies`, `DSH_HARNESS_SOURCE_ROOT`, `ctx\.on\(`, `session/event`, `ctx\.get\(`, `apiProxy`, `DSH_HOME`/`\.dsh`/`homedir\(`, `registerCommand`/`contributes`/`/internal`, `createServer`/`127\.0\.0\.1`/`/api/`, `spawn`/`execFileSync`/`--profile headless`), plus the corridor-specific tokens above.

Why a zero hit could not be read as "no problem" even if it had occurred:

1. The scan is **heuristic regex matching**, per pre-flight.md: "Zero hits across the seven classes only means 'not detected by the current patterns'"; data flow (e.g. a host path assembled indirectly) escapes line-level search.
2. The card files are **curated lists, not a complete API diff** — an uncatalogued breaking change produces no pattern to match.
3. Corridor coverage starts at `dsh-v0.1.1-rc.2`; any source predating that edge is an **unsupported gap** that no card can cover.
4. Static scanning cannot see runtime behavior: a real build/typecheck, a cold-boot mount on the target tag (`--dump-config` showing no pending rows), and one functional path remain mandatory before declaring compatibility. This fixture is intentionally non-compilable, so those layers are **not executed** here and are recorded as pending.

## Report structure (per skill "Validation and reporting")

- **Pre-existing baseline**: not collected — Mode A static inspection; the fixture is non-executable by design.
- **Completed**: read-only scan of all 6 files; corridor rc.2→alpha.1→alpha.2 built from the index; 7/7 touchpoints hit and mapped (A1-01, A1-02→A2-01 folded, A1-03 ×2, A1-04, A1-05, A1-08; conditional A1-13/A2-04 examined and not applicable; packaging A2-03/A2-08 vacuous).
- **Skipped / not applicable**: all Web Client-face cards (no client half), privacy/composition cards (no such rows), capability cards (A1-09/10/11 — suggestions only, not adopted).
- **Pending / residual risk**: patch target `src/session/view/SessionView.ts` and the `SessionView` internal import have **no confirmed target-tag replacement** (pending confirmation against exact-tag source); the #3 migration must be re-derived per the host-plane inject rule, not from the client table alone; build/typecheck/mount/behavior validation not run (static-only task).
- **Rollback**: nothing was changed — the fixture tree was treated strictly read-only, so the rollback baseline is the untouched tree itself.
- **Recommendations**: replace the source-patch surface and internal import with public seams; migrate `apiProxy` calls to domain-service injection with `RemoteError`-aware handling; drive the two headless wrappers off stdout-JSONL; if the loopback bridge is ever activated, wire it through the Connection auth gate.
