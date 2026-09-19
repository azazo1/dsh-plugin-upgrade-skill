# S4 · Migration Touchpoint Report — dsh-pet-session-bench (0.1.1-rc.2 → 0.1.2-alpha.2)

Mode A/C inspection (read-only). Fixture inspected at the local evidence pack
`E:/deepseek-harness/dsh-plugin-upgrade-skill/benchmark/tasks/S4-legacy-client-imports/environment/fixture`
(the brief's `/app/fixture/`). No file under the fixture was modified, created, or deleted.
No build, install, or reproduction environment was created. Card IDs and actions come only
from the installed `plugin-upgrade` skill references (`references/v0.1.2-alpha.1.md`,
`references/v0.1.2-alpha.2.md`, `references/api-migration-0.1.2-alpha.2.md`).

## Source identity

- Plugin: `dsh-pet-session-bench` v0.1.0, `"private": true`, `"type": "module"`, client half declared via `"dsh": { "client": { "platform": "web" } }` (`package.json`).
- Plane: Web Client plugin (browser half only; no Host entry, no cordis.patch.yml in the pack).
- Source cohort: dsh 0.1.1-rc.2 era; target: dsh 0.1.2-alpha.2. Corridor: rc.2 → alpha.1 (cards `DSH-0.1.2-A1-*`) then alpha.1 → alpha.2 (cards `DSH-0.1.2-A2-*`).

## Files scanned (complete inventory)

- `README.md` (fixture notes only, no runtime code)
- `package.json` (6 lines)
- `src/client/index.ts` (14 lines — all executable touchpoints live here)
- `src/client/Pet.tsx` (1 line: `export function Pet() {}` — no imports, no DSH APIs, no touchpoints)

## Confirmed breaking touchpoints (4)

### T1 · Import of the removed `@deepseek-ai/dsh-client-runtime/client` package

- **Location**: `src/client/index.ts:1` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane**: Web Client
- **Card**: `DSH-0.1.2-A1-25` (rc.2 → alpha.1)
- **Evidence / symptom**: alpha.1 deleted the `packages/client` runtime package; the card's symptom is "build/typecheck report missing exports or a nonexistent module; at runtime the plugin does not enter the boot graph or its assembly row stays pending forever".
- **Migration action**: `ClientContext` maps to `import type { Context as ClientContext } from '@deepseek-ai/cordis'` (verified mapping table in card A1-25). Also declare direct dev/peer dependencies for every package whose declarations the plugin consumes (card A1-25 cleanup and API-10 §"Type composition and dependency ownership"); the fixture's `package.json` currently declares no dependencies at all.

### T2 · Client bundle registration id ≠ package.json name

- **Location**: `src/client/index.ts:5` (`declare const __ModuleLoader__: { load: (id: string, fn: () => void) => void }`) and `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', ...)` with the inline comment "legacy bundle id, not package name"
- **Plane**: Web Client
- **Card**: `DSH-0.1.2-A1-26` (rc.2 → alpha.1)
- **Evidence / symptom**: 0.1.2's boot manifest keys entries/modules/plugin registrations by package name (`Entry name == package name`). Symptoms: startup assertion `loaded without registering "<id>"`, or the plugin silently missing from the boot graph.
- **Migration action**: the registration id must equal the `package.json` `name` — i.e. `'dsh-pet-session-bench'`, not `'pet-legacy-bundle'`. All three ids (bundle registration id, assembly row name, package.json name) must agree; verify via `window.__DSH_BOOT__.entries` containing `"id":"dsh-pet-session-bench"` after a real web cold boot.

### T3 · Flat `useSession()` `nodes` snapshot read

- **Location**: `src/client/index.ts:2` (`import { useSession } from '@deepseek-ai/dsh-client-ui-chat/client'`), line 12 (`const { nodes } = useSession()`), line 13 (`const first = nodes[0]`)
- **Plane**: Web Client
- **Card**: `DSH-0.1.2-A1-27` (rc.2 → alpha.1); exact replacement surface in the alpha.2 API ledger **API-10** ("Web Client runtime unbundling, keyed chat snapshots, and command attachment parameters"), cross-referenced by card A1-03's field notes.
- **Evidence / symptom**: per-session conversation-node snapshots are no longer exposed; on alpha.2 `ChatSnapshot.nodes` is a keyed store (`order` + `nodes.get(id)`), not the old flat `ConversationNode[]`. API-10's one-page conclusion lists "read the flat `nodes[]` via `useSession`" as a break.
- **Migration action**: read via `useChat(chat => ...)`, iterate `ChatSnapshot.order` and call `snapshot.nodes.get(id)` per id (minimal read shape in API-10, importing `ChatSnapshot` from `@deepseek-ai/dsh-client-ui-chat/client`). `snapshot.legacy.nodes` is staged compatibility only and must not become the primary surface for an alpha.2-only plugin.

### T4 · Removed `ctx.connection.api` face

- **Location**: `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list().then(presets => { /* legacy connection.api face */ })`
- **Plane**: Web Client
- **Card**: `DSH-0.1.2-A1-30` (rc.2 → alpha.1); call-site re-mapping from `DSH-0.1.2-A1-01` (APIProxy → Remote table: `agentPreset.list` → `agentPresets/list`)
- **Evidence / symptom**: alpha.1 removed the apiProxy mirror face on `ctx.connection`; client calls throw. Card A1-30 warns the break renders "forever blank" when a catch swallows the error — a no-crash smoke cannot catch it (here the rejection would surface only in the console).
- **Migration action**: call the Remote projection `ctx.remote.agentPresets.list()` (generated declarations via `@deepseek-ai/dsh-api-remotes/client`; declare the needed Remote contributions in the client inject). The alpha.2 return is a `RemoteResult<T>`: resolve the result branch and handle `result.error.code` per **`DSH-0.1.2-A2-02`** (alpha.1 → alpha.2: errors become `RemoteError` instances with namespaced codes; never branch on old dotted code strings or use `instanceof`). Once no call site consumes the old face, remove `connection` from the inject list (card A1-30: "leave no dead face").

## Inject list note

`src/client/index.ts:7` declares `export const inject = ['slots', 'conversation']`. After the T4 migration to `ctx.remote`, verify each remaining inject name against the target tag's mounted client services and add any service the migrated code requires. This is a review checkpoint, not an independently carded break — no fabricated card is asserted here.

## Cards checked and confirmed non-hits (with evidence)

- `DSH-0.1.2-A1-26` assembly-row id: no `cordis.patch.yml` / assembly row exists in the pack, so only the bundle registration id (T2) is in scope from that card.
- `DSH-0.1.2-A1-28` (composer `<textarea>` → contenteditable): no composer DOM manipulation in any of the 4 source files — non-hit.
- `DSH-0.1.2-A1-29` (`MarkdownText` labels): `@deepseek-ai/dsh-client-ui-primitives` is not imported — non-hit.
- `DSH-0.1.2-A1-32` (`IWorkspaces` navigation → `ctx.uiWorkspace`): no `ctx.workspaces` usage — non-hit.
- `DSH-0.1.2-A1-06` (PTC rename), A1-20 (user-questions), A1-21 (resolveSessionPreset), A1-22 (isTokenDelta), A1-31 (subagent descriptor): no corresponding identifiers in the pack — non-hits.
- `DSH-0.1.2-A2-01` (ignorable events), A2-05 (plugin inventory), A2-06 (`$host` facts), A2-08 (sessionProjections peers), A2-10 (settings namespace): no session-event production, inventory consumption, `$host` reads, tool-package composition, or `ctx.settings` usage — non-hits.
- `DSH-0.1.2-A2-03` (peer trimming) applies conditionally: the fixture declares no dependencies today; after re-pointing type imports (T1/T3), the consumed packages must be added as direct dev/peer dependencies. `DSH-0.1.2-A2-04` (Node loader fix) is host-side — not a plugin source change.

## Pending / residual risk

- No lockfile or build manifest is present in the pack, so dependency-cohort verification (rollup R-01 `link:` staging while the cohort is unpublished) could not be assessed from artifacts — unconfirmed, to be resolved at migration time.
- No runtime verification was performed (forbidden by the brief): the T2/T3/T4 fixes require a real `dsh web` cold boot with boot-manifest + registration checks (cards A1-19/A1-26 verification steps) before being called complete.

## Read-only discipline

Fixture tree listed via glob (4 files) and read in place; zero writes, edits, deletes, installs, or builds were performed against the fixture. This report is the only file written by this task.
