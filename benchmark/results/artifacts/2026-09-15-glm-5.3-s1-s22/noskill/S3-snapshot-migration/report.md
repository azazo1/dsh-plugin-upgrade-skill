# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (0.1.1-rc.1 → 0.1.2-alpha.2)

Read-only assessment. No fixture, skill, verifier, or reference file was modified; the only write is this report.

**Scope**: `@demo/dsh-bench-pet` — a Web Client (browser) plugin that renders a pixel pet in the
`conversation.session.header.actions` slot and drives its animation from the flat conversation
snapshot (`running`, `partial`, `runningCalls`, `turnEnds`). Corridor: 0.1.1-rc.1 → 0.1.2-alpha.2
(crossing the DSH-0.1.2-A1-01…A1-32 and DSH-0.1.2-A2-01…A2-10 card sets).

**Authorities used**: `skills/plugin-upgrade/references/v0.1.2-alpha.1.md` (card set DSH-0.1.2-A1),
`skills/plugin-upgrade/references/v0.1.2-alpha.2.md` (card set DSH-0.1.2-A2), and
`skills/plugin-upgrade/references/api-migration-0.1.2-alpha.2.md` (practice ledger, esp. API-10).

## Verdict in one line

The plugin is a textbook hit of the **Web Client runtime unbundling + snapshot read-surface migration**:
every transcript-facing read goes through the removed `@deepseek-ai/dsh-client-runtime` aggregation and the
flat `ConversationSnapshot`, both gone on 0.1.2-alpha.2. The registration/slot/locale plumbing
(`ctx.slots.register`, `ctx.locale.register`, `inject: ['slots', 'conversation', 'locale']`) survives
unchanged. Migration is required before the plugin will even typecheck, let alone enter the boot graph.

## Hit table

| # | Hit location (fixture, read-only) | Old surface | Symptom on 0.1.2-alpha.2 | Target surface | Card | Required / staged |
|---|---|---|---|---|---|---|
| 1 | `package.json:8` | `client.inject` lists `dsh-client-runtime` | Assembly row stays pending forever / plugin never enters the boot graph, often with no explicit error | Remove `dsh-client-runtime`; keep only packages that actually provide services | **DSH-0.1.2-A1-25** | Required immediately |
| 2 | `src/client/index.ts:6` | `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'` | TS2305 / ERR_MODULE_NOT_FOUND — package deleted in alpha.1 | `import type { Context as ClientContext } from '@deepseek-ai/cordis'` | **DSH-0.1.2-A1-25** | Required immediately |
| 3 | `src/client/Pet.tsx:8,13` | `import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`; `isThinking(snapshot: ConversationSnapshot)` | Same missing-module failure; the flat snapshot type no longer exists as a primary surface | `ChatSnapshot` from `@deepseek-ai/dsh-client-ui-chat/client` (keyed store, hit 5-7) | **DSH-0.1.2-A1-25**, **DSH-0.1.2-A1-03** | Required immediately |
| 4 | `src/client/Pet.tsx:19` | `useSession(s => s.running)` | Keeps working — `running` is a session-lifecycle field, **not** in the compat projection; stays on the `useSession` seat | Unchanged: lifecycle state via `useSession` | **DSH-0.1.2-A1-03** (field note) | No change (documented boundary) |
| 5 | `src/client/Pet.tsx:20` (+13-14) | `useSession(isThinking)` reading `snapshot.partial?.blocks…kind === 'reasoning'` | Type error; flat `partial` gone from the primary surface | Compat first: `views.get('chat')?.legacy`; end state: `useChat` over `ChatSnapshot` live nodes | **DSH-0.1.2-A1-03**, **DSH-0.1.2-A1-25** (+ API-10) | Staged compat allowed |
| 6 | `src/client/Pet.tsx:21` | `useSession(s => s.runningCalls.length > 0)` | Same — flat `runningCalls` gone | Compat: `legacy.runningCalls`; end state: derive tool-in-flight from live chat nodes | **DSH-0.1.2-A1-03**, **DSH-0.1.2-A1-25** (+ API-10) | Staged compat allowed |
| 7 | `src/client/Pet.tsx:23` | `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` | Same — flat `turnEnds` gone | Compat: `legacy.turnEnds`; end state: turn timeline from the chat view (`type === 'assistant-step'` → `data.finalNode`) | **DSH-0.1.2-A1-03**, **DSH-0.1.2-A1-25** (+ API-10) | Staged compat allowed |
| 8 | `package.json:6-9` (manifest key shape) | `"client": { "platform": "web", "inject": [...] }` | Cards reference the roster entry as `dsh.client` / `dsh.client.inject`; a differently-keyed manifest can silently keep the client half out of the browser roster | Verify manifest key/shape against the alpha.2 client-modules scan; registration id must equal package.json `name` | **DSH-0.1.2-A1-26** (+ A1-01 field note) | Verify (pending confirmation — no build config in fixture) |
| 9 | `cordis.patch.yml` (row `id: bench-pet`, `name: '@demo/dsh-bench-pet'`) | Loader composition overlay | Not a break: `cordis.patch.yml` is composition, not a source patch | None; confirm the row `name` keeps matching the package name under the A1-26 scan | (API-08 — no action; **DSH-0.1.2-A1-26** name-equality check) | Verification only |

Non-hits checked and cleared: `ctx.locale.register` and the `LocaleNamespaceMap` augmentation (locale
plugin unchanged across the corridor); `ctx.slots.register` into `conversation.session.header.actions`
with the `inject: ['slots', 'conversation']` ordering edge (`dsh-client-ui-conversation` still exists and
still declares the slot — but its packed artifact only ships `lib/**`, so never import its `./src/*`
subpath: API-07); `PropsRuntime`/`PropsLocale` from `dsh-client-ui-slots` (present at alpha.2); no
APIProxy / `ctx.connection.api` usage (A1-01 / A1-30 not hit); no `settingsNamespace` (A2-10 not hit);
no persisted custom SessionEvents (A1-02 / A2-01 not hit); no workspace navigation (A1-32 not hit); no
MarkdownText rendering (A1-29 not hit).

## Per-hit detail

### 1. `package.json:8` — `dsh-client-runtime` in the client inject list · DSH-0.1.2-A1-25

- **Evidence**: `client.inject`: `["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]`.
- **How it breaks**: `@deepseek-ai/dsh-client-runtime` was deleted from `packages/client` in alpha.1.
  Keeping it in the inject list is a runtime phantom dependency: the assembly row stays pending and the
  plugin never enters the boot graph — frequently with no explicit error (card symptom; confirmed by the
  dsh-input-history field note: with the runtime package left in `inject` the row did not enter the graph,
  and removing it restored it).
- **Post-migration form**:

  ```json
  "client": {
    "platform": "web",
    "inject": ["dsh-client-ui-conversation", "dsh-client-locale"]
  }
  ```

  Keep only packages that actually provide services the client bundle consumes. While the 0.1.2 cohort is
  unpublished, point type dependencies at the official source checkout with `link:` or tarball `overrides`
  (A1-25 recipe).
- **Cannot run through a projection**: a missing package cannot be projected away; hard, immediate change.

### 2. `src/client/index.ts:6` — `ClientContext` import · DSH-0.1.2-A1-25

- **Evidence**: `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`.
- **How it breaks**: missing module — typecheck/build fail outright.
- **Post-migration form**:

  ```ts
  import type { Context as ClientContext } from '@deepseek-ai/cordis'
  ```

  The client facets merged into Context come from owning packages via type-only imports (`index.ts:8,10`
  already do this correctly for locale and ui-conversation). Changing `ClientContext` to Cordis `Context`
  alone is not sufficient without those augmentations — here they are present, and a
  `import type {} from '@deepseek-ai/dsh-client-ui-chat/client'` line must be added once `useChat` /
  `ChatSnapshot` are consumed (hits 5-7). Per the A2-03 field note, every owning package whose
  declarations the source touches must be the plugin's own direct dev/peer dependency — run once with
  `skipLibCheck: false` to find the missing declaration chain, because `skipLibCheck: true` silently
  turns `useChat` selectors into implicit `any`.
- **Immediate** — missing module, no compat path.

### 3. `src/client/Pet.tsx:8,13` — `ConversationSnapshot` type · DSH-0.1.2-A1-25 / DSH-0.1.2-A1-03

- **Evidence**: line 8 imports the type from the removed runtime package; line 13 types `isThinking` with it.
- **How it breaks**: missing module (A1-25); independently, session-view internals were split extensively
  in alpha.1 (A1-03) — the flat `ConversationSnapshot` is no longer the primary read surface.
- **Post-migration form**: type snapshot-driven helpers over the owning package's shape:

  ```ts
  import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'
  ```

  For the staged-compat phase the legacy projection exposes the old flat fields, so the helper signature
  can stay shaped like the old one while reading from `views.get('chat')?.legacy` (hits 5-7).
- **Immediate** for the import itself (module gone); the semantics can move in two steps.

### 4. `src/client/Pet.tsx:19` — `useSession(s => s.running)` · DSH-0.1.2-A1-03 (documented boundary)

Not a break. The A1-03 field note (dsh-ui-whale migration) states explicitly: lifecycle fields such as
`running` are **not** in the `legacy` compat projection and must go through the `useSession` seat —
exactly what this line already does. Keep it as-is; do not migrate it to `useChat`.

### 5-7. `src/client/Pet.tsx:20,21,23` — flat snapshot fields `partial`, `runningCalls`, `turnEnds` · DSH-0.1.2-A1-03 + DSH-0.1.2-A1-25 (practice: API-10)

These three selectors are the core of the task: the pet's animation reads the flat conversation
snapshot, and that read surface is exactly what the corridor changed.

**Stage 1 — compatibility projection (allowed to run first).** Per the A1-03 field note
(dsh-ui-whale / dsh-ui-progress / dsh-input-history, Windows, real migrations): the old flat
`ConversationSnapshot` fields — `nodes` / `partial` / `runningCalls` / `turnEnds` — are all still
readable through the `views.get('chat')?.legacy` projection. The documented two-step approach is
"migrate everything to `legacy` first, then migrate field-by-field to views/timeline once stable". So
`thinking`, `toolRunning`, and `lastTurnEnd` can keep their exact semantics in stage 1 by selecting
over the legacy projection instead of the removed flat snapshot, while the `dsh-client-runtime`
imports/inject entries (hits 1-3) still must be removed immediately — the projection covers field
*reads*, not the removed *package*.

**Stage 2 — the alpha.2 read path (end state).** `ChatSnapshot.nodes` is a keyed store, not
`ConversationNode[]`; transcript reads go through `useChat`:

```ts
import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'

/** Ordered live nodes: iterate order, resolve each id through the keyed store. */
function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap((id) => {
    const node = snapshot.nodes.get(id)
    return node ? [node] : []
  })
}
```

- `thinking`: detect a live assistant step emitting reasoning blocks (reasoning content on the streaming
  node in `orderedNodes(chat)`), replacing `partial?.blocks.some(b => b.kind === 'reasoning')`.
- `toolRunning`: derive from live tool-call blocks on the streaming assistant step, replacing
  `runningCalls.length > 0`.
- `lastTurnEnd`: read the turn timeline from the chat view — for the last settled assistant output,
  narrow by discriminant to `type === 'assistant-step'` and read `data.finalNode` (API-10), replacing
  `turnEnds[len-1]?.reason`.

Select via the slot-provided seat: `useChat(chat => chat ? <derive> : <default>)`. API-10 is explicit
that `snapshot.legacy.nodes` is only for staged compatibility with a dual-host requirement and must not
become the primary data surface of an alpha.2-only plugin — stage 2 is mandatory for the final state
even though stage 1 unblocks the build.

Do not mask the shapes in tests: build fixtures with the real `ChatNodeStore` shape (`order` + keyed
`get`), covering missing ids and the assistant final node; `as unknown as ChatSnapshot` over old array
fixtures is a migration failure (API-10 verification).

### 8. `package.json:6-9` — manifest key shape and roster entry · DSH-0.1.2-A1-26 (+ A1-01 field note)

The A1-01 field note states the plugin "must declare `dsh.client` in package.json to enter the browser
plugin roster", while the fixture uses a `"client"` key. The fixture carries no build/tsdown config, so
the client-bundle registration id (the `__ModuleLoader__.load` banner id) is not observable here. Both
must be verified against the alpha.2 client-modules scan contract (A1-26): registration id == assembly
row `name` == package.json `name` (`@demo/dsh-bench-pet`), with the row using the bare scoped package
name — which `cordis.patch.yml` already does. Verification per A1-26:
`window.__DSH_BOOT__.entries` contains `"id":"@demo/dsh-bench-pet"`; the combo route URL contains `??`;
no `loaded without registering` / `entries did not activate` in the startup log. Marked **pending
confirmation** because the fixture is task material that cannot be run.

### 9. `cordis.patch.yml` — composition overlay, not a patch · API-08 (no action)

Correctly classified as the official Profile composition overlay (`insert` row). No source-patch
migration applies. Only the A1-26 name-equality check above touches it.

## Compat-projection vs immediate switch (requirement 4)

| Field / surface | Can run first through compat projection? | Rationale |
|---|---|---|
| `partial` (thinking) | **Yes** — `views.get('chat')?.legacy.partial` | A1-03 field note: flat fields still readable via `legacy`; two-step migration is the documented practice |
| `runningCalls` (toolRunning) | **Yes** — `legacy.runningCalls` | Same |
| `turnEnds` (lastTurnEnd) | **Yes** — `legacy.turnEnds` | Same |
| `nodes`-style transcript iteration (future needs) | Yes (`legacy.nodes`) but time-boxed | API-10: `legacy` is staged compat only, never the primary surface of an alpha.2-only plugin |
| `running` | N/A — no migration | Lifecycle field; stays on `useSession`, not in the projection at all |
| `dsh-client-runtime` import (`Pet.tsx:8`, `index.ts:6`) | **No — immediate** | Package deleted; no projection can supply a missing module (A1-25) |
| `dsh-client-runtime` in `client.inject` (`package.json:8`) | **No — immediate** | Phantom dependency keeps the row pending / out of the boot graph (A1-25) |
| `ConversationSnapshot` type usage | **No — immediate** (retype to `ChatSnapshot` or the legacy projection's type) | Follows from the removed module (A1-25 / A1-03) |

## Recommended migration order

1. Remove `dsh-client-runtime` from `client.inject`; retarget `ClientContext` → Cordis `Context`;
   add `@deepseek-ai/dsh-client-ui-chat/client` (and keep ui-conversation / ui-locale) as direct type
   dependencies (A1-25; A2-03 field note; run once with `skipLibCheck: false`).
2. Switch the three animation selectors to the `views.get('chat')?.legacy` projection, preserving
   semantics (`running` untouched on `useSession`) — the documented stage-1 unblock (A1-03).
3. Field-by-field, move `thinking` / `toolRunning` / `lastTurnEnd` onto `useChat` + the keyed
   `ChatSnapshot` (`order` + `nodes.get(id)`; assistant-step → `data.finalNode`) — the alpha.2 end state
   (A1-25 / API-10).
4. Verify the manifest key / registration-id / package-name triplet under the alpha.2 scan (A1-26), then
   run the API-10 verification ladder: real `ChatNodeStore` fixtures, pack/install artifact smoke, and a
   Web cold boot with no pending rows.

## Verification ladder (distinct completion levels)

1. **Typecheck**: real `Context` + owning-package augmentations, no `dsh-client-runtime` references, no
   new implicit `any` (`skipLibCheck: false` pass recorded).
2. **Loader/config smoke**: isolated profile `--dump-config` — row names match the package name, no
   pending rows (A1-25 / A1-26).
3. **Artifact smoke**: pack manifest resolves entries and `.d.ts` from the actual tarball (API-07 / API-10).
4. **Real behavior**: Web cold boot — pet mounts in the header slot; reasoning stream → `thinking` frame;
   tool call in flight → `working` frame; settled turn → settle frame; locale switch updates dictionary
   copy. Only this level proves the snapshot read-surface migration complete.

## Honest limitations

- The fixture is task material that "cannot be run"; no runtime or typecheck execution was possible, so
  hit 8 (manifest key shape / registration id) remains verified-by-documentation only ("pending
  confirmation", per the skill's own convention).
- Line numbers refer to the fixture files as checked in; the fixture is read-only and was not modified.
- The exact shape of reasoning/tool-call content on live assistant-step nodes at the alpha.2 tag was not
  inspectable from the local card set; the report states the discriminator-level read path
  (`type === 'assistant-step'` → `data.finalNode`, keyed store via `order`) per API-10 and flags
  field-level details for confirmation against the target tag's `.d.ts`, as the cards themselves instruct
  ("the generated declarations are authoritative").
