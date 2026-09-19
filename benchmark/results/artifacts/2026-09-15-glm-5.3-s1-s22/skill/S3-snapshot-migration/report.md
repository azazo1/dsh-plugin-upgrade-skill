# S3 · Snapshot Read-Surface Migration Assessment (Read-Only)

**Plugin**: `@demo/dsh-bench-pet` 0.1.0 (fixture `bench-pet`, browser pixel-pet in the session header)
**Corridor**: plugin written in the `dsh-v0.1.1-rc.1` era → target host `dsh-v0.1.2-alpha.2`
Corridor edges read in full: rc.1→rc.2 (`DSH-0.1.1-R2-*`), rc.2→alpha.1 (`DSH-0.1.2-A1-*`), alpha.1→alpha.2 (`DSH-0.1.2-A2-*`), plus the exact interface ledger `api-migration-0.1.2-alpha.2.md` (API-01…API-10, CFG-01) and the rc.8→rc.1 cards (`DSH-0.1.1-R1-*`) for baseline-era context.
**Mode**: A · inspect (per `plugin-upgrade` skill). No source, manifest, dependency, or composition file was modified; the fixture directory was only read. No install, no build, no package-script run, no network access.

---

## 1. What this plugin is, and which seam it lives on

- Pure **Web Client plugin** (browser face): `src/client/index.ts` registers the `Pet` component into the `conversation.session.header.actions` slot declared by `dsh-client-ui-conversation`, and registers a `pet` locale namespace via `ctx.locale`.
- The Pet's animation is driven entirely by the **conversation snapshot read surface**: `useSession` selectors over the flat `ConversationSnapshot` fields `running`, `partial.blocks`, `runningCalls`, `turnEnds`.
- That read surface is exactly what the 0.1.2 corridor dismantles: `dsh-client-runtime` is deleted (alpha.1) and chat state moves to the keyed `ChatSnapshot` + `useChat` store (alpha.2, API-10). So every data input of this plugin is a hit; the slot/locale registration seams are stable in this corridor.

Touchpoint classes hit (pre-flight numbering): **#3 services/Remote** (client runtime/symbol ownership, `dsh.client.inject` roster), **#5 UI/commands/tools** (slot component, snapshot selectors). Non-hits with evidence in §4.

---

## 2. Breaking surfaces, target forms, and card citations

### 2.1 `src/client/Pet.tsx:6` — import of `ConversationSnapshot` from the removed runtime package

- **Current**: `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`
- **How it breaks**: `@deepseek-ai/dsh-client-runtime` was deleted from `packages/client` in alpha.1; build/typecheck reports a nonexistent module, and at runtime the plugin does not enter the client boot graph (its assembly row stays pending, often with no explicit error).
- **Target form** (alpha.2): the type is `ChatSnapshot` from the owning package:
  ```ts
  import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'
  ```
- **Cards**: **DSH-0.1.2-A1-25** (`dsh-client-runtime` removed, symbols migrated by domain) + **API-10** in `api-migration-0.1.2-alpha.2.md` (exact mapping table; alpha.2 `ChatSnapshot`/`ChatNodeStore` source pinned to `packages/client/ui-chat/src/client/contract/snapshot.ts` at tag `dsh-v0.1.2-alpha.2`).

### 2.2 `src/client/Pet.tsx:10-12` — `isThinking` reads the flat `snapshot.partial?.blocks`

- **Current**: `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')` over the flat `ConversationSnapshot`.
- **How it breaks**: `ConversationSnapshot.nodes` is gone; on alpha.2 `ChatSnapshot.nodes` is a **keyed store** (`Map`-like, `nodes.get(id)`) plus an `order: id[]` array — `Array.prototype` access patterns and `partial.blocks` array scans no longer typecheck, and silently degrade to `any` under `skipLibCheck: true`.
- **Target form** (alpha.2 minimal read shape, per API-10):
  ```ts
  import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'

  function orderedNodes(snapshot: ChatSnapshot) {
    return snapshot.order.flatMap((id) => {
      const node = snapshot.nodes.get(id)
      return node ? [node] : []
    })
  }
  // then narrow nodes by discriminant (e.g. type === 'assistant-step' → data.finalNode)
  // and read reasoning presence from the in-flight assistant node's blocks
  ```
  The exact field coordinates of the *partial/streaming* surface on `ChatSnapshot` are **not spelled out in the card ledger** — pin them from the target tag's `packages/client/ui-chat/src/client/contract/snapshot.ts` types before implementing; do not invent them (card-file rule 3).
- **Cards**: **DSH-0.1.2-A1-25**, **API-10** (keyed chat snapshots), with **DSH-0.1.2-A1-03** (session view internals split — the field note records that the old flat fields are still readable through the `views.get('chat')?.legacy` projection).

### 2.3 `src/client/Pet.tsx:21` — transcript read via `useSession(isThinking)` / `useSession(s => s.runningCalls.length > 0)`

- **Current**: all chat-transcript selectors go through the `useSession` hook (flat snapshot).
- **How it breaks**: API-10 maps `useSession(session => session?.nodes)` → `useChat(chat => ...)`; on alpha.2 transcript reads belong to `ctx.useChat` (Context augmentation from `@deepseek-ai/dsh-client-ui-chat/client`). Under `skipLibCheck: true` the missing declaration chain turns the selectors into implicit `any` — a silent migration failure.
- **Target form**:
  ```ts
  // type-only augmentations (each owning package becomes a direct dep)
  import type {} from '@deepseek-ai/dsh-client-ui-chat/client'
  import type {} from '@deepseek-ai/dsh-api-session-controller/client'

  const toolRunning = ctx.useChat(chat => chat ? /* runningCalls-derived */ false : false)
  ```
  (component props keep receiving it via the slot; only the data hook changes.)
- **Cards**: **API-10**, **DSH-0.1.2-A1-25**; precision requirements in **DSH-0.1.2-A2-03** field note (temporarily run `tsc --skipLibCheck false` to find missing declaration owners, then declare those packages as direct dev/peer dependencies).

### 2.4 `src/client/Pet.tsx:23` — `s.turnEnds[s.turnEnds.length - 1]?.reason` (turn timeline read)

- **How it breaks**: `turnEnds` is a flat `ConversationSnapshot` field; same dismantling as above.
- **Target form**: staged — first `views.get('chat')?.legacy` (see §3), then the timeline/views surface once stable (the A1-03 field note prescribes exactly this two-step: "migrate everything to legacy first, then migrate field-by-field to views/timeline"). The new timeline API coordinates are **not in the card ledger**; pin from the target tag before switching (mark "pending review" rather than guessing).
- **Cards**: **DSH-0.1.2-A1-03** (field note: dsh-ui-whale/dsh-ui-progress/dsh-input-history migrated this exact surface), **API-10**.

### 2.5 `src/client/Pet.tsx:20` — `useSession(s => s.running)` (lifecycle field)

- **How it behaves**: `running` is a **lifecycle field, not part of the chat transcript**: per DSH-0.1.2-A1-03's field note it is *not* included in the `legacy` projection and "must go through the `useSession` seat instead". This selector is therefore already on the correct seat — keep it on `useSession`; do **not** move it to `useChat`.
- **Cards**: **DSH-0.1.2-A1-03** (field note), **API-10** (mapping table).
- **Caveat**: the fixture only `void`s the value; in a real migration this is the one selector that survives unchanged.

### 2.6 `package.json:6-9` — `client.inject` lists the removed `dsh-client-runtime`

- **Current**: `"client": { "platform": "web", "inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"] }`
- **How it breaks**: (a) `dsh-client-runtime` no longer exists, so the plugin never enters the browser plugin roster / its client row stays pending (DSH-0.1.2-A1-25 symptom); (b) the manifest key itself: since the 0810 baseline the scan key is **`dsh.client**, not `client` (DSH-0.1.1-R1-02/R1-03 lineage; A1-25's recipe also says to clean up `package.json`, and API-10's type-composition rule 1 says "list only the client services the runtime actually needs injected by the host in `dsh.client.inject`"). As written, the fixture's bare `client` key would not even be scanned on a strict rc.1+ host — treat normalizing the key as part of this migration.
- **Target form**:
  ```json
  "dsh.client": {
    "platform": "web",
    "inject": ["dsh-client-ui-conversation", "dsh-client-ui-chat", "dsh-client-locale"]
  }
  ```
  (`dsh-client-ui-chat` joins because the plugin now consumes `useChat`/`ChatSnapshot`.)
- **Cards**: **DSH-0.1.2-A1-25**, **API-10** (type composition & dependency ownership), **DSH-0.1.1-R1-02**, **DSH-0.1.1-R1-03**.

### 2.7 `cordis.patch.yml` — composition row `id: bench-pet` vs `name: '@demo/dsh-bench-pet'`

- **How it breaks**: alpha.1 tightens the client-modules scan contract — the **registration id must equal the `package.json` `name`** (card title: "client-modules scan contract: registration id must equal the package.json name"). The fixture's insert row id `bench-pet` ≠ package name `@demo/dsh-bench-pet`, so the row does not resolve to the package on the alpha host.
- **Target form**: make the composition row id identical to the package name (`id: '@demo/dsh-bench-pet'`), keeping the `name`-referring source line as-is otherwise.
- **Cards**: **DSH-0.1.2-A1-26**.
- **Honesty note**: the body text of DSH-0.1.2-A1-26 is truncated in the local card file `references/v0.1.2-alpha.1.md` (the file ends mid-card A1-25 at line 434; A1-26…A1-32 exist only as TOC titles). The mapping above follows the card title and the corroborating client-modules contract in DSH-0.1.1-R1-03; **verify the exact id-matching rule against the alpha.2 tag's client-modules scanner before editing** and treat this item as "pending tag confirmation".

### 2.8 `src/client/index.ts:2,8,11` — `ClientContext` and type-only augmentations from the runtime package

- **Current**: `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'` (plus `type {}` merges from `dsh-client-locale/client` and `dsh-client-ui-conversation/client`).
- **Target form** (A1-25 verified mapping):
  ```ts
  import type { Context as ClientContext } from '@deepseek-ai/cordis'
  import type {} from '@deepseek-ai/dsh-client-locale/client'
  import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
  import type {} from '@deepseek-ai/dsh-client-ui-chat/client' // new: useChat/ChatSnapshot merge
  ```
  Each owning package whose declarations the source consumes must become a **direct dev/peer dependency** of the plugin (published packages' `devDependencies` are not transitive).
- **Cards**: **DSH-0.1.2-A1-25**, **API-10** ("Type composition and dependency ownership"), **DSH-0.1.2-A2-03**.

### 2.9 Non-breaks in the same files (checked, no action)

- Slot registration `conversation.session.header.actions` via `ctx.slots.register` and `PropsRuntime`/`PropsLocale` from `dsh-client-ui-slots`: **no card in the rc.1→alpha.2 corridor moves this slot or the ui-slots prop types** (the `conversation` slot restructure lands later, in 0.1.5-alpha.2 — outside this corridor).
- `inject = ['slots', 'conversation', 'locale']` + `ctx.inject(['slots','conversation'], ...)` and `ctx.locale.register(NS, {zh, en})`: satisfies cordis strict injection (DSH-0.1.1-R1-04/R1-05); the locale registration surface is unchanged in the corridor; the nested `ctx.inject` ordering edge remains valid.
- Locale dictionary shape (`zh`/`en` parity, `LocaleNamespaceMap` merge): unchanged in the corridor.

---

## 3. Compatibility projection vs. immediate new read path (requirement 4)

Per **DSH-0.1.2-A1-03**'s field note (dsh-ui-whale v0.3.5 / dsh-ui-progress v0.9.4 / dsh-input-history v0.1.4, real npm-link migration on this exact corridor) and **API-10**:

| Snapshot field the Pet reads | Can run first via compatibility projection? | Path |
|---|---|---|
| `partial` (→ `isThinking`) | **Yes** | `views.get('chat')?.legacy` still exposes the old flat `nodes/partial/runningCalls/turnEnds` fields during migration |
| `runningCalls` (→ `toolRunning`) | **Yes** | same `legacy` projection |
| `turnEnds` (→ `lastTurnEnd`) | **Yes** | same `legacy` projection; switch to the views/timeline surface field-by-field once stable |
| `running` (→ `running`) | **No — already on the required seat** | lifecycle fields are *not* in the `legacy` projection; they must go through the `useSession` seat, which this code already does. Keep it there; moving it into `useChat` would be a regression |
| Anything read as `ChatSnapshot` (`order` + `nodes.get(id)`) | n/a — target | `snapshot.legacy.nodes` is only for staged dual-host compatibility; an alpha.2-only plugin must make the keyed store the primary surface |

**Recommended staging** (the cards' prescribed two-step): (1) swap imports/manifest/inject roster and move all flat reads to `legacy` — plugin compiles and runs on alpha.2; (2) migrate selectors one field at a time to `useChat` + keyed reads / timeline, each with a behavior test (frame `idle`/`thinking`/`working` observable in `data-frame`). `snapshot.legacy.*` must not survive as the final state.

---

## 4. Skipped (non-hit cards, with evidence)

- **DSH-0.1.1-R2-01/02/03** (image refs, `read_image` text, Files API): plugin touches no image surfaces.
- **DSH-0.1.2-A1-01 / API-01, A2-02 / API-02** (APIProxy→Remote, `RemoteError`): the plugin makes **no** `connection.api`/`ctx.remote` calls; its only host interaction is snapshot reads + slot/locale services.
- **DSH-0.1.2-A1-02 / A2-01 / API-05** (`SessionEvent.ignorable`): the plugin persists no session events.
- **DSH-0.1.2-A1-08, A1-19** (bootstrap tokens, boot-manifest acceptance): no custom routes/channels; relevant only as *verification methodology* (§5).
- **DSH-0.1.2-A1-20** (`userQuestions` waterfall): no answerer registered.
- **DSH-0.1.2-A1-22** (`isTokenDelta`): no TPS logic.
- **DSH-0.1.2-A1-24** (pi-ai second instance): no LLM-provider dependency.
- **DSH-0.1.2-A1-27** (SessionBinding durable event window): host-side content-read seam; the plugin reads the client snapshot surface, which API-10 governs instead.
- **DSH-0.1.2-A1-28/29** (composer contenteditable, `MarkdownText`): no composer/primitive rendering.
- **DSH-0.1.2-A1-30** (`ctx.connection.api` removed): not used.
- **DSH-0.1.2-A1-31/32** (subagent descriptor, `ctx.uiWorkspace`): no workspace navigation.
- **DSH-0.1.2-A2-04/05/06/08/10, API-03/04/06/07/08/09, CFG-01**: Node 24 loader workaround, plugin inventory, `$host` facts, `sessionProjections` peer, settings helper, headless contract, subpath exports, composition-vs-patch classification, inventory schema, PTC rename — none of these surfaces appear in the fixture (the one composition file is a plain insert row, correctly classified as composition, not a source patch, per API-08).

## 5. Validation plan (when the migration is authorized — Mode C)

1. **Static**: `tsc` once with `skipLibCheck: false` to surface the missing declaration chain (`dsh-client-ui-chat`, `dsh-client-store`, ui primitives…); add every consumed declaration owner as a direct dev/peer dependency; then restore the repo's typecheck policy. No new implicit `any` may remain (DSH-0.1.2-A2-03 field note, API-10).
2. **Roster/composition**: `dsh --profile <p> --dump-config` shows the row resolving under the package-name id, no `pending (waiting for service: …)` lines; lockfile scanned for the old cohort and `dsh-client-runtime` (zero hits expected).
3. **Runtime/behavior** (per DSH-0.1.2-A1-19 + skill validation layer 4): isolated profile, `dsh web --no-open`; redeem the token URL → Cookie; read `window.__DSH_BOOT__.entries`, find the entry by `package.json#name`, fetch the *advertised* URL; prove `__ModuleLoader__.load` registration and the Pet's DOM mount; then exercise one turn and assert the `data-frame` transitions idle→thinking→working→idle (this is the plugin's core path, equivalent to the message→tool→response flow).
4. Tests must build the **keyed** store shape (`order` + `nodes.get`), covering a missing id and the assistant final node — not masked old array fixtures (API-10 verification).

## 6. Pending / residual risk

- **Card-body gap**: `references/v0.1.2-alpha.1.md` is truncated mid-A1-25; the bodies of A1-26…A1-32 are unavailable locally. The A1-26 id-equality mapping in §2.7 rests on the card title + R1-03 corroboration and needs tag confirmation. (Skill repository gap, not fixable from here — the skill must not be modified.)
- **Exact alpha.2 field coordinates** for the streaming/partial surface and the turn timeline on `ChatSnapshot` are not in the ledger; per card rules, pin from `dsh-v0.1.2-alpha.2` types before implementing — marked "pending review" items, not guesses.
- `ConversationSnapshot`'s own fate (removed vs. type-only legacy) should be confirmed at the target tag; the ledger only guarantees the `legacy` *projection* on the view, not the exported type name.
- Untested: everything — this is a read-only assessment; no build, mount, or behavior evidence was collected (fixture is task material that "cannot be run" per its README).

## 7. Rollback

Not applicable — Mode A read-only; no files were written outside this report, and the fixture is untouched.

## 8. Recommendations

- Sequence: manifest + inject roster + import swap + `legacy` projection first (one compilable commit), then field-by-field `useChat` migration; keep the plugin's own version bump (SemVer, e.g. 0.2.0) separate from the host-version migration, and verify the packed tarball carries the plugin version, not `0.1.2-alpha.2`.
- The `Pet` component's dead `void running / void lastTurnEnd as CSSProperties` lines and the unused `useRef` frame indirection should be cleaned up in the same migration PR (behavior-neutral).
- After the corridor lands, watch the later 0.1.5-alpha.2 `conversation`-slot move under root-scoped `main` — this plugin will be hit again by that edge when the host advances past 0.1.2.
