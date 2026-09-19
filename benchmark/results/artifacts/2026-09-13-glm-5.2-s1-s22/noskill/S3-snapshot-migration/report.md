# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (0.1.1-rc.1 → 0.1.2-alpha.2)

Read-only assessment. No fixture files were modified; this report is the only artifact written.

Fixture: `@demo/dsh-bench-pet` — a Web Client pet plugin whose animation follows the live conversation snapshot
(`src/client/Pet.tsx`), registered into the session-header actions slot (`src/client/index.ts`).

Primary upgrade cards:

- **DSH-0.1.2-A1-03 · Session view internals split up extensively** (breaking; the snapshot read surface)
- **DSH-0.1.2-A1-25 · `@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain** (breaking; imports + `client.inject`)

Supporting cross-reference: API-10 (Web Client runtime unbundling, keyed chat snapshots) in the alpha.2 API-migration reference — same corridor, elaborates A1-03/A1-25 for alpha.2.

---

## 1. Breaking surfaces, locations, and post-migration forms

### 1.1 Flat `ConversationSnapshot` reads in `Pet.tsx` — card **DSH-0.1.2-A1-03**

| # | Old read | Location | Post-migration form |
|---|---|---|---|
| a | `snapshot.partial?.blocks.some(b => b.kind === 'reasoning')` (`isThinking`, lines 13–15) | `src/client/Pet.tsx:13-15` | **Stage 1 (compatibility projection):** the old flat fields (`nodes` / `partial` / `runningCalls` / `turnEnds`) are still readable through the `views.get('chat')?.legacy` projection on alpha.2. **Stage 2 (target read path):** derive per the new chat view — read via `useChat(chat => ...)` over the keyed `ChatSnapshot` (`ChatNodeStore`: iterate `chat.order`, `chat.nodes.get(id)`); the streaming/partial state comes from the new view's equivalent field — the exact symbol for the partial/turn-timeline surface is **deferred to the target tag's `@deepseek-ai/dsh-client-ui-chat/client` exports** (do not guess new paths per A1-03's recipe). |
| b | `useSession(s => s.runningCalls.length > 0)` (`toolRunning`, line 21) | `src/client/Pet.tsx:21` | Same as (a): runs first through `views.get('chat')?.legacy.runningCalls`; final form reads the in-flight tool-call state from the chat view/timeline surface owned by `dsh-client-ui-chat` (exact symbol deferred to target exports). |
| c | `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` (`lastTurnEnd`, line 23) | `src/client/Pet.tsx:23` | Runs first through the `legacy` projection (`turnEnds`); final form migrates to the **timeline** surface (turn-end reasons live on the new timeline view, not on the keyed chat-node store). Exact symbol deferred to target exports. |

Why it breaks: the session view internals were split up extensively in alpha.1/alpha.2 (A1-03); the flat
`ConversationSnapshot` shape is no longer the primary surface. On alpha.2 `ChatSnapshot.nodes` is a keyed store,
not an array, and the transcript seat moved from `useSession` selectors to `useChat`.

### 1.2 `running` read in `Pet.tsx` — lifecycle seat, **not** part of the chat legacy projection

- Location: `src/client/Pet.tsx:19` — `const running = useSession(s => s.running)`.
- Per DSH-0.1.2-A1-03's field note: **lifecycle fields (e.g. `running`) are NOT in the `views.get('chat')?.legacy` projection** — they must go through the **`useSession` lifecycle seat**.
- Post-migration form: keep reading it exactly where it is — the session lifecycle via `useSession` (the `PropsRuntime` slot prop from `dsh-client-ui-slots` is unchanged). The existing `useSession` call itself does **not** need renaming for `running`; only the transcript/chat-derived selectors (1.1a–c) move to `useChat`/views/timeline.

### 1.3 Removed `dsh-client-runtime` imports — card **DSH-0.1.2-A1-25**

| Old | Location | Post-migration form |
|---|---|---|
| `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'` | `src/client/Pet.tsx:8` | The package was deleted in alpha.1. Snapshot types now live with their target owner — for the chat snapshot, `@deepseek-ai/dsh-client-ui-chat/client` (`ChatSnapshot`) — with the legacy-projection type (if used in stage 1) taken from the owning package at the target tag; the exact legacy-projection symbol is explicitly deferred to target exports. Do **not** claim cordis exports snapshot types. |
| `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'` | `src/client/index.ts:6` | `import type { Context as ClientContext } from '@deepseek-ai/cordis'` (verified mapping, A1-25). Client facets merged into `Context` come from their owning packages — keep/add the type-only augmentation imports from the owning packages actually hit (`dsh-client-locale/client`, `dsh-client-ui-conversation/client`, and — new — the renderer, see 1.5). |

### 1.4 `package.json` `client.inject` phantom entry — card **DSH-0.1.2-A1-25**

- Location: `package.json:8` — `"inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`.
- Post-migration form: **remove `@deepseek-ai/dsh-client-runtime`** — after the package's removal it is a runtime phantom dependency; keeping it leaves the assembly row pending / keeps the plugin out of the boot graph, often with no explicit error (A1-25 symptom + field note). Keep the packages that actually provide services consumed: `dsh-client-ui-conversation` (declares the header.actions slot / conversation service), `dsh-client-locale` (locale service). If the pet's runtime `slots` service wait is now satisfied by the renderer composition, verify the module table at the target tag rather than adding `ui-renderer` to `client.inject` for type-only reasons (a type-only import must not drive `client.inject`).

### 1.5 Slot registration ordering + renderer-owned `ctx.slots` declaration — cards **DSH-0.1.2-A1-25 / A1-03**

- Location: `src/client/index.ts:29` (`export const inject = ['slots', 'conversation', 'locale']`) and `src/client/index.ts:38-43` — `ctx.inject(['slots','conversation'], scope => scope.slots.register({ name: 'conversation.session.header.actions', id: 'pet', order: 10 }, Pet))`.
- What changes on 0.1.2-alpha.2:
  1. The **`slots` service is now owned by `@deepseek-ai/dsh-client-ui-renderer`** after the split. The plugin consumes slots, so it needs the renderer-owned Context declarations in its type graph — add an explicit type-only augmentation: `import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'`. This import is erased from JavaScript; it cannot register or resolve a runtime wait — the service-level `inject` edge and the real renderer activation in the client composition remain what satisfies `slots`.
  2. Registration into a slot **declared by another entry** (`conversation.session.header.actions` is declared by ui-conversation's apply) must be wrapped so it lands only after the owner's declaration, because apply order is undefined. The supported form is the slot-declaration injection: `ctx.slots.inject('conversation.session.header.actions', () => ctx.slots.register({ name: 'conversation.session.header.actions', id: 'pet', order: 10 }, Pet))` — equivalent supported registration forms are acceptable. The registrant passes only `name`/`id`/`order`(`label`).
  3. **Preserve the slot name and lifetime**: keep the slot name `conversation.session.header.actions`, the registration id `pet`, `order: 10`, and the `ctx.effect`-scoped dictionary registration; the pet stays a resident header slot with the same disposal behavior.

### 1.6 Non-issues (verified unchanged — no migration needed)

- `cordis.patch.yml` insert row already uses the bare package name `'@demo/dsh-bench-pet'` and `id: bench-pet`; per A1-26 the registration id must equal the package.json `name` — worth confirming the client bundle's registration id equals `@demo/dsh-bench-pet` at the target tag, but the row itself is in the post-0.1.2 shape.
- `PropsRuntime`/`PropsLocale` from `@deepseek-ai/dsh-client-ui-slots` and `ctx.locale.register` + `LocaleNamespaceMap` augmentation (locale pairing) are unchanged surfaces; keep them.

---

## 2. Compatibility projection vs. immediate switch (card DSH-0.1.2-A1-03)

**Can run first through the `views.get('chat')?.legacy` compatibility projection (staged, temporary):**

- `partial` (`Pet.tsx:13-15`)
- `runningCalls` (`Pet.tsx:21`)
- `turnEnds` (`Pet.tsx:23`)

These three flat `ConversationSnapshot` fields are still readable through the `legacy` chat projection on the
target host. Recommended staged plan (the two-step approach validated in the A1-03 field note): first migrate
everything to the `legacy` projection in one pass (fixing imports/inject per A1-25 at the same time), then — once
stable — migrate field-by-field off `legacy` to the new views/timeline/`useChat` read path. The `legacy`
projection is a staged-compatibility surface only; it must not become the primary data surface for an
alpha.2-only plugin, and the keyed `ChatSnapshot` (`order` + `nodes.get(id)`) is the eventual transcript shape.

**Must switch to the new read path immediately (not covered by any projection):**

- `running` (`Pet.tsx:19`) — a session lifecycle field, outside the chat legacy projection; it must go through the
  `useSession` lifecycle seat (which the code already does — no rename of this call is required, only the awareness
  that it stays on `useSession` while the chat-derived selectors move to `useChat`/views).

**Must change immediately (hard breaks — build/boot failures, not readable at runtime in any compat form):**

- The `@deepseek-ai/dsh-client-runtime/client` imports in `Pet.tsx:8` and `index.ts:6` (module no longer exists →
  typecheck/build fails; types repoint per A1-25: `ClientContext` → `@deepseek-ai/cordis` `Context`; snapshot types
  → their target owner, exact symbols deferred to target exports).
- `package.json:8` `client.inject` still listing `dsh-client-runtime` (phantom runtime dependency → assembly row
  stays pending / plugin never enters the boot graph). Remove it now.
- The slot-registration ordering seam in `index.ts:38-43` plus the missing renderer-owned Context augmentation —
  adopt `slots.inject(...)` wrapping and the `import type {} from '@deepseek-ai/dsh-client-ui-renderer/client'`
  declaration import as part of the same immediate pass, preserving slot name/id/order and effect lifetime.

## 3. Suggested execution order (when the code freeze lifts)

1. **Immediate pass (A1-25):** repoint `ClientContext` to `@deepseek-ai/cordis`; repoint/defer snapshot types to the
   owning package; remove `dsh-client-runtime` from `client.inject`; add owning-package type-only augmentation
   imports (locale, ui-conversation, ui-renderer); wrap the slot registration in `slots.inject`; run typecheck once
   with `skipLibCheck: false` to surface the full declaration chain.
2. **Stage 1 (A1-03 compat):** move the three chat-derived selectors (`partial`, `runningCalls`, `turnEnds`) onto the
   `views.get('chat')?.legacy` projection; keep `running` on `useSession`.
3. **Stage 2 (A1-03 target):** migrate field-by-field to `useChat` + keyed `ChatSnapshot` / timeline surfaces once
   stable; verify exact symbols against the target tag's exports before committing to them.

Report complete. Fixture untouched; no migrations or installs executed.
