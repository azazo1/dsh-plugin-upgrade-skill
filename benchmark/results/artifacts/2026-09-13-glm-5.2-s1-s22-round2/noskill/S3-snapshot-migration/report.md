# S3 · Snapshot Read-Surface Migration Assessment — `@demo/dsh-bench-pet`

**Corridor assessed:** plugin written in the 0.1.1-rc.1 era → host upgraded to **dsh 0.1.2-alpha.2**.
**Mode:** read-only assessment. No file under the fixture was modified, created, deleted, or renamed; no migration or installation was executed. Evidence: fixture source read in full, plus the local upgrade-card references (card sets `DSH-0.1.2-A1-*`, `DSH-0.1.2-A2-*`, and the rc.2→alpha.2 API ledger).

**Scope caveat (honest limitation):** the available card sets start at `dsh-v0.1.1-rc.2` (`DSH-0.1.2-A1-*` covers rc.2→alpha.1; `DSH-0.1.2-A2-*` covers alpha.1→alpha.2). No card set in the local references covers the rc.1→rc.2 segment, so rc.1-only surfaces not present in rc.2 are outside card-backed evidence. Every mapping below cites the exact card; where the target tag's concrete field name is not pinned by a card, the report says so instead of inventing a shape.

---

## 1 · Breaking surfaces, locations, target forms, and card mapping

### 1.1 `package.json` — `dsh.client.inject` lists the removed `dsh-client-runtime`

- **Location:** `fixture/package.json` → `"client": { "inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"] }`.
- **How it breaks:** `@deepseek-ai/dsh-client-runtime` was deleted in alpha.1. Keeping it in `dsh.client.inject` leaves a runtime phantom dependency: the assembly row stays pending / the plugin silently never enters the client boot graph, often with no explicit error.
- **Card:** **DSH-0.1.2-A1-25** (`@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain); packaging follow-up per **DSH-0.1.2-A2-03** and the API ledger's API-10 "Type composition and dependency ownership".
- **Post-migration form:** remove `dsh-client-runtime`; keep only packages whose services the client bundle actually consumes. After the snapshot migration the bundle will also consume `dsh-client-ui-chat` types, so its owner becomes a direct type/dev/peer dependency of the plugin (a published package's `devDependencies` are not transitively installed for consumers):

```json
"client": { "platform": "web", "inject": ["dsh-client-ui-conversation", "dsh-client-locale"] }
```

plus direct type dependencies on `@deepseek-ai/cordis`, `@deepseek-ai/dsh-client-ui-chat`, `@deepseek-ai/dsh-client-ui-conversation`, `@deepseek-ai/dsh-client-locale`. Run `tsc --skipLibCheck false` once during migration to surface the missing declaration chain (otherwise `useChat` selectors silently become `any`).

### 1.2 `cordis.patch.yml` — registration id ≠ package.json name

- **Location:** `fixture/cordis.patch.yml` → row `{ id: bench-pet, name: '@demo/dsh-bench-pet' }`.
- **How it breaks:** 0.1.2's client-modules scan keys entries/modules/plugin registrations by package name (`Entry name == package name`). With `id: bench-pet` ≠ `name: '@demo/dsh-bench-pet'` you get either the startup assertion `loaded without registering "<id>"` or, worse, the pet silently disappearing from the boot graph with no plugin-related error.
- **Card:** **DSH-0.1.2-A1-26** (client-modules scan contract: registration id must equal the package.json name).
- **Post-migration form:** all three ids agree, with the bare package name (scope included) as the baseline: (1) the client bundle's `__ModuleLoader__.load({ id })` registration (usually injected by the tsdown banner `PLUGIN_ID`), (2) the assembly row's `id`, (3) `package.json#name`:

```yaml
- insert:
    - id: '@demo/dsh-bench-pet'
      name: '@demo/dsh-bench-pet'
```

- **Verify:** `window.__DSH_BOOT__.entries` contains `"id":"@demo/dsh-bench-pet"`; the combo route `/plugins/??@demo/dsh-bench-pet/client.js&rev=...` serves the bundle; `dsh --profile <p> --dump-config` shows no pending rows.

### 1.3 `src/client/index.ts` — `ClientContext` imported from the removed runtime package

- **Location:** `fixture/src/client/index.ts`, `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`.
- **How it breaks:** typecheck reports a nonexistent module / missing exports; with stale declarations the plugin compiles but does not enter the boot graph (see 1.1).
- **Card:** **DSH-0.1.2-A1-25** (symbol mapping table: `Context`, alias `ClientContext`).
- **Post-migration form:**

```ts
import type { Context as ClientContext } from '@deepseek-ai/cordis'
```

The client facets merged into `Context` now come from each owning package via the type-only augmentation imports the file already performs (`dsh-client-locale/client`, `dsh-client-ui-conversation/client`) — keep those, and add the owning packages the migrated code newly consumes (see 1.5).

### 1.4 `src/client/Pet.tsx` — `ConversationSnapshot` type from the removed runtime package

- **Location:** `fixture/src/client/Pet.tsx`, `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'` (used by `isThinking`).
- **How it breaks:** same as 1.3 — missing module/exports; the selector's parameter silently degrades to `any` under `skipLibCheck: true`.
- **Cards:** **DSH-0.1.2-A1-25** (`ConversationNode` etc. moved to `@deepseek-ai/dsh-client-ui-conversation/client`) and **DSH-0.1.2-A1-03** / API ledger **API-10** (the flat `ConversationSnapshot` read surface is replaced by the keyed `ChatSnapshot`).
- **Post-migration form:** the transcript snapshot type is now `ChatSnapshot` from `@deepseek-ai/dsh-client-ui-chat/client` — a keyed store (`order: id[]` + `nodes: Map<id, node>`), not a flat `ConversationNode[]`:

```ts
import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'

function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap((id) => {
    const node = snapshot.nodes.get(id)
    return node ? [node] : []
  })
}
```

To read an assistant step's final node, narrow by discriminant to `type === 'assistant-step'` and read `data.finalNode`; do not cast old array fixtures with `as unknown as ChatSnapshot`.

### 1.5 `src/client/Pet.tsx` — the four flat-snapshot selectors (the core read-surface break)

- **Location:** `fixture/src/client/Pet.tsx`, inside `Pet({ useSession, t })`:

  | Selector (line) | Old flat field | Break class |
  |---|---|---|
  | `useSession(s => s.running)` | lifecycle field | not projected at all — must move to the session seat |
  | `useSession(isThinking)` reading `snapshot.partial?.blocks…kind === 'reasoning'` | transcript field | projection first, then keyed read path |
  | `useSession(s => s.runningCalls.length > 0)` | transcript field | projection first, then keyed read path |
  | `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` | turn-timeline field | projection first, then new read path |

- **Cards:** **DSH-0.1.2-A1-03** (session-view internals split; its field note is the authority for the `views.get('chat')?.legacy` compatibility projection and for `running` not being projected), **DSH-0.1.2-A1-27** (session content reads go through the `SessionBinding` durable event window), API ledger **API-10** (`useSession(session => session?.nodes)` → `useChat(chat => …)`; keyed `order` + `nodes.get(id)`).
- **How it breaks:** the per-session flat conversation snapshot is gone as a primary surface — the timeline became an internal projection of each view package. Selectors typed against the old shape either fail typecheck (after devDeps move) or read `undefined` at runtime (pet freezes on `idle`, console shows factory errors).
- **Post-migration form (final state):**

```ts
// lifecycle: stays on the session seat (useSession) — never was a chat-view field
const running = useSession(s => s.running)

// transcript: useChat over the keyed ChatSnapshot
const toolRunning = useChat(chat => chat ? countRunningCalls(chat) > 0 : false)
const thinking   = useChat(chat => chat ? hasLiveReasoning(chat) : false)
```

  - `countRunningCalls` / `hasLiveReasoning` walk `chat.order` + `chat.nodes.get(id)` (helper shape in 1.4). The exact discriminants for "tool call in flight" and "partial reasoning block" inside the new `ChatSnapshot` node vocabulary are **not pinned by any card** — confirm them against the target tag's `packages/client/ui-chat/src/client/contract/snapshot.ts` before coding; do not transliterate `partial.blocks`/`runningCalls` field names by guess.
  - The settle-frame input (`turnEnds[...].reason`) has no flat successor on the chat view. Per **DSH-0.1.2-A1-27**, third-party reads of turn-timeline content go through the session binding's durable event window: `sessions.binding(id)` → `SessionBinding { sessionId, session, eventSource, ctx }` → `binding.eventSource.getSnapshot().entries` (`SessionEventLikeEntry[]`, `SessionEvent`/`SessionBinding` from `@deepseek-ai/dsh-api-session-controller/client`), folding the last turn-end event. Mark this one "pending target-tag confirmation" for the exact event type carrying the end reason.

### 1.6 Surfaces checked and NOT breaking (negative scan, so the report is complete)

- `fixture/src/client/locales.ts` and the `ctx.locale.register(NS, { zh, en })` + `LocaleNamespaceMap` augmentation in `index.ts` — no card in the corridor changes the locale registration seam (A1-10 adds a new optional host capability only).
- `slots.register({ name: 'conversation.session.header.actions', id: 'pet', order: 10 }, Pet)` and the `PropsRuntime`/`PropsLocale` helpers from `@deepseek-ai/dsh-client-ui-slots` — `ui-slots` still exists at alpha.2 (it is the cited owner of client slot base Context augmentation). **DSH-0.1.2-A1-03** warns session-view/UI internals were split extensively, so re-verify the slot key string against the target tag's `ui-conversation` slot declarations during implementation; no card declares a rename.
- `inject = ['slots', 'conversation', 'locale']` with the `ctx.inject([...])` ordering edge — cordis fiber semantics unchanged; none of the corridor cards renames these services.
- `Pet.tsx` JSX/`.tsx` style — build concern, not a corridor break.

---

## 2 · Compatibility projection vs. immediate new read path

**Can run first through the compatibility projection** (per the DSH-0.1.2-A1-03 field note from the dsh-ui-whale / dsh-ui-progress / dsh-input-history migrations): the old flat `ConversationSnapshot` transcript fields — `nodes`, **`partial`**, **`runningCalls`, **`turnEnds`** — remain readable via `views.get('chat')?.legacy`. The proven strategy is two-step: (1) migrate everything to `legacy` first so the plugin runs on alpha.2, (2) once stable, migrate field-by-field to the keyed `useChat` view (and to the A1-27 event window for turn-timeline data). The `legacy` projection is a staged bridge, not the new primary surface — an alpha.2-only plugin must not stop there.

**Must switch to the new read path immediately (no projection exists):**

1. **`s.running`** — a lifecycle field, explicitly *not* present in the `legacy` projection; it must go through the `useSession` seat (session face) right away. This is the one selector that cannot be staged.
2. **Every `dsh-client-runtime` import** (`ClientContext`, `ConversationSnapshot`) — the package is deleted; this is a compile/boot-graph break, not a data-shape drift. No projection can paper over a missing module.
3. **`dsh.client.inject` cleanup** (1.1) and the **registration-id equality** fix (1.2) — boot-graph mechanics; they fail before any data read happens.

**Summary table**

| # | Hit location | Old surface | Symptom on 0.1.2-alpha.2 | Target form | Card | Migration path |
|---|---|---|---|---|---|---|
| 1.1 | `package.json` `client.inject` | `dsh-client-runtime` inject row | row pending / out of boot graph | drop it; own type deps per package | DSH-0.1.2-A1-25 (+A2-03) | immediate |
| 1.2 | `cordis.patch.yml` | `id: bench-pet` | `loaded without registering` or silent no-show | `id: '@demo/dsh-bench-pet'` everywhere | DSH-0.1.2-A1-26 | immediate |
| 1.3 | `src/client/index.ts` | `ClientContext` from runtime/client | missing module/exports | `Context as ClientContext` from `@deepseek-ai/cordis` | DSH-0.1.2-A1-25 | immediate |
| 1.4 | `src/client/Pet.tsx` | `ConversationSnapshot` from runtime/client | missing module / `any` selectors | `ChatSnapshot` from `dsh-client-ui-chat/client`, keyed `order`+`nodes.get` | DSH-0.1.2-A1-25, A1-03, API-10 | immediate (type), staged (reads) |
| 1.5a | `Pet.tsx` `s.running` | flat lifecycle field | `undefined` — pet never reacts | `useSession` seat | DSH-0.1.2-A1-03 | immediate — not projected |
| 1.5b | `Pet.tsx` `partial.blocks` | flat transcript field | `undefined` → always idle | `views.get('chat')?.legacy` → then `useChat` keyed read | DSH-0.1.2-A1-03, API-10 | projection first |
| 1.5c | `Pet.tsx` `runningCalls` | flat transcript field | `undefined` → tail never "working" | `views.get('chat')?.legacy` → then `useChat` | DSH-0.1.2-A1-03, API-10 | projection first |
| 1.5d | `Pet.tsx` `turnEnds[].reason` | flat turn-timeline field | `undefined` → no settle frame | `legacy` → then `SessionBinding` durable event window | DSH-0.1.2-A1-03, DSH-0.1.2-A1-27 | projection first |

**Suggested execution order for the later code change (not performed here):** fix 1.1–1.3 so the plugin boots; move all four selectors onto `legacy` except `running` (1.5a, session seat); then migrate `partial`/`runningCalls` to `useChat` and `turnEnds` to the event window; verify with a real Web boot (token→Cookie, boot entry, advertised resource, registration/mount, remove) plus `--dump-config` with no pending rows.

---

## 3 · Read-only discipline statement

The fixture directory and the rest of the benchmark repository were only read. The single file written by this assessment is this report, in the designated output directory. No migrations, installations, commits, pushes, or external services were involved.
