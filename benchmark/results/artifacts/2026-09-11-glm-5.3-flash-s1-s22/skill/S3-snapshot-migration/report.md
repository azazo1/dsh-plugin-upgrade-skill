# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (`@demo/dsh-bench-pet` 0.1.1-rc.1 → dsh 0.1.2-alpha.2)

**Mode**: plugin-upgrade skill, Mode A (read-only inspect). No fixture file was modified; no migration or install was executed.
**Corridor read in full** (per `references/README.md` from→to edges, not filename order):
`dsh-v0.1.1-rc.1` → `dsh-v0.1.1-rc.2` (DSH-0.1.1-R2-01…03) → `dsh-v0.1.2-alpha.1` (DSH-0.1.2-A1-01…32) → `dsh-v0.1.2-alpha.2` (DSH-0.1.2-A2-01…10), plus the exact interface ledger `references/api-migration-0.1.2-alpha.2.md` (API-01…10).

**Fixture identity**: `package.json` name `@demo/dsh-bench-pet`, version 0.1.0, private, web client half with `client.inject: ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`. Source: `src/client/index.ts` (registration), `src/client/Pet.tsx` (snapshot consumer), `src/client/locales.ts` (dictionary), `cordis.patch.yml` (assembly row). The pet's animation "follows the live conversation snapshot" — this plugin is exactly on the snapshot read surface.

Net corridor state: the rc.2 edge (image-attachment cards R2-01…03) does not intersect this plugin — no hits. All breaking surfaces come from the alpha.1 edge and carry into alpha.2 unchanged.

---

## 1. Breaking surfaces, tied to source locations

### B1. `dsh-client-runtime` import — package removed
- **Location**: `src/client/index.ts` line `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`; `src/client/Pet.tsx` line `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`; `package.json` `client.inject[0] = "dsh-client-runtime"`.
- **Break**: `@deepseek-ai/dsh-client-runtime` was deleted in alpha.1 (card **DSH-0.1.2-A1-25**). Typecheck/build report missing module/exports; at runtime the plugin never enters the boot graph or its assembly row stays pending, often with no explicit error. The field note on A1-25 (dsh-input-history) confirms: with the runtime package left in `inject`, the row did not enter the graph; removing it restored it.

### B2. Flat `ConversationSnapshot` read surface — snapshot becomes a keyed store, seat becomes `useChat`
- **Location**: `src/client/Pet.tsx`:
  - `isThinking(snapshot: ConversationSnapshot)` reading `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')`
  - `useSession(s => s.running)`
  - `useSession(s => s.runningCalls.length > 0)`
  - `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)`
- **Break**: on alpha.2, `ChatSnapshot.nodes` is a keyed store (`order` + `nodes.get(id)`), not `ConversationNode[]`; the transcript seat is `useChat(chat => ...)`, not `useSession(session => session?.nodes)` (ledger **API-10** in `api-migration-0.1.2-alpha.2.md`, cross-cited by DSH-0.1.2-A1-03 and the DSH-0.1.2-A2-03 field note). `ConversationSnapshot` no longer exists as a public type. Per the A1-03 field note (dsh-ui-whale / dsh-ui-progress / dsh-input-history migration): the old flat fields `nodes/partial/runningCalls/turnEnds` are only still readable through the `views.get('chat')?.legacy` projection, and **lifecycle fields such as `running` are not in the projection at all** — they must go through the `useSession` seat. So `isThinking`, `toolRunning`, and `lastTurnEnd` all break; `running` survives only if the plugin keeps reading it from the correct seat.
- Related context card: **DSH-0.1.2-A1-27** — 0.1.2 no longer exposes per-session conversation-node snapshots (`session.getSnapshot().nodes` is undefined/empty); the timeline becomes an internal projection of each view package. This fixture does not call `sessions.scope(id)`/`getSnapshot()` directly (it consumes the slot-supplied seat), so A1-27 applies as the mechanism behind B2 rather than as a separate call-site fix; it would apply directly if the plugin ever reads historical content itself.

### B3. `ClientContext` type source — Context re-homed to Cordis
- **Location**: `src/client/index.ts` — `export function apply(ctx: ClientContext)` and the `inject` scope cast use the runtime package's `ClientContext` alias.
- **Break**: part of **DSH-0.1.2-A1-25** / **API-10** "Exact mapping": `ClientContext` → `Context` from `@deepseek-ai/cordis`, with the merged client facets arriving only via type-only augmentation imports from the owning packages (`type {} from '@deepseek-ai/dsh-client-ui-conversation/client'` etc., which the file already does for slots/locale). Changing the type alone is insufficient — without direct type dependencies, `skipLibCheck: true` silently turns selectors/callback parameters into implicit `any` (API-10 "Type composition").

### B4. Manifest `dsh.client.inject` contains a phantom package
- **Location**: `package.json` `client.inject`.
- **Break**: `dsh-client-runtime` must be removed from the inject list (A1-25 recipe: after the dismantling it is a runtime phantom dependency; keeping it leaves the assembly row pending / out of the boot graph). `dsh-client-ui-conversation` and `dsh-client-locale` provide real services (`conversation` ordering edge, `locale`) and stay. Additionally, the packages whose declarations the source now consumes directly (`@deepseek-ai/dsh-client-ui-chat` for `ChatSnapshot`/`useChat`, plus `@deepseek-ai/cordis`) must become direct dev/peer type dependencies of the plugin — packaging surface of **DSH-0.1.2-A2-03** and API-10 rule 2.

### B5. Client-module registration id must equal the package.json name
- **Location**: `cordis.patch.yml` insert row (`id: bench-pet`, `name: '@demo/dsh-bench-pet'`) and the client bundle build (tsdown `PLUGIN_ID` banner — not present in the trimmed fixture, verify in the real build).
- **Break**: **DSH-0.1.2-A1-26** — the boot manifest keys entries/modules/plugin registrations by package name; the `__ModuleLoader__.load` id and the assembly row `name` must both equal `@demo/dsh-bench-pet`. The assembly row already uses the bare scoped name (correct form). The slot registration id `'pet'` in `ctx.slots.register({ name: 'conversation.session.header.actions', id: 'pet', order: 10 }, Pet)` is a slot-entry id, not the module registration id, and is unaffected. Residual risk: the bundle banner id must be checked in the real build; any mismatch gives `loaded without registering "<id>"` or a silent boot-graph absence.

### Non-hits (checked, with evidence)
- **DSH-0.1.2-A2-02** (`RemoteError`): the plugin makes no `ctx.remote` calls. Not hit.
- **DSH-0.1.2-A1-28/29/30/31/32** (composer DOM, `MarkdownText` labels, `ctx.connection.api`, subagent descriptor version, `IWorkspaces` navigation): no composer manipulation, no markdown rendering, no connection/api reads, no subagent descriptors, no workspace calls anywhere in the three source files. Not hit.
- **DSH-0.1.1-R2-01…03**: image-attachment surface; the pet renders no attachments. Not hit.
- **DSH-0.1.2-A2-01/04/05/06/08/10**: ignorable-event retention (plugin persists no session events), Node 24 loader fix (environmental, conditional), plugin-inventory `agentPresets` (not consumed), `$host.*` facts (not consumed), `sessionProjections` inject (tool packages only, not this client plugin), `settingsNamespace` (no settings usage). Not hit.
- **DSH-0.1.2-A1-20/21/22/23/24**: host-plane / provider / composition surfaces absent from this fixture. Not hit.

---

## 2. Post-migration form (new API shapes)

### B1/B3 — imports and context (`src/client/index.ts`)
```ts
// 旧：import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
import type { Context } from '@deepseek-ai/cordis'
// keep the type-only augmentation imports that are actually used:
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client' // SlotMap merge (header.actions)
import type {} from '@deepseek-ai/dsh-client-locale/client'          // ctx.locale merge
export function apply(ctx: Context): void { /* unchanged body */ }
```

### B2 — `src/client/Pet.tsx`, alpha.2-only minimal read shape (API-10)
```ts
import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'
import type {} from '@deepseek-ai/dsh-client-ui-chat/client' // seat/augmentation activation
import type {} from '@deepseek-ai/dsh-api-session-controller/client'

function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap((id) => {
    const node = snapshot.nodes.get(id)   // keyed ChatNodeStore, not ConversationNode[]
    return node ? [node] : []
  })
}
// transcript/tool reads: ctx.useChat((chat) => ...) replaces the flat useSession selectors.
// assistant-step final node: narrow by discriminant type === 'assistant-step', read data.finalNode.
```
Concretely for the pet:
- `runningCalls`/`partial`/`turnEnds` derive from the ordered nodes obtained via `order` + `nodes.get(id)` (or the staged legacy projection — see §4).
- `running` stays on the lifecycle seat: per the A1-03 field note, lifecycle fields are **not** in the projection; read them through the `useSession` seat that remains available, i.e. keep `useSession(s => s.running)` while moving the content selectors to `useChat`.
- `PropsRuntime<'conversation.session.header.actions'>` from `@deepseek-ai/dsh-client-ui-slots` continues to carry the seat props; the slot name itself is unchanged in this corridor (no card moves `conversation.session.header.actions` between rc.1 and alpha.2 — verify on a real alpha.2 page if any doubt, per the A1-28 verification discipline).
- `locales.ts` and the `LocaleNamespaceMap` merge are unchanged (locale registration contract untouched in this corridor).

### B4 — `package.json`
```json
"client": { "platform": "web",
  "inject": ["dsh-client-ui-conversation", "dsh-client-locale"] }
```
plus direct dev/peer type dependencies on `@deepseek-ai/dsh-client-ui-chat`, `@deepseek-ai/dsh-api-session-controller`, `@deepseek-ai/dsh-client-ui-slots`, `@deepseek-ai/dsh-client-ui-conversation`, `@deepseek-ai/dsh-client-locale`, `@deepseek-ai/cordis` — only the ones actually imported (API-10 rule 2; A2-03 field note). During migration run one `tsc` with `skipLibCheck: false` to surface every missing declaration owner, then restore the repo policy.

---

## 3. Card mapping (full IDs)

| Surface | Card / ledger entry |
|---|---|
| `dsh-client-runtime` removal (imports, `ClientContext`, manifest inject, type re-homing) | **DSH-0.1.2-A1-25** (exact mapping table) |
| Flat snapshot → keyed `ChatSnapshot`, `useSession`→`useChat`, dependency-ownership rules | **API-10** in `references/api-migration-0.1.2-alpha.2.md` (cross-cited by DSH-0.1.2-A1-03 field note and DSH-0.1.2-A2-03 field note; API-10 is a ledger entry, not a numbered card) |
| Session view internals split; `views.get('chat')?.legacy` projection; `running` seat exception | **DSH-0.1.2-A1-03** (field note, dsh-ui-whale v0.3.5 / dsh-ui-progress v0.9.4 / dsh-input-history v0.1.4) |
| Per-session node snapshots no longer exposed (mechanism behind B2) | **DSH-0.1.2-A1-27** |
| Registration id == package.json name (bundle banner + assembly row) | **DSH-0.1.2-A1-26** |
| Type/peer dependency ownership, `skipLibCheck: false` diagnostic pass | **DSH-0.1.2-A2-03** (+ field note 2026-08-31) |

---

## 4. Compatibility projection vs. immediate new read path

**Can run first through the compatibility projection (staged, `views.get('chat')?.legacy` / `snapshot.legacy.nodes`)** — the conversation-content fields whose semantics still exist in the legacy view:
- `partial` (reasoning-block detection in `isThinking`),
- `runningCalls` (tool-in-flight pose),
- `turnEnds` (settle-frame reason), and any ordered `nodes` iteration.

The A1-03 field note documents the proven two-step pattern ("migrate everything to legacy first, then field-by-field to views/timeline once stable") with a dual-host requirement. Caveat from API-10: `snapshot.legacy.nodes` is staged compatibility only and must not become the primary data surface for an alpha.2-only plugin.

**Must switch to the new read path immediately (no projection covers them):**
- `running` — a lifecycle field, explicitly **not** in the legacy projection (A1-03 field note); it must keep flowing through the `useSession` lifecycle seat.
- `ClientContext` type source and the `@deepseek-ai/dsh-client-runtime` entries in `client.inject` — the package is deleted; there is no legacy surface, and keeping it in the manifest leaves the assembly row pending / the plugin out of the boot graph (A1-25).
- The bundle registration id alignment of A1-26 — a boot-graph contract, not a data read; nothing can project it.

---

## 5. Validation plan (read-only assessment; to execute at migration time)
1. Static: typecheck/build with one `skipLibCheck: false` pass; zero leftover `dsh-client-runtime` references; no new implicit `any` in `Pet.tsx` selectors.
2. Enablement: `dsh --profile <p> --dump-config` — insert row name `@demo/dsh-bench-pet`, no pending rows; `window.__DSH_BOOT__.entries` contains the package name; combo resource `/plugins/??@demo/dsh-bench-pet/client.js&rev=...` contains `__ModuleLoader__.load({ id: "@demo/dsh-bench-pet"` (A1-26 verification).
3. Behavior: one streaming turn — pet frames cycle idle→thinking→working→settle; reasoning pose driven by the new keyed-node derivation (or legacy projection during staging); `running` seat verified on the lifecycle selector.
4. Skipped layers in this assessment: baseline run, runtime cold boot, and browser verification were not executed — Mode A is read-only and the fixture is declared non-runnable task material. Residual risk: the exact post-migration shapes of `partial`/`runningCalls`/`turnEnds` inside the view/timeline projection and the slot name should be confirmed against `dsh-v0.1.2-alpha.2` package declarations at implementation time, per the cards' "defer to the target tag's actual exports" rule.
