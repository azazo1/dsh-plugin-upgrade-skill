# S3 · Snapshot Read-Surface Migration Assessment — `@demo/dsh-bench-pet`

**Task**: read-only migration assessment (skill mode: A/C hybrid — inspection and plan only, no writes to plugin source).
**Corridor**: `dsh-v0.1.1-rc.1 → dsh-v0.1.2-alpha.2`, built from the published card edges
`v0.1.1-rc.1` → (`DSH-0.1.1-R2-*) → `v0.1.2-alpha.1` (`DSH-0.1.2-A1-*) → `v0.1.2-alpha.2` (`DSH-0.1.2-A2-*)`,
plus the rc.2→alpha.2 interface ledger `api-migration-0.1.2-alpha.2.md` (API-10 et al.).
The rc.1→rc.2 edge (`DSH-0.1.1-R2-01..03`) touches only image attachment refs / `read_image` / DeepSeek Files API — no hit for this plugin.

**Fixture identity**: `@demo/dsh-bench-pet` v0.1.0, private, browser (Web Client) plugin only — no Host half.
Files: `package.json`, `cordis.patch.yml`, `src/client/index.ts`, `src/client/Pet.tsx`, `src/client/locales.ts`.
Baseline suite: **not collected** — the fixture is task material that "cannot be run" (fixture README); no build/install was attempted, preserving read-only discipline.

---

## 1. Breaking surfaces, locations, post-migration forms, and cards

### 1.1 `package.json` — `client.inject` lists the removed `dsh-client-runtime` · **DSH-0.1.2-A1-25** (required)

- **Location**: `package.json` → `client.inject: ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`.
- **How it breaks**: `@deepseek-ai/dsh-client-runtime` was deleted in alpha.1. Keeping it in the client inject list is a runtime phantom dependency: the assembly row stays **pending / never enters the boot graph**, "often without an explicit error" (card symptom; confirmed by the dsh-input-history field note — with the runtime package left in `inject` the row did not enter the graph, removing it restored it).
- **Post-migration form**: remove `dsh-client-runtime` from the inject list; keep only packages that actually provide services the plugin consumes (`dsh-client-ui-conversation` for the header-actions slot / conversation service, `dsh-client-locale` for `ctx.locale`). Add `@deepseek-ai/dsh-client-ui-chat` (and, per the API-10 dependency-ownership rule, every owner of a declaration the source directly imports: `@deepseek-ai/cordis`, `@deepseek-ai/dsh-client-ui-slots`) as **direct dev/peer dependencies** — a packed package's `devDependencies` are not transitively installed, and with `skipLibCheck: true` a missing owner silently turns selectors into implicit `any` (`DSH-0.1.2-A2-03` field note + API-10 "Type composition and dependency ownership").

### 1.2 `package.json` — manifest key is `client`, not `dsh.client` · **DSH-0.1.1-R1-02 / DSH-0.1.1-R1-03** (required; already wrong on rc.1)

- **Location**: `package.json` top-level `"client": { "platform": "web", "inject": [...] }`.
- **How it breaks**: hosts from the 0810 baseline onward read only `dsh.client`; client-modules scans packages by the `dsh.client` declaration alone. A `client` (or `dshClient`) field is ignored, so the client half is **silently absent from the browser plugin roster with no Node-half error**. This is a pre-existing defect of the fixture, not something alpha.2 introduces — but any migration must fix it or the pet never mounts.
- **Post-migration form**: `"dsh.client": { "platform": "web", "entry": "<client bundle entry>", "inject": ["dsh-client-ui-conversation", "dsh-client-locale"] }` — platform `web`, the client entry path the build produces, and the trimmed inject list from 1.1. Verify the **packed** manifest carries `dsh.client`, not just the source tree.

### 1.3 `src/client/index.ts` — `ClientContext` imported from the removed runtime package · **DSH-0.1.2-A1-25** + ledger **API-10** (required)

- **Location**: `index.ts:5` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`.
- **How it breaks**: typecheck/build TS2305/missing module; at runtime the plugin does not enter the boot graph (see 1.1).
- **Post-migration form** (exact mapping from A1-25 / API-10):

```ts
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// type-only augmentations, only from owning packages actually hit:
import type {} from '@deepseek-ai/dsh-client-locale/client'        // ctx.locale merge
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client' // SlotMap merge (header.actions)
```

  Client facets merged into `Context` come from their owning packages; do not rely on the old aggregation package or accidental hoisting. The existing type-only imports for locale and ui-conversation already follow this pattern and survive unchanged.

### 1.4 `src/client/Pet.tsx` — `ConversationSnapshot` imported from the removed runtime package · **DSH-0.1.2-A1-25** + **API-10** (required)

- **Location**: `Pet.tsx:6` — `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`; used by `isThinking(snapshot)` at `Pet.tsx:10`.
- **How it breaks**: same missing-module failure; the type no longer exists anywhere in 0.1.2.
- **Post-migration form**: the flat `ConversationSnapshot` is replaced by the keyed chat snapshot — `import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'`, where `ChatSnapshot.nodes` is a **keyed store** (`Map`-like `nodes.get(id)`) iterated in `snapshot.order` order, not `ConversationNode[]`:

```ts
function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap((id) => {
    const node = snapshot.nodes.get(id)
    return node ? [node] : []
  })
}
```

  To read an assistant step's final node, narrow by discriminant to `type === 'assistant-step'` and read `data.finalNode`; never mask old array fixtures with `as unknown as ChatSnapshot`.

### 1.5 `src/client/Pet.tsx` — flat snapshot field selectors (`partial`, `runningCalls`, `turnEnds`) · **DSH-0.1.2-A1-03** (required; staged path available) and **DSH-0.1.2-A1-27** (adjacent read-path card)

- **Location**: `Pet.tsx:19` `const thinking = useSession(isThinking)` (reads `snapshot.partial?.blocks`); `Pet.tsx:20` `s.runningCalls.length > 0`; `Pet.tsx:21` `s.turnEnds[s.turnEnds.length - 1]?.reason`.
- **How it breaks**: 0.1.2 no longer exposes per-session conversation-node snapshots on the old flat surface — the timeline becomes an internal projection of each view package (`DSH-0.1.2-A1-27` symptom: `session.getSnapshot().nodes` undefined/empty, console factory errors). The flat fields stop being populated on the primary seat.
- **Post-migration form — two-step**, exactly the pattern recorded in the A1-03 field note (dsh-ui-whale / dsh-ui-progress / dsh-input-history, 2026-08-28):
  1. **Step 1 (compatibility projection)**: the old flat fields (`nodes` / `partial` / `runningCalls` / `turnEnds`) are still readable through the `views.get('chat')?.legacy` projection — "migrate everything to legacy first", keeping the selectors' semantics identical while the imports/registration are fixed.
  2. **Step 2 (final read path)**: migrate field-by-field to the new surfaces — transcript-derived state from `useChat(chat => ...)` over the keyed `ChatSnapshot` (`order` + `nodes.get(id)`, assistant-step `data.finalNode`; API-10), and turn-timeline facts (settle frame from the last completed turn's end reason) from the view's timeline projection. For reading raw session content (user message text etc.) the third-party seam is the **SessionBinding durable event window**: `sessions.binding(id)` → `binding.eventSource.getSnapshot().entries` (`SessionEventLikeEntry[]` from `@deepseek-ai/dsh-api-session-controller/client`), per `DSH-0.1.2-A1-27` — the pet does not read message content today, so this card is a *conditional* reference for the step-2 rewrite, not a direct hit (see §3).
  
  `snapshot.legacy.nodes` must not become the permanent primary data surface for an alpha.2-only plugin (API-10).
  
  Caveat flagged per skill rules: the cards spell out `legacy` availability and the keyed-store target but not the exact new field names for `partial`/`runningCalls`/`turnEnds` equivalents on `ChatSnapshot` — pin those from the target tag's `packages/client/ui-chat/src/client/contract/snapshot.ts` types before writing step-2 code; do not invent the interface from this report.

### 1.6 `src/client/Pet.tsx` — lifecycle field `running` · **DSH-0.1.2-A1-03** field note (no code change needed, but a hard boundary)

- **Location**: `Pet.tsx:18` `const running = useSession(s => s.running)`.
- **Assessment**: lifecycle fields such as `running` are **not carried by the `legacy` compatibility projection** — they must keep going through the `useSession` seat, which is exactly what this line does. Keep it on `useSession`; do not move it onto the chat view or the legacy projection during either migration step. (Currently the value is only `void`-ed in the fixture stub, but the real pre-migration code it was trimmed from renders from it.)

### 1.7 `src/client/index.ts` — `useSession` transcript seat → `useChat` · **DSH-0.1.2-A1-25 / API-10** (required for step 2)

- **Location**: the `useSession` prop consumed via `PropsRuntime<'conversation.session.header.actions'>` in `Pet.tsx:17`.
- **Post-migration form**: `useSession(session => session?.nodes)` → `useChat(chat => ...)` (API-10 exact mapping). Lifecycle reads stay on `useSession` (1.6); transcript/animation-derived reads move to `useChat`. Ensure `@deepseek-ai/dsh-client-ui-chat/client` is a direct dependency so the selector's parameter is not implicit `any` (API-10; `DSH-0.1.2-A2-03` field note).

### 1.8 `cordis.patch.yml` + client registration id — three-way id equality · **DSH-0.1.2-A1-26** (required)

- **Location**: `cordis.patch.yml` row `{ id: bench-pet, name: '@demo/dsh-bench-pet' }`; the client bundle registration id (not shown in the fixture, injected by the build banner) must also be considered.
- **How it breaks**: 0.1.2's boot manifest keys entries/modules/plugin registrations by package name (`Entry name == package name`). Any id mismatch produces either the startup assertion `loaded without registering "<id>"` or the subtle variant — the pet silently disappears from the header, the boot graph lacks the plugin, and **no plugin-related error is logged**.
- **Post-migration form**: align all three ids to the bare package name `@demo/dsh-bench-pet` (scope included): (1) `__ModuleLoader__.load` id / tsdown banner `PLUGIN_ID`; (2) the assembly row `name` (the row's `id: bench-pet` short form must not survive as the registration key); (3) `package.json#name` (already correct). Note the fixture's patch yml is **composition**, not a source patch (API-08) — migrate it as a Loader row, not a hunk rebase.

### 1.9 Slot name `conversation.session.header.actions` · **DSH-0.1.2-A1-03** (verify; pending confirmation)

- **Location**: `index.ts` slot registration and the `PropsRuntime<'conversation.session.header.actions'>` type parameter in `Pet.tsx:8`.
- **Assessment**: A1-03 splits session view internals extensively, and its recipe requires verifying the actual 0.1.2 page shape (slot names, panel ids) "not from 0.1.1 memory" (same requirement repeated by A1-28). No card records a rename of this specific slot, so this is a **verification item**, not a known break: confirm the entry still exists in `@deepseek-ai/dsh-client-ui-conversation/client`'s SlotMap at `dsh-v0.1.2-alpha.2` before assuming it survived. The nested `ctx.inject(['slots', 'conversation'], ...)` ordering edge (register only after the slot is declared) is sound under strict injection (`DSH-0.1.1-R1-04`: every consumed service is declared in `inject` — satisfied by `['slots', 'conversation', 'locale']`).

---

## 2. Compatibility projection vs immediate switch (requirement 4)

| Read/field | Old location | Strategy on 0.1.2-alpha.2 | Why |
|---|---|---|---|
| `partial` (thinking detection) | `useSession` flat snapshot | **May run first through the compatibility projection** (`views.get('chat')?.legacy`), then move to `useChat` keyed nodes | A1-03 field note: flat fields still readable via `legacy`; two-step migration is the verified pattern |
| `runningCalls` (tool-in-flight) | flat snapshot | **Compatibility projection first**, then `useChat` | same |
| `turnEnds` (settle frame) | flat snapshot | **Compatibility projection first**, then the view timeline / durable event window (A1-27) | same |
| `nodes` (transcript) | flat snapshot array | **Compatibility projection first**, then `ChatSnapshot.order` + `nodes.get(id)` | API-10; `legacy` is staged compatibility only, never the primary surface |
| `running` (lifecycle) | `useSession(s => s.running)` | **Must stay on the new `useSession` seat immediately** — it is *not* in the legacy projection | A1-03 field note: lifecycle fields must go through the `useSession` seat |
| `dsh-client-runtime` imports (`ClientContext`, `ConversationSnapshot`) | type imports | **Must switch immediately** — no projection exists; the package is deleted; build fails and/or the assembly row never enters the boot graph | DSH-0.1.2-A1-25 |
| `dsh-client-runtime` in the client inject list | `client.inject` | **Must switch immediately** — phantom dependency leaves the row pending | DSH-0.1.2-A1-25 |
| Manifest key `client` → `dsh.client` (+ entry path) | `package.json` | **Must switch immediately** — otherwise the client half is never scanned into the roster at all | DSH-0.1.1-R1-02/R1-03 |
| Registration id / row name alignment | bundle banner + `cordis.patch.yml` | **Must switch immediately** — silent roster omission, no error | DSH-0.1.2-A1-26 |

---

## 3. Summary table (per the API-10 report template)

| Hit location | Old interface | Typical symptom | Target interface | Change | Verification status |
|---|---|---|---|---|---|
| `package.json` inject list | `dsh-client-runtime` in `client.inject` | row pending / absent from boot graph, no error | trimmed inject: ui-conversation + locale only; direct deps for every consumed declaration owner | required (A1-25, A2-03) | card + field-note evidence; not executed (read-only task) |
| `package.json` manifest | top-level `client` key | client half silently not scanned | `dsh.client` with platform/entry/inject | required (R1-02/R1-03) | card evidence; not executed |
| `index.ts:5` | `ClientContext` from `dsh-client-runtime/client` | TS2305 / boot-graph miss | `Context as ClientContext` from `@deepseek-ai/cordis` + owning-package augmentations | required (A1-25, API-10) | card evidence; not executed |
| `Pet.tsx:6,10` | `ConversationSnapshot` from runtime pkg | TS2305 / missing type | `ChatSnapshot` from `dsh-client-ui-chat/client`; keyed `nodes.get` + `order` | required (A1-25, API-10) | card evidence; not executed |
| `Pet.tsx:19-21` | flat `partial`/`runningCalls`/`turnEnds` | fields empty/undefined; factory errors | staged: `views.get('chat')?.legacy` first → `useChat`/timeline | required, staged (A1-03; A1-27 adjacent) | card + field-note evidence; not executed |
| `Pet.tsx:18` | `useSession(s => s.running)` | (would break if moved to legacy) | keep on `useSession` seat | boundary, no change (A1-03 note) | card evidence |
| `index.ts`/`Pet.tsx:8` slot | `conversation.session.header.actions` | possible silent slot disappearance | verify SlotMap at target tag; rename if moved | verify (A1-03) | **pending confirmation** |
| `cordis.patch.yml` + bundle id | `id: bench-pet` short id | `loaded without registering` or silent absence | all three ids = `@demo/dsh-bench-pet` | required (A1-26; API-08 classification) | card evidence; not executed |

## 4. Skipped (non-hits, with evidence)

- **DSH-0.1.1-R2-01..03** (rc.1→rc.2): image attachments / `read_image` / DeepSeek Files API — the pet touches none of these surfaces.
- **DSH-0.1.2-A1-01 / A1-30, A2-02, A2-06** (APIProxy→Remote, `connection.api`, `RemoteError`, `$host`): no `ctx.remote`/`connection` usage in the fixture.
- **DSH-0.1.2-A1-27 direct hit**: the pet reads animation state, not message content; `session.getSnapshot().nodes` is never called. Referenced only as the step-2 content-read seam if the settle-frame logic later needs turn-end reasons from raw events.
- **DSH-0.1.2-A1-28** (composer DOM), **A1-29** (MarkdownText labels), **A1-32** (uiWorkspace navigation), **A2-08** (sessionProjections inject — the pet's patch row inserts only itself; it mounts no tool packages and assumes the shipped bundle provides the projection service), **A2-05** (plugin inventory schema), **A2-10** (settings namespace), **A1-06** (PTC rename), **A1-08/A1-19** (auth tokens/acceptance — relevant only to the e2e harness, not plugin source).
- **DSH-0.1.2-A2-04**: environment note — verify the host boots on Node ≥ 24.12 (or 22 LTS); no plugin action.
- **Locale surface** (`ctx.locale.register`, `LocaleNamespaceMap` augmentation, zh/en pairing): unaffected by any card in the corridor; keep as-is.

## 5. Pending / residual risk

- Exact post-alpha.2 field names for the `partial`/`runningCalls`/`turnEnds` equivalents on `ChatSnapshot`/timeline are not spelled out in the cards — pin from `dsh-v0.1.2-alpha.2` `packages/client/ui-chat/src/client/contract/snapshot.ts` before step 2 (skill rule: the target tag wins over any card).
- Slot `conversation.session.header.actions` survival unverified (§1.9).
- No build, cold boot, or browser mount was run — this is a static, read-only assessment; "typecheck passed / Loader mount passed / real behavior passed" are all **not** established.
- `skipLibCheck: false` diagnostic typecheck recommended once before merging, to surface missing declaration owners (API-10).

## 6. Rollback / recommendations

- The fixture was not modified (read-only discipline; benchmark repository untouched). Rollback baseline: fixture files as read, listed in §"Fixture identity".
- Recommended implementation order when migration is authorized: (1) manifest + inject-list + id alignment (1.1/1.2/1.8) — unblocks mounting; (2) import migration (1.3/1.4); (3) selectors to `legacy` projection, keep `running` on `useSession` (1.5/1.6); (4) field-by-field move to `useChat`/timeline; validate per the skill ladder: typecheck (`skipLibCheck: false` once) → pack smoke → isolated-profile cold boot with `--dump-config` (no pending rows) → real Web chain (token→Cookie, boot entry, advertised resource, registration/mount, DOM marker `[data-frame]`, page errors) → one message → tool-call → response round to observe the working/thinking/settle frames.
