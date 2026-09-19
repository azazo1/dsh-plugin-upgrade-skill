# S3 · Snapshot Read-Surface Migration Assessment — `@demo/dsh-bench-pet` (0.1.1-rc.1 → dsh 0.1.2-alpha.2)

Read-only assessment. No code was changed; the fixture at `environment/fixture/` was not modified. Evidence sources: the fixture files themselves, the local upgrade card sets `references/v0.1.2-alpha.1.md`, `references/v0.1.2-alpha.2.md`, `references/api-migration-0.1.2-alpha.2.md`, and first-hand migration evidence `examples/06-real-world-batch-migration.md` / `examples/08-real-web-client-alpha2-migration.md` (the pet fixture is visibly trimmed from Example 06's "WhalePet" heavy type).

Corridor note: the fixture is rc.1-era; the rc.1 → rc.2 edge (cards `DSH-0.1.1-R2-01..03`) touches only image attachments and does not affect this plugin. All breaking surfaces come from the 0.1.2-alpha.1 edge and carry unchanged into alpha.2.

## Summary of findings

| # | Hit location (fixture) | Old surface | Breaks how on alpha.2 | Card | Fix class |
|---|---|---|---|---|---|
| 1 | `src/client/index.ts:10` | `ClientContext` from `@deepseek-ai/dsh-client-runtime/client` | Package removed since alpha.1 — typecheck/module-not-found | DSH-0.1.2-A1-25 | Required now |
| 2 | `src/client/Pet.tsx:4` | `ConversationSnapshot` from `dsh-client-runtime/client` | Type import gone; flat snapshot fields gone | DSH-0.1.2-A1-25 + DSH-0.1.2-A1-03 + API-10 | Required now (types) / staged (fields) |
| 3 | `src/client/Pet.tsx:16` (`snapshot.partial`) | flat `ConversationSnapshot.partial` | Field no longer flat | DSH-0.1.2-A1-03 | Compat projection first, then views |
| 4 | `src/client/Pet.tsx:21` (`s.runningCalls`) | flat `runningCalls` | same | DSH-0.1.2-A1-03 | Compat projection first, then timeline |
| 5 | `src/client/Pet.tsx:24` (`s.turnEnds`) | flat `turnEnds` | same | DSH-0.1.2-A1-03 | Compat projection first; turn-end detection moves to `chat?.timeline` |
| 6 | `src/client/Pet.tsx:19` (`s.running`) | lifecycle field via `useSession` | **Not present in the `legacy` projection at all** | DSH-0.1.2-A1-03 (field note) | Must stay on the `useSession` seat — no compat projection exists |
| 7 | `src/client/index.ts:47-53` | direct `slots.register` inside `ctx.inject(['slots','conversation'])` | Slot registration form changed to `ctx.slots.inject(name, () => register)` | documented by Example 06; closest card DSH-0.1.2-A1-03 | Required now |
| 8 | `package.json` `client.inject` | declares `"dsh-client-runtime"` | Removed package left in `dsh.client.inject` — assembly row stays pending / boot missing-service error even with no code reference | DSH-0.1.2-A1-25 | Required now |
| 9 | `cordis.patch.yml` (`id: bench-pet`) + client bundle id | 0.1.1 id conventions | alpha.1+ scan: entry/module/registration ids must equal the `package.json` name; mismatches silently drop the client half from the boot graph | DSH-0.1.2-A1-26 | Verify/align |
| 10 | type dependency ownership (`ui-slots`/`ui-chat` declarations) | accidental hoisting from the aggregate runtime package | `skipLibCheck: true` turns `useChat` selectors into implicit `any` | DSH-0.1.2-A2-03 (field note) + API-10 §Type composition | Required now (packaging) |

---

## 1. Removed aggregate package: `@deepseek-ai/dsh-client-runtime`

- **Evidence — current**: `src/client/index.ts:10` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`; `src/client/Pet.tsx:4` — `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`; `package.json` — `"inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`.
- **How it breaks** (DSH-0.1.2-A1-25): the package was deleted in alpha.1. Symptom is either typecheck "missing exports / nonexistent module", or — for the leftover `inject` entry — no explicit error at all: the assembly row stays pending forever / the plugin never enters the boot graph. The card's own field note confirms the `inject` row failure mode reproduces even with zero code references.
- **Post-migration form**:
  ```ts
  // index.ts / Pet.tsx
  import type { Context as ClientContext } from '@deepseek-ai/cordis'        // A1-25 mapping row 1
  import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client' // snapshot type owner (API-10)
  ```
  ```json
  // package.json
  "inject": ["dsh-client-ui-conversation", "dsh-client-locale"]   // only real service providers remain
  ```
- **Verification**: `grep -r "dsh-client-runtime" src/ package.json` returns nothing; cold boot shows this plugin in the boot graph with no pending rows (card verification clause).

## 2. Flat `ConversationSnapshot` read surface → `ChatSnapshot` views / keyed store (the core of this task)

- **Evidence — current**: `Pet.tsx:15-24` reads four flat fields of the old `ConversationSnapshot` through `useSession`:
  - `useSession(s => s.running)` (line 19, lifecycle)
  - `isThinking` → `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')` (lines 15-17)
  - `useSession(s => s.runningCalls.length > 0)` (line 21)
  - `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` (line 24)
- **How it breaks** (DSH-0.1.2-A1-03 + API-10): alpha.1+ no longer exposes per-session conversation-node snapshots with flat fields. The A1-03 field note (dsh-ui-whale v0.3.5 / dsh-ui-progress v0.9.4 / dsh-input-history v0.1.4, real migration) states the old flat `ConversationSnapshot` fields (nodes/partial/runningCalls/turnEnds) remain readable **only** through the `views.get('chat')?.legacy` projection, and that **lifecycle fields such as `running` are not in the projection and must go through the `useSession` seat instead**. On alpha.2, `ChatSnapshot.nodes` is a keyed `ChatNodeStore` (`order` + `get(id)`), not an array; API-10 warns `snapshot.legacy.nodes` is staged compatibility only and must not become the primary data surface for alpha.2-only plugins.
- **Post-migration form** (two-step plan exactly as executed by Example 06's WhalePet, step one "migrate everything to legacy so it runs"):

  ```tsx
  import { useConversation } from '@deepseek-ai/dsh-client-ui-chat/client' // component combines useSession + useConversation
  import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'

  const EMPTY_PROJECTION = { partial: undefined, runningCalls: [], turnEnds: [] }

  export function Pet({ useSession, t }: PetProps) {
    const chat = useConversation() // ChatSnapshot on alpha.2
    // Step 1 (compat projection — runs today on alpha.2):
    const { partial, runningCalls } = chat?.views.get('chat')?.legacy ?? EMPTY_PROJECTION
    // Step 2 (new read path, migrate per field once stable):
    //  - partial   → per-view streaming state (views)
    //  - runningCalls → tool-call view / timeline
    const thinking = (partial?.blocks.some(b => b.kind === 'reasoning') ?? false)
    const toolRunning = runningCalls.length > 0
    const running = useSession(s => s.running) // lifecycle: useSession seat only — NOT in the projection
    // turn timeline: legacy.turnEnds first; final home is the new timeline:
    const lastTurnEnd = chat?.views.get('chat')?.timeline /* turn-end entries */ ?? undefined
    ...
  }
  ```
  For any future transcript node read, the alpha.2-only shape is:
  ```ts
  const node = chat.order.flatMap(id => { const n = chat.nodes.get(id); return n ? [n] : [] })
  ```
  (assistant final node: narrow `type === 'assistant-step'` then read `data.finalNode` — API-10.)
- **Card mapping**: field relocation = **DSH-0.1.2-A1-03** (with its field note supplying the exact per-field projection ledger); keyed store / `useChat` shape = **API-10** in `api-migration-0.1.2-alpha.2.md` (alpha.2-precise); package type reassignment = **DSH-0.1.2-A1-25**.

## 3. Which fields ride the compatibility projection vs. must switch immediately

**Can run first through the compat projection** (`chat.views.get('chat')?.legacy`, staged, two-step plan sanctioned by A1-03 field note + Example 06):
- `partial` (reasoning blocks — the pet's "thinking" pose)
- `runningCalls` (the pet's "working" pose)
- `turnEnds` (the pet's settle frame; final home per Example 06 is the new `timeline`, which is where dsh-ui-progress moved turn-end detection)
- `nodes` (not read by this plugin today; if ever read, `legacy.nodes` may bridge a dual-host window only, never as the primary surface — API-10)

**Must be on the new/immediate path — no projection exists**:
- `running` (`Pet.tsx:19`): explicitly absent from the `legacy` projection (A1-03 field note); it stays on the `useSession` lifecycle seat. The fixture already reads it via `useSession`, so this line survives — but the migration must not "fix" it into the legacy projection.
- The type/import/identity surfaces (findings 1, 2, 7, 8, 9, 10): these are removals and contract changes, not deprecated fields — there is no compatibility projection for a deleted package or a renamed registration contract; they must switch in the same change.

## 4. Slot registration form (`index.ts:47-53`)

- **Evidence — current**:
  ```ts
  ctx.inject(['slots', 'conversation'], (scope: ClientContext) => {
    scope.slots.register({ name: 'conversation.session.header.actions', id: 'pet', order: 10 }, Pet)
  })
  ```
- **Post-migration form** (Example 06 step 5, verified first-hand on the same slot name `conversation.session.header.actions`):
  ```ts
  import type {} from '@deepseek-ai/dsh-client-ui-renderer/client' // owns the ctx.slots types — add as direct devDep

  export function apply(ctx: ClientContext): void {
    ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register(
      { name: 'conversation.session.header.actions', id: 'pet', order: 10 },
      Pet,
    ))
  }
  ```
  This also removes the hand-rolled ordering edge (the fixture's own comment: `'conversation' is an ordering edge ... register() into an undeclared slot throws`).
- **Card mapping**: no dedicated card exists for the `ctx.slots.inject` form; Example 06 documents it as first-hand source and names **DSH-0.1.2-A1-03** as the closest existing card. Flagged here as a knowledge-base gap per the reference rule "when the actual types at the target tag conflict, the target tag wins; flag the gap".

## 5. Registration identity: `cordis.patch.yml` + client bundle id

- **Evidence — current**: `cordis.patch.yml` inserts `- id: bench-pet` / `name: '@demo/dsh-bench-pet'`. The row `name` already uses the bare scoped package name (compliant with DSH-0.1.2-A1-26 rule 2). However A1-26 requires all three ids — client bundle registration id (`__ModuleLoader__.load` banner id), entry name, and the package name `@demo/dsh-bench-pet` — to agree.
- **How it breaks**: mismatches produce `loaded without registering "<id>"` or, worse, the silent shape: panel gone, plugin absent from the boot graph, no error logged (card symptom text).
- **Action**: when building the client bundle, ensure the tsdown banner `PLUGIN_ID` equals `@demo/dsh-bench-pet`; verify `window.__DSH_BOOT__.entries` contains `"id":"@demo/dsh-bench-pet"` and the combo route `/plugins/??@demo/dsh-bench-pet/client.js&rev=...` contains `__ModuleLoader__.load({ id: "@demo/dsh-bench-pet"` (A1-26 verification clause).

## 6. Type-dependency ownership / packaging

- **Evidence — current**: `index.ts:11-15` pulls `ui-conversation` and `locale` augmentations; `Pet.tsx:3` imports `PropsRuntime`/`PropsLocale` from `@deepseek-ai/dsh-client-ui-slots`. After the aggregate runtime disappears, every directly consumed declaration's owner must be a direct dev/peer dependency of the plugin.
- **How it breaks** (A2-03 field note + API-10 §Type composition): ui-chat's `.d.ts` references declarations from `dsh-client-store`, ui primitives, session/commands/conversation, etc. With `skipLibCheck: true` (default in most plugin repos) the missing owners do not error at the import; instead `useChat` selectors and callback params silently become `any`.
- **Action**: after editing, run one pass with `tsc --skipLibCheck false` to enumerate every declaration owner actually hit, add each as a direct dependency (expected additions for this plugin: `dsh-client-ui-chat`, `dsh-client-ui-renderer`, plus the existing `dsh-client-ui-slots` / `dsh-client-locale` / `dsh-client-ui-conversation`), then restore the repo policy. No new implicit `any` is tolerable (Example 08's rule: "any newly introduced implicit `any` is a migration failure").

## Not affected (checked, no action)

- `ctx.locale.register(NS, { zh, en })` and the `LocaleNamespaceMap` merge (`index.ts:20-24, 43`) — no card in the rc.1→alpha.2 corridor touches the locale registration surface.
- Slot name `conversation.session.header.actions`, `PropsRuntime`/`PropsLocale` prop shape, `order: 10` — Example 06's migrated WhalePet keeps exactly these on alpha.1/alpha.2.
- `DSH-0.1.1-R2-01..03` (rc.1→rc.2) — image-attachment/read_image surfaces only; the pet reads none of them.
- `DSH-0.1.2-A1-01/02` (APIProxy/RemoteResult), `A1-30` (`ctx.connection.api`), `A1-27` (SessionBinding event window) — the pet makes no Remote/host calls and reads no transcript via those faces; the snapshot reads in §2 are its only data path.

## Recommended verification ladder (for when the code change is authorized)

1. Static: `grep -rn "dsh-client-runtime"` over `src/` **and** `package.json` → empty (Example 06 Error 2: the `inject` leftover fails boot even with clean sources).
2. `pnpm run clean && build && typecheck && test` — the clean is mandatory (stale tsbuildinfo masked errors in Example 06 Error 1); one `skipLibCheck: false` pass first.
3. Focused behavior: pet frame flips idle→thinking (streaming reasoning block), idle→working (`runningCalls`), settle frame on turn end, and `running` still reflects the lifecycle seat.
4. Live: `dsh --profile web` cold boot → boot graph has no pending rows; `__DSH_BOOT__.entries` contains `@demo/dsh-bench-pet`; pet renders in the header; hard refresh only (client-half change). Fixtures use the real `ChatSnapshot` keyed-store shape (`order` + `get`), not `nodes: []` arrays (Example 08 reproducible failure 3).
