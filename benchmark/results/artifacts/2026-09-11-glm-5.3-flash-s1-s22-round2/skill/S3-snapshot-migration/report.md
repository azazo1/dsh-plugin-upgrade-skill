# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (`@demo/dsh-bench-pet`)

**Mode**: A · inspect (read-only). No file under the fixture was modified; no migration or install was executed.
**Corridor**: DSH `0.1.1-rc.1 → 0.1.2-alpha.2` (edges rc.1→rc.2 [`DSH-0.1.1-R2`], rc.2→alpha.1 [`DSH-0.1.2-A1`], alpha.1→alpha.2 [`DSH-0.1.2-A2`], plus the rc.2→alpha.2 API ledger and the skill's Web Client examples).
**Plugin identity**: npm package `@demo/dsh-bench-pet` v0.1.0, private, ESM; Web Client half only (no Host half beyond the cordis.patch insert row). DSH cohort: 0.1.1-rc.1-era.

Fixture evidence read: `README.md`, `cordis.patch.yml`, `package.json`, `src/client/index.ts`, `src/client/Pet.tsx`, `src/client/locales.ts`.

---

## 1 · Every surface that breaks on 0.1.2-alpha.2, with source location

### 1.1 Manifest: client half declared under legacy top-level `client`, not `dsh.client` — card **DSH-0.1.1-R1-02**

- **Evidence**: `package.json:6-9` — a top-level `"client": { "platform": "web", "inject": [...] }` field. Hosts on the 0810 baseline and later read **only** `dsh.client`; a leftover/legacy field is silently ignored, so the client half never enters the browser plugin roster or bundle assembly (no Node-half error — invisible failure).
- **Post-migration form**: nest the same value shape under `"dsh": { "client": { "platform": "web", "inject": [...] } }` and verify the **packed** manifest carries `dsh.client`, not just the source `package.json`.

### 1.2 `dsh-client-runtime` imports: package deleted — card **DSH-0.1.2-A1-25** (+ ledger **API-10**)

- **Evidence**:
  - `src/client/index.ts:6` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
  - `src/client/Pet.tsx:8` — `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`
  - `package.json:8` — `"dsh-client-runtime"` listed in `client.inject`.
- **How it breaks**: typecheck reports a nonexistent module; keeping the deleted package in `client.inject` leaves the assembly row pending / the plugin out of the boot graph, often without an explicit error.
- **Post-migration form** (verified mapping, A1-25 table + API-10):
  - `ClientContext` → `import type { Context as ClientContext } from '@deepseek-ai/cordis'`
  - `ConversationNode` / `IConversation` → `@deepseek-ai/dsh-client-ui-conversation/client`
  - `ISessions` / `SessionBinding` → `@deepseek-ai/dsh-api-session-controller/client`
  - Remove `dsh-client-runtime` from `dsh.client.inject` and from devDependencies; keep only packages that actually provide injected services (`dsh-client-locale`; `dsh-client-ui-conversation` only if its service is genuinely still needed as an ordering edge — see 1.4).

### 1.3 Snapshot read surface: flat `ConversationSnapshot` fields removed (session-view split) — card **DSH-0.1.2-A1-03**, final form per ledger **API-10**

- **Evidence** (`src/client/Pet.tsx`, all reads go through the `useSession` seat against the old flat snapshot):
  - `Pet.tsx:19` — `useSession(s => s.running)` (lifecycle field)
  - `Pet.tsx:13-15` — `isThinking(snapshot)` reads `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')`
  - `Pet.tsx:21` — `useSession(s => s.runningCalls.length > 0)`
  - `Pet.tsx:23` — `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` (turn timeline)
  - `Pet.tsx:8,13` — the `ConversationSnapshot` type itself from the removed runtime.
- **How it breaks**: 0.1.2 no longer exposes per-session flat conversation snapshots (the timeline becomes an internal projection of each view package, A1-03). Selectors silently become implicit `any` under `skipLibCheck: true` (API-10 §Type composition), and runtime reads return `undefined` — the pet would freeze on `idle` with no error.
- **Post-migration form** (two steps, per A1-03 field note from dsh-ui-whale v0.3.5 / dsh-ui-progress v0.9.4 / dsh-input-history v0.1.4, and Example 06 "WhalePet"):

  Step 1 — compat-projection read that runs on alpha.1/alpha.2:
  ```ts
  const chat = conversationSnapshot.views.get('chat')
  const { partial, runningCalls } = chat?.legacy ?? EMPTY_PROJECTION
  // turn timeline now lives at chat?.timeline
  ```
  `isThinking` becomes `chat?.legacy.partial?.blocks.some(b => b.kind === 'reasoning') ?? false`; tool-in-flight becomes `chat?.legacy.runningCalls.length > 0`; the settle frame reads `chat?.timeline` (turn-end detection moved to the new timeline — dsh-ui-progress precedent).

  Step 2 (alpha.2-only best practice, API-10): transcript/node reads must use `useChat` over the keyed store — `snapshot.order.flatMap(id => { const n = snapshot.nodes.get(id); return n ? [n] : [] })`; assistant final nodes narrow to `type === 'assistant-step'` then `data.finalNode`. This Pet reads no nodes, so it does not need `useChat` today; `snapshot.legacy.nodes` is staged compatibility only and "should not become the new primary data surface for alpha.2-only plugins" (API-10). Any future transcript read must go through `useChat`.

### 1.4 Slot registration: rc.1 nested `ctx.inject` + direct `slots.register` — card **DSH-0.1.2-A1-03** family (Example 06 recipe; `ctx.slots` types from the renderer package)

- **Evidence**: `src/client/index.ts:29` — `export const inject = ['slots', 'conversation', 'locale']`; `src/client/index.ts:38-43` — `ctx.inject(['slots', 'conversation'], (scope) => { scope.slots.register({ name: 'conversation.session.header.actions', id: 'pet', order: 10 }, Pet) })`. The comment at `index.ts:24-28` documents the `conversation` ordering edge: "register() into an undeclared slot throws".
- **Post-migration form** (Example 06, whale pet — same slot name survives):
  ```ts
  import type {} from '@deepseek-ai/dsh-client-ui-renderer/client' // ctx.slots types; add to devDependencies

  export const inject = ['slots', 'locale']
  export function apply(ctx: ClientContext): void {
    ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register(
      { name: 'conversation.session.header.actions', id: 'pet', order: 10 },
      Pet,
    ))
  }
  ```
  `ctx.slots.inject(name, register)` replaces the manual `'conversation'` inject-as-ordering-edge; `'locale'` and its `ctx.locale.register(NS, { zh, en })` (`index.ts:36`) stay as-is; the `LocaleNamespaceMap` augmentation (`index.ts:14-19`) stays, with `@deepseek-ai/dsh-client-ui-slots` declared as the plugin's own direct dev dependency.

### 1.5 Composition row id vs package name: registration id must equal `package.json` name — card **DSH-0.1.2-A1-26**

- **Evidence**: `cordis.patch.yml:1-3` — insert row `id: bench-pet`, `name: '@demo/dsh-bench-pet'`; `package.json:2` — `"name": "@demo/dsh-bench-pet"`. In 0.1.2 the boot manifest keys entries/modules/plugin registrations by package name ("Entry name == package name"); the client bundle's `__ModuleLoader__.load` id (tsdown `PLUGIN_ID` banner), the assembly row, and `package.json#name` must all agree. A mismatch produces the startup assertion `loaded without registering "<id>"` — or the silent form: the panel/pet disappears, the boot graph lacks the plugin, no plugin-related error is logged.
- **Post-migration form**: make the bundle registration id exactly `@demo/dsh-bench-pet`; keep the row `name` as the scoped bare package name (it already is); verify with `dsh --profile <p> --dump-config` (no pending) and by checking `window.__DSH_BOOT__.entries` for `"id":"@demo/dsh-bench-pet"` and the combo artifact `/plugins/??@demo/dsh-bench-pet/client.js&rev=...` containing `__ModuleLoader__.load({ id: "@demo/dsh-bench-pet"`.

### 1.6 Dependency ownership for consumed declarations — card **DSH-0.1.2-A2-03** (peer trimming/addition direction)

- **Evidence**: the plugin's types come from `@deepseek-ai/dsh-client-ui-slots` (`Pet.tsx:7` — `PropsRuntime`, `PropsLocale`; `index.ts:14`), `@deepseek-ai/dsh-client-locale` (`index.ts:8`), `@deepseek-ai/dsh-client-ui-conversation` (`index.ts:10`), and post-migration `@deepseek-ai/dsh-client-ui-chat/client` / `@deepseek-ai/dsh-client-ui-renderer/client` / `@deepseek-ai/dsh-api-session-controller/client`. Published packages' `devDependencies` are not transitively installed; ui-chat declarations reference `dsh-client-store`, ui primitives, session/commands/conversation types.
- **How it breaks**: with `skipLibCheck: true` a missing declaration owner turns selectors/callbacks into implicit `any` — "any newly introduced implicit `any` is a migration failure" (API-10 §3).
- **Post-migration form**: declare each directly imported/consumed declaration owner as a direct dev/peer dependency; run one diagnostic `tsc --skipLibCheck false` pass to enumerate the missing chain, then restore the repo's policy.

### Non-hits (corridor checked, no evidence of hit — with evidence)

- **DSH-0.1.1-R2-01/02/03** (image refs, `read_image` text, DeepSeek Files API): no image/attachment/LLM-adapter code anywhere in the fixture.
- **DSH-0.1.1-R1-04/05** (strict injection / weak `ctx.get`): `index.ts:29` already declares every consumed service in `inject`; no undeclared property access.
- **DSH-0.1.1-R1-06/07/08/09** (session event `type`, `ctx.sessions` aggregation, `tasks.peek`, 0812 service renames): the fixture has no Host half, no event subscription, no `tasks`/`httpServer`/`sessions` usage — the only service reads are `slots`, `conversation` (ordering edge, itself replaced by 1.4), `locale`.
- **DSH-0.1.2-A1-01 / A1-30** (APIProxy / `ctx.connection.api`): no `ctx.remote`, no `connection`, no history/transcript RPC calls; the pet is fed by the slots runtime's snapshot props only.
- **DSH-0.1.2-A1-27** (SessionBinding durable event window): the pet reads only the *live* snapshot via the slot seat, never `sessions.scope(id)`/`session.getSnapshot().nodes`; hit only if future features read historical content.
- **DSH-0.1.2-A1-20/21/22/28/29/31/32**, **A2-01/02/05/06/08/10**: no user-question providers, no preset roots, no `isTokenDelta`, no composer DOM access, no `MarkdownText`, no subagent descriptors, no workspace navigation, no persisted events, no Remote calls, no tool-package peers, no `settingsNamespace`.
- **Corridor note**: Example 06's Follow-up records that a six-plugin fleet with this exact shape (including the pixel pet) rode alpha.1 → alpha.2 → … → rc.1 with **zero further source changes**, so the A2 edge adds no new break for this fixture.

---

## 2 · Correct post-migration API shapes (summary)

| Old (0.1.1-rc.1) | New (0.1.2-alpha.2) | Card |
|---|---|---|
| `package.json` top-level `"client": {...}` | `"dsh": { "client": { "platform": "web", "inject": [...] } }` | DSH-0.1.1-R1-02 |
| `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'` | `import type { Context as ClientContext } from '@deepseek-ai/cordis'` | DSH-0.1.2-A1-25 |
| `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'` | `ChatSnapshot` from `@deepseek-ai/dsh-client-ui-chat/client` (+ type-only augmentation imports per owning package) | A1-25 + API-10 |
| `client.inject: ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]` | remove the deleted runtime; keep only real injected services (`dsh-client-locale`; `dsh-client-ui-conversation` only if still an actual service dependency) | A1-25 |
| `useSession(s => s.running)` | unchanged seat: lifecycle field `running` stays on the `useSession` seat (not in the projection); component props may combine `useSession` + `useConversation` | A1-03 (field note) |
| `snapshot.partial?.blocks` | `conversationSnapshot.views.get('chat')?.legacy.partial?.blocks` (compat projection; migrate to views/timeline later) | A1-03 |
| `s.runningCalls.length` | `chat?.legacy.runningCalls.length` (compat projection) | A1-03 |
| `s.turnEnds[s.turnEnds.length - 1]?.reason` | `chat?.timeline` (turn timeline's new location; legacy projection also carries `turnEnds` per A1-03 field note) | A1-03 |
| transcript nodes (future): `session => session.nodes` array | `useChat` + `chat.order` iteration with `chat.nodes.get(id)` per id (keyed `ChatNodeStore`; test fixtures must provide `get`/`values`, not arrays) | API-10 |
| `ctx.inject(['slots','conversation'], scope => scope.slots.register(...))` | `ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register(...))`; `ctx.slots` types from `@deepseek-ai/dsh-client-ui-renderer/client` | A1-03 family (Example 06) |
| row `id: bench-pet` + any short-name bundle id | bundle registration id == assembly row name == `@demo/dsh-bench-pet` (tsdown `PLUGIN_ID` banner) | DSH-0.1.2-A1-26 |
| implicit type hoisting from the aggregated runtime | direct dev/peer dependency per consumed declaration owner; one `skipLibCheck: false` diagnostic pass | DSH-0.1.2-A2-03 + API-10 |

`locales.ts` (PetKey dictionaries) and `ctx.locale.register(NS, { zh, en })` need **no change**; `PropsLocale<'pet'>` and the `LocaleNamespaceMap` augmentation survive on `dsh-client-ui-slots`/`dsh-client-locale`, which must become direct dev dependencies.

---

## 3 · Card mapping (full numbers)

| Break | Card (full number) |
|---|---|
| legacy `client` manifest field | `DSH-0.1.1-R1-02` |
| `dsh-client-runtime` removal / symbol re-homing | `DSH-0.1.2-A1-25` |
| flat snapshot fields / session-view split | `DSH-0.1.2-A1-03` (field note: dsh-ui-whale v0.3.5 et al.) |
| registration id == package name | `DSH-0.1.2-A1-26` |
| declaration dependency ownership | `DSH-0.1.2-A2-03` |
| final snapshot read form (keyed chat snapshots) | ledger `API-10` in `references/api-migration-0.1.2-alpha.2.md` |
| Web acceptance procedure for validation | `DSH-0.1.2-A1-19` |

rc.2-edge cards `DSH-0.1.1-R2-01/02/03` and the remaining A1/A2 cards were evaluated and are non-hits (§1 evidence).

---

## 4 · Compat projection now vs. immediate new read path

**Can run first through the compatibility projection** (`conversationSnapshot.views.get('chat')?.legacy` — staged compatibility with an explicit dual-host requirement; readable on alpha.1 and alpha.2, so the plugin can run before the field-by-field views/timeline migration):

- `partial` (reasoning detection, `Pet.tsx:14`) — present in the projection.
- `runningCalls` (tool-in-flight, `Pet.tsx:21`) — present in the projection.
- `turnEnds` (settle frame, `Pet.tsx:23`) — present in the projection per the A1-03 field note ("nodes/partial/runningCalls/turnEnds are all still readable through the views.get('chat')?.legacy projection"), but the true new home is `chat?.timeline` — target that in step 2.
- `nodes` (not read today) — projection-readable, but any new code must use `useChat` + `order` + `nodes.get(id)` (API-10); `legacy.nodes` must not become the primary data surface.

**Must switch to the new read path / new surface immediately** (no compat projection exists):

- `running` (`Pet.tsx:19`) — a lifecycle field, explicitly "not in the projection"; it stays on the `useSession` seat (which survives as the lifecycle seat). No change of seat, but it can never be sourced from `views...`.
- `dsh-client-runtime` imports (`index.ts:6`, `Pet.tsx:8`) and its `client.inject` row (`package.json:8`) — the package is deleted; keeping it leaves the assembly row pending / the plugin out of the boot graph. No shim exists.
- `ClientContext` → `Context` from `@deepseek-ai/cordis` — required the moment the runtime import goes.
- Manifest `client` → `dsh.client` (R1-02) — ignored silently otherwise; the client half never loads, so nothing else in this report matters until this is fixed.
- Slot registration via `ctx.slots.inject(...)` and the id alignment of `DSH-0.1.2-A1-26` — without them the pet either throws at registration or silently vanishes from the graph.

---

## 5 · Recommended migration order and validation plan (not executed — read-only assessment)

1. Fix `package.json` (R1-02 shape; remove `dsh-client-runtime` from inject/deps; add direct dev deps: `@deepseek-ai/cordis`, `dsh-client-ui-slots`, `dsh-client-locale`, `dsh-client-ui-renderer`, `dsh-client-ui-chat`, `dsh-api-session-controller`, `dsh-client-ui-conversation` as consumed).
2. Swap type imports (A1-25); rewrite slot registration (1.4); move `partial`/`runningCalls`/`turnEnds` onto `views.get('chat')?.legacy` and keep `running` on `useSession` (A1-03).
3. Align the tsdown banner `PLUGIN_ID` and the insert row to `@demo/dsh-bench-pet` (A1-26).
4. `pnpm run clean` (stale tsbuildinfo false positives), then one `tsc --skipLibCheck false` diagnostic pass (A2-03/API-10), then build/typecheck/tests.
5. Residue check: `grep -r "dsh-client-runtime" src/ package.json` (and packed `lib/`) — expected: no output.
6. Runtime acceptance (A1-19): isolated profile, `dsh web --no-open` at the exact target tag, token→Cookie, read `window.__DSH_BOOT__.entries` by package name, request the host-advertised bundle URL, prove `__ModuleLoader__.load({ id: "@demo/dsh-bench-pet" })` and a DOM marker (`.pet` mounted in `conversation.session.header.actions`), then exercise one streaming turn and one tool call and confirm the pet frames `thinking`/`working`/settle render.
7. Distinguish completion states: "typecheck passed" ≠ "Loader mount passed" ≠ "real behavior passed"; record all three.

**Pending / residual risk**: the legacy projection is staged compatibility; alpha.2-only best practice (API-10) is the views/timeline + keyed chat store — schedule step 2 of the two-step plan. Exact prop/selector shapes must be confirmed against the target tag's packed declarations (`packages/client/ui-chat/src/client/contract/snapshot.ts`, `slots.ts`, `packages/client/ui-slots/src/index.ts`); where a local observation conflicts with the target tag, the tag wins and the gap is flagged rather than guessed.

**Rollback baseline** (recorded, nothing changed): fixture files as read above — `package.json` v0.1.0 with top-level `client` field; `cordis.patch.yml` row `id: bench-pet`; `src/client/index.ts`, `src/client/Pet.tsx`, `src/client/locales.ts` unmodified; fixture directory untouched (read-only discipline held).
