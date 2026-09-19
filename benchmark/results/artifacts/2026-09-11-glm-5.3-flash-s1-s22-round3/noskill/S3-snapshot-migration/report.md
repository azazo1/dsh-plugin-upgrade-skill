# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (0.1.1-rc.1 → 0.1.2-alpha.2)

Read-only assessment. No code was modified; the fixture at `environment/fixture/` was only inspected. Evidence cited per file:line from the fixture, and per upgrade card from the plugin-upgrade skill reference set (`v0.1.2-alpha.1.md`, `v0.1.2-alpha.2.md`, `rollup-0.1.2.md`, `api-migration-0.1.2-alpha.2.md`).

## 0. Plugin summary

- Browser (Web Client) pixel pet plugin: `@demo/dsh-bench-pet`, registers dictionaries (`pet` namespace) and a resident `Pet` component into slot `conversation.session.header.actions`.
- Snapshot-coupled animation: pose follows the live conversation snapshot — reasoning in progress ("thinking"), tool calls in flight ("working"), settled turn.

---

## 1 / 2 / 3. Breaking surfaces, post-migration form, and card mapping

### Break 1 · Import of the removed `dsh-client-runtime` package

- **Evidence**: `src/client/index.ts:6` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`; `src/client/Pet.tsx:8` — `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`.
- **How it breaks**: `@deepseek-ai/dsh-client-runtime` was deleted in alpha.1 (rollup R-05 removed-package list: "rc.2 → alpha.1 removes 5 — … `dsh-client-runtime` …"). Card **DSH-0.1.2-A1-25** ("`dsh-client-runtime` package removed, client symbols migrated by domain"): typecheck fails with missing module/exports; at runtime the plugin can fall out of the boot graph or stay pending without an explicit error.
- **Post-migration form** (card DSH-0.1.2-A1-25 mapping table, confirmed by API-10):
  - `ClientContext` → `import type { Context as ClientContext } from '@deepseek-ai/cordis'` (Cordis `Context`, plus type-only augmentations from owning packages).
  - `ConversationSnapshot` (flat transcript snapshot) → `ChatSnapshot` from `@deepseek-ai/dsh-client-ui-chat/client`; the node type `ConversationNode` lives at `@deepseek-ai/dsh-client-ui-conversation/client`.
  - Both consuming packages (`@deepseek-ai/dsh-client-ui-chat`, `@deepseek-ai/dsh-client-ui-conversation`) must become direct type/dev/peer dependencies; a published package's devDependencies are not transitively installed (API-10 "Type composition and dependency ownership"; card **DSH-0.1.2-A2-03** field note on ui-chat `.d.ts` referencing `dsh-client-store` and friends — run one `tsc --skipLibCheck false` pass to locate the missing declaration chain).

### Break 2 · `dsh-client-runtime` declared in `dsh.client.inject`

- **Evidence**: `package.json:8` — `"inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`.
- **How it breaks**: card **DSH-0.1.2-A1-25** migration recipe: "Remove `@deepseek-ai/dsh-client-runtime` from `dsh.client.inject` — after the dismantling it is a runtime phantom dependency, and keeping it leaves the assembly row pending / out of the boot graph." Field note (dsh-input-history): "with the runtime package left in `inject` the row did not enter the graph, and removing it restored it."
- **Post-migration form**: `"inject": ["dsh-client-ui-conversation", "dsh-client-locale"]` — only packages that actually provide services. `@deepseek-ai/dsh-client-ui-chat` is added as a package dependency, not an inject row, unless it provides an injected client service at the target tag (verify against alpha.2 exports).
- **Verification** (per card): typecheck shows no leftover `dsh-client-runtime` imports; `dsh --profile <p> --dump-config` shows no pending rows; cold boot contains this plugin in the boot graph.

### Break 3 · Flat `ConversationSnapshot` field reads (`partial`, `runningCalls`, `turnEnds`, `running`)

- **Evidence**: `src/client/Pet.tsx`:
  - lines 13–15: `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')`;
  - line 19: `useSession(s => s.running)`;
  - line 21: `useSession(s => s.runningCalls.length > 0)`;
  - line 23: `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)`;
  - line 10: props typed via `PropsRuntime<'conversation.session.header.actions'>`.
- **How it breaks**: the flat snapshot consumption surface was split in alpha.1 — card **DSH-0.1.2-A1-03** ("Session view internals split up extensively") field note: "the old flat `ConversationSnapshot` fields (nodes/partial/runningCalls/turnEnds) are all still readable through the `views.get('chat')?.legacy` projection … lifecycle fields (e.g. running) are not in the projection and must go through the `useSession` seat instead." On alpha.2 the primary transcript surface is the keyed `ChatSnapshot` (`nodes` is a keyed store, not `ConversationNode[]` — API-10 / rollup R-11 row: "`useSession` reading `ConversationSnapshot.nodes[]` → on alpha.2 use `useChat`, keeping order via `ChatSnapshot.order` with `nodes.get(id)`").
- **Post-migration form** (alpha.2 primary read path, per the API-10 minimal shape):

```ts
import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'

// per-node projection: iterate order, resolve each id in the keyed store
function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap((id) => {
    const node = snapshot.nodes.get(id)
    return node ? [node] : []
  })
}
// selector hook: ctx.useChat((chat) => ...) replaces the useSession transcript selectors;
// narrow per node by discriminant (e.g. type === 'assistant-step') before reading reasoning blocks.
```

  - `runningCalls.length > 0` and `turnEnds[last].reason`: migrate to the new chat views/timeline surfaces per the A1-03 field note two-step recipe ("migrate everything to legacy first, then migrate field-by-field to views/timeline once stable"); do not treat `snapshot.legacy.nodes` as the new primary data surface for alpha.2-only code.
  - `running` (line 19): **no legacy projection exists** — it must read from the lifecycle seat (`useSession`), which survives on alpha.2; keep the selector, re-type the context.
- **Cards**: **DSH-0.1.2-A1-03** (field note on the legacy projection and the `useSession` lifecycle seat), **DSH-0.1.2-A1-25** (symbol/package mapping), corroborated by rollup **R-11** (type-surface export drift ledger) and the API-10 ledger.

---

## 4. Compatibility projection vs. immediate new read path

Per the DSH-0.1.2-A1-03 field note (dsh-ui-whale / dsh-ui-progress / dsh-input-history migration, 2026-08-28):

- **Can run first through the compatibility projection** (`views.get('chat')?.legacy`): the data-shaped flat fields — `partial`, `runningCalls`, `turnEnds` (and `nodes`, if read; this Pet does not read `nodes` directly). These keep their old semantics under the projection, so the plugin can move to the new import/type surface first and keep animating while the field-by-field migration to views/timeline proceeds.
- **Must switch immediately — no projection available**:
  1. **`running`** (Pet.tsx:19) — "lifecycle fields (e.g. running) are not in the projection and must go through the `useSession` seat instead." There is no legacy mirror; the lifecycle seat is the only path.
  2. **Every import and the inject row touching `dsh-client-runtime`** (index.ts:6, Pet.tsx:8, package.json:8) — the package does not exist at all on alpha.2, so nothing loads until DSH-0.1.2-A1-25 is applied. The projection is a runtime read surface; it does not shim a missing module.
  3. Any direct node iteration must use `ChatSnapshot.order` + `nodes.get(id)` from day one — API-10: "alpha.2-only code must not treat `legacy.nodes` as the primary data surface."

---

## Negative findings (checked, no card hit, no break expected)

- **Slot registration** `conversation.session.header.actions` (index.ts:40) and the `declare module '@deepseek-ai/dsh-client-ui-slots'` `LocaleNamespaceMap` augmentation (index.ts:14–19): no card in the 0.1.1→0.1.2 corridor renames this slot or the `PropsRuntime`/`PropsLocale` props. No action.
- **Dictionary registration** `ctx.locale.register(NS, { zh, en })` (index.ts:36) and `locales.ts`: unchanged; rollup **R-13** only affects plugins that locate host UI by displayed text — this plugin anchors by slot id, so it is unaffected.
- **Ordering inject** `ctx.inject(['slots', 'conversation'], ...)` (index.ts:38): no card removes the `conversation` client service; keep it (the header.actions slot is declared by ui-conversation's apply).
- **Remote/error surfaces**: the plugin makes no `ctx.remote` calls, so **DSH-0.1.2-A2-02** (RemoteError / namespaced codes), **DSH-0.1.2-A2-06** (`$host` facts), **DSH-0.1.2-A2-08** (`sessionProjections` peer), **DSH-0.1.2-A2-10** (`settingsNamespace`) do not hit. **DSH-0.1.2-A2-01** (ignorable) does not hit — the plugin persists no custom SessionEvents.

## Recommended sequence

1. Apply DSH-0.1.2-A1-25: rewrite both imports to Cordis `Context` + `ChatSnapshot` (ui-chat) and drop `dsh-client-runtime` from the `package.json` inject; add `@deepseek-ai/dsh-client-ui-chat` as a direct dependency (DSH-0.1.2-A2-03 field note: verify with one `skipLibCheck: false` pass).
2. Keep the data-field selectors reading through the `views.get('chat')?.legacy` projection; keep `running` on the `useSession` lifecycle seat.
3. Field-by-field, migrate `partial` / `runningCalls` / `turnEnds` to the alpha.2 chat views/timeline and `useChat` selectors (`order` + `nodes.get(id)`), then delete the legacy reads.
4. Verify per the cards: typecheck with real types (no `any` masking), `--dump-config` with no pending rows, one cold boot with a full message → tool-call → reply round watching the pet frame transitions.
