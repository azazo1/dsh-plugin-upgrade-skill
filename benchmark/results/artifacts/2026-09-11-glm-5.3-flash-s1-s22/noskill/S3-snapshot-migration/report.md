# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (@demo/dsh-bench-pet), 0.1.1-rc.1 → dsh 0.1.2-alpha.2

Read-only assessment. Evidence: the fixture pack (paths below relative to fixture/); card sources: skills/plugin-upgrade/references/v0.1.2-alpha.1.md (idPrefix DSH-0.1.2-A1, 28 cards), v0.1.2-alpha.2.md (idPrefix DSH-0.1.2-A2, 8 cards), v0.1.1-rc.2.md (DSH-0.1.1-R2), api-migration-0.1.2-alpha.2.md (API-10), rollup-0.1.2.md. The rc.1→alpha.2 corridor was folded to its alpha.2 net state before assessment (e.g. SessionEvent.ignorable removed by DSH-0.1.2-A1-02, restored by DSH-0.1.2-A2-01 — this plugin produces no persisted SessionEvents, so neither applies). No fixture file was modified; no migration or installation was executed.

## 1. Break surfaces on 0.1.2-alpha.2, tied to source locations

**B1 · Removed package `@deepseek-ai/dsh-client-runtime` (type import + client inject).** src/client/index.ts:6 `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`; src/client/Pet.tsx:8 `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`; package.json:8 lists it in `client.inject`. Card DSH-0.1.2-A1-25: the package was deleted in alpha.1, symbols split by domain — build/typecheck missing-module, and at runtime the assembly row stays pending / out of the boot graph ("runtime phantom dependency").

**B2 · Flat `ConversationSnapshot` content fields removed.** Pet.tsx:13-14 `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')`; Pet.tsx:21 `useSession(s => s.runningCalls.length > 0)`; Pet.tsx:23 `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)`. Cards DSH-0.1.2-A1-03 ("Session view internals split up extensively") + DSH-0.1.2-A1-27: per-session conversation-node snapshots are no longer exposed; the A1-03 field note names exactly these flat fields (nodes/partial/runningCalls/turnEnds). Selectors degrade to `any` or type-error (API-10: "selectors become any"), so the pet's thinking/working/settle poses silently stop updating.

**B3 · `useSession` chat-read seat replaced by `useChat` for content.** Pet.tsx:18 `export function Pet({ useSession, t }: PetProps)` with `PetProps = PropsRuntime<'conversation.session.header.actions'> & PropsLocale<'pet'>` (Pet.tsx:10); all four selectors (Pet.tsx:19-23) go through it. API-10 ledger: `useSession(session => session?.nodes)` → `useChat(chat => ...)`; `ConversationSnapshot.nodes[]` → keyed `ChatSnapshot` (`order` + `nodes.get(id)`). Split per the A1-03 field note: lifecycle field `running` is NOT in the views/legacy projection and "must go through the `useSession` seat instead" — the seat survives for lifecycle only (Pet.tsx:19 stays; Pet.tsx:20-23 must move).

**B4 · Registration-id triple must equal package.json name.** cordis.patch.yml:2-3 insert row `{ id: bench-pet, name: '@demo/dsh-bench-pet' }`; third id = client bundle banner `__ModuleLoader__.load({ id })` (tsdown PLUGIN_ID, not visible in the trimmed fixture). Card DSH-0.1.2-A1-26: 0.1.2 boot manifest keys entries/modules/registrations by package name ("Entry name == package name"); symptoms: `loaded without registering "<id>"` or silent boot-graph absence. The row `name` already matches package.json:2; the short id `bench-pet` and a non-matching banner id are hit.

**B5 · Type ownership of surviving augmentations (packaging).** index.ts:8 (`@deepseek-ai/dsh-client-locale/client`), index.ts:10 (`@deepseek-ai/dsh-client-ui-conversation/client` SlotMap merge), Pet.tsx:7 (`PropsLocale, PropsRuntime` from `@deepseek-ai/dsh-client-ui-slots`). Cards DSH-0.1.2-A1-25 + DSH-0.1.2-A2-03 + API-10 type-ownership rule: each touched declaration's owner must become the plugin's own direct dev/peer dependency; with `skipLibCheck: true` a missing owner silently makes slot props implicit `any`.

**Not hit (negative findings):** no `ctx.connection.api.*` → DSH-0.1.2-A1-30 no; no APIProxy → A1-01 no; no Remote error handling → A2-02 no; no persisted SessionEvents → A1-02/A2-01 net no; no workspace navigation/list → A1-32 no; no MarkdownText → A1-29 no; no settings namespace → A2-10 no; no composer DOM → A1-28 no; no Code-Mode vocabulary → A1-06 no; locale registration (index.ts:36, LocaleNamespaceMap merge index.ts:14-19, NS='pet') follows the documented pattern; locales.ts is version-independent. No DSH-0.1.1-R2-xx card is hit (that edge only touched image attachment / read_image / DeepSeek adapter surfaces).

## 2. Correct post-migration form

**M1 (B1, DSH-0.1.2-A1-25).** index.ts:6 → `import type { Context as ClientContext } from '@deepseek-ai/cordis'`. Pet.tsx:8 → chat content owner: `import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'` (ChatSnapshot/ChatNodeStore, packages/client/ui-chat/src/client/contract/snapshot.ts). package.json:8 → drop `dsh-client-runtime` entirely; keep only real service providers: `["dsh-client-ui-conversation", "dsh-client-locale"]`; add `@deepseek-ai/dsh-client-ui-chat`, `@deepseek-ai/dsh-client-ui-slots`, `@deepseek-ai/cordis` as direct type/dev deps (API-10 ownership step; run one `tsc --skipLibCheck false` pass to surface the chain).

**M2 (B2/B3, DSH-0.1.2-A1-03 + A1-27, API-10).** Content reads become `useChat` over the keyed snapshot: iterate `ChatSnapshot.order`, `snapshot.nodes.get(id)` per id (keyed store, not `ConversationNode[]`); `thinking` re-derived from chat nodes after narrowing the node discriminant; `toolRunning`/`lastTurnEnd` re-derived from the node stream (e.g. `type === 'assistant-step'` → `data.finalNode`) or from the SessionBinding durable event window (`sessions.binding(id)` → `binding.eventSource.getSnapshot().entries`, `SessionEventLikeEntry[]`). Exact field re-derivation must be confirmed against the target tag's ChatSnapshot declarations — A1-03 rule: "do not guess new paths". Pet.tsx:19 `running` stays on the `useSession` lifecycle seat. `PropsLocale<'pet'>` unchanged.

**M3 — staged alternative.** Per the A1-03 field note, `partial`/`runningCalls`/`turnEnds` "are all still readable through the `views.get('chat')?.legacy` projection", enabling the two-step plan ("migrate everything to legacy first, then field-by-field to views/timeline once stable"). API-10 constraint: `snapshot.legacy.nodes` is staged compatibility only with an explicit dual-host requirement — not the primary surface for an alpha.2-only plugin.

**M4 (B4, DSH-0.1.2-A1-26).** Bundle banner registers id == package name: `__ModuleLoader__.load({ id: '@demo/dsh-bench-pet' })`; insert row keeps `name: '@demo/dsh-bench-pet'` and the short `bench-pet` id must not be relied on. Verify: `dsh --profile <name> --dump-config` (no pending), `window.__DSH_BOOT__.entries` contains the package name, combo route `/plugins/??@demo/dsh-bench-pet/client.js&rev=...`, no loaded-without-registering in the log.

## 3. Card mapping (full numbers)

| Surface | Card | Level |
|---|---|---|
| dsh-client-runtime import/inject (index.ts:6, Pet.tsx:8, package.json:8) | DSH-0.1.2-A1-25 | required-if-hit |
| Flat snapshot content fields (Pet.tsx:13-14, 21, 23) | DSH-0.1.2-A1-03 (legacy projection field note) with DSH-0.1.2-A1-27 | required-if-hit |
| useSession → useChat keyed store (Pet.tsx:18-23) | DSH-0.1.2-A1-03 via API-10 ledger; ledger anchor DSH-0.1.2-A1-25 | required-if-hit |
| Registration-id triple (cordis.patch.yml:2-3, banner) | DSH-0.1.2-A1-26 | required-if-hit |
| Type ownership of augmentations (index.ts:8,10; Pet.tsx:7) | DSH-0.1.2-A1-25 + DSH-0.1.2-A2-03 | conditional |
| Staged/coexistence context | rollup-0.1.2.md R-01–R-03, R-06 (corridor file) | process |

## 4. Projection-first vs. immediate switch

**Can run first through `views.get('chat')?.legacy` (DSH-0.1.2-A1-03 field note):** `snapshot.partial` (Pet.tsx:13-14), `snapshot.runningCalls` (Pet.tsx:21), `snapshot.turnEnds` (Pet.tsx:23) — staged landing, then field-by-field to useChat/timeline; staging surface only, dual-host requirement.

**Must switch immediately:** `s.running` (Pet.tsx:19) — lifecycle fields are not in the projection; they live on the surviving `useSession` seat and nothing projected can substitute; the import/inject plane (index.ts:6, Pet.tsx:8, package.json:8) — dsh-client-runtime is deleted, not projected, so re-homing per DSH-0.1.2-A1-25 must land in the same change or the plugin never assembles; the registration-id triple (DSH-0.1.2-A1-26) — no shim exists for "Entry name == package name"; any direct node/message content read — only `ChatSnapshot.order + nodes.get(id)` or the SessionBinding event window (DSH-0.1.2-A1-27) remain, with no legacy array fallback.

## 5. Suggested order (plan only; not executed)
1. Re-home types + drop phantom inject (M1). 2. Align registration ids, verify boot (M4). 3. Keep `running` on the useSession seat; stage content fields through the legacy projection; then move to useChat + keyed ChatSnapshot. 4. Verify per cards: dump-config clean, boot entry present, one real turn exercising idle/thinking/working + settle frame on a 0.1.2-alpha.2 host.
