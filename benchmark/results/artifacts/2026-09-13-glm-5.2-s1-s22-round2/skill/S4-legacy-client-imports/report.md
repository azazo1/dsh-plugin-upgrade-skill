# S4 · Legacy Client Runtime Touchpoints — Read-Only Migration Report

- **Task**: analyze a 0.1.1-rc.2-era Web Client plugin source against target dsh **0.1.2-alpha.2**; read-only, no migration performed.
- **Skill mode**: A · inspect (read-only). Corridor: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1` (cards `DSH-0.1.2-A1-*`, references/v0.1.2-alpha.1.md) plus `dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (cards `DSH-0.1.2-A2-*`, references/v0.1.2-alpha.2.md) and the exact interface ledger `references/api-migration-0.1.2-alpha.2.md` (API-10).
- **Fixture identity**: `dsh-pet-session-bench@0.1.0`, `"private": true`, `"type": "module"`, Web Client plugin (`dsh.client.platform: "web"`), 3 source files (`package.json`, `src/client/index.ts`, `src/client/Pet.tsx`). No `dsh.client.inject`, no cordis.patch.yml, no lockfile in the fixture. Host plane: none (client-only source).
- **Discipline**: fixture untouched; no build, no dependency install, no reproduction environment; only this report file was written.

## Completed — touchpoints that break on 0.1.2-alpha.2

### T1 · `ClientContext` imported from the removed `@deepseek-ai/dsh-client-runtime/client`

- **Hit**: `src/client/index.ts:1` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane**: Web Client (plugin's client half)
- **Card**: **DSH-0.1.2-A1-25** — `@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain (removed in alpha.1, still absent in alpha.2); supported by **API-10** (ledger, "Web Client runtime unbundling").
- **How it breaks**: build/typecheck report a nonexistent module / missing exports; at runtime the plugin does not enter the boot graph or its assembly row stays pending forever, often without an explicit error (card symptom, verbatim).
- **Migration action** (card's verified mapping table):
  ```ts
  import type { Context as ClientContext } from '@deepseek-ai/cordis'
  ```
  plus type-only augmentations from the owning packages actually consumed (here: `import type {} from '@deepseek-ai/dsh-client-ui-chat/client'` for the `useChat` seat introduced in T3; API-10 "Type composition and dependency ownership"). Each owning package consumed becomes the plugin's own direct dev/peer dependency (API-10 §Type composition; alpha.2 peer-trim context in DSH-0.1.2-A2-03). While the cohort is unpublished, point type dependencies at the official source checkout with `link:` or tarball `overrides` per rollup R-01 (A1-25 cleanup item; noted, not executed).
- **Also check** (non-hit today, card-required): `dsh.client.inject` must not retain `@deepseek-ai/dsh-client-runtime` — this fixture declares no `dsh.client.inject` at all, so there is no phantom row; after T2–T4 migration the inject list must declare the services actually consumed (see T4).

### T2 · `__ModuleLoader__.load` registration id ≠ package.json name

- **Hit**: `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', () => { /* legacy bundle id, not package name */ })`; package name is `dsh-pet-session-bench` (`package.json:2`).
- **Plane**: Web Client (bundle registration / boot manifest)
- **Card**: **DSH-0.1.2-A1-26** — client-modules scan contract: registration id must equal the package.json name.
- **How it breaks**: startup assertion `loaded without registering "<id>"`, or the subtler variant — the panel silently disappears, the boot graph lacks this plugin, and logs show no plugin-related errors (card symptom, verbatim).
- **Migration action**: align the three ids with package.json `name` as baseline: (1) the bundle registration id — the `__ModuleLoader__.load` id, usually injected by the tsdown banner `PLUGIN_ID` — becomes `'dsh-pet-session-bench'`; (2) the assembly row name (in the plugin's own `cordis.patch.yml`/home patch — none exists in this fixture) uses the bare package name; (3) verify via `dsh --profile <name> --dump-config` for row names and no pending. Post-migration acceptance (verification guidance, DSH-0.1.2-A1-19): `window.__DSH_BOOT__.entries` contains `"id":"dsh-pet-session-bench"` and the combo route `/plugins/??dsh-pet-session-bench/client.js&rev=...` serves the bundle.

### T3 · Flat `useSession()` `nodes` array snapshot read

- **Hit**: `src/client/index.ts:2` (`import { useSession } from '@deepseek-ai/dsh-client-ui-chat/client'`), `src/client/index.ts:12-13` — `const { nodes } = useSession(); const first = nodes[0]`.
- **Plane**: Web Client (session content read)
- **Card**: **DSH-0.1.2-A1-27** — Session content reads now go through the SessionBinding durable event window; exact replacement mapping in **API-10** (`useSession(session => session?.nodes)` → `useChat(chat => ...)`; `ConversationSnapshot.nodes[]` → iterate `ChatSnapshot.order` calling `snapshot.nodes.get(id)`). On alpha.2 `ChatSnapshot.nodes` is a keyed store, not `ConversationNode[]` (API-10 "How it breaks").
- **How it breaks**: plugin loads but the feature is broken — snapshot `nodes` is undefined/empty, console reports factory errors (A1-27 symptom); `nodes[0]` against a keyed store does not yield the first node. With `skipLibCheck: true`, selectors may silently become `any` instead of failing typecheck (API-10).
- **Migration action** (API-10 minimal alpha.2-only shape):
  ```ts
  import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'
  const nodes = ctx.useChat((chat) => chat
    ? chat.order.flatMap((id) => { const n = chat.nodes.get(id); return n ? [n] : [] })
    : [])
  const first = nodes[0]
  ```
  Do **not** keep reading the flat array; `snapshot.legacy.nodes` exists only for staged dual-host compatibility (A1-03 field note) and must not become the primary surface for an alpha.2-only plugin. For raw event-window reads (not needed by this call site), the durable gap is `sessions.binding(id).eventSource.getSnapshot().entries` with `SessionBinding`/`SessionEventLikeEntry` from `@deepseek-ai/dsh-api-session-controller/client` (A1-27 recipe). *Unconfirmed*: whether the `useSession` export itself remains on `dsh-client-ui-chat/client` at alpha.2 for lifecycle fields (A1-03 field note implies a `useSession` "seat" for lifecycle fields like `running`); the `nodes` read must move to `useChat` regardless.
- **Sibling note**: `ctx.getSnapshot()`-style per-session conversation-node snapshots are gone because the timeline became an internal projection of each view package (A1-27 → DSH-0.1.2-A1-03 context).

### T4 · `ctx.connection.api` face removed — `agentPresets.list()`

- **Hit**: `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list().then(presets => { /* legacy connection.api face */ })`
- **Plane**: Web Client (Remote call)
- **Card**: **DSH-0.1.2-A1-30** — Client `ctx.connection.api` face removed entirely; successor mapping for `agentPreset.list` → `agentPresets/list` is in **DSH-0.1.2-A1-01** (APIProxy→Remote table); the exact client pattern is **API-01** in the ledger. Error-flow semantics on alpha.2: **DSH-0.1.2-A2-02**.
- **How it breaks**: alpha.1 removed the old apiProxy mirror face on `ctx.connection`; client calls throw — and "if the call site silently swallows the error in a catch, the UI renders 'forever blank' instead of an error" (A1-30 symptom, verbatim).
- **Migration action**:
  ```ts
  import type {} from '@deepseek-ai/dsh-api-remotes/client' // type mounts for ctx.remote namespaces
  export const inject = ['slots', 'conversation', 'remote', 'remote.agentPresets']
  const result = await ctx.remote.agentPresets.list()
  if (!result.ok) {
    switch (result.error.code) { /* 'gateway/cancelled' | 'agent-preset/not-found' | ... */ }
  }
  ```
  Declare `remote` plus the specific namespace injections (API-01 client pattern); unary Remote calls return `RemoteResult<T>` and do not reject on business/carrier failures — branch on `result.ok`, not `try/catch`; codes are namespaced (`agent-preset-not-found` → `agent-preset/not-found`) and `error` is a `RemoteError` instance on alpha.2 (A2-02). Once no `connection` consumer remains, remove `connection` from the inject list and the type mirror — the fixture's inject (`['slots', 'conversation']`, index.ts:7) does not list `connection`, so only the additions above apply.

## Non-hits checked (evidence)

- `package.json:6` `dsh: { client: { platform: 'web' } }` — the `dshClient` → `dsh.client` manifest merge belongs to the rc.8→rc.1 edge (DSH-0.1.1-R1 series), already the rc.2 shape; no change required in this corridor.
- `src/client/index.ts:7` `inject = ['slots', 'conversation']` — the `conversation` service/`IConversation` still exists on alpha.2 at `@deepseek-ai/dsh-client-ui-conversation/client` (cited by A1-25 mapping and A1-27 recipe); no corridor card removes it. (The `conversation` slot move under root-scoped `main` is a 0.1.5-alpha.2 change — outside this corridor.)
- `src/client/Pet.tsx:1` — empty exported component; no host/client API consumption; no card hit. A1-29 (MarkdownText labels) and A1-28 (composer DOM) require `MarkdownText`/composer-DOM usage — absent here.
- No Host half, no subagents, no settings, no events, no custom routes, no subprocess — A1-08, A1-20, A1-21, A2-08, A2-10 etc. are non-hits by inspection.
- No `dsh.client.inject` in the manifest, so the A1-25 "remove `dsh-client-runtime` from `dsh.client.inject`" cleanup has nothing to delete today — but the import in T1 still hits the card.

## Pending / residual risk

- The corridor cards are a curated list, not a complete API diff (per the corridor header); the target tag's actual package exports are authoritative — final import specifiers (`useChat` availability, `remote.agentPresets` namespace name) must be confirmed against the alpha.2 generated declarations during implementation ("unconfirmed" items are marked inline).
- This is a static, read-only analysis: no build, typecheck, mount, or behavior verification was run (per the brief); nothing below "static inventory" on the API-10 validation ladder is claimed.
- Packaging/dependency work (direct dev/peer dependencies for `@deepseek-ai/cordis`, `dsh-client-ui-chat`, `dsh-api-remotes`, and declaration owners found via `skipLibCheck: false`) is described but not performed.

## Rollback

Not applicable — no file under the fixture or anywhere in the benchmark repository was modified; the only write is this report.

## Summary table

| # | Hit location | Old surface | Plane | Card | Target action |
|---|---|---|---|---|---|
| T1 | src/client/index.ts:1 | `ClientContext` from `@deepseek-ai/dsh-client-runtime/client` | Web Client | DSH-0.1.2-A1-25 (+API-10) | `Context as ClientContext` from `@deepseek-ai/cordis` + owning-package type deps |
| T2 | src/client/index.ts:10 | `__ModuleLoader__.load('pet-legacy-bundle', …)` vs name `dsh-pet-session-bench` | Web Client | DSH-0.1.2-A1-26 | registration id := package.json name (tsdown banner PLUGIN_ID); align assembly row; dump-config check |
| T3 | src/client/index.ts:2,12-13 | flat `useSession()` `nodes[0]` | Web Client | DSH-0.1.2-A1-27 (+API-10) | `useChat` + `order`/`nodes.get(id)` keyed store; event-window via `sessions.binding(id)` for raw reads |
| T4 | src/client/index.ts:11 | `ctx.connection.api.agentPresets.list()` | Web Client | DSH-0.1.2-A1-30 (+A1-01 table, API-01; errors A2-02) | `ctx.remote.agentPresets.list()` with `inject: ['remote','remote.agentPresets']`, `RemoteResult` branching |

All four touchpoints are on the Web Client plane; the plugin has no Host half. Sources: skill `references/v0.1.2-alpha.1.md` (cards A1-25/26/27/30, A1-19), `references/v0.1.2-alpha.2.md` (A2-02, A2-03), `references/api-migration-0.1.2-alpha.2.md` (API-01, API-10), and the fixture files themselves.
