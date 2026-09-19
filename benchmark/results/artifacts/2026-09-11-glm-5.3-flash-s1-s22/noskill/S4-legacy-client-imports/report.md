# Migration Touchpoint Report · dsh-pet-session-bench (0.1.1-rc.2 → 0.1.2-alpha.2)

Static, read-only scan of `E:/deepseek-harness/dsh-plugin-upgrade-skill/benchmark/tasks/S4-legacy-client-imports/environment/fixture` (brief's `/app/fixture/`). No file was modified, created, or deleted; no reproduction environment was built; no network access.

## Sources of evidence

- `fixture/README.md` (line 3): "four touchpoints that break on dsh 0.1.2-alpha.2".
- `fixture/README.md` (line 5, maintainer-reference hints): names the four known changes with their full upgrade card IDs: the `@deepseek-ai/dsh-client-runtime/client` package removal (DSH-0.1.2-A1-25), `__ModuleLoader__.load` registration id ≠ package.json name (DSH-0.1.2-A1-26), the flat `useSession()` `nodes` snapshot (DSH-0.1.2-A1-27), and the removed `ctx.connection.api` face (DSH-0.1.2-A1-30).
- `fixture/package.json`, `fixture/src/client/index.ts`, `fixture/src/client/Pet.tsx` (quoted per touchpoint below).

No other change-card documentation exists inside the fixture (closed-book brief), so each card ID below is sourced from the fixture README line 5; per-card migration actions beyond what that line states are marked accordingly.

## Touchpoints

### 1. Import of removed package `@deepseek-ai/dsh-client-runtime/client`

- **File/line:** `src/client/index.ts` line 1 — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane:** Web Client (plugin client entry).
- **Card:** `DSH-0.1.2-A1-25` — the `@deepseek-ai/dsh-client-runtime/client` package is removed in 0.1.2-alpha.2 (fixture README line 5).
- **Migration action:** Re-point the `ClientContext` type import to its 0.1.2 home (per the card, the package no longer exists; the type must come from the replacement module documented on the card). Unconfirmed: the exact replacement module name is not stated in the fixture; verify against the 0.1.2-alpha.2 card/changelog before editing.

### 2. `__ModuleLoader__.load` registration id does not match package.json name

- **File/line:** `src/client/index.ts` lines 5 and 10 — `declare const __ModuleLoader__...` and `__ModuleLoader__.load('pet-legacy-bundle', () => { /* legacy bundle id, not package name */ })`. The id `'pet-legacy-bundle'` differs from `package.json` line 2 `"name": "dsh-pet-session-bench"`.
- **Plane:** Web Client (plugin registration).
- **Card:** `DSH-0.1.2-A1-26` — `__ModuleLoader__.load` registration id must equal the package.json name (fixture README line 5).
- **Migration action:** Change the first argument to the package name `'dsh-pet-session-bench'` (or derive it from the package identity) so registration matches `package.json`.

### 3. Flat `useSession()` `nodes` snapshot

- **File/line:** `src/client/index.ts` lines 2, 12–13 — `import { useSession } from '@deepseek-ai/dsh-client-ui-chat/client'`; `const { nodes } = useSession()`; `const first = nodes[0]`.
- **Plane:** Web Client (UI hook consumption).
- **Card:** `DSH-0.1.2-A1-27` — the flat `useSession()` `nodes` snapshot changed in 0.1.2-alpha.2 (fixture README line 5).
- **Migration action:** Update the session-state consumption to the new `nodes` shape/API introduced by the card (destructuring `nodes` as a flat array no longer matches). Unconfirmed: the exact new shape (nesting/selector) is not stated in the fixture; confirm from the card before rewriting lines 12–13.

### 4. Removed `ctx.connection.api` face

- **File/line:** `src/client/index.ts` line 11 — `ctx.connection.api.agentPresets.list().then(presets => { /* legacy connection.api face */ })`.
- **Plane:** Web Client (plugin code calling the client context connection face).
- **Card:** `DSH-0.1.2-A1-30` — the `ctx.connection.api` face is removed (fixture README line 5).
- **Migration action:** Replace the `ctx.connection.api.agentPresets.list()` call with the 0.1.2 successor access path for agent presets (per the card, the face no longer exists). Unconfirmed: the exact successor API is not stated in the fixture.

## Completeness

Exactly four break-on-upgrade touchpoints exist in the fixture, matching the count declared in `fixture/README.md` line 3 ("four touchpoints"). `src/client/Pet.tsx` (a stub `export function Pet() {}`, line 1) and `package.json` carry no 0.1.2 colliding pattern. Host plane: no Host-side source exists in the fixture; all four touchpoints are Web Client plane. No additional legacy imports, loader calls, session hook uses, or connection-face accesses were found beyond those listed above.

## Read-only discipline

Fixture inspected only via read operations; no write, edit, or delete under the fixture tree; report written only to the designated output directory outside the fixture.
