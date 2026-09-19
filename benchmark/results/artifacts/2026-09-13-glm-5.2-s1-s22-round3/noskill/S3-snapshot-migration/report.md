# S3 · Snapshot Read-Surface Migration Assessment — `@demo/dsh-bench-pet` (0.1.1-rc.1 → dsh 0.1.2-alpha.2)

Read-only assessment. No fixture files were modified. Line numbers refer to the fixture tree `environment/fixture/` (`src/client/Pet.tsx`, `src/client/index.ts`, `src/client/locales.ts`, `package.json`).

Corridor: `dsh-v0.1.1-rc.1/rc.2` → `dsh-v0.1.2-alpha.1` → `dsh-v0.1.2-alpha.2`.
Governing upgrade cards: **DSH-0.1.2-A1-03** (Session view internals split up extensively — `skills/plugin-upgrade/references/v0.1.2-alpha.1.md`) and, as the supporting package-removal card, **DSH-0.1.2-A1-25** (`@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain). Supplementary practice reference: **API-10** (`references/api-migration-0.1.2-alpha.2.md`, Web Client runtime unbundling / keyed chat snapshots) and the precision checklist's renderer/slots ownership section.

---

## 1. Breaking surfaces, location by location

### 1.1 Chat-transcript reads on the flat `ConversationSnapshot` — `src/client/Pet.tsx`

| Read | Location | Field class |
|---|---|---|
| `snapshot.partial?.blocks.some(b => b.kind === 'reasoning')` (`isThinking`, consumed at `Pet.tsx:20`) | `Pet.tsx:13-15` | chat view data (legacy projection field) |
| `useSession(s => s.runningCalls.length > 0)` | `Pet.tsx:21` | chat view data (legacy projection field) |
| `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` | `Pet.tsx:23` | chat view / turn timeline (legacy projection field) |
| `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'` | `Pet.tsx:8` | removed type owner (see §1.3) |

**What breaks and why (DSH-0.1.2-A1-03).** The alpha.1 session-view split changed the public snapshot consumption surface: the flat `ConversationSnapshot` shape (flat `nodes`/`partial`/`runningCalls`/`turnEnds`) is no longer the primary read surface. Reading these fields off the session store via `useSession` selectors either stops typechecking once the `dsh-client-runtime` types are gone (§1.3), or silently becomes `any`-typed under `skipLibCheck`, and the eventual target shape is a **keyed store**, not an array.

**Temporary compatibility read path (can run first).** DSH-0.1.2-A1-03's field note (2026-08-28, dsh-ui-whale v0.3.5 / dsh-ui-progress v0.9.4 / dsh-input-history v0.1.4) records that the old flat fields `nodes` / `partial` / `runningCalls` / `turnEnds` are **all still readable through the `views.get('chat')?.legacy` projection**. The proven two-step strategy is: "migrate everything to `legacy` first, then migrate field-by-field to views/timeline once stable." So the first migration step for `Pet.tsx` is:

```ts
// Step 1 (compatibility projection — runs first, unblocks the alpha.2 host):
const thinking    = useChat(chat => chat?.views.get('chat')?.legacy.partial?.blocks.some(b => b.kind === 'reasoning') ?? false)
const toolRunning = useChat(chat => (chat?.views.get('chat')?.legacy.runningCalls.length ?? 0) > 0)
const lastTurnEnd = useChat(chat => {
  const ends = chat?.views.get('chat')?.legacy.turnEnds
  return ends?.[ends.length - 1]?.reason
})
```

(The exact selector root — `useChat` vs a session-scope `views` accessor — and the exact legacy symbol names must be confirmed against the alpha.2 target exports before committing; the card itself says "defer to each package's actual exports at the target tag".)

**Target form (after stabilization, field by field).** Per DSH-0.1.2-A1-03's second field note (omdsh-plugin-lab 0.7.0-alpha.0) and API-10's exact mapping:

```ts
import type { Context } from '@deepseek-ai/cordis'
import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'
import type {} from '@deepseek-ai/dsh-client-ui-chat/client'
import type {} from '@deepseek-ai/dsh-api-session-controller/client'

// Transcript nodes: ChatSnapshot.nodes is a keyed store, not ConversationNode[]:
function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap(id => {
    const node = snapshot.nodes.get(id)
    return node ? [node] : []
  })
}

// The pet's selectors migrate from useSession-on-flat-ConversationSnapshot to
// useChat(chat => ...) over the ChatSnapshot (nodes keyed store); the
// turn-settle frame moves off turnEnds[] onto the target turn-timeline /
// assistant-step surface: narrow nodes by discriminant type === 'assistant-step'
// and read data.finalNode for the completed-turn signal that used to be
// turnEnds[len-1].reason.
```

`ChatSnapshot.order` + `snapshot.nodes.get(id)` replaces `nodes[]`; `partial` and `runningCalls` equivalents move onto the chat view's own contract in `@deepseek-ai/dsh-client-ui-chat/client`; `turnEnds` maps to the timeline/assistant-step view. Exact replacement symbols for `partial`/`turnEnds` on the target view contract are **pending confirmation against alpha.2 exports** (A1-03: "Mark capabilities that have no stable public seam as 'pending confirmation'; do not guess new paths") — which is exactly why the `legacy` projection step is recommended before the field-by-field switch.

**Card: DSH-0.1.2-A1-03 · Session view internals split up extensively** (breaking; required-if-hit; applies to Web Client snapshot consumers; symptom: old flat snapshot reads / internal view imports stop working).

### 1.2 Session-lifecycle field `running` — `src/client/Pet.tsx:19`

`const running = useSession(s => s.running)` is **not** a chat-view read. Per DSH-0.1.2-A1-03's field note: lifecycle fields (e.g. `running`) are not in the [legacy] projection and must go through the `useSession` seat instead. The migration therefore leaves this line essentially as it is — the **`useSession` lifecycle seat itself is not renamed**; only the type graph behind it changes (the `useSession` hook's declaration now comes from its owning client package instead of the removed `dsh-client-runtime` aggregation, §1.3).

What does change around it:

- `PetProps` must keep resolving `useSession` from the owner's Context augmentation (whichever package owns the session hook at alpha.2 — confirm at the target tag), because the augmentation previously pulled in transitively by `@deepseek-ai/dsh-client-runtime/client` no longer exists;
- the chat-transcript selectors listed in §1.1 move **off** `useSession` (they become `useChat`), while `running` stays **on** `useSession` — the split between the two seats is the point of A1-03.

**Card: DSH-0.1.2-A1-03** (same card; this is the projection/lifecycle boundary it documents). Note specifically: do **not** claim the existing `useSession(s => s.running)` call must be renamed — the break is the removed type owner, not the lifecycle seat.

### 1.3 Removed `dsh-client-runtime` imports and `client.inject` entry — `Pet.tsx:8`, `src/client/index.ts:6`, `package.json:8`

Three hits of **DSH-0.1.2-A1-25 · `@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain** (breaking; required-if-hit; symptoms: build/typecheck report a nonexistent module / missing exports; at runtime the assembly row stays pending forever and the plugin never enters the boot graph, often with no explicit error):

1. `Pet.tsx:8` — `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`.
2. `index.ts:6` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`.
3. `package.json:8` — `"inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`: keeping the deleted package in `dsh.client.inject` leaves the row **pending / out of the boot graph** (field note, dsh-input-history: with the runtime package left in inject the row did not enter the graph; removing it restored it).

**Target forms (A1-25 verified mapping + API-10):**

```ts
// index.ts
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// Type-only augmentations, one per owning package actually consumed:
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'

// Pet.tsx — ConversationSnapshot is no longer exported by an aggregation runtime.
// The chat read surface at alpha.2 is ChatSnapshot from the owning ui-chat package;
// a legacy-projection type (if exported by the view owner) may be used in step 1.
import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'
```

```json
"client": {
  "platform": "web",
  "inject": ["dsh-client-ui-conversation", "dsh-client-locale"]
}
```

Rules applied:

- `ClientContext` → `Context` from scoped `@deepseek-ai/cordis` (A1-25 mapping row 1); bare cordis imports are otherwise unchanged on this plane.
- Snapshot types go to their **target owner** (`@deepseek-ai/dsh-client-ui-chat/client` for the chat snapshot; conversation node types to `@deepseek-ai/dsh-client-ui-conversation/client`) — they are **not** exported by cordis itself. The precise legacy-projection symbol names for step 1 are pending the alpha.2 export check (explicitly deferred, per A1-03's "do not guess new paths").
- Remove `dsh-client-runtime` from `dsh.client.inject`; keep only packages that actually provide services the plugin injects at runtime. While the cohort is unpublished, type dependencies point at the official source checkout with `link:` or tarball `overrides` (A1-25 → rollup R-01).
- Run one typecheck with `skipLibCheck: false` after recomposition (API-10): a new implicit `any` on a selector/callback is a migration failure, not a warning.

### 1.4 Scoped slot registration — `src/client/index.ts:29,38-43`

```ts
export const inject = ['slots', 'conversation', 'locale']          // index.ts:29
ctx.inject(['slots', 'conversation'], (scope: ClientContext) => {   // index.ts:38
  scope.slots.register(
    { name: 'conversation.session.header.actions', id: 'pet', order: 10 },  // index.ts:40
    Pet,
  )
})
```

This is a **supported registration form that survives the corridor** — the equivalent supported pattern at alpha.2 is unchanged in shape:

- keep the **scoped** `ctx.inject([...], scope => ...)` wrapper (the `slots.inject`-style scoping around registration): it is an ordering edge — `conversation.session.header.actions` is declared by ui-conversation's apply, and `register()` into an undeclared slot throws (`slot "<name>" is not declared`, troubleshooting table). The plugin-level `export const inject` and the scoped registration together preserve the slot's **lifetime** (the disposer belongs to the scoped fiber) and the load order;
- preserve the slot **name** `conversation.session.header.actions`, `id: 'pet'`, and `order: 10` verbatim — the slot name is owned by the declaring entry, not by this plugin.

What does change at alpha.2 is **ownership of the slots service and its declarations**: after the client runtime split, the renderer/slots service lives in `@deepseek-ai/dsh-client-ui-renderer` (`packages/client/ui-renderer/src/client/index.ts`). Consequences for this plugin:

- it is a slots **consumer** (it mounts into a host slot point), so it needs the renderer-owned `ctx.slots` Context declarations in its type graph. If no other import already brings the augmentation in, make the dependency visible with an explicit type-only import: `import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'` — and keep the owning package in `peerDependencies`. This import is erased at runtime: it cannot register a service or resolve a pending `slots` wait, so it is **not** a boot fix and does **not** belong in package-level `dsh.client.inject` by itself;
- the runtime wait on the `slots` service is satisfied by the real renderer module's activation in the host's client composition, and is expressed through the consumer's service-level `export const inject = ['slots', ...]` (already present at `index.ts:29`). The type graph and the runtime service graph are checked separately.

**Cards: DSH-0.1.2-A1-25** (the removed aggregation runtime that used to carry these augmentations) and the A1-03 surface (view/UI registration points). If the registration stops resolving, the symptom is the boot-graph row pending forever (A1-25) or `slot ... is not declared` at apply time (troubleshooting) — not a slot rename.

### 1.5 Non-breaking surfaces (explicitly checked, no action)

- `src/client/locales.ts` and the `LocaleNamespaceMap` augmentation + `ctx.locale.register(NS, { zh, en })` (`index.ts:14-19, 36`): `dsh-client-locale` still exists and stays in `dsh.client.inject`. Locale pairing (type-level augmentation **and** runtime register) is already complete — keep it; it is a mandatory final check for any plugin shipping user-facing text, not a migration hit.
- `cordis.patch.yml` insert row (`id: bench-pet`, `name: '@demo/dsh-bench-pet'`) matches `package.json` `name`, so the A1-26 registration-id scan contract holds as-is.
- `PetProps = PropsRuntime<'conversation.session.header.actions'> & PropsLocale<'pet'>` from `@deepseek-ai/dsh-client-ui-slots` — package unchanged; only its augmentation chain (previously pulled in transitively via `dsh-client-runtime`) must now be reached through the owning packages' type-only imports.

---

## 2. What can run first via the compatibility projection vs. what must switch immediately

**Can run first (compatibility projection, DSH-0.1.2-A1-03 field note):**

- `partial.blocks` reasoning check (`Pet.tsx:13-15,20`) → `views.get('chat')?.legacy.partial...`
- `runningCalls.length > 0` (`Pet.tsx:21`) → `views.get('chat')?.legacy.runningCalls`
- `turnEnds[...].reason` settle frame (`Pet.tsx:23`) → `views.get('chat')?.legacy.turnEnds`

These three flat fields are explicitly still readable through the chat legacy projection at the target, so the pet's animation behavior can be preserved unchanged on day one of the alpha.2 host. They are staging only: the end state is the field-by-field migration to the keyed `ChatSnapshot` (`order` + `nodes.get(id)`) and the timeline/assistant-step surface, done once the plugin is stable on the new host.

**Must switch immediately (no compatibility path):**

- `import ... from '@deepseek-ai/dsh-client-runtime/client'` in `Pet.tsx:8` and `index.ts:6` — the package no longer exists; builds/typecheck fail outright (A1-25).
- `package.json` `client.inject` containing `dsh-client-runtime` — a phantom runtime dependency; the assembly row stays pending and the client half never enters the boot graph (A1-25 field note). Must be edited in the same change as the import rewrite.
- Type ownership: `ClientContext` → `@deepseek-ai/cordis` `Context`; snapshot/conversation types → their owning packages (`dsh-client-ui-chat` / `dsh-client-ui-conversation` / `dsh-client-ui-renderer` for slots declarations), plus the corresponding `peerDependencies` entries. Skipping this yields silent `any`s, which count as migration failure (API-10).
- The `running` lifecycle read stays on `useSession` — immediate but a *non-change*: it is outside the chat legacy projection and must not be dragged along with the chat selectors, and the `useSession` seat itself is not renamed.
- Scoped slot registration form, slot name, and registration lifetime are preserved as-is; only the augmentation sources behind the types move.

**Suggested order:** (1) rewrite imports + package.json inject + peers; (2) move the three chat selectors to the `legacy` projection with `useSession` kept for `running`; (3) verify typecheck with `skipLibCheck: false`, cold-boot the isolated profile, and confirm the boot graph contains `@demo/dsh-bench-pet` with no pending rows; (4) migrate selectors field-by-field off `legacy` onto the keyed snapshot/timeline, confirming exact target symbols against alpha.2 exports at each step.

## 3. Summary table

| Hit location | Old interface | Symptom on 0.1.2-alpha.2 | Target interface | Card | Required / staged |
|---|---|---|---|---|---|
| `Pet.tsx:8` | `ConversationSnapshot` from `dsh-client-runtime/client` | missing module/exports | `ChatSnapshot` from `@deepseek-ai/dsh-client-ui-chat/client` (legacy-projection type for step 1, symbol pending target export check) | DSH-0.1.2-A1-25 (+API-10) | immediate |
| `index.ts:6` | `ClientContext` from `dsh-client-runtime/client` | missing module/exports | `Context as ClientContext` from `@deepseek-ai/cordis` + owning-package type-only augmentations | DSH-0.1.2-A1-25 | immediate |
| `package.json:8` | `dsh-client-runtime` in `client.inject` | assembly row pending; boot graph never includes plugin | remove it; keep only real service packages | DSH-0.1.2-A1-25 | immediate |
| `Pet.tsx:20` (`partial.blocks`) | flat `ConversationSnapshot.partial` | type/shape drift off the flat snapshot | `views.get('chat')?.legacy.partial` first; then chat view contract | DSH-0.1.2-A1-03 | projection first |
| `Pet.tsx:21` (`runningCalls`) | flat `ConversationSnapshot.runningCalls` | as above | `views.get('chat')?.legacy.runningCalls` first; then target view | DSH-0.1.2-A1-03 | projection first |
| `Pet.tsx:23` (`turnEnds[].reason`) | flat `ConversationSnapshot.turnEnds` | as above | `views.get('chat')?.legacy.turnEnds` first; then timeline / `assistant-step` `data.finalNode` | DSH-0.1.2-A1-03 | projection first |
| `Pet.tsx:19` (`running`) | `useSession(s => s.running)` lifecycle seat | only its type owner is removed | unchanged seat: stays on `useSession`; not in legacy projection, not renamed | DSH-0.1.2-A1-03 | immediate (types only) |
| `index.ts:29,38-43` | scoped `ctx.inject(['slots','conversation'])` + `slots.register('conversation.session.header.actions')` | declarations chain broken if types drift; row pending if service waits | same supported scoped registration; slots service/declarations owned by `@deepseek-ai/dsh-client-ui-renderer` (type-only import; runtime via `inject`/host composition) | DSH-0.1.2-A1-25 (+A1-03 UI registration points) | immediate (types), form preserved |
| `index.ts:14-19,36`, `locales.ts` | locale namespace pairing | none | unchanged; mandatory final check | — | no change |

## 4. Blockers / open confirmations

- None blocking this assessment. Two symbols are explicitly deferred to the alpha.2 target exports, per the cards' own "defer to each package's actual exports at the target tag" rule: (a) the exact legacy-projection accessor/symbol for `views.get('chat')?.legacy` in the client type graph, and (b) the exact target replacements for `partial` / `turnEnds` on the chat view contract. Both belong to steps 2/4 of the plan above and do not change the card mapping.
