# S1 · Static Touchpoint Scan Report — legacy-plugin (0.1.1 → 0.1.2-alpha.2)

## Scope and method

- Scanned (read-only; nothing under the fixture was modified): `README.md`, `cordis.patch.yml`, `package.json`, `patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts` (6 source files + README; no node_modules or build output present).
- Corridor: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1` (card set `DSH-0.1.2-A1-xx`, 28 cards) then `dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (card set `DSH-0.1.2-A2-xx`). Cards are read from the plugin-upgrade skill's references `v0.1.2-alpha.1.md` and `v0.1.2-alpha.2.md` (curated lists, not a complete API diff).
- Corridor folding applied: changes removed in alpha.1 and restored in alpha.2 are judged by the **final net state** (per skill SKILL.md step "read the full corridor first and compute the final net state" and pre-flight §1.3).

## 1. Per-touchpoint findings

### #1 Source patch / monkey patch — HIT

- Files/lines: `cordis.patch.yml:5-6` (`patch: - patch.yml`), `patch.yml:2-6` (`surface: - target: src/session/view/SessionView.ts` with a `replacements` find/replace of `export function renderSessionView`), `scripts/apply-patch.mjs:5-9` (`DSH_HARNESS_SOURCE_ROOT` + applying `patch.yml`).
- Coupling points: the patch targets an exact host source path `src/session/view/SessionView.ts` and an exact exported symbol. `cordis.patch.yml` here is **not** plain profile composition — it declares a source patch surface (per pre-flight #1: "A line-level search cannot reveal... an ordinary cordis.patch.yml is composition and must be classified per API-08; a filename containing patch alone is not a hit" — here the file explicitly carries `patch:` + `surface`, so it is a genuine #1 hit).
- Card: **DSH-0.1.2-A1-03** (Session view internals split up extensively; Touchpoints #1 and #5). The patch target path and symbol must be re-derived against the exact alpha.2 tag or marked "pending confirmation"; do not guess new paths.

### #2 Internal / persistent events — HIT

- Files/lines: `src/index.ts:13-22` — `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: ... })` (producer of a third-party persisted informational event) and `ctx.on('session/event', ...)` (observer).
- Coupling points: the custom event type `legacy/informational-note` and the `ignorable: true` envelope marker on a persisted external event.
- Cards: corridor pair **DSH-0.1.2-A1-02** ("SessionEvent.ignorable temporarily removed", alpha.1) folded with **DSH-0.1.2-A2-01** ("Restore SessionEvent.ignorable for third-party persisted events", alpha.2). Folding verdict: removed-then-restored ⇒ **zero net change to the marker semantics**; A1-02's own recipe states for a final target of alpha.2 or later, "do not delete the producer marker and then restore it". Action: **keep `ignorable: true`** exactly as written. Residual obligations from A2-01: the plugin is a producer seam only (plain `ctx.emit`), and alpha.2's public live `Session.append` still has no `ignorable` parameter — no code edit indicated by the corridor; verify at runtime that the unknown event survives reload and is omittable by old readers, and note the SQLite schema-20-only provider rule if any deployment pins a schema-19 store.

### #3 Internal service probes / Remote — HIT (the hardest break)

- Files/lines: `src/index.ts:24-32` — two registrations: `rename-session` calls `await ctx.get('apiProxy')` then `apiProxy.invoke('session.rename', { id, title })`; `list-providers` calls `ctx.get('apiProxy')` + `apiProxy.invoke('llm.providers')`.
- Coupling points: the `apiProxy` service key, the `ApiProxy` surface, and the wire operation names `session.rename` and `llm.providers`.
- Card: **DSH-0.1.2-A1-01** (APIProxy removed, Host/Web Client calls moved to `@Remote`). alpha.1 deletes the `@deepseek-ai/dsh-host-apiproxy` package; there is no `apiProxy` key or `APIProxy` identifier. This plugin is a **host-plane ordinary Cordis plugin** (not a Web Client), so per A1-01's field note the correct host-plane migration is to skip the gateway and inject the domain service directly: `rename-session` → inject the session domain service and call the session-rename seam (`session/rename` in the Remote table; do **not** switch to `inject: ["remote"]` — the host plane reports `pending (waiting for service: remote)`); `llm.providers` → `inject: ["llm"]` + `ctx.llm.listProviders()` (one call split into `llm/listProviders` + `llm/listConfigurableProviders`). Only a browser-plane face would use `ctx.remote.*`, and this package.json declares no `dsh.client`.
- Secondary mapping note: if/when any code path inspects Remote call results, **DSH-0.1.2-A2-02** applies (errors become `RemoteError` instances with namespaced codes, e.g. `session/not-found`, `gateway/cancelled`); the fixture never branches on error codes, so this is a conditional note, not a required edit. A1-01 also lists `Touchpoints: #3; indirectly #1`.

### #4 Direct host directory reads/writes — HIT

- Files/lines: `src/index.ts:34-38` — `join(homedir(), '.dsh', 'profiles', 'default')` then `writeFileSync` of `legacy-note.txt` into that directory.
- Coupling points: the hard-coded user-directory layout `~/.dsh/profiles/default` — the plugin writes a foreign file into the host's own profile home instead of using runtime `DSH_HOME`/a host service.
- Card: **DSH-0.1.2-A1-04** (ACP/SDK examples merged into the `dsh` profile, standalone demo bins removed; Touchpoints #4 and #7). Its recipe: "Use the runtime DSH_HOME, the target profile, and the official launcher as the source of truth ... do not hardcode user directories." `DSH-0.1.2-A1-13` (Touchpoints #4/#7, conditional) is a weaker secondary association: platform shell/directory fixes may obsolete workarounds — no workaround is planted here, so A1-13 is noted, not mapped.

### #5 Internal UI / commands / tool registration — HIT

- Files/lines: `src/index.ts:9-10` — `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'`; `src/index.ts:40-43` — `ctx.contributes.registerCommand('legacy.openView', () => new SessionView({ enhanced: true }))`.
- Coupling points: a `/internal` subpath import of a session-view symbol, and a view-constructing command registration bound to that internal component.
- Card: **DSH-0.1.2-A1-03** (same card as #1 — Touchpoints #1 and #5). alpha.1 splits session-view internals; the `/internal` import path and the symbol are expected to disappear. Migration: rebuild the import by owning module against the exact target tag; if no stable public seam exists for this view, mark the capability "pending confirmation" rather than guessing. (A1-03's field notes confirm both a patch-surface validation flow and client-side real migrations through this card.)

### #6 Custom HTTP / WS / RPC / DOM channels — HIT

- Files/lines: `src/index.ts:45-54` — `startLegacyBridge()` creates a `node:http` `createServer` and `server.listen(43121, '127.0.0.1')` (comment: `http://localhost:43121/api/legacy`), described as "Private loopback HTTP bridge that bypasses the Host Gateway authentication model." The function is defined but never invoked (`void startLegacyBridge`) — the coupling is static, not live.
- Coupling points: an unauthenticated loopback HTTP channel outside the host's Web/API auth model, with an `/api/*`-style path name.
- Card: **DSH-0.1.2-A1-08** (Web/API channels use process-scoped bootstrap tokens and signed cookies; Touchpoints: #6). After alpha.1, unauthenticated channels that reach Web UI or `/api` semantics receive 401/403, and "private routes that bypass auth become security holes"; loopback is not exempt. Migration: wire the handler into the Connection auth gate (`ctx.connection.requestRejection(req)` first) or move it to a Connection-owned carrier; never treat "listening on loopback only" as protection.

### #7 Subprocess / stdout / stderr parsing — HIT (two independent sites)

- Files/lines:
  - `scripts/apply-patch.mjs:12-19` — `execFileSync('dsh', ['--profile', 'headless', 'ping'])`, then splits stdout by newline and `JSON.parse`s each line looking for `{ type: 'final' }`. Comment on line 11 admits: "Deliberately wrong expectation: target headless stdout is final text, not JSONL."
  - `src/index.ts:56-67` — `spawn('dsh', ['--profile', 'headless', prompt])` and `JSON.parse` per stdout chunk expecting `event.type === 'final'`.
- Coupling points: assumption that headless stdout is JSONL event stream; argv shape `--profile headless`; no exit-code or stderr handling.
- Cards: **DSH-0.1.2-A1-05** (Headless: stderr gains a `dsh: reasoning:` segment; stdout remains the final text; Touchpoints: #7). rc.2's stdout was *already* the final assistant text (`packages/bundle/headless/src/index.ts:129`) — it was never JSONL, so both parsers fail on every version in the corridor and must parse stdout as plain final text, judge success by exit code, and consume the alpha.1-added stderr `dsh: reasoning:` / `dsh: <code>: <message>` segments. Secondary: **DSH-0.1.2-A1-04** (Touchpoints #4/#7 — profile/launcher wrappers must follow the official launcher and not hardcode profile paths); conditional note **DSH-0.1.2-A2-04** (`dsh web` Node 24.0–24.11.1 loader fix, Touchpoint #7 — relevant only if a wrapper added Node-version workarounds; none present here). A1-05 is an additional stdout mapping beyond the six core cards and is valid to include.

## 2. Card mapping summary (0.1.1-rc.2 → 0.1.2-alpha.2 corridor)

| Touchpoint | Hit | Location | Card(s) | Net-state note |
|---|---|---|---|---|
| #1 source patch | Yes | `cordis.patch.yml:5-6`, `patch.yml:2-6`, `scripts/apply-patch.mjs:5-9` | DSH-0.1.2-A1-03 | Validate each surface target against the exact alpha.2 tag or mark pending confirmation |
| #2 events | Yes | `src/index.ts:13-22` | DSH-0.1.2-A1-02 ⇄ **DSH-0.1.2-A2-01 (folded)** | Removed in alpha.1, restored in alpha.2 ⇒ net-zero; keep `ignorable: true`; do not delete-and-restore |
| #3 service/Remote | Yes | `src/index.ts:24-32` | DSH-0.1.2-A1-01 (secondary conditional: DSH-0.1.2-A2-02) | Host-plane: inject domain services (`llm` etc.), not `remote` |
| #4 host directory | Yes | `src/index.ts:34-38` | DSH-0.1.2-A1-04 | Stop hardcoding `~/.dsh/profiles/default`; use runtime DSH_HOME |
| #5 UI/commands | Yes | `src/index.ts:9-10, 40-43` | DSH-0.1.2-A1-03 | `/internal` import + `registerCommand` seam; rebuild or mark pending |
| #6 custom channel | Yes | `src/index.ts:45-54` | DSH-0.1.2-A1-08 | Unauthenticated loopback `/api/legacy` bridge must join the Connection auth gate |
| #7 subprocess/output | Yes | `scripts/apply-patch.mjs:11-19`, `src/index.ts:56-67` | DSH-0.1.2-A1-05 (secondary: DSH-0.1.2-A1-04; conditional: DSH-0.1.2-A2-04) | stdout is final text, never JSONL; add exit-code + stderr handling |

Folding rule as applied: the corridor's `ignorable` field is removed by A1-02 at alpha.1 and restored by A2-01 at alpha.2, the target version. Judged by the final net state, the producer marker must remain; A1-02 is cited only to document the corridor history, and the actionable card is A2-01.

## 3. No-hit accounting and limits of a static scan

Strictly, all seven categories produced hits in this fixture. The nearest "negative" conclusions, stated with their evidence:

- **No Web Client plane**: scanned `package.json` — no `dsh.client` field, no `@deepseek-ai/dsh-client-runtime`, no client dependencies; `src/index.ts` has no `ctx.remote`, `useSession`/`useChat`, slot, or DOM code. Cards DSH-0.1.2-A1-25, A1-19, A1-26, A1-28–A1-32 are therefore not hit **on this static evidence**.
- **No settings/user-questions/preset/llm-type seams**: no `settingsNamespace`, `registerProvider`, `resolveSessionPreset`, `isTokenDelta` anywhere (grep-equivalent read of all six files) — A2-10, A1-20, A1-21, A1-22 not hit.
- **No packaging coupling**: `package.json` has no `@deepseek-ai/*` dependencies at all, so A1-24 (pi-ai) and A2-03 (peer trims) cannot bind — though note the flip side: the plugin also declares no DSH cohort, so the static scan cannot tell which host packages it will actually resolve against.

Why "no hit = no problem" cannot be concluded (per pre-flight.md's own header: "This is a heuristic scan, not proof of compatibility"):

1. **Coverage limits**: the scan covered 6 files with no dependency tree, lockfile, tests, CI, or node_modules present; generated artifacts, vendor code, and transitively imported code were invisible. A pattern not present in text can still be present at runtime (dynamic property access, string-built imports).
2. **Data-flow limits**: line-level search cannot prove data flow (pre-flight #4 says so explicitly) — e.g. the #4 path construction is static here, but whether any other code path feeds the same directory can only be seen when running.
3. **Card list is curated, not exhaustive**: each card file states it is "a curated list of plugin-relevant changes, not a complete API diff". A zero-hit against the cards does not zero-hit against the actual alpha.2 API surface.
4. **Static cannot see the running host**: the ghost-host problem (pre-flight §1.5) and runtime-only failure modes (a wrong `inject` stalls as `pending (waiting for service: …)`; a missing peer never fails typecheck — A2-08's warning) are only observable on a real mount.

Required verification before declaring the migration done: build/typecheck against alpha.2 devDependencies; a real `dsh plugin add` + cold boot on an isolated profile with `--dump-config` showing no pending lines; per-hit functional checks — session rename and provider listing on the new host-plane services, the informational event surviving reload with `ignorable: true`, the command/view seam resolving or being explicitly retired, a 401-then-cookie path for any channel kept outside the gate, and one headless round reading stdout as final text with exit-code-based success.

*Fixture left untouched: no file under the fixture directory was created, modified, or deleted during this scan.*
