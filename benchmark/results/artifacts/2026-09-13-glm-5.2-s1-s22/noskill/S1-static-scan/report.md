# S1 · Static Touchpoint Scan — legacy-plugin (dsh 0.1.1 era → 0.1.2-alpha.2)

- **Mode**: read-only static scan (Mode A inspect). No file under the fixture was modified, created, deleted, or renamed; no script was executed.
- **Fixture scanned**: `E:\deepseek-harness\dsh-plugin-upgrade-skill\benchmark\tasks\S1-static-scan\environment\fixture\` — 6 files, all read in full:
  `README.md`, `package.json`, `patch.yml`, `cordis.patch.yml`, `scripts/apply-patch.mjs`, `src/index.ts`.
- **Corridor**: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2`, connected by the corridor index as two edges:
  rc.2→alpha.1 (card set `DSH-0.1.2-A1`, 28 cards) + alpha.1→alpha.2 (card set `DSH-0.1.2-A2`, 8 cards).
  Card IDs below use the short form (e.g. `A1-01` = `DSH-0.1.2-A1-01`).
- **Corridor folding rule applied**: when a field is removed in an intermediate version and restored in the target, the hit is mapped by the **final net state**, not by delete-then-re-add. This corridor has exactly one such pair: `SessionEvent.ignorable` (removed by A1-02 in alpha.1, restored by A2-01 in alpha.2).

## Summary table

| Touchpoint | Hit | File/line | Applicable card(s) | Confidence note |
|---|---:|---|---|---|
| #1 source patch / monkey patch | YES | `patch.yml`:1-6; `scripts/apply-patch.mjs`:5-9; (`cordis.patch.yml`:1-6 = composition, not a patch hit) | A1-03 | Patch target `src/session/view/SessionView.ts` no longer exists as such; exact new owning module must be confirmed against the target tag |
| #2 internal/persistent events | YES | `src/index.ts`:15-22 | A2-01 (net state; folds A1-02) | Producer + observer roles both present; net state keeps `ignorable: true` |
| #3 internal service / Remote | YES | `src/index.ts`:25-32 | A1-01 (primary), A2-02 (follow-on) | Host-plane `apiProxy` consumer; `session.rename` and `llm.providers` both in the A1-01 migration table |
| #4 host directory reads/writes | YES | `src/index.ts`:34-38 | A1-21 (primary), A1-04 / A1-13 (related) | Hard-coded `~/.dsh/profiles/default`; data-flow trace limited by static-only scan |
| #5 internal UI / commands / tools | YES | `src/index.ts`:10, 40-43 | A1-03 (primary), A1-25 (related) | `@deepseek-ai/dsh-session-view/internal` import + `registerCommand` |
| #6 custom HTTP/WS/RPC channel | YES | `src/index.ts`:47-54 | A1-08 | Loopback-only listener is NOT exempt from the auth gate |
| #7 subprocess / output parsing | YES | `src/index.ts`:57-67; `scripts/apply-patch.mjs`:12-18 | A1-05 (primary), A2-04 (conditional) | Both sites wrongly parse headless stdout as JSONL; stdout is final text in the target |

All seven touchpoint categories hit — there are **no no-hit categories** in this fixture (see "No-hit discipline" for why that still does not prove compatibility).

---

## Per-touchpoint detail

### #1 · Source patch / monkey patch — HIT

**Hits**
- `patch.yml` lines 1-6: declares a patch `surface` with `target: src/session/view/SessionView.ts` and a replacement renaming `export function renderSessionView` → `renderSessionViewPatched`.
- `scripts/apply-patch.mjs` lines 5-9: requires `DSH_HARNESS_SOURCE_ROOT` and reads/applies the `patch.yml` surface — the classic patch-surface mechanism (`DSH_HARNESS_SOURCE_ROOT` + `patch-surface` patterns).
- `cordis.patch.yml` lines 1-6: **not** a source-patch hit. Per the pre-flight classification (API-08 in the alpha.2 API ledger), an ordinary `cordis.patch.yml` is **profile composition**; a filename containing "patch" alone is not a hit for this class. It is recorded under configuration inventory, and its `patch:` list entry referencing `patch.yml` is the composition-side link to the real #1 hit.

**Coupling points + card mapping**
- **A1-03 (Session view internals split up extensively; touchpoints #1, #5, required-if-hit)**: the host session-view internals were extensively split in alpha.1. The patch target path `src/session/view/SessionView.ts` and the symbol `renderSessionView` must be re-validated one-by-one against an exact-tag compare of the target; each old target must map to a target-version file or state an explicit removal reason. Capabilities with no stable public seam are "pending confirmation" — do not guess new paths. (dsh-tui's field-verified approach: point `DSH_HARNESS_SOURCE_ROOT` at the target tag and validate each patch-surface path by composition.)

### #2 · Internal event names / persistent events — HIT

**Hits**
- `src/index.ts` lines 15-19: **producer** of a third-party persisted session event — `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: {...} })`. This is an external informational SessionEvent producer.
- `src/index.ts` lines 20-22: plain **observer** — `ctx.on('session/event', ...)` logging `event.type`. Observer-only coupling; no card action beyond verifying the event vocabulary still reaches it.

**Coupling points + card mapping — the corridor-folding case**
- **A1-02 (`SessionEvent.ignorable` temporarily removed)** removed the marker in alpha.1: unknown persisted events without `ignorable` are treated as required and first-party readers **reject the reload**.
- **A2-01 (Restore `SessionEvent.ignorable` for third-party persisted events)** restores the retention semantics in alpha.2 (envelope/persistence/reload/transport keep the field as-is).
- **Net state for the 0.1.1-rc.2 → 0.1.2-alpha.2 corridor: the marker survives.** The producer's `ignorable: true` on line 17 must be **kept as-is** — do NOT delete it for alpha.1 and re-add it; map the hit to **A2-01** (which explicitly reverts A1-02). Two caveats from A2-01 still apply to this producer:
  1. `ignorable: true` is only correct for informational events whose semantics an old reader can omit without affecting reconstruction — `legacy/informational-note` qualifies;
  2. the public live `Session.append(...)` still has no `ignorable` parameter; a plugin limited to that API should mark the producer seam as a capability gap, not fake a public entry via cast. This fixture emits through `ctx.emit('session/event', ...)`, i.e. exactly the producer/persistence seam A2-01 governs.
- Only if the migration were to **stop at alpha.1** (it is not the target here) would A1-02's recipe apply (stop writing the unknown event / switch to known public vocabulary).

### #3 · Internal service probes / Remote — HIT

**Hits**
- `src/index.ts` line 26: `const apiProxy = await ctx.get('apiProxy')` (rename-session), line 27: `apiProxy.invoke('session.rename', { id, title })`.
- `src/index.ts` lines 30-31: `ctx.get('apiProxy')` again, `apiProxy.invoke('llm.providers')`.

**Coupling points + card mapping**
- **A1-01 (APIProxy removed, Host/Web Client calls moved to `@Remote`; touchpoint #3, breaking, required-if-hit)**: the `apiProxy` service key (package `@deepseek-ai/dsh-host-apiproxy`) is **deleted in alpha.1**; there is no `APIProxy` identifier at all in the target. Both fixture call sites are in the A1-01 migration table:
  - `session.rename` → Remote `session/rename` (`ctx.remote.session.rename`, generated declaration in the `session` namespace);
  - `llm.providers` → **split into two**: `llm/listProviders` + `llm/listConfigurableProviders` — one old call becomes two results; the fixture's single-call `list-providers` registration must return the merged/chosen shape deliberately.
- **Plane discipline (A1-01 field note)**: this fixture's `activate(ctx)` is a **host-plane** plugin (no `dsh.client` declaration, server-side Node imports). The old `apiProxy` was the host-plane facade; `ctx.remote.*` is the **client-plane** facade — they are not interchangeable. The correct host-plane migration is to **skip the gateway and inject the domain service directly** (e.g. `inject: ['llm']` then `ctx.llm.listProviders()`); switching to `inject: ['remote']` on the host plane stalls forever at `pending (waiting for service: remote)`.
- **A2-02 (Remote failures become `RemoteError`; error codes gain namespaces; touchpoint #3)**: follow-on card for whatever Remote calls the migration lands on. `RemoteResult<T>` is `{ ok, value } | { ok: false, error }`; `error` is now a `RemoteError` instance; codes are namespaced (`session-not-found` → `session/not-found`, `internal` → `gateway/internal`, `cancelled` → `gateway/cancelled`, ...). Do not branch on old code strings, parse `Error.message`, wrap calls in defensive catches, or use `instanceof` across realms; use `isRemoteFailure` from `@deepseek-ai/dsh-api-gateway/client` for structural discrimination only.
- Not applicable: A1-22 (`isTokenDelta`), A2-05 (pluginInventory), A2-06 (`$host.home` — client-plane only), A2-08 (sessionProjections inject), A2-10 (settingsNamespace) — no corresponding call sites in the fixture.

### #4 · Direct host directory reads/writes — HIT

**Hits**
- `src/index.ts` lines 5-7 (`homedir`, `join`, `writeFileSync` imports) and lines 34-38: hard-coded profile path `join(homedir(), '.dsh', 'profiles', 'default')` with `writeFileSync(join(profileDir, 'legacy-note.txt'), text)`.

**Coupling points + card mapping**
- The coupling is a **hard-coded Host/profile directory assumption** (`~/.dsh/profiles/default`), including the assumption that the directory exists and is writable. Per the pre-flight #4 card set (A1-04, A1-13, A1-21), the most relevant cards:
  - **A1-21 (`dsh-agent-presets` drops `resolveSessionPreset`; shipped presets now come from the package's `presets/`)** — primary: profile/preset directory ownership moved; a plugin writing into a guessed profile layout can no longer assume the rc.2-era directory semantics.
  - **A1-04 (ACP/SDK examples merged into the `dsh` profile; standalone demo bins/packages removed)** and **A1-13 (platform shell and directory-picker fixes may obsolete old workarounds)** — related: both change what may legitimately be assumed about host directories/profiles and provide the public `directoryPicker/*` Remote surface as the sanctioned alternative.
- A line-level scan cannot reveal data flow; the static scan confirms the path is fully static (no env override, no existence check, no `DSH_HOME` handling). Migration should stop deriving host paths from `homedir()` and use the owning public seam (settings/preset documents or `$host.home` on the client plane / the host-side owning service), and never write into a guessed profile directory.

### #5 · Internal UI / commands / tool registration — HIT

**Hits**
- `src/index.ts` line 10: `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` — a private Host/Web Client internal path.
- `src/index.ts` lines 40-43: `ctx.contributes.registerCommand('legacy.openView', ...)` constructing `new SessionView({ enhanced: true })`.

**Coupling points + card mapping**
- **A1-03 (Session view internals split up extensively; touchpoints #1, #5, breaking)**: the `/internal` import path and the `SessionView` symbol's home were split up by owning module; the import must be rebuilt against the target tag's actual exports, and capabilities without a stable public seam marked "pending confirmation". Ordinary plugins should migrate to public facets/services rather than add new internal imports.
- **A1-25 (`@deepseek-ai/dsh-client-runtime` removed, client symbols migrated by domain; touchpoints #3, #5)** — related: the domain-migration pattern (symbols moved to per-domain `.../client` packages, e.g. conversation UI to `@deepseek-ai/dsh-client-ui-conversation/client`) is the template for rebuilding this import if the plugin is (or becomes) a Web Client plugin; `package.json` dependencies/`dsh.client` declarations must be cleaned up in the same pass. Note the fixture's `package.json` declares no dependencies at all — after migration the actually-consumed packages must be declared directly.
- Not hit: A1-09/A1-10/A1-11 (new capabilities — suggestions only, never adopted automatically), A1-26 (client-modules registration-id rule; no client bundle here), A1-28/A1-29 (composer/markdown UI internals; no DOM code in fixture).

### #6 · Custom HTTP / WS / RPC / DOM / CSS channels — HIT

**Hits**
- `src/index.ts` lines 4 (`createServer` import) and 47-54: `startLegacyBridge()` — `createServer` answering `'legacy'`, `server.listen(43121, '127.0.0.1')` (comment: `http://localhost:43121/api/legacy`), explicitly documented as bypassing the Host Gateway authentication model. The function is never invoked (`void startLegacyBridge`), but the coupling is present in source.

**Coupling points + card mapping**
- **A1-08 (Web/API channels use process-scoped bootstrap tokens and signed cookies; touchpoint #6 via the pre-flight card list)**: in the target, Web/API channels require process-scoped bootstrap tokens and signed cookies, and **loopback is not exempt** — the ghost-host probe measurement showed the identical loopback request flip from `ok:true` (old generation) to `401` (new generation). A custom unauthenticated loopback HTTP bridge like this one is exactly the pattern the card invalidates; it has no migration recipe other than removing the private channel and using the authenticated Host Gateway / Remote surface.
- Also record port lifecycle/teardown: the server handle is created inside `activate` with no disposal registration — even aside from auth, this violates reversible-effect lifecycle rules and must be addressed in any migration.

### #7 · Subprocess / stdout / stderr parsing — HIT

**Hits**
- `src/index.ts` lines 8, 57-67: `spawn('dsh', ['--profile', 'headless', prompt])`; `child.stdout.on('data', ...)` runs `JSON.parse` per chunk and looks for `event.type === 'final'` — i.e. assumes headless stdout is JSONL.
- `scripts/apply-patch.mjs` lines 3, 12-18: `execFileSync('dsh', ['--profile', 'headless', 'ping'])` then `JSON.parse` each stdout line expecting `{ type: 'final', text }` — same wrong JSONL assumption, and additionally parses per-line on a chunk stream that gives no line-boundary guarantee.

**Coupling points + card mapping**
- **A1-05 (Headless: stderr gains a `dsh: reasoning:` segment; stdout remains the final text; touchpoint #7, required-if-hit)**: in the target, headless **stdout is the final text, not JSONL**. Both fixture sites are built on the deliberately wrong assumption; after migration, stdout must be consumed as plain final text (no `JSON.parse`, no `event.type === 'final'` scan), and any reasoning output is on **stderr** under the `dsh: reasoning:` prefix — parsing stderr as structured output is also wrong.
- **A2-04 (empty client graph fix for `dsh web` on Node 24.0-24.11.1; touchpoint #7, conditional)**: only relevant if the wrapper carries workarounds for that Node window (forcing Node 22, skipping `dsh web`, probing the loader by major version). The fixture has no such workaround branch — record as scanned and not applicable, keep other Node constraints untouched. Also note `engines.node` is unchanged across the corridor, so no engine-range edit is warranted.
- Wrapper verification beyond "the process starts": argv, cwd, env, cancellation, exit codes, and stdout/stderr ownership must each be covered; both fixture sites ignore stderr entirely and have no error/exit-code handling (`execFileSync` throws on nonzero exit; the spawn site resolves with whatever partial string was captured).

---

## No-hit discipline (requirement 3)

All seven categories hit in this fixture, so there is no no-hit row to justify. Two adjacent statements still required by the method:

1. **Zero hits would not have proven compatibility.** The pre-flight scan is heuristic: "zero hits across the seven classes only means 'not detected by the current patterns'". A clean scan still requires (a) the dependency/configuration inventory (`package.json` peers/engines/`@deepseek-ai/*` imports — this fixture declares **none**, which itself must be re-checked after migration because A1-25/A2-03 make direct dependency declaration load-bearing), (b) build + typecheck against the target cohort, (c) a real profile mount with entry activation verified (no `pending (waiting for service: ...)` lines), and (d) a functional smoke path including wrapper exit-code/stdout/stderr behavior.
2. **Cards are a curated list, not a complete API diff.** Absence of a card for a surface does not prove absence of impact; where corridor edges or API coordinates are missing (e.g. the exact post-split home of `SessionView` under A1-03), the correct output is "pending confirmation against the target tag", never a guessed path.

## Scan-scope and read-only attestation

- Files read (in full, with line numbers): the 6 fixture files listed above. No other fixture-adjacent file was touched; no command was executed against the fixture; nothing inside the fixture directory (or anywhere in the benchmark repository) was modified, created, deleted, or renamed.
- Reference material used for card mapping (read-only, outside the fixture): `skills/plugin-upgrade/SKILL.md`, `references/pre-flight.md`, `references/v0.1.2-alpha.1.md`, `references/v0.1.2-alpha.2.md`. The task's `solution/` directory was **not** read.
- Static-only limitations: no build/typecheck/mount was run (the fixture is a static copy that cannot compile by design); all "pending confirmation" items above are exactly the ones a static scan cannot close.
