# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report

**Task**: read-only analysis of a 0.1.1-rc.2-era Web Client plugin source against target `dsh 0.1.2-alpha.2`.
**Method**: plugin-upgrade skill, Mode A (inspect). Corridor: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (edges connected via the references/README.md corridor index, not filename order). No file under the fixture was modified, created, or deleted; no build, install, or reproduction environment was created; nothing outside the designated output directory was written.

## Fixture identity

| Item | Value |
|---|---|
| Package name | `dsh-pet-session-bench` (fixture `package.json:2`) |
| Plugin version | 0.1.0, `private: true` |
| Manifest fragment | `"dsh": { "client": { "platform": "web" } }` (`package.json:6`) — already the post-rc.1 merged `dsh.client` shape, no hit |
| Declared dependencies | none (`package.json` has no `dependencies`/`peerDependencies` — relevant to T-1 below) |
| Files | `README.md`, `package.json`, `src/client/index.ts`, `src/client/Pet.tsx` |
| Plane | Web Client only (no Host half, no profile composition files, no lockfile) |

## Hits (ordered by file/line)

### T-1 · Import from the removed `@deepseek-ai/dsh-client-runtime/client`

- **File/line**: `src/client/index.ts:1` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane**: Web Client (plugin source)
- **Card**: `DSH-0.1.2-A1-25` — *`@deepseek-ai/dsh-client-runtime` package removed, client symbols migrated by domain* (breaking, touchpoints #3/#5, required-if-hit). Exact interface mapping: API-10 in `references/api-migration-0.1.2-alpha.2.md`.
- **How it breaks**: the package was deleted in alpha.1; typecheck/build report a nonexistent module. Because the fixture's `package.json` declares no dependencies at all, the old import only resolved via the aggregated runtime package's presence on the rc.2 host — on 0.1.2 there is no owner for the declaration at all.
- **Migration action**:
  1. Replace with `import type { Context as ClientContext } from '@deepseek-ai/cordis'`.
  2. Add type-only Context augmentations from the owning packages actually consumed (here: `@deepseek-ai/dsh-client-ui-chat/client` for `useChat`; `@deepseek-ai/dsh-api-session-controller/client` if `SessionBinding` types are used) and declare those owning packages as the plugin's own direct dev/peer dependencies (API-10 "Type composition and dependency ownership"; also `DSH-0.1.2-A2-03` — peer-dependency trimming means accidental hoisting cannot be relied on).
  3. Run one diagnostic typecheck with `skipLibCheck: false` to catch implicit-`any` selector drift (API-10; skill Mode C step 5).
  4. If `dsh.client.inject` ever lists `@deepseek-ai/dsh-client-runtime`, remove it — it is a runtime phantom dependency that leaves the assembly row pending / out of the boot graph (card field note). This fixture has no `dsh.client.inject` at all, so that sub-step is a no-op here.
- **Source**: alpha.1 card `DSH-0.1.2-A1-25` (cites alpha.1 release notes + `packages/client` tree with no runtime package); API-10 exact mapping table (`ClientContext` → Cordis `Context`).

### T-2 · `__ModuleLoader__.load` registration id ≠ package.json name

- **File/line**: `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', ...)`; package name is `dsh-pet-session-bench` (`package.json:2`)
- **Plane**: Web Client (client bundle registration; interacts with packaging/assembly row)
- **Card**: `DSH-0.1.2-A1-26` — *client-modules scan contract: registration id must equal the package.json name* (breaking, touchpoint #5, required-if-hit).
- **How it breaks**: 0.1.2's boot manifest keys entries/modules/plugin registrations by package name (`Entry name == package name`). Symptom is either the startup assertion `loaded without registering "<id>"`, or — more subtly — the panel silently disappears, the boot graph lacks this plugin, and logs show no plugin-related error.
- **Migration action**: align all three ids to the bare package name `dsh-pet-session-bench`:
  1. the bundle registration id passed to `__ModuleLoader__.load` (usually injected via the tsdown banner `PLUGIN_ID`) == package.json `name`;
  2. the assembly row `name` in the plugin's composition uses the bare package name (with scope when present); 0.1.1's `file:///` literal-path + short-name id form silently keeps the client half out of the graph;
  3. verify with `dsh --profile <name> --dump-config` (no pending rows) and the boot page: `window.__DSH_BOOT__.entries` contains `"id":"dsh-pet-session-bench"`, and the combo-route script contains `__ModuleLoader__.load({ id: "dsh-pet-session-bench"`.
- **Source**: alpha.1 card `DSH-0.1.2-A1-26` (cites `packages/client/modules/src/client/system.ts` registration assertion and `manifest.ts`).

### T-3 · Flat `useSession()` `nodes` snapshot read

- **File/line**: `src/client/index.ts:12–13` — `const { nodes } = useSession()`; `const first = nodes[0]` (import at `src/client/index.ts:2` from `@deepseek-ai/dsh-client-ui-chat/client`)
- **Plane**: Web Client
- **Card**: `DSH-0.1.2-A1-27` — *Session content reads now go through the SessionBinding durable event window* (breaking, touchpoint #3, required-if-hit). Exact selector/snapshot mapping: API-10 (`useSession(session => session?.nodes)` → `useChat(chat => ...)`; `ConversationSnapshot.nodes[]` → `ChatSnapshot.order` + keyed `nodes.get(id)`). Related context: `DSH-0.1.2-A1-03` (session view internals split; field note: old flat fields still readable via `views.get('chat')?.legacy` projection — staged compatibility only, not a primary surface for an alpha.2-only plugin).
- **How it breaks**: 0.1.2 no longer exposes per-session conversation-node snapshots; the plugin loads but `nodes` is `undefined`/empty and the console reports factory errors (`nodes[0]` dereference of `undefined`). Note also that in this fixture `useSession()` is invoked inside plain `apply()` rather than a React render — host hooks must run in a React context; flagged as a fixture-code observation, not a corridor card (unconfirmed which host-hook contract the original plugin relied on in rc.2).
- **Migration action** (choose by what the plugin actually needs):
  - transcript/UI-node reads: switch to `ctx.useChat((chat) => chat ? chat.order.flatMap(id => { const n = chat.nodes.get(id); return n ? [n] : [] }) : [])` (`ChatSnapshot` keyed store; API-10 minimal read shape); assistant final node via `type === 'assistant-step'` → `data.finalNode`;
  - durable session content (user messages): `sessions.binding(id)` → `SessionBinding`, read `binding.eventSource.getSnapshot().entries` (`SessionEventLikeEntry[]`), user text in `event.data.content` `{ type: 'text', text }` blocks (A1-27 recipe);
  - dual-host staged compatibility only: `views.get('chat')?.legacy` (A1-03 field note) — do not adopt as the new primary surface.
- **Source**: alpha.1 card `DSH-0.1.2-A1-27` (cites `SessionBinding` definition and `SessionEventLikeEntry` contract at the alpha.1 tag); API-10 (cites alpha.2 `ChatSnapshot`/`ChatNodeStore` and `useChat` at `packages/client/ui-chat`).

### T-4 · Removed `ctx.connection.api` face (`agentPresets.list`)

- **File/line**: `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list().then(presets => ...)`
- **Plane**: Web Client (Remote/service consumption)
- **Card**: `DSH-0.1.2-A1-30` — *Client `ctx.connection.api` face removed entirely; history/transcript reads rerouted* (breaking, touchpoint #3, required-if-hit). Successor coordinates: `DSH-0.1.2-A1-01` (`agentPreset.list` → Remote `agentPresets/list`) and API-01 Web-Client consumer ledger (`ctx.remote.agentPresets.list()`); error-flow semantics at the alpha.2 target: `DSH-0.1.2-A2-02`.
- **How it breaks**: alpha.1 removed the old apiProxy mirror face on `ctx.connection`; client calls throw. The card's field note warns that if the call site swallows the error in a catch, the UI renders "forever blank" instead of an error — this fixture's `.then(...)` with no `.catch` means the rejection surfaces as an unhandled rejection instead; either way presets never arrive.
- **Migration action**:
  1. Replace with the generated client projection: `const result = await ctx.remote.agentPresets.list()` (client Remotes assembly from `@deepseek-ai/dsh-api-remotes/client`); declare `'remote'` plus the specific namespace injection (e.g. `inject: ['remote', 'remote.agentPresets']`) instead of `connection`;
  2. handle `RemoteResult<T>` explicitly: branch on `result.ok`, then `result.error.code` — error codes are namespaced at the alpha.2 target (`agent-preset-not-found` → `agent-preset/not-found`, `internal` → `gateway/internal`, `cancelled` → `gateway/cancelled`), `error` is a `RemoteError` instance; use `isRemoteFailure` from `@deepseek-ai/dsh-api-gateway/client` only at catch boundaries, never `instanceof` (A2-02);
  3. once nothing consumes it, remove `connection` from `inject` and the type mirror so no dead face remains (A1-30 recipe).
- **Source**: alpha.1 card `DSH-0.1.2-A1-30` (cites alpha.1 `packages/client/connection/src/client/api.ts`, which now only re-exports protocol types); `DSH-0.1.2-A1-01` mapping table; `DSH-0.1.2-A2-02` (RemoteError vocabulary).

## Pre-flight summary (dsh-pet-session-bench, 0.1.1-rc.2 → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 patch | no | — | — | no `patch.yml`/patchedDependencies/monkey-patch tokens in the four fixture files |
| #2 events | no | — | — | no `ctx.on`/SessionEvent production; corridor note: A1-02 (removed) is restored by A2-01 — net no-op, and not hit anyway |
| #3 services/Remote | yes | index.ts:1, 11, 12 | A1-25, A1-30 (+A1-27, A2-02) | see T-1, T-3, T-4 |
| #4 filesystem | no | — | — | no path/DSH_HOME/readFile usage |
| #5 UI/commands/tools | yes | index.ts:1, 10, 12 | A1-25, A1-26, A1-27 | see T-1, T-2, T-3 |
| #6 custom channel | no | — | — | no HTTP/WS/DOM-channel code |
| #7 subprocess/output | no | — | — | no child_process/stdout parsing |

No-hit notes: scan scope = all 4 fixture files (full-text read); no tests, scripts, CI, vendor, or node_modules exist in the fixture. Dependency/config inventory: no lockfile, no `dsh-plugin.json`, no composition files; `package.json` declares zero dependencies (itself a gap under T-1/API-10 ownership rules).

## Corridor net state check

- `DSH-0.1.2-A1-02` (ignorable removed) vs `DSH-0.1.2-A2-01` (restored): net state at alpha.2 = retained; fixture produces no events, no action.
- No remove-then-restore field among the four hits; all four cards land on alpha.1 and remain in force at alpha.2 (A1-30's successor error semantics are refined by A2-02 — applied in T-4's action).
- alpha.2-only cards A2-03…A2-10: none hit directly by source; A2-03 informs T-1's dependency-ownership action; A2-04/05/06/08/10 non-hits (no Node workarounds, no pluginInventory consumer, no host-facts read, no composed profile mounting tool packages, no settings namespace usage).

## Report per skill structure

- **pre-existing (baseline)**: not collected — read-only Mode A inspection; no build/test environment was created (per the brief's prohibition).
- **Completed**: full read of all 4 fixture files; corridor built rc.2→alpha.1→alpha.2 from the corridor index; 4 breaking touchpoints identified and mapped to full card IDs (`DSH-0.1.2-A1-25`, `DSH-0.1.2-A1-26`, `DSH-0.1.2-A1-27`, `DSH-0.1.2-A1-30`) with exact file/line, plane, symptom, migration action, and primary-source citations taken from the card files and the alpha.2 API ledger.
- **Skipped (non-hits with evidence)**: touchpoint classes #1/#2/#4/#6/#7 (see table); cards A1-01/03/05–24/28/29/31/32 (no matching source constructs: no APIProxy host-plane use, no composer DOM, no MarkdownText, no subagent descriptors, no workspace navigation, no PTC mode, no pi-ai dependency, no settings namespace); all A2 cards except the two cross-references above.
- **Pending/residual risk**: (a) the exact rc.2 signature of `useSession` in a non-React call site is unconfirmed (closed-book; the rc.2 aggregation exports were not available locally) — regardless, the flat `nodes` read is removed at the target, so the T-3 action stands; (b) the target-tag declarations themselves are the final authority for exact new signatures (cards say "still defer to each package's actual exports at the target tag") — before implementing, verify against `dsh-v0.1.2-alpha.2` exports; (c) runtime/behavioral verification (boot graph, `__DSH_BOOT__.entries`, mount smoke) is deliberately not performed per the read-only brief; static evidence only.
- **Rollback**: nothing to roll back — zero writes outside the report file; the fixture directory is byte-identical to its delivered state.
- **Recommendations**: when the actual migration is authorized (Mode C), sequence as: fix dependency/type ownership first (T-1), then registration id (T-2), then data reads (T-3, T-4); adopt `useChat` keyed-store reads as the primary surface (not `legacy`); add client tests using the real `ChatNodeStore` shape; run one `skipLibCheck: false` pass; finally a real-profile web mount with boot-entry + registration + DOM-marker verification per the skill's runtime layer.

## Read-only discipline statement

The fixture at `...\\S4-legacy-client-imports\\environment\\fixture` was only read. No builds, installs, dependency resolution, network access, or reproduction environments were created. The only file written is this report.
