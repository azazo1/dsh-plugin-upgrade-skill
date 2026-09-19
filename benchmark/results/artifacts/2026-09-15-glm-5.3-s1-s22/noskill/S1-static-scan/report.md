# S1 · Static Touchpoint Scan Report — legacy-plugin (0.1.1 era)

**Task**: read-only touchpoint inspection of `<fixture>/` for the planned migration
**dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.2**.
**Mode**: Mode A-style static scan (skill `plugin-upgrade`, pre-flight seven-class checklist). No file under the fixture was modified, created, deleted, or renamed; no build, install, or execution was performed.

## 0. Scope, corridor, and method

- **Files scanned (complete fixture inventory, 6 files)**:
  - `README.md` (16 lines, fixture self-description — cross-checked against findings, not used as sole evidence)
  - `package.json` (9 lines)
  - `cordis.patch.yml` (6 lines)
  - `patch.yml` (6 lines)
  - `scripts/apply-patch.mjs` (19 lines)
  - `src/index.ts` (68 lines)
- **Corridor construction**: edges connected by `from → to` metadata, not filename order:
  `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1` (28 cards, prefix `DSH-0.1.2-A1`, `references/v0.1.2-alpha.1.md`) plus `dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (8 cards, prefix `DSH-0.1.2-A2`, `references/v0.1.2-alpha.2.md`). Net state folded before mapping (see §2 and touchpoint #2).
- **Dependency/configuration inventory (pre-flight step 0)**: `package.json` declares `name: legacy-plugin`, `version: 0.1.1`, `private: true`, `type: module`, one script (`apply-patch`). It declares **no** `dependencies`, `peerDependencies`, `engines`, `dsh.client`, or `dsh-plugin.json` manifest — yet `src/index.ts:10` imports `@deepseek-ai/dsh-session-view/internal`, an undeclared phantom internal import. No lockfile present. Install track: source tree (not an installable plugin; fixture).
- Cards are a **curated list, not a complete API diff**; every mapping below is a corridor intersection, not a guarantee of exhaustive impact.

## Summary table

| Touchpoint | Hit | File/line | Applicable card(s) | Confidence note |
|---|---:|---|---|---|
| #1 source patch | YES | `cordis.patch.yml:5-6`; `patch.yml:2-6`; `scripts/apply-patch.mjs:5-9` | DSH-0.1.2-A1-03 (primary; A1-01 indirect) | patch target `src/session/view/SessionView.ts` is inside the split-up session-view internals; must revalidate per exact tag |
| #2 events | YES | `src/index.ts:15-19` (producer, `ignorable: true`); `:20-22` (observer) | **A1-02 + A2-01 folded → net: restored** (map to A2-01) | corridor folding: removed in alpha.1, restored in alpha.2 — keep the marker, do not delete-and-readd |
| #3 service/Remote | YES | `src/index.ts:26-27` (`session.rename`); `:29-32` (`llm.providers`) | DSH-0.1.2-A1-01 (primary); DSH-0.1.2-A2-02 (error flow after migration) | host-plane plugin: migrate to domain-service injection, **not** `ctx.remote` |
| #4 host filesystem | YES | `src/index.ts:36-37` | DSH-0.1.2-A1-04 (primary); A1-21 (adjacent) | hardcoded `~/.dsh/profiles/default` ignores `DSH_HOME` |
| #5 UI/commands/tools | YES | `src/index.ts:10` (internal import); `:41-43` (`registerCommand` + `new SessionView`) | DSH-0.1.2-A1-03 (primary); A1-25 (symbol redistribution) | private `/internal` path removed by UI decomposition |
| #6 custom channel | YES | `src/index.ts:47-53` (loopback HTTP :43121) | DSH-0.1.2-A1-08 | unauthenticated route bypassing the Connection auth gate; loopback is not an exemption |
| #7 subprocess/output | YES | `src/index.ts:57-66`; `scripts/apply-patch.mjs:12-18` | DSH-0.1.2-A1-05 (primary); A1-04 (wrapper/profile discipline) | both sites assume headless stdout is JSONL — it never was (rc.2 already final text) |

All seven classes hit; there are **no no-hit categories** in this fixture (no-hit evidencing obligations of requirement 3 therefore do not attach — but see §"Why no-hit ≠ no problem", which applies symmetrically to hits).

## Per-touchpoint findings

### #1 Source patch / monkey patch — HIT

**Evidence**:
- `cordis.patch.yml:5-6`: declares `patch:` → `patch.yml`. Note: the file itself is profile composition (API-08: `cordis.patch.yml` is composition, not a source patch), but the `patch:` key makes it a genuine **source-patch declaration** — a filename containing "patch" alone would not be a hit; the declared surface is.
- `patch.yml:2-6`: patch surface with `target: src/session/view/SessionView.ts`, replacement `export function renderSessionView` → `export function renderSessionViewPatched`.
- `scripts/apply-patch.mjs:5-9`: consumes `DSH_HARNESS_SOURCE_ROOT` and reads `patch.yml` to apply the surface against host source.

**Card mapping**: **DSH-0.1.2-A1-03** ("Session view internals split up extensively", touchpoints #1/#5, breaking, required-if-hit). The patch target lives exactly in the split-up session-view internals; the target path, the symbol `renderSessionView`, and the find/replace anchors must each be re-mapped to an owning module at the exact target tag (exact-tag compare `dsh-v0.1.1-rc.2...dsh-v0.1.2-alpha.2`); where no stable public seam exists the capability must be marked "pending confirmation", not guessed (A1-03 recipe). A1-01 lists #1 as an *indirect* touchpoint here (the APIProxy→Remote architecture note co-moved host internals), but A1-03 owns this hit. Verification per card: run the patch-surface composition against target-tag source; every old target maps to a target-version file or states an explicit removal reason.

### #2 Internal/persistent events — HIT (corridor folding applies)

**Evidence**:
- `src/index.ts:15-19`: **producer** of a third-party persisted SessionEvent — `ctx.emit('session/event', { type: 'legacy/informational-note', ignorable: true, payload: {...} })`.
- `src/index.ts:20-22`: plain **observer** via `ctx.on('session/event', ...)` (logs `event.type` only; no persistence role).

**Card mapping with corridor folding (the brief's requirement 2)**:
- `DSH-0.1.2-A1-02`: alpha.1 **temporarily removed** `SessionEvent.ignorable`; alpha.1 readers reject sessions containing unknown unmarked events on reload.
- `DSH-0.1.2-A2-01`: alpha.2 **restored** the marker's producer/persistence/reload/transport retention semantics (explicit revert of A1-02).
- **Net state for target 0.1.2-alpha.2: the field exists.** The correct mapping is therefore **A2-01 as the final-state card, with A1-02 recorded only as the intermediate corridor state**. Concretely: the migration must **keep** the producer's `ignorable: true` at `src/index.ts:17` — do *not* delete the marker for alpha.1 and re-add it for alpha.2 (A1-02's own recipe forbids exactly that churn when the final target is alpha.2+). A1-02 becomes actionable only if the plugin were ever pinned to exactly alpha.1.
- A2-01 caveats that attach to this hit: the marker is producer-side semantics for informational events an old reader may omit; it is not a consumer-side filter, and events remain in loaded events after reload. The public `Session.append(...)` still has no `ignorable` parameter — this fixture emits through the raw `session/event` producer seam, which is the envelope-level capability; if the migration moves to public APIs, mark the producer seam as a capability gap rather than casting a fake public entry. (SQLite provider accepts only schema 20 — persistence-side note from A2-01, not directly hit by this source.)
- The observer at `:20-22` is unaffected by the folding (it never branches on `ignorable`).

### #3 Internal service / Remote — HIT

**Evidence** (`src/index.ts`):
- `:26-27`: `const apiProxy = await ctx.get('apiProxy')` → `apiProxy.invoke('session.rename', { id, title })` (registered as `rename-session`).
- `:29-32`: same probe → `apiProxy.invoke('llm.providers')` (registered as `list-providers`).

**Card mapping**: **DSH-0.1.2-A1-01** ("APIProxy removed, Host/Web Client calls moved to `@Remote`", touchpoint #3 — and #1 indirectly — breaking, required-if-hit). The `apiProxy` service key (package `@deepseek-ai/dsh-host-apiproxy`) is deleted in alpha.1; both call sites die.
- **Plane determination (decisive for the recipe)**: this is a **host-plane** plugin (server-side `activate(ctx)`, uses `ctx.get`/`ctx.register`, no `dsh.client` declaration). Per A1-01's field note, host-plane consumers must **not** swap to `inject: ['remote']` (that yields `pending (waiting for service: remote)`); the correct migration is to skip the gateway and inject the domain service behind it (e.g. `inject: ['llm']`, `ctx.llm.listProviders()`). The `ctx.remote.*` table applies to the client plane only.
- Operation mapping per A1-01's table: `session.rename` → `session/rename` (client-plane spelling; host-plane equivalent is the session-domain service); `llm.providers` → `llm/listProviders` **plus** `llm/listConfigurableProviders` — one call splits into two results, so `list-providers`'s return shape changes too.
- **DSH-0.1.2-A2-02** (secondary, touchpoint #3): after migration, Remote failures are `RemoteError` instances with namespaced codes (`session/not-found`, `gateway/cancelled`, ...); handle `RemoteResult<T>` result branches, never parse `Error.message` or blanket-catch. Applies to whichever call form the migrated code adopts.

### #4 Host filesystem — HIT

**Evidence**: `src/index.ts:36-37`: `const profileDir = join(homedir(), '.dsh', 'profiles', 'default')` then `writeFileSync(join(profileDir, 'legacy-note.txt'), text)` — a hardcoded host/profile directory built from `os.homedir()`, ignoring `DSH_HOME`.

**Card mapping**: **DSH-0.1.2-A1-04** (touchpoints #4/#7, required-if-hit): profiles live under the runtime `DSH_HOME` (`$DSH_HOME/profiles`); wrappers/code that hardcode user directories or fixed profile paths "no longer match". Recipe: use runtime `DSH_HOME`, the target profile, and the official launcher as the source of truth; do not hardcode user directories. **DSH-0.1.2-A1-21** is adjacent (touchpoints #3/#4): it concerns `roots` pointing at the old CLI `config/agent-presets/` directory — this fixture does not configure `roots`, so A1-21 is *not* hit on #4; recorded to show it was considered and excluded. A1-13 (shell/directory-picker workarounds, #4/#7) considered and excluded: no platform workaround branches exist in the fixture.

### #5 Internal UI / commands / tools — HIT

**Evidence** (`src/index.ts`):
- `:10`: `import { SessionView } from '@deepseek-ai/dsh-session-view/internal'` — a private internal Host/Web Client path (the file's own comment: "private Host/Web Client path removed by UI decomposition"), and an undeclared dependency (see inventory, §0).
- `:41-43`: `ctx.contributes.registerCommand('legacy.openView', ...)` returning `new SessionView({ enhanced: true })`.

**Card mapping**: **DSH-0.1.2-A1-03** (primary; touchpoints #1/#5): internal imports and UI registration points around the session view no longer work; rebuild imports by owning module, mark capabilities without a stable public seam "pending confirmation", and prefer public facets/services over new internal imports. **DSH-0.1.2-A1-25** (secondary; touchpoints #3/#5): the client-symbol unbundling/redistribution pattern — `SessionView`-class symbols moved to domain-owning packages; the concrete new owner must be read from the target tag's actual exports, not assumed. Considered and excluded: **A1-26** (client-modules registration id == package name) applies to plugins with a Web Client half building a client bundle — this fixture has no `dsh.client`/client bundle, so not hit; **A1-06** (PTC rename): no `tools.mode: 'code'`, preset ids, or dispatch identifiers present; **A1-28/A1-29** (composer DOM, MarkdownText labels): no client DOM/render code; **A1-09/A1-10/A1-11** are optional capabilities — never adopted automatically.

### #6 Custom channel — HIT

**Evidence**: `src/index.ts:47-53`: `startLegacyBridge()` creates a `node:http` server on `127.0.0.1:43121` (comment: `http://localhost:43121/api/legacy`) that "bypasses the Host Gateway authentication model" (never invoked; `void startLegacyBridge` at `:54`).

**Card mapping**: **DSH-0.1.2-A1-08** ("Web/API channels use process-scoped bootstrap tokens and signed cookies", touchpoint #6, required-if-hit): custom loopback HTTP routes that bypass the Connection auth gate are exactly the card's target — old channels may see 401/403 at the official surface while the private route becomes a security hole. Recipe: custom routes registered directly do not inherit auth/Host-Origin fence/CORS/TLS; handlers must call `ctx.connection.requestRejection(req)` first or switch to a Connection-owned carrier/seam; tokens are for `GET /?token=...` redemption only, never in `/api`, WS URLs, or Authorization headers. Loopback-only binding is **not** an exemption (pre-flight #6 rule). Considered and excluded: **A1-28** (composer contenteditable DOM) — no DOM manipulation in this fixture; **A1-19** (web acceptance/boot manifest) concerns acceptance scripts against `dsh web`, not an in-plugin server; not hit.

### #7 Subprocess / output parsing — HIT

**Evidence**:
- `src/index.ts:57-66`: `spawn('dsh', ['--profile', 'headless', prompt])`; `child.stdout.on('data', ...)` runs `JSON.parse(line)` per chunk hunting `event.type === 'final'`. Two defects: (a) the JSONL assumption is wrong, (b) `JSON.parse` on arbitrary stream chunk boundaries throws on partial lines.
- `scripts/apply-patch.mjs:12-18`: `execFileSync('dsh', ['--profile', 'headless', 'ping'])` then `JSON.parse(line)` per line of stdout with the same `type === 'final'` expectation (the file's own comment flags it: "Deliberately wrong expectation: target headless stdout is final text, not JSONL").

**Card mapping**: **DSH-0.1.2-A1-05** (touchpoint #7, required-if-hit): headless **stdout was already the final assistant text in rc.2** — it was never JSONL; the only alpha.1 change is stderr gaining a `dsh: reasoning:` segment. Recipe: treat stdout as final text, do not `JSON.parse` it by default, judge success by exit code (0/1), and do not treat "stderr has output" as failure. Both call sites violate the contract on both tags, and the corridor makes it worse (reasoning on stderr invites misclassification). **DSH-0.1.2-A1-04** (secondary, #4/#7): wrapper discipline for `dsh --profile` launches — the profile mechanism itself is unchanged in the corridor (`--profile` existed in rc.2), but wrappers hardcoding bins/process trees/fixed profile paths must be re-checked against the target profile layout. Considered and excluded: **A2-04** (Node 24.0–24.11.1 loader workaround removal) — the fixture has no Node-version workaround branches; **A1-06** — no PTC/code-mode identifiers in argv or parsing; **A1-13** — no shell workaround branches.

## Corridor folding — explicit statement (requirement 2)

Exactly one folded pair exists in this corridor and this fixture hits it: **`SessionEvent.ignorable`** — removed by A1-02 (alpha.1), restored by A2-01 (alpha.2). Folded treatment: **net state = present in the target**; the producer at `src/index.ts:15-19` keeps writing `ignorable: true` unchanged across the migration; no delete/re-add churn; A1-02 is cited only as corridor history and would become operative solely under an alpha.1 pin. All other mapped cards (A1-01, A1-03, A1-04, A1-05, A1-08, A2-02) are monotone in the corridor — no other remove/restore folds among them (A2-02 changes error *shape*, not presence of the call surface; A1-01's removal is not reversed anywhere in the corridor).

## No-hit categories (requirement 3)

None: all seven classes hit, so there is no class for which no-hit evidence must be documented. For completeness, the *within-class* exclusions recorded above (A1-13, A1-21-on-#4, A1-26, A1-06, A1-19, A1-28, A1-29, A2-04, and the packaging/privacy surfaces A1-24/A2-03/A1-12/A1-14/A1-23) each name the scanned file and the absent pattern.

**Why even a fully-mapped scan cannot conclude "no problem"** (applies to this report):
1. The card sets are **curated, not a complete API diff** (stated in both card files); an unhit surface can still drift.
2. This was a **static, read-only** scan per the brief: no baseline build/typecheck/test run, no dependency resolution, no real profile mount, no cold boot, no functional message→tool→response flow, no wrapper exit-code/cancellation/teardown verification — the skill's validation layers 1–6 are all unexecuted by design.
3. Line-level search cannot reveal data flow (pre-flight #4 caveat); e.g. the `DSH_HARNESS_SOURCE_ROOT` env contract in `apply-patch.mjs` was assessed from the script text only.
4. The fixture itself is deliberately non-compilable and never executed (its README says so); runtime behavior of every hit is inferred from source plus card contracts, not observation.
5. Host UI/performance changes without cards only mean no migration action is declared — not proof of no API impact.

## Must-verify before/at migration (recommendations)

- Exact-tag compare `dsh-v0.1.1-rc.2...dsh-v0.1.2-alpha.2` for the `SessionView.ts` patch target and the `@deepseek-ai/dsh-session-view/internal` import owner (A1-03).
- Re-validate the patch surface by composition against target-tag source with `DSH_HARNESS_SOURCE_ROOT` pinned to the tag.
- Host-plane service migration for both `apiProxy` call sites (A1-01 field note: domain-service injection, split `llm.providers` into two calls) plus `RemoteResult` error-branch design (A2-02).
- Replace `~/.dsh/profiles/default` with `DSH_HOME`-derived resolution (A1-04).
- Drop or gate the loopback bridge behind the Connection auth gate (A1-08).
- Rewrite both headless parsers to the stdout-is-final-text / exit-code contract, with line-buffered parsing if any structured output is ever introduced (A1-05).
- Add the missing dependency declarations for any retained `@deepseek-ai/*` imports (currently phantom, §0).

*Report generated read-only; fixture untouched.*
