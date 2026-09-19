# S3 · Snapshot Read-Surface Migration Assessment — `@demo/dsh-bench-pet`

**Mode**: read-only assessment (plugin-upgrade skill, Mode A/C planning only — no code, config, dependency, or install changes were made; the fixture was only read).
**Corridor**: `dsh-v0.1.1-rc.1` → `dsh-v0.1.1-rc.2` → `dsh-v0.1.2-alpha.1` → `dsh-v0.1.2-alpha.2` (built from the `from → to` edges in `references/README.md`, not filename order).
**Baseline**: not collected — the fixture is trimmed task material that per its own README "cannot be run"; no build/test of the plugin was attempted (read-only discipline).

The plugin is a Web Client (browser) plugin: a pixel pet mounted in the session-header actions slot whose animation follows the live conversation snapshot. All break surfaces are on the client face; there is no Host half.

---

## 1. Every breaking surface, its location, the target form, and the card

### 1.1 Import of the removed `@deepseek-ai/dsh-client-runtime` (type imports)

- **Location**: `src/client/Pet.tsx:8` (`import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'`) and `src/client/index.ts:6` (`import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`).
- **How it breaks**: the package was deleted in alpha.1; typecheck reports a nonexistent module / missing exports, and at runtime the plugin never enters the boot graph or its assembly row stays pending forever, often with no explicit error.
- **Card**: **DSH-0.1.2-A1-25** (`@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain), reinforced by **API-10** in `references/api-migration-0.1.2-alpha.2.md` (Web Client runtime unbundling, keyed chat snapshots).
- **Post-migration form** (per the A1-25 verified mapping; defer to each package's actual exports at the target tag):

```ts
// index.ts
import type { Context as ClientContext } from '@deepseek-ai/cordis'
// keep the type-only augmentations that pull the merged faces:
import type {} from '@deepseek-ai/dsh-client-locale/client'
import type {} from '@deepseek-ai/dsh-client-ui-conversation/client'
```

```ts
// Pet.tsx — ConversationSnapshot is gone; the chat read surface is now ChatSnapshot
// from '@deepseek-ai/dsh-client-ui-chat/client' (keyed store), or the staged
// views.get('chat')?.legacy projection (see §1.2).
```

  The owning packages of every declaration the source directly imports (`dsh-client-ui-conversation`, `dsh-client-ui-chat`, `dsh-client-ui-slots`, `dsh-client-locale`) must become the plugin's own direct dev/peer dependencies — a published package's `devDependencies` are not transitively installed (API-10 "Type composition and dependency ownership"; **DSH-0.1.2-A2-03** peer-trim field note). Run one diagnostic typecheck with `skipLibCheck: false`; a selector that silently becomes `any` is a migration failure.

### 1.2 The flat `ConversationSnapshot` read surface in `Pet.tsx`

- **Location**: `src/client/Pet.tsx:13–23`:
  - `isThinking`: `snapshot.partial?.blocks.some(block => block.kind === 'reasoning')` (line 14)
  - `useSession(s => s.running)` (line 19)
  - `useSession(s => s.runningCalls.length > 0)` (line 21)
  - `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` (line 23)
- **How it breaks**: 0.1.2 no longer exposes per-session conversation-node snapshots; the timeline became an internal projection of each view package. Selecting `partial` / `runningCalls` / `turnEnds` through the old `useSession` snapshot shape yields `undefined` / factory errors — "the plugin loads but half its functionality is broken".
- **Cards**: **DSH-0.1.2-A1-03** (Session view internals split up extensively — its field note is the authoritative snapshot-read guidance: the old flat fields `nodes`/`partial`/`runningCalls`/`turnEnds` remain readable through the `views.get('chat')?.legacy` projection, while lifecycle fields such as `running` are **not** in the projection and must go through the `useSession` seat), **DSH-0.1.2-A1-27** (session content reads move behind the SessionBinding durable event window — applies if the pet ever needs raw message content), and **API-10** (alpha.2 best practice: read via `useChat` with the keyed `ChatSnapshot`).
- **Post-migration form**:

  Staged (compatibility projection — runs first):

```ts
const legacy = useSession(s => s.views.get('chat')?.legacy) // nodes/partial/runningCalls/turnEnds
```

  Target (new read path — switch per field once stable):

```ts
import type { Context } from '@deepseek-ai/cordis'
import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'

// keyed store, not ConversationNode[]:
function orderedNodes(snapshot: ChatSnapshot) {
  return snapshot.order.flatMap(id => {
    const node = snapshot.nodes.get(id)
    return node ? [node] : []
  })
}
// transcript-driven state: useChat(chat => chat ? ... : ...)
// an assistant step's final node: narrow type === 'assistant-step', read data.finalNode
```

  Lifecycle state stays on the seat and never moves into a projection:

```ts
const running = useSession(s => s.running) // correct seat in 0.1.2 — keep
```

### 1.3 `dsh.client.inject` still lists the phantom runtime package

- **Location**: `package.json:6–9` — `"client": { "platform": "web", "inject": ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"] }`.
- **How it breaks**: after the unbundling, `dsh-client-runtime` in the inject list is a runtime phantom dependency — keeping it leaves the assembly row pending / keeps the plugin out of the boot graph (verified field note in A1-25: "with the runtime package left in `inject` the row did not enter the graph, and removing it restored it").
- **Card**: **DSH-0.1.2-A1-25** (also its package.json cleanup step).
- **Post-migration form**: `inject` keeps only packages that actually provide services the client half consumes — e.g. `["dsh-client-ui-conversation", "dsh-client-locale"]` (drop `dsh-client-runtime`).
- **Additional packaging note (verify, do not assume)**: since the 0810 baseline the host reads the client-half manifest under the **`dsh.client`** key, and client-modules enumerates packages by that declaration (**DSH-0.1.1-R1-02**, **DSH-0.1.1-R1-03** — pre-corridor for an rc.1-era plugin, so an rc.1-era fixture should already satisfy it). The fixture's manifest uses a bare top-level `"client"` key; whether that is a fixture simplification or a real drift must be confirmed against the target tag's scan contract before release — check the **packed** manifest, not only the source `package.json`.

### 1.4 Client-bundle registration id vs package name

- **Location**: `cordis.patch.yml:1–3` (insert row `id: bench-pet`, `name: '@demo/dsh-bench-pet'`) and the (absent) client build banner that stamps the `__ModuleLoader__.load` id.
- **How it breaks**: 0.1.2's boot manifest keys entries/modules/plugin registrations by package name (`Entry name == package name`). A short-name registration id (`bench-pet`) triggers the startup assertion `loaded without registering "<package name>"`, or more subtly the panel silently disappears with no plugin-related error. Under the new scan, 0.1.1's `file:///` literal-path plus short-name id form silently keeps the client half out of the graph.
- **Card**: **DSH-0.1.2-A1-26** (client-modules scan contract: registration id must equal the package.json name).
- **Post-migration form**: all three ids agree with `package.json#name` = `@demo/dsh-bench-pet`: (1) the client bundle's `__ModuleLoader__.load` id (tsdown banner `PLUGIN_ID`), (2) the assembly row's `name` (already the bare scoped name — keep, drop any `file:///` literal-path form), (3) verified via `dsh --profile <p> --dump-config` (row names, no pending) and `window.__DSH_BOOT__.entries` containing `"id":"@demo/dsh-bench-pet"`.

### 1.5 Type-only augmentations and locale/slot registration (no break, keep with ownership fixes)

- `src/client/index.ts:8–10` type-only imports from `dsh-client-locale/client` and `dsh-client-ui-conversation/client`: the packages still exist in 0.1.2 as owning packages; the imports stay, but each becomes a direct dependency (see §1.1). `ctx.locale.register`, the `LocaleNamespaceMap` merge, the `inject = ['slots', 'conversation', 'locale']` ordering edge, and the `conversation.session.header.actions` slot name all remain valid on the 0.1.2 target (the conversation slot only moves under root-scoped `main` in 0.1.5-alpha.2 — outside this corridor). No card action.

---

## 2. Compatibility projection vs immediate new read path

| Read in the fixture | Field class | Migration order |
|---|---|---|
| `s.running` (`Pet.tsx:19`) | session **lifecycle** field | **Immediate new path required** — lifecycle fields are not in the `legacy` projection; keep reading through the `useSession` seat (the seat itself is the 0.1.2-correct surface; only snapshot-content selectors must stop using `useSession`). |
| `snapshot.partial?.blocks` (`Pet.tsx:14`), `s.runningCalls` (`Pet.tsx:21`), `s.turnEnds` (`Pet.tsx:23`) | conversation **content/timeline** fields | **Can run first through the compatibility projection** `views.get('chat')?.legacy` (DSH-0.1.2-A1-03 field note), then migrate field-by-field to the `useChat` keyed `ChatSnapshot` (`order` + `nodes.get(id)`, `assistant-step` → `data.finalNode`) once stable — API-10 notes `snapshot.legacy.nodes` is staged compatibility only and must not become the primary surface for an alpha.2-only plugin. |
| `dsh-client-runtime` imports (`Pet.tsx:8`, `index.ts:6`) and its `dsh.client.inject` entry (`package.json:8`) | packaging / boot graph | **Immediate switch** — no projection exists; leaving the phantom package keeps the plugin out of the boot graph (DSH-0.1.2-A1-25). |
| Registration id / assembly row (`cordis.patch.yml`) | boot-manifest scan | **Immediate switch** at upgrade time (DSH-0.1.2-A1-26). |
| Raw message content (not currently read) | durable event window | n/a today; if ever needed, read through `sessions.binding(id)` → `binding.eventSource.getSnapshot().entries` (DSH-0.1.2-A1-27), never a resurrected node snapshot. |

The two-step approach ("migrate everything to legacy first, then migrate field-by-field to views/timeline once stable") is the exact pattern the A1-03 field note records for three sibling UI plugins (dsh-ui-whale / dsh-ui-progress / dsh-input-history).

---

## 3. Cards consulted and disposition

| Card | Verdict for this plugin |
|---|---|
| DSH-0.1.2-A1-25 | **Hit** — runtime package import + `dsh.client.inject` (§1.1, §1.3) |
| DSH-0.1.2-A1-03 | **Hit** — flat `ConversationSnapshot` read surface (§1.2) |
| DSH-0.1.2-A1-26 | **Hit** — registration id vs package name (§1.4) |
| DSH-0.1.2-A1-27 | Conditional — applies only if the pet later reads message content (§2) |
| DSH-0.1.2-A2-03 (+ API-10 ownership section) | **Hit** — direct dev/peer dependency ownership for consumed declarations; run `skipLibCheck: false` once |
| DSH-0.1.1-R1-02 / R1-03 | Verification item — `dsh.client` manifest key on the packed artifact (§1.3) |
| DSH-0.1.1-R2-01…03 (image/attachment) | Non-hit — plugin touches no image attachments; skipped with evidence (no `ImageAttachmentRef`/`read_image` usage in the fixture) |
| DSH-0.1.2-A1-01/A1-30 (APIProxy / `ctx.connection.api`) | Non-hit — the pet makes no Host calls; snapshot reads are local store reads |
| DSH-0.1.2-A1-32 (workspace navigation) | Non-hit — no `ctx.workspaces.*` navigation or `baselinesReady` reads |
| DSH-0.1.2-A1-19 (boot-manifest acceptance) | Verification guidance — after migration, acceptance must read `window.__DSH_BOOT__.entries` and the host-advertised resource URL, not a hardcoded `/plugins/<id>/client.js` + HTTP 200 |
| Remaining alpha.1/alpha.2 cards (A1-02/A1-05…A1-29 minus hits, A2-01/02/04/05/06/08/10) | Non-hit — Host-plane, events-persistence, headless, settings, Remote-error, or composition surfaces the fixture does not touch; A2-01 net-state note: the plugin neither produces nor persists session events |

## 4. Suggested migration plan (for later execution, after confirmation)

1. Host face: none (browser-only plugin).
2. Client face, in order: (a) swap `ClientContext`/`ConversationSnapshot` imports to `@deepseek-ai/cordis` + owning packages; (b) drop `dsh-client-runtime` from `dsh.client.inject`; (c) rewire `Pet.tsx` selectors — keep `useSession(s => s.running)`, move `partial`/`runningCalls`/`turnEnds` onto `views.get('chat')?.legacy` first, then to `useChat`/keyed `ChatSnapshot`; (d) align all registration ids to `@demo/dsh-bench-pet`; (e) add direct dev/peer deps for every consumed declaration and typecheck once with `skipLibCheck: false`.
3. Validation ladder: dependency resolution (lockfile free of the old cohort and `dsh-client-runtime`) → `--dump-config` (no pending rows) → typecheck/build with no new implicit `any` → isolated-profile cold boot with token→Cookie exchange, boot-entry check, host-advertised resource fetch, and proof of registration/mount (a visible pet DOM marker with the right `data-frame`) → behavior: one message → tool-call → response turn driving `working`/`thinking`/`idle` frames and the settle frame from the last turn-end reason.

## 5. Pending / residual risk

- The bare `"client"` manifest key in `package.json` vs the `dsh.client` key the scan contract reads (§1.3) — confirm on the packed artifact against the target tag before release; the fixture is trimmed task material, so this may be fixture simplification rather than a real defect.
- Exact `ChatSnapshot` partial/turn-end field names at `dsh-v0.1.2-alpha.2` were not read from the target tag source in this read-only pass; per the card rules, re-check the target tag's `packages/client/ui-chat/src/client/contract/snapshot.ts` before writing the new selectors — do not invent interfaces from this report.
- No runtime verification was performed (read-only task; fixture is non-runnable by its own README).

## 6. Rollback

Not applicable — no files were modified. The fixture and every file under the benchmark repository are untouched; the only write is this report in the designated output directory.
