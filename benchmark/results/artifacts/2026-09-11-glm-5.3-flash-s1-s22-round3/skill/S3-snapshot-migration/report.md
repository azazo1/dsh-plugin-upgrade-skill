# S3 · Snapshot Read-Surface Migration Assessment — @demo/dsh-bench-pet (read-only)

Mode A · inspect (plugin-upgrade skill). Corridor: `dsh-v0.1.1-rc.1 → dsh-v0.1.2-alpha.2` (edges: rc.1→rc.2 `DSH-0.1.1-R2`, rc.2→alpha.1 `DSH-0.1.2-A1`, alpha.1→alpha.2 `DSH-0.1.2-A2`; full rc.2→alpha.2 interface ledger: `api-migration-0.1.2-alpha.2.md`). No source was modified; the fixture was read read-only.

Fixture identity: package `@demo/dsh-bench-pet` v0.1.0, Web Client plugin — `package.json` (client block, `inject: ["dsh-client-runtime","dsh-client-ui-conversation","dsh-client-locale"]`), `cordis.patch.yml` (one insert row `id: bench-pet`, `name: '@demo/dsh-bench-pet'`), source `src/client/index.ts`, `src/client/Pet.tsx`, `src/client/locales.ts`.

The plugin is a Web Client plugin whose animation follows the live conversation snapshot. Every breaking surface below is a snapshot read-surface hit: the whole snapshot consumption shape changed between rc.1 and alpha.2 (client-runtime unbundling + keyed chat snapshots).

---

## 1 · Breaking surfaces and their post-migration forms

### 1.1 Import of `ClientContext` from `@deepseek-ai/dsh-client-runtime/client` — package removed

- Evidence: `src/client/index.ts:7` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`.
- Breaks how: `@deepseek-ai/dsh-client-runtime` was deleted from `packages/client` in alpha.1; build/typecheck report a nonexistent module, and at runtime the plugin can fail to enter the boot graph with no explicit error. Full card: **DSH-0.1.2-A1-25**.
- Post-migration form:
```ts
import type { Context as ClientContext } from '@deepseek-ai/cordis'
```
plus type-only augmentations from the owning packages actually used (the file already uses this pattern for locale/ui-conversation).
- Compat projection? **No — immediate.** A missing package cannot be projected around; this is the prerequisite for every other fix.

### 1.2 `dsh-client-runtime` in the manifest `client.inject` list

- Evidence: `package.json` — `"inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`.
- Breaks how: after the dismantling the package is a runtime phantom dependency; keeping it in `client.inject` leaves the assembly row pending / out of the boot graph (A1-25 field note, dsh-input-history). Full card: **DSH-0.1.2-A1-25**.
- Post-migration form: `"inject": ["dsh-client-ui-conversation", "dsh-client-locale"]` — keep only packages that actually provide services and that the client half imports.
- Compat projection? **No — immediate** (boot-graph level; no projection exists).

### 1.3 `ConversationSnapshot` type + `useSession` flat read of the node-era fields (`Pet.tsx`)

- Evidence: `src/client/Pet.tsx:4` — `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`; the component reads four flat snapshot fields via the slot-injected `useSession` selector:
  - `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')` (`isThinking`, Pet.tsx:11);
  - `s.running` (Pet.tsx:15);
  - `s.runningCalls.length > 0` (Pet.tsx:17);
  - `s.turnEnds[s.turnEnds.length - 1]?.reason` (Pet.tsx:19).
- Breaks how: on alpha.2 `ChatSnapshot.nodes` is a **keyed store, not `ConversationNode[]`**; the flat rc-era `ConversationSnapshot` type is gone and the transcript read moves from `useSession` to `useChat`. Without the owning type dependencies, `skipLibCheck: true` silently turns the selectors into `any`. Full cards: **API-10** (api-migration-0.1.2-alpha.2.md — Web Client runtime unbundling, keyed chat snapshots), **DSH-0.1.2-A1-03** (session view internals split; its field note names exactly this: flat `nodes/partial/runningCalls/turnEnds`), **DSH-0.1.2-A1-25** (symbol rehoming).
- Post-migration form:
  - Type: `import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'` (plus `type {}` augmentations from `dsh-client-ui-chat/client`, `dsh-api-session-controller/client`, etc.).
  - Ordered node read: iterate `snapshot.order` and call `snapshot.nodes.get(id)` per id:
```ts
function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap((id) => {
    const node = snapshot.nodes.get(id)
    return node ? [node] : []
  })
}
```
    consumed via `ctx.useChat(...)` / the slot's chat seat. The final assistant node is found by narrowing to `type === 'assistant-step'` and reading `data.finalNode`.
  - Reasoning detection is rewritten over the ordered nodes' discriminants instead of `snapshot.partial.blocks`; tool-in-flight detection over tool-call nodes instead of `runningCalls`; turn-end reason is derived from the node/event timeline instead of `turnEnds`.
- Compat projection? Partially — see §2.

### 1.4 Lifecycle field `running` — not covered by the legacy projection

- Evidence: `src/client/Pet.tsx:15` — `const running = useSession(s => s.running)`.
- Breaks how: A1-03's field note (dsh-ui-whale v0.3.5 / dsh-ui-progress v0.9.4 / dsh-input-history v0.1.4 migration) states the legacy projection exposes only the content fields (`nodes/partial/runningCalls/turnEnds`); **lifecycle fields such as `running` are not in the projection** and must go through the `useSession` seat. Full cards: **DSH-0.1.2-A1-03**, **API-10**.
- Post-migration form: keep a lifecycle read on the `useSession` seat (still mounted), scoped to the `running` flag; the transcript read moves to `useChat`. Note the component currently only voids `running` (Pet.tsx:22 `void running`) — if it stays unused, drop the selector rather than migrating dead code.
- Compat projection? **No — must switch to the new seat immediately.** No projection carries it.

### 1.5 Slot prop surface `PropsRuntime<'conversation.session.header.actions'>`

- Evidence: `src/client/Pet.tsx:8` — `export type PetProps = PropsRuntime<'conversation.session.header.actions'> & PropsLocale<'pet'>`; `src/client/index.ts` registers `{ name: 'conversation.session.header.actions', id: 'pet', order: 10 }` via `ctx.slots.register`.
- Breaks how: the removed `dsh-client-runtime` re-exported the rc-era props/seat contract; `dsh-client-ui-slots` itself survives alpha.2 (its `src/index.ts` is the cited source of the client slot base Context augmentation in API-10), so the slot name and registration shape remain, but the snapshot-injecting prop behind `PropsRuntime` is now the `useChat`-backed chat seat — the component destructure `{ useSession, t }` no longer matches what the slot provides for transcript reads. Full cards: **DSH-0.1.2-A1-25**, **API-10**; verify the exact prop name against the target-tag `dsh-client-ui-slots` / `dsh-client-ui-chat` declarations (A1-03's rule: verify against the actual 0.1.2 packages/page, not 0.1.1 memory).
- Post-migration form: `PetProps = PropsRuntime<'conversation.session.header.actions'> & PropsLocale<'pet'>` with the transcript consumed via the chat seat (`useChat`); imports of `PropsRuntime`/`PropsLocale` stay on `@deepseek-ai/dsh-client-ui-slots`.
- Compat projection? **No — immediate** (type/prop surface).

### 1.6 Context augmentations in `index.ts` (`ctx.locale`, `ctx.slots`, nested `ctx.inject(['slots','conversation'], …)`)

- Evidence: `src/client/index.ts:8-10` (type-only imports of `@deepseek-ai/dsh-client-locale/client` and `@deepseek-ai/dsh-client-ui-conversation/client`), `index.ts:39-45` (nested inject + `scope.slots.register`).
- Breaks how: only indirectly — the `ClientContext` alias came from the removed runtime, and with `skipLibCheck: true` a missing owning package makes the augmentations silently degrade to `any`. The strict-injection contract itself is unchanged: `index.ts:33` already declares `inject = ['slots', 'conversation', 'locale']`, so card **DSH-0.1.1-R1-04** is satisfied (see §3). Cards: **DSH-0.1.2-A1-25** + API-10 "Type composition and dependency ownership".
- Post-migration form: code unchanged, but every declaration the source consumes must be a **direct** dev/peer dependency of `@demo/dsh-bench-pet` (`@deepseek-ai/cordis`, `dsh-client-ui-slots`, `dsh-client-ui-conversation`, `dsh-client-locale`, `dsh-client-ui-chat`, and `dsh-api-session-controller/client` if consumed). Published packages' devDependencies are not transitively installed. Run one `tsc --skipLibCheck false` diagnostic pass to locate missing declaration owners, then restore the repo policy.
- Compat projection? N/A — packaging/type-ownership discipline, done in the same pass.

### 1.7 Assembly row id / registration id consistency (verification; likely already compliant)

- Evidence: `cordis.patch.yml` — `- insert: - { id: bench-pet, name: '@demo/dsh-bench-pet' }`.
- Breaks how (if drifted): 0.1.2's boot manifest keys entries/modules/plugin registrations by package.json `name` — full card **DSH-0.1.2-A1-26**. The row's `name` already uses the bare scoped package name (correct form); the remaining requirement is the client bundle's `__ModuleLoader__.load` registration id == `@demo/dsh-bench-pet` (build banner, outside this fixture's source files).
- Post-migration form: keep the row; verify `window.__DSH_BOOT__.entries` contains `"id":"@demo/dsh-bench-pet"` and the combo route `/plugins/??@demo/dsh-bench-pet/client.js&rev=...` serves a script containing `__ModuleLoader__.load({ id: "@demo/dsh-bench-pet"`.
- Compat projection? N/A — verification item.

---

## 2 · Compatibility projection vs immediate new read path

Per the DSH-0.1.2-A1-03 field note, migrated hosts expose the old flat snapshot content fields through the **`views.get('chat')?.legacy` projection**; API-10 states `snapshot.legacy.nodes` is "only for staged compatibility with an explicit dual-host requirement; it should not become the new primary data surface for alpha.2-only plugins".

| Snapshot field (fixture site) | Runs first via legacy projection? | Must switch immediately |
|---|---|---|
| `partial?.blocks.some(kind === 'reasoning')` (Pet.tsx:11) | **Yes** — `partial` is in the legacy projection; a shim can compute `thinking` from `views.get('chat')?.legacy` while the timeline rewrite lands | Eventually — alpha.2-only builds derive it from `order + nodes.get(id)` node discriminants |
| `runningCalls.length > 0` (Pet.tsx:17) | **Yes** — `runningCalls` is in the legacy projection; shim "tool in flight" from it first | Eventually — new primary path reads tool-call nodes from the keyed store |
| `turnEnds[last]?.reason` (Pet.tsx:19) | **Yes** — `turnEnds` is in the legacy projection; shim the settle frame first | Eventually — derive from the node/event timeline |
| `running` (Pet.tsx:15) | **No** — lifecycle fields are explicitly **not** in the legacy projection (A1-03 field note) | **Immediately** — the `useSession` lifecycle seat (or drop the unused selector) |
| `ConversationSnapshot` / `ClientContext` imports; manifest `client.inject` (index.ts:7, package.json) | **No** — the package is deleted; no projection substitutes a missing module | **Immediately** — re-home symbols (`Context` from `@deepseek-ai/cordis`, `ChatSnapshot` from `dsh-client-ui-chat/client`), prune `dsh-client-runtime` from `client.inject` |
| `useSession` transcript selector (Pet.tsx) | Only through `legacy.nodes` under an explicit dual-host requirement | **Immediately** for an alpha.2-only plugin — `useChat` + `order + nodes.get()` |

Recommended sequencing (the two-step the field-note plugins used: "migrate everything to legacy first, then field-by-field to views/timeline"): fix imports/manifest/lifecycle fields first (hard breaks), then move the three content selectors off the legacy projection to the keyed timeline.

---

## 3 · Checked and cleared (skipped, with evidence)

- **DSH-0.1.1-R1-04 / R1-05** (strict injection / weak `ctx.get`) — not hit: `index.ts:33` declares `inject = ['slots', 'conversation', 'locale']` and consumes only injected services.
- **DSH-0.1.1-R1-02 / R1-03** (manifest `dsh.client` / client-modules scan) — the fixture declares the client half with `platform: "web"` and an entry; re-verify the packed manifest carries it, but the declaration is present.
- **DSH-0.1.1-R1-07** (`ctx.sessions`) — not hit: the pet uses the slot-injected seat, not `ctx.sessions`.
- **DSH-0.1.2-A1-27** (SessionBinding durable event window) — not hit: no direct `session.getSnapshot().nodes` call.
- **DSH-0.1.2-A1-28/29/30/31/32, DSH-0.1.2-A2-01/02/05/06/08/10, API-01…API-09** — no matching touchpoints (no composer DOM access, no MarkdownText, no `ctx.connection.api`, no subagent descriptors, no workspace navigation, no Remote calls, no settings namespaces, no command execution, no plugin-inventory consumption).
- **Locale and slot registration shapes** (`locales.ts`, `index.ts:40-41`) — no corridor card removes `ctx.locale.register`, `LocaleNamespaceMap`, or `PropsLocale`; keep and verify at the target tag.

## 4 · Card mapping summary

| Hit location | Old interface | Symptom on alpha.2 | Target interface | Card (full number) | Projection vs immediate |
|---|---|---|---|---|---|
| `src/client/index.ts:7` | `ClientContext` from `dsh-client-runtime/client` | nonexistent module | `Context` from `@deepseek-ai/cordis` | DSH-0.1.2-A1-25; API-10 | immediate |
| `package.json` `client.inject` | `dsh-client-runtime` row | assembly row pending / out of boot graph | remove the row | DSH-0.1.2-A1-25 | immediate |
| `src/client/Pet.tsx:4,11,17,19` | flat `ConversationSnapshot` via `useSession` | selectors become `any` / fields gone | `ChatSnapshot` via `useChat`, `order + nodes.get(id)` | API-10; DSH-0.1.2-A1-03; DSH-0.1.2-A1-25 | content fields: legacy projection first, keyed read second |
| `src/client/Pet.tsx:15` | lifecycle `running` on the flat snapshot | field absent from projection | `useSession` lifecycle seat | DSH-0.1.2-A1-03 (field note); API-10 | immediate |
| `src/client/Pet.tsx:8` | `PropsRuntime` seat contract re-homed | destructure `{ useSession, t }` no longer matches | `PropsRuntime`/`PropsLocale` from `dsh-client-ui-slots` + chat seat | DSH-0.1.2-A1-25; API-10 | immediate |
| declaration ownership | hoisted runtime types | implicit `any` under `skipLibCheck: true` | direct dev/peer deps per owning package | API-10 §Type composition; DSH-0.1.2-A2-03 (field note) | same pass |
| `cordis.patch.yml` row | id/name consistency | `loaded without registering "<id>"` / silent omission | registration id == package name | DSH-0.1.2-A1-26 | verification |

## 5 · Validation plan (when migration is authorized; not executed here)

1. Static: one `tsc --skipLibCheck false` diagnostic pass to surface missing declaration owners; then the repo's normal typecheck/build — no new implicit `any`.
2. Packaging: lockfile/tarball contain no `dsh-client-runtime`; all DSH packages on the exact 0.1.2-alpha.2 cohort; the packed manifest carries the client declaration.
3. Runtime: cold-boot the web profile; `dsh --profile <p> --dump-config` shows the `bench-pet` row with no pending lines; `window.__DSH_BOOT__.entries` contains `@demo/dsh-bench-pet`; the advertised combo route serves the client artifact that registers.
4. Behavior: send one message with a tool call — pet frames go idle → thinking → working → settle; reasoning/tool/settle detection matches the transcript within one render cycle.

Baseline run: not collected (Mode A read-only inspection).
