# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report (Read-Only)

- **Task**: static, read-only analysis of a Web Client plugin source from the dsh 0.1.1-rc.2 era, targeting dsh 0.1.2-alpha.2.
- **Fixture**: `environment/fixture` (4 files: `README.md`, `package.json`, `src/client/index.ts`, `src/client/Pet.tsx`). No file under the fixture was modified, created, or deleted; no build, install, or reproduction environment was created.
- **Corridor**: dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1 (cards `DSH-0.1.2-A1-*`) → dsh-v0.1.2-alpha.2 (cards `DSH-0.1.2-A2-*`, interface ledger `API-*`). Net-state check: the only removed-then-restored field in this corridor is `SessionEvent.ignorable` (A1-02 → A2-01); the fixture produces no SessionEvents, so no net-state folding applies.
- **Plugin identity**: `package.json` name `dsh-pet-session-bench`, version 0.1.0, `"private": true`, `"type": "module"`, declares `dsh.client.platform: "web"` — a Web Client (browser-plane) plugin. No lockfile, no `dsh.client.inject`, no dependency declarations present in the fixture.

## 1. Breaking touchpoints (all hits)

All four hits are on the **Web Client plane** (the plugin's client half / its packaging). Line numbers refer to the fixture's `src/client/index.ts`.

### T1 · `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`

- **File/line**: `src/client/index.ts:1`
- **Plane**: Web Client (plugin source)
- **Card**: **DSH-0.1.2-A1-25** (`@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain)
- **Why it breaks**: the package was deleted from `packages/client` in alpha.1; build/typecheck report a nonexistent module and at runtime the plugin may not enter the boot graph / its assembly row stays pending, often without an explicit error.
- **Action**: replace with `import type { Context as ClientContext } from '@deepseek-ai/cordis'` (the card's verified mapping; the alpha.2 ledger API-10 gives the same mapping and adds that Context facet types come from owning packages via type-only augmentation imports). Any other symbol imported from the runtime package would follow the card's per-domain table; this fixture imports only `ClientContext`. Also clean up `package.json`: remove `@deepseek-ai/dsh-client-runtime` from `dsh.client.inject` if it ever appears — **not present in this fixture** (no `dsh.client.inject` key), so nothing to remove there.

### T2 · `__ModuleLoader__.load('pet-legacy-bundle', …)` — registration id ≠ package.json name

- **File/line**: `src/client/index.ts:5` (declaration) and `src/client/index.ts:10` (call); baseline name in `package.json:2` (`dsh-pet-session-bench`)
- **Plane**: Web Client (plugin source / bundle registration)
- **Card**: **DSH-0.1.2-A1-26** (client-modules scan contract: registration id must equal the package.json name)
- **Why it breaks**: 0.1.2's boot manifest keys entries/modules/plugin registrations by package name (`Entry name == package name`). The literal `'pet-legacy-bundle'` does not equal `dsh-pet-session-bench`, so the startup assertion `loaded without registering "<id>"` fires — or, more subtly, the client half silently stays out of the boot graph with no plugin-related log error.
- **Action**: change the registration id to the exact bare package name `'dsh-pet-session-bench'` (with scope if the package name gains one at publish time), keeping package.json `name` as the baseline; the tsdown banner `PLUGIN_ID` is the usual injection point. Verify via `window.__DSH_BOOT__.entries` containing `"id":"dsh-pet-session-bench"` and no `loaded without registering` in the startup log (per the card's verification recipe — to be executed in a later migration phase, not in this read-only pass).

### T3 · flat `const { nodes } = useSession()` snapshot read

- **File/line**: `src/client/index.ts:2` (`useSession` import from `@deepseek-ai/dsh-client-ui-chat/client`), `src/client/index.ts:12–13` (`nodes[0]` array indexing)
- **Plane**: Web Client (plugin source)
- **Card**: **DSH-0.1.2-A1-27** (Session content reads now go through the SessionBinding durable event window); supplemented by the alpha.2 interface ledger entry **API-10** (Web Client runtime unbundling, keyed chat snapshots) and **DSH-0.1.2-A1-03** (session-view internals split; its field note records the real migration pattern `useSession` transcript → `useChat`, keyed store read via `order + nodes.get(id)`).
- **Why it breaks**: 0.1.2 no longer exposes per-session flat `ConversationNode[]` conversation snapshots; on alpha.2 `ChatSnapshot.nodes` is a keyed store (`Map`-like), not an array — `nodes[0]` is `undefined`; the plugin loads but the feature is broken (`session.getSnapshot().nodes` undefined/empty, console factory errors).
- **Action**: switch the seat and read shape: `useChat(chat => …)` in place of `useSession()`, and iterate `snapshot.order` calling `snapshot.nodes.get(id)` per id (API-10's `orderedNodes` minimal read shape). For raw SessionEvent content, the card's replacement gap is the SessionBinding durable event window (`sessions.binding(id)` → `binding.eventSource.getSnapshot().entries`), importing `SessionBinding`/`SessionEventLikeEntry` from `@deepseek-ai/dsh-api-session-controller/client`. `snapshot.legacy.nodes` exists only for staged dual-host compatibility and must not become the primary surface for an alpha.2-only plugin.

### T4 · `ctx.connection.api.agentPresets.list()` — removed connection api face

- **File/line**: `src/client/index.ts:11`
- **Plane**: Web Client (plugin source)
- **Card**: **DSH-0.1.2-A1-30** (Client `ctx.connection.api` face removed entirely; history/transcript reads rerouted); the successor call name comes from **DSH-0.1.2-A1-01**'s mapping table (`agentPreset.list` → `ctx.remote.agentPresets.list`); error handling on the new Remote follows **DSH-0.1.2-A2-02**.
- **Why it breaks**: alpha.1 removed the old apiProxy mirror face on `ctx.connection`; client calls throw. The card warns that if the call site swallows the error in a catch, the UI renders "forever blank" instead of an error — the fixture's `.then(...)` with no `.catch` would at least surface the rejection, but neither state is acceptable.
- **Action**: as a browser-plane plugin, declare the needed Remote contributions in `inject` (plus the `remote` service), mount the generated types via `@deepseek-ai/dsh-api-remotes/client`, and call `await ctx.remote.agentPresets.list(...)` (generated declarations are authoritative). Handle the `RemoteResult<T>` result branch by `result.ok`/`result.error.code` per A2-02 (namespaced codes such as `agent-preset/not-found`; do not `instanceof` across realms). Once no `ctx.connection.*` consumption remains, remove `connection` from `inject` — the fixture's `inject = ['slots', 'conversation']` does **not** include `connection`, so no inject cleanup is required here. Note `apply(ctx)` uses `ctx.connection` as a property without declaring it in `inject` — after migration this dead face reference disappears entirely.

## 2. Non-hits (cards reviewed and excluded, with evidence)

| Card | Why not hit |
|---|---|
| DSH-0.1.2-A1-32 (`IWorkspaces` navigation → `ctx.uiWorkspace`) | no `ctx.workspaces` / `connectWorkspace` / `pickDirectory` usage anywhere in the fixture (grep: zero hits) |
| DSH-0.1.2-A1-28 (composer `<textarea>` → contenteditable) | no composer/DOM manipulation in the fixture |
| DSH-0.1.2-A1-29 (`MarkdownText` labels) | no `MarkdownText` / ui-primitives usage |
| DSH-0.1.2-A1-22 (`isTokenDelta`), A1-20 (userQuestions waterfall), A1-21 (`resolveSessionPreset`), A1-31 (subagent descriptor v3) | no corresponding identifiers in the fixture |
| DSH-0.1.2-A1-02 / A2-01 (`SessionEvent.ignorable` remove/restore) | fixture writes no SessionEvents |
| DSH-0.1.2-A2-03/A2-08 (peer trims/additions), A1-24 (pi-ai) | fixture declares no dependencies and no lockfile; nothing to reconcile statically |
| DSH-0.1.2-A1-19 / A1-08 (token boot, auth gate) | fixture is plugin source only, no acceptance scripts or custom routes |
| Remaining A1/A2 cards (04–07, 09–14, 23, A2-04/05/06/10) | host-plane, packaging, or capability cards with no corresponding surface in this 4-file client-only fixture |

## 3. Completeness and confidence

- The scan covered all fixture files line-by-line (imports, `__ModuleLoader__` registration, `ctx` faces, hook usage, `package.json` `dsh` block, `inject` list). Every assertion above cites a card in `skills/plugin-upgrade/references/v0.1.2-alpha.1.md`, `v0.1.2-alpha.2.md`, or `api-migration-0.1.2-alpha.2.md`; no card was fabricated.
- **Unconfirmed / pending**: exact alpha.2 signatures (e.g. `ctx.remote.agentPresets.list` argument wrapper key, `ChatSnapshot` field names) were not verified against target-tag source — this closed-book pass had only the fixture and the skill's references; treat them as "pending review" per the skill's rule and confirm against the generated declarations (`lib/typert.remote-client.d.ts`) and owning package exports at the target tag before writing code. Per API-10, run one `tsc --skipLibCheck false` pass during the real migration to catch missing declaration owners, and add the owning packages (`@deepseek-ai/dsh-client-ui-chat`, `@deepseek-ai/dsh-api-session-controller/client` owner, `@deepseek-ai/dsh-api-remotes`) as direct dev/peer dependencies of the plugin.

## 4. Suggested migration order (for the later Mode-C pass; nothing was changed now)

1. Fix the registration id first (T2) — without it the plugin never enters the boot graph and no other fix is observable.
2. Replace the `dsh-client-runtime` import (T1) and add owning type dependencies.
3. Migrate the Remote call (T4) with `RemoteResult` branch handling.
4. Migrate the transcript read (T3) to `useChat` + keyed store.
5. Validate per the skill's ladder: dependency resolution → enablement → static (build/typecheck, `skipLibCheck: false` once) → runtime cold boot with boot-graph/pending check → one core behavior path.

**Rollback / baseline**: this pass was read-only; the fixture is unchanged (grading requires it unchanged relative to git HEAD). No baseline beyond the fixture's current content was needed or recorded.
