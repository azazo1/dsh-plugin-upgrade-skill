# S4 · Legacy Client Runtime Touchpoints — Migration Report

**Task:** read-only collision scan of the 0.1.1-rc.2-era Web Client plugin in the fixture against dsh 0.1.2-alpha.2.
**Method:** full inspection of every fixture file (README.md, package.json, src/client/index.ts, src/client/Pet.tsx). No file under the fixture was modified, created, or deleted; no reproduction environment was built. This is a closed-book analysis: the only sources used are the fixture files themselves. Card IDs and change descriptions below are sourced from the fixture's own maintainer reference (fixture README.md, line 7); beyond that mapping, card details are **unconfirmed** because no change-card catalogue was available inside the fixture.

## Inventory scanned

| File | Lines | Notes |
|---|---|---|
| package.json | 7 | name `dsh-pet-session-bench`, private, ESM, dsh client platform web |
| src/client/index.ts | 14 | plugin entry; all four breaking touchpoints live here |
| src/client/Pet.tsx | 1 | stub component, no touchpoints |
| README.md | 7 | fixture description (not plugin code) |

## Touchpoints that break on 0.1.2-alpha.2

All four touchpoints are in `src/client/index.ts` and affect the **Web Client plane** (the plugin is a client-only plugin per `package.json` `dsh.client.platform = "web"`; there is no Host half).

### 1. Import from removed `@deepseek-ai/dsh-client-runtime/client` package

- **File/line:** `src/client/index.ts:1` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane:** Web Client (plugin type dependency)
- **Card:** `DSH-0.1.2-A1-25` — removal of the `@deepseek-ai/dsh-client-runtime/client` package (source: fixture README.md:7)
- **Why it breaks:** the package no longer exists in 0.1.2-alpha.2, so the import (even a type-only import) fails to resolve at build/typecheck time and `ClientContext` has no source.
- **Migration action:** replace the import with the 0.1.2-alpha.2 successor client context module (re-exported from the new client runtime entry — exact new specifier **unconfirmed**, not present in fixture). Update the `apply(ctx: ClientContext)` annotation at `index.ts:9` accordingly.

### 2. `__ModuleLoader__.load` registration id ≠ package.json name

- **File/line:** `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', ...)`
- **Plane:** Web Client (plugin registration)
- **Card:** `DSH-0.1.2-A1-26` (source: fixture README.md:7)
- **Why it breaks:** the registration id `pet-legacy-bundle` does not match the package name `dsh-pet-session-bench` declared in `package.json:2`. 0.1.2-alpha.2 enforces that the module-loader registration id equals the package name; the mismatched legacy bundle id is rejected.
- **Migration action:** change the call to `__ModuleLoader__.load('dsh-pet-session-bench', ...)` (the exact `package.json` `name`), keeping the dsh/platform metadata in `package.json` as-is.

### 3. Flat `useSession()` `nodes` snapshot

- **File/line:** `src/client/index.ts:12-13` — `const { nodes } = useSession()` then `const first = nodes[0]`
- **Plane:** Web Client (UI/session state hook)
- **Card:** `DSH-0.1.2-A1-27` (source: fixture README.md:7)
- **Why it breaks:** the flat `nodes` array snapshot was restructured in 0.1.2-alpha.2; `nodes` is no longer exposed as a flat array on the hook's return, so the destructure yields `undefined` and `nodes[0]` fails.
- **Migration action:** migrate to the new session-snapshot accessor for node list access — the 0.1.2-alpha.2 `useSession()` return fields (exact new field name/shape **unconfirmed**, not present in fixture) — and re-derive `first` from the new structure instead of indexing a flat array.

### 4. Removed `ctx.connection.api` face

- **File/line:** `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list().then(...)`
- **Plane:** Web Client (Host↔Client RPC face)
- **Card:** `DSH-0.1.2-A1-30` (source: fixture README.md:7)
- **Why it breaks:** the `connection.api` face was removed in 0.1.2-alpha.2; `ctx.connection.api` is undefined and the property access on `.agentPresets` throws at plugin activation.
- **Migration action:** call the presets listing through the replacement client→Host call surface introduced in 0.1.2-alpha.2 (exact replacement API name **unconfirmed**, not present in fixture). If the replacement is async JSON-RPC, keep the `.then()` consumption pattern.

## Non-touchpoints (verified clean)

- `src/client/index.ts:2` — `import { useSession } from '@deepseek-ai/dsh-client-ui-chat/client'`: the module specifier itself is not listed as removed in the fixture reference; only its `nodes` return field changed (covered by card A1-27). Unconfirmed whether the package name is unchanged in 0.1.2-alpha.2.
- `src/client/index.ts:7` — `export const inject = ['slots', 'conversation']`: standard Cordis plugin declaration, no collision identified in fixture evidence.
- `src/client/Pet.tsx` — empty stub, nothing to migrate.
- `package.json` — `dsh.client.platform = "web"` metadata; no collision identified in fixture evidence (beyond being the authority for the A1-26 name match).

## Summary table

| # | Location | Plane | Card | Action |
|---|---|---|---|---|
| 1 | src/client/index.ts:1 | Web Client | DSH-0.1.2-A1-25 | Replace removed `dsh-client-runtime/client` import with successor client context module |
| 2 | src/client/index.ts:10 | Web Client | DSH-0.1.2-A1-26 | Use package name `dsh-pet-session-bench` as `__ModuleLoader__.load` id |
| 3 | src/client/index.ts:12-13 | Web Client | DSH-0.1.2-A1-27 | Migrate off flat `useSession().nodes` to new snapshot structure |
| 4 | src/client/index.ts:11 | Web Client | DSH-0.1.2-A1-30 | Replace removed `ctx.connection.api` calls with new client→Host RPC surface |

## Read-only discipline

No writes were performed inside the fixture or anywhere in the benchmark repository; the only file created is this report in the designated output directory. No builds, installs, or external services were used.
