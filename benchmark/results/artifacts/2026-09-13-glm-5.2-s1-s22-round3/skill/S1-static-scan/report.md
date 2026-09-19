# S1 · Static Touchpoint Scan (Read-Only) — legacy-plugin

**Task**: read-only touchpoint inspection of a dsh 0.1.1-era plugin source before migration to **dsh 0.1.2-alpha.2**.
**Fixture scanned**: E:\deepseek-harness\dsh-plugin-upgrade-skill\benchmark\tasks\S1-static-scan\environment\fixture\ (6 files, all read; nothing under the fixture was modified, created, or deleted).
**Corridor**: dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2, connected via the from → to index in references/README.md: rc.2 →(v0.1.2-alpha.1.md, 28 cards)→ alpha.1 →(v0.1.2-alpha.2.md, 8 cards)→ alpha.2. The full corridor was read before mapping; net-state folding applied (see #2).
**Method**: skill plugin-upgrade, Mode A (inspect, read-only) + references/pre-flight.md seven-class scan. No builds, installs, migrations, or executions were performed (the fixture is declared non-executable by its own README).

## 0. Configuration and dependency inventory

| Item | Value |
|---|---|
| Files scanned | README.md, package.json, cordis.patch.yml, patch.yml, scripts/apply-patch.mjs, src/index.ts (complete tree; no other files exist) |
| Plugin name / version | legacy-plugin 0.1.1 (private: true, type: module) |
| peerDependencies / engines / lockfile | **absent** — no DSH host cohort declared at all |
| @deepseek-ai/* imports | @deepseek-ai/dsh-session-view/internal (src/index.ts:10) — **undeclared** in package.json |
| dsh-plugin.json manifest | not present |
| Profile composition | cordis.patch.yml (id legacy-plugin, empty config, patch: [patch.yml] row) |
| Install track | static fixture only (not installable by design) |
| Script surface | apply-patch → node scripts/apply-patch.mjs; reads DSH_HARNESS_SOURCE_ROOT |

## Touchpoint checkup (legacy-plugin, 0.1.1-rc.2 → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 patch | YES | cordis.patch.yml:5-6, patch.yml:2-6, scripts/apply-patch.mjs:5-9 | DSH-0.1.2-A1-03 (+ API-08 classification) | patch surface targets a session-view internal; exact target path must be re-validated against the alpha.2 tag |
| #2 events | YES | src/index.ts:15-19 (producer), :20-22 (observer) | DSH-0.1.2-A2-01 (net state; A1-02 folded away) | corridor folding: removed in alpha.1, restored in alpha.2 → keep the marker, do not delete-then-restore |
| #3 services/Remote | YES | src/index.ts:26-32 | DSH-0.1.2-A1-01, DSH-0.1.2-A2-02 | both hit calls map to the A1-01 table; error flow must move to RemoteResult branches |
| #4 filesystem | YES | src/index.ts:36-37 | DSH-0.1.2-A1-04 (A1-13 conditional, no workaround found) | hardcoded ~/.dsh/profiles/default; must move to DSH_HOME-derived paths |
| #5 UI/commands/tools | YES | src/index.ts:10, 41-43 | DSH-0.1.2-A1-03, API-07 (deep-subpath import); related A1-25 | private /internal import + registerCommand returning a SessionView |
| #6 custom channel | YES | src/index.ts:47-53 | DSH-0.1.2-A1-08 | loopback-only listener is NOT exempt from the auth gate |
| #7 subprocess/output | YES | scripts/apply-patch.mjs:12-18, src/index.ts:57-67 | DSH-0.1.2-A1-05 (A1-04 tangential; A2-04 non-hit) | both wrappers JSON.parse headless stdout, which was never JSONL — pre-existing breakage, not a corridor regression |

All seven categories hit. No-hit notes for checked sub-surfaces are in the "No-hit / ruled-out notes" section below.

---

## #1 Source patch / monkey patch — HIT

**Coupling points**
- cordis.patch.yml:5-6: a patch: row referencing patch.yml. Per **API-08** (api-migration-0.1.2-alpha.2.md), cordis.patch.yml is by default the official Profile composition overlay, *not* a source patch; here, however, the row points at a real source-patch surface, so the file genuinely straddles both roles — the composition file itself is legitimate, the referenced patch.yml is the patch class hit.
- patch.yml:3-6: patch surface targeting host source src/session/view/SessionView.ts, replacing "export function renderSessionView" with "...Patched".
- scripts/apply-patch.mjs:5-9: applies the surface against DSH_HARNESS_SOURCE_ROOT (pre-flight #1 pattern for host-source patching).

**Card mapping**
- **DSH-0.1.2-A1-03** (breaking, touchpoints #1/#5): session-view internals were split up extensively in alpha.1. The patch target path src/session/view/SessionView.ts and the renderSessionView symbol almost certainly no longer exist at alpha.2 in that form. Recipe: verify every old target against an exact-tag compare of alpha.2; map each to the owning module or record an explicit removal reason; capabilities without a stable public seam are "pending confirmation" — do not guess new paths.
- **API-08**: keep the composition/loader row and the source-patch row classified separately when migrating; do not delete the whole cordis.patch.yml as a "patch" nor rebase hunks that no longer exist.

---

## #2 Internal event names and persistent events — HIT

**Coupling points**
- src/index.ts:15-19: **producer** of a third-party persisted SessionEvent — ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload }).
- src/index.ts:20-22: plain **observer** via ctx.on('session/event', ...) (logs event.type only; low coupling).

**Card mapping — corridor folding applies**
- The corridor removes SessionEvent.ignorable in alpha.1 (**DSH-0.1.2-A1-02**) and restores it in alpha.2 (**DSH-0.1.2-A2-01**). Per the folding rule (read the full corridor, compute the final net state; do not delete-then-re-add), the correct mapping for a 0.1.1-rc.2 → 0.1.2-alpha.2 migration is the **net state = A2-01**: the producer's ignorable: true on this informational unknown event is *retained as-is* at the target. Mapping this hit to A1-02 alone and stripping the marker would be wrong and would strand an intermediate-version edit.
- A2-01 nuances that survive folding: (a) the marker is producer-side retention semantics, not a consumer filter — the observer at :20-22 must not use it to drop events; (b) the public Session.append(...) still has no ignorable parameter, so this producer seam is a capability gap to mark explicitly rather than fake via cast; (c) if the persistence layer ever goes through the SQLite provider, it accepts only schema 20 (schema 19 rejected, no auto-migration).

---

## #3 Internal service probes / Remote — HIT

**Coupling points** (both in src/index.ts, Host face, ordinary Cordis plugin)
- :26-28 ctx.get('apiProxy') → apiProxy.invoke('session.rename', { id, title }).
- :29-32 ctx.get('apiProxy') → apiProxy.invoke('llm.providers').

**Card mapping**
- **DSH-0.1.2-A1-01** (breaking, required-if-hit): the apiProxy service (package @deepseek-ai/dsh-host-apiproxy) is deleted in alpha.1. Exact remaps from the card's table:
  - session.rename → ctx.remote.session.rename (generated session namespace declaration);
  - llm.providers → **two** calls: llm/listProviders + llm/listConfigurableProviders (one call splits into two results).
  - Calling plugins declare the needed Remote contributions in inject and obtain generated type mounts via @deepseek-ai/dsh-api-remotes/client; no hand-written wire relay objects.
- **DSH-0.1.2-A2-02** (breaking): after the rename, unary calls resolve to RemoteResult<T>; failures are RemoteError instances with namespaced codes (session/not-found, session/agent-busy, gateway/cancelled, gateway/internal, ...). The migrated handlers must branch on result.ok / result.error.code; gateway/cancelled terminates/propagates, gateway/internal and unknown codes are reported without retry.
- Also noted: the current await ctx.get('apiProxy') weak-get pattern has no alpha.2 equivalent for this service at all — it fails at runtime, not as a pending inject, so this is a hard break, not a graceful degradation.

---

## #4 Direct host directory reads/writes — HIT

**Coupling points**
- src/index.ts:36-37: join(homedir(), '.dsh', 'profiles', 'default') — hardcoded Host home + hardcoded profile name; writeFileSync of legacy-note.txt into it.

**Card mapping**
- **DSH-0.1.2-A1-04** (touchpoints #4/#7): wrappers/plugins that hardcode fixed profile paths or user directories no longer match; use runtime DSH_HOME, the target profile, and the official launcher as the source of truth. Profiles live under $DSH_HOME/profiles at alpha.2; ~/.dsh is only the default home, and the target profile here is assumed, not resolved.
- **DSH-0.1.2-A1-13** (conditional): platform shell/directory-picker fixes may obsolete workarounds — checked; the fixture contains no such workaround, so this card is a non-hit (recorded, not actionable).
- Line-level caveat from pre-flight #4 honored: the path is fully static (no variable flow to trace); the write target sits inside host-owned profile storage, which additionally risks colliding with host-managed files.

---

## #5 Internal UI / commands / tool registration — HIT

**Coupling points**
- src/index.ts:10: import { SessionView } from '@deepseek-ai/dsh-session-view/internal' — private Host/Web Client deep-subpath import (the file's own comment marks it as removed by UI decomposition).
- src/index.ts:41-43: ctx.contributes.registerCommand('legacy.openView', ...) returning new SessionView({ enhanced: true }) — internal UI registration point.

**Card mapping**
- **DSH-0.1.2-A1-03** (breaking): the primary card — internal imports and UI registration points from the split-up session-view internals no longer work; rebuild imports by owning module, prefer public facets/services, mark seam-less capabilities "pending confirmation".
- **API-07** (api-migration-0.1.2-alpha.2.md): even where an export map still exposes ./src/*-style deep subpaths, the packed registry artifact may not contain the target file (ERR_MODULE_NOT_FOUND) or its .d.ts. A /internal import must be validated against the installed alpha.2 artifact, not the source checkout. Compounding factor found in inventory: the import is **undeclared** in package.json (no dependencies at all), so dependency resolution for the replacement owning package must be added as part of the migration.
- **DSH-0.1.2-A1-25** (related, not the primary mapping): @deepseek-ai/dsh-client-runtime was removed and its symbols migrated by domain; the fixture does not import that package directly (verified — no dsh-client-runtime string), but if SessionView-class client symbols were consumed via the old runtime elsewhere, the A1-25/API-10 domain mapping table is the lookup for replacement entry points.
- Checked and non-hit: **DSH-0.1.2-A1-26** — the composition id legacy-plugin equals the package.json name, so the registration-id-equals-package-name contract is already satisfied.

---

## #6 Custom HTTP / WS / RPC / DOM / CSS channels — HIT

**Coupling points**
- src/index.ts:47-53: createServer(...) listening on 127.0.0.1:43121 (http://localhost:43121/api/legacy), a private loopback HTTP bridge explicitly bypassing the Host Gateway auth model. The function is never invoked (void startLegacyBridge) — a static coupling hit regardless of execution.

**Card mapping**
- **DSH-0.1.2-A1-08** (security, required-if-hit): Web/API channels moved to process-scoped bootstrap tokens + signed cookies behind a Connection auth gate. Consequences for this hit: (a) "loopback only" is explicitly **not** an exemption; (b) a private route that bypasses auth is a security hole at alpha.2, not just a style issue; (c) the recipe is to call ctx.connection.requestRejection(req) first in any ctx.webServer.register()/registerUpgrade() custom route (inheriting the Host/Origin fence, CORS, TLS) or switch to a Connection-owned carrier/seam; the bootstrap token must never appear in /api URLs, WS URLs, or the Authorization header.
- Also flagged per pre-flight #6: the listener has no teardown/ownership story (the server is created and leaked if ever called) — lifecycle must belong to the plugin fiber in any migrated version.

---

## #7 Subprocess / stdout / stderr parsing — HIT

**Coupling points**
- scripts/apply-patch.mjs:12-18: execFileSync('dsh', ['--profile','headless','ping']), then JSON.parse of every stdout line expecting {type:'final',text} JSONL events.
- src/index.ts:57-67: spawn('dsh', ['--profile','headless', prompt]), JSON.parse on each stdout data chunk expecting event.type === 'final'.

**Card mapping**
- **DSH-0.1.2-A1-05** (required-if-hit): headless **stdout was already the final assistant text in rc.2 and was never JSONL**; the only alpha.1 change is that stderr gains a "dsh: reasoning:" segment. So both wrappers are broken *today* (pre-existing incorrect assumption, not caused by the corridor) and remain wrong at alpha.2. Migration recipe per the card and the API table: treat stdout as final text, receive "dsh: reasoning:" / "dsh: <code>: <message>" on stderr, judge success by exit code (0 completion / 1 failure), never JSON.parse stdout by default. The data-chunk JSON.parse in src/index.ts additionally splits on arbitrary chunk boundaries — an independent wrapper bug to fix in the same pass.
- **DSH-0.1.2-A1-04** (tangential, already mapped under #4): wrappers hardcoding profile/process assumptions should source truth from DSH_HOME + the official launcher; note the card's field note that a headless cold boot without credentials reports "dsh: MISSING_CREDENTIAL" — a profile-config issue, not a plugin failure, when triaging.
- Checked and non-hit: **DSH-0.1.2-A2-04** — the fixture contains no Node-24 workaround branch (no engine pinning, no "dsh web" skip), so nothing to remove.

---

## No-hit / ruled-out notes (sub-surfaces and why "no hit" is not "no problem")

All seven primary categories hit, so per requirement 3 the ruled-out sub-surfaces are listed, with the standing caveat from pre-flight.md: **this is a heuristic pattern scan; zero hits only means "not detected by the current patterns"** — a real migration still requires dependency/lockfile resolution, a skipLibCheck:false typecheck, build, a real profile mount (verify-runtime-style), and one functional message → tool → response round before compatibility can be claimed.

| Surface | Cards | What was scanned / ruled out | Residual risk |
|---|---|---|---|
| Permissions/approval, WebFetch | A1-07 | all 6 files: no web_fetch, approval, or sandbox-policy usage | fixture declares no tools that interact with the approval model; a migrated version that adds tools must re-check |
| Packaging/dependencies | A1-24, A2-03, A2-08 | package.json: no @earendil-works/pi-ai (A1-24 non-hit), no peers to prune (A2-03 non-hit as pruning); no dsh-tool-todo / dsh-tool-subagent / dsh-agent peers (A2-08 non-hit) | the *absence* of any declared DSH cohort is itself the gap: the /internal import is undeclared, and self-composed profiles hit A2-08 pending behavior |
| Privacy/telemetry | A1-12, A1-14, A1-23 | no telemetry, upload, or adapter usage in source | base-composition default changes (A1-23) apply at deployment level regardless of plugin source |
| PTC rename vocabulary | A1-06 | no tools.mode:'code', no 'code' preset ids, no CodeDispatch*, no tools/code-dispatch-log strings | none for this fixture |
| Client runtime/snapshot selectors | A1-25/API-10 detail | no dsh-client-runtime, useSession, useChat, ctx.slots, keyed-store usage | if the UI registration migrates to a Web Client face, API-10's keyed-snapshot/command-attachment contracts become applicable |
| rc.2-edge behavior cards | R2-01/02/03 | no image attachments, read_image, or DeepSeek adapter usage | n/a |

## Must verify (before any actual migration; out of scope for this read-only scan)

1. Exact-tag compare rc.2…alpha.2 for the patch-surface target src/session/view/SessionView.ts and the renderSessionView symbol; map to owning module or record removal (A1-03).
2. Dependency/lockfile plan: declare the replacement owning packages for the /internal import and the Remote client mounts; verify packed-artifact resolution (API-07, A2-03 field note on skipLibCheck:false).
3. Build + typecheck + real profile mount on an alpha.2 host; confirm no pending (waiting for service …) rows; one functional path per migrated seam (A1-01 rename + provider list, note write, headless round-trip with exit-code-based success).
4. Decide the custom loopback bridge: wire into the Connection auth gate or remove it (A1-08).

## Integrity statement

Read-only discipline respected: the fixture tree was only ever opened with read/glob/grep tools; no file under environment/fixture (or anywhere in the benchmark repository) was written, and no commands were executed against fixture code. The only write performed by this task is the report file itself.
