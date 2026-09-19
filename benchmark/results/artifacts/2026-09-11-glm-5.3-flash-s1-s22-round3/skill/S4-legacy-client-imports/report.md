# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report

- **Source**: read-only inspection of the S4 fixture (dsh 0.1.1-rc.2-era Web Client plugin `dsh-pet-session-bench` 0.1.0, `"private": true`).
- **Target corridor**: dsh `0.1.1-rc.2 → 0.1.2-alpha.1 → 0.1.2-alpha.2`, per the plugin-upgrade skill's version-corridor metadata (`references/v0.1.1-rc.2.md`, `references/v0.1.2-alpha.1.md`, `references/v0.1.2-alpha.2.md`).
- **Mode**: A · inspect (read-only). No file under the fixture was modified, created, or deleted; no build, install, or reproduction environment was created. All cards below are quoted from the skill's reference card sets (no fabricated cards).
- **Fixtures inspected**: `package.json`, `README.md`, `src/client/index.ts`, `src/client/Pet.tsx`.

---

## 1. Breaking touchpoints (must fix on 0.1.2-alpha.2)

### 1.1 `src/client/index.ts:1` — import from the removed `@deepseek-ai/dsh-client-runtime/client`

```ts
import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
```

- **Plane**: Web Client (plugin client bundle).
- **Card**: `DSH-0.1.2-A1-25` — "`@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain" (breaking, required-if-hit, touches #3/#5). The package was deleted from `packages/client` in alpha.1; the verified mapping table sends `Context` (client ctx, alias `ClientContext`) to `import type { Context as ClientContext } from '@deepseek-ai/cordis'`.
- **Breakage**: build/typecheck report a nonexistent module/missing exports; at runtime the plugin never enters the boot graph with no explicit error.
- **Migration action**: import `ClientContext` as `Context` from `@deepseek-ai/cordis`; audit the whole `dsh.client` dependency set — if other symbols from this package existed they would remap per the A1-25 table (none others appear in this fixture).

### 1.2 `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', …)` registration id ≠ package.json name

```ts
__ModuleLoader__.load('pet-legacy-bundle', () => { /* legacy bundle id, not package name */ })
```

- **Plane**: Web Client (plugin registration/boot graph).
- **Card**: `DSH-0.1.2-A1-26` — "client-modules scan contract: registration id must equal the package.json name" (breaking, required-if-hit, touchpoint #5). The boot manifest keys entries/modules/plugin registrations by package name (`Entry name == package name`); the bundle's `__ModuleLoader__.load` id must equal `package.json` `name`.
- **Breakage**: startup assertion `loaded without registering "<id>"`, or the silent variant — the boot graph lacks this plugin and the panel silently disappears with no plugin-related error in the logs.
- **Migration action**: change the registration id from `'pet-legacy-bundle'` to the exact package name `'dsh-pet-session-bench'` (usually via the tsdown `PLUGIN_ID` banner injection), and verify `window.__DSH_BOOT__.entries` contains `"id":"dsh-pet-session-bench"` and the combo route serves `__ModuleLoader__.load({ id: "dsh-pet-session-bench"`.

### 1.3 `src/client/index.ts:12–13` — flat `useSession()` `nodes` snapshot read

```ts
const { nodes } = useSession()
const first = nodes[0]
```

- **Plane**: Web Client (session-content consumption).
- **Cards**: `DSH-0.1.2-A1-27` — "Session content reads now go through the SessionBinding durable event window" (breaking, required-if-hit, touchpoint #3): 0.1.2 no longer exposes per-session conversation-node snapshots (`session.getSnapshot().nodes` is undefined/empty; console factory errors); reads move to `sessions.binding(id)` → `binding.eventSource.getSnapshot().entries`. The skill's alpha.2 API ledger [API-10] confirms the Web Client runtime unbundling: "read via `useChat` with `order + nodes.get()`" instead of the flat `nodes[]` via `useSession`.
- **Breakage**: the plugin loads but the transcript read is broken — `nodes` is undefined/empty, with console factory errors (classic "loads but half its functionality is broken").
- **Migration action**: replace the flat `useSession().nodes[0]` read with the keyed chat surface (`useChat` + `order` + `nodes.get(id)`) or, for direct session-content reads, the `SessionBinding` durable event window (`SessionBinding`/`SessionEventLikeEntry` from `@deepseek-ai/dsh-api-session-controller/client`). Note the fixture calls `useSession()` inside a plain `apply()` function rather than a React component/hook context — flagged as an additional latent defect of the legacy pattern, unconfirmed against a specific card.

### 1.4 `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list()` on the removed `connection.api` face

```ts
ctx.connection.api.agentPresets.list().then(presets => { /* legacy connection.api face */ })
```

- **Plane**: Web Client (Host API consumption).
- **Cards**:
  - `DSH-0.1.2-A1-30` — "Client `ctx.connection.api` face removed entirely; history/transcript reads rerouted" (breaking, required-if-hit, touchpoint #3): alpha.1 removed the old apiProxy mirror face on `ctx.connection`; client calls throw. If the error is swallowed in a catch, the UI renders forever blank and a no-crash smoke cannot catch it.
  - `DSH-0.1.2-A1-01` — "APIProxy removed, Host/Web Client calls moved to `@Remote`" (breaking, touchpoint #3): the underlying `agentPreset.list` operation becomes the Remote method `agentPresets/list` (called as `ctx.remote.agentPresets.list(...)`), with generated type mounts via `@deepseek-ai/dsh-api-remotes/client`; on alpha.2, failure handling follows `DSH-0.1.2-A2-02` (unary calls return `RemoteResult<T>`; branch on `result.ok`, handle `result.error.code` namespaces such as `agent-preset/not-found`).
- **Breakage**: `ctx.connection.api` is `undefined` on alpha.1+ hosts — the call throws immediately; inside a promise chain without a rejection handler this fails silently.
- **Migration action**: move the preset list read to `ctx.remote.agentPresets.list()` (declare the Remote namespace injections and `@deepseek-ai/dsh-api-remotes/client` type mounts), handle `RemoteResult` per A2-02, and — per A1-30 — remove `connection`-style dead-face residue once no client code consumes it.

---

## 2. Explicitly checked, no card hit

- `package.json` (`"dsh": { "client": { "platform": "web" } }`): the `dsh.client` declaration that enters the plugin into the browser roster is present (required by the A1-01 field note). No lockfile/dependency cohort rows exist in the fixture (no `dependencies` block), so no cohort-mixing or peer-trim card (e.g. `DSH-0.1.2-A2-03`) applies.
- `src/client/index.ts:7` `export const inject = ['slots', 'conversation']`: client-plane injections; no corridor card removes these names. (Not verified against target-tag type declarations — static inspection only; runtime injection resolution was not executed, per read-only constraints.)
- `src/client/Pet.tsx`: a plain component with no imports; no touchpoint.
- `README.md`: fixture documentation only.
- Other alpha.1/alpha.2 cards (A1-02 ignorable events, A1-06 PTC rename, A1-08 auth, A1-20 user-questions, A1-21 agent-presets `resolveSessionPreset`, A1-22 `isTokenDelta`, A1-28 composer, A1-29 `MarkdownText`, A1-31/32, A2-01…A2-08, A2-10): no intersecting touchpoint in the fixture source.

## 3. Residual risk / pending items

- No build, typecheck, or mount verification was run (closed-book, read-only discipline); the findings are static-analysis grade. The Skill's Mode A ladder (build → real mount → `__DSH_BOOT__.entries` check) remains to be executed at migration time.
- Whether the target-tag `useSession`/`useChat` exact export names and signatures match the API-10 recipe is to be confirmed against the packed declarations of `@deepseek-ai/dsh-client-ui-chat` at the alpha.2 tag (card guidance says "defer to each package's actual exports at the target tag"); not verifiable offline here.
- If the migration also bumps `dsh.client` peer declarations, the alpha.2 field note about `skipLibCheck: false` diagnostics (A2-03) applies to find declaration owners turned implicit `any`.

## Summary table

| # | File:Line | Plane | Card ID | Breaks | Action |
|---|---|---|---|---|---|
| 1 | src/client/index.ts:1 | Web Client | DSH-0.1.2-A1-25 | removed `dsh-client-runtime/client` package | import `ClientContext` from `@deepseek-ai/cordis` |
| 2 | src/client/index.ts:10 | Web Client | DSH-0.1.2-A1-26 | registration id ≠ package.json name | `__ModuleLoader__.load('dsh-pet-session-bench', …)` |
| 3 | src/client/index.ts:12–13 | Web Client | DSH-0.1.2-A1-27 (+ API-10) | flat `useSession().nodes` snapshot removed | keyed `useChat` `order + nodes.get(id)` / SessionBinding event window |
| 4 | src/client/index.ts:11 | Web Client | DSH-0.1.2-A1-30, DSH-0.1.2-A1-01 (+ DSH-0.1.2-A2-02) | `ctx.connection.api` face removed | `ctx.remote.agentPresets.list()` with `RemoteResult` handling |

All four breakages were independently hinted in the fixture's own `README.md` (touchpoint hints list), and each is mapped above only to cards that exist verbatim in the skill's reference card sets. Nothing was fabricated; read-only discipline was respected — no fixture file was modified and no reproduction environment was built.
