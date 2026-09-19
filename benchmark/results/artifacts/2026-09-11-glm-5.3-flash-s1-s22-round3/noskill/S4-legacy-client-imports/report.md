# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report

Fixture (read-only, unchanged): `E:/deepseek-harness/dsh-plugin-upgrade-skill/benchmark/tasks/S4-legacy-client-imports/environment/fixture` — a dsh 0.1.1-rc.2 era Web Client plugin (`package.json`: `"name": "dsh-pet-session-bench"`, `"private": true`, `"dsh": { "client": { "platform": "web" } }`).

Files scanned: `package.json`, `README.md`, `src/client/index.ts`, `src/client/Pet.tsx`.

## Touchpoints that break on dsh 0.1.2-alpha.2

### 1. Import of the removed `@deepseek-ai/dsh-client-runtime/client` package
- **Location:** `src/client/index.ts`, line 1 — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane:** Web Client (plugin client entry)
- **Upgrade card:** `DSH-0.1.2-A1-25` — removal of the `@deepseek-ai/dsh-client-runtime/client` package
- **Migration action:** replace the package import with the successor `ClientContext` type export defined by card `DSH-0.1.2-A1-25` (exact successor module not present in the fixture — unconfirmed); the import is type-only, so it is a compile-time break only.

### 2. `__ModuleLoader__.load` registration id ≠ `package.json` name
- **Location:** `src/client/index.ts`, lines 8 and 10 — `declare const __ModuleLoader__: { load: (id: string, fn: () => void) => void }` and the call `__ModuleLoader__.load('pet-legacy-bundle', ...)` (in-source comment: `/* legacy bundle id, not package name */`)
- **Plane:** Web Client (plugin runtime registration)
- **Upgrade card:** `DSH-0.1.2-A1-26` — client registration id must match `package.json` name
- **Migration action:** change the id passed to `__ModuleLoader__.load` from `'pet-legacy-bundle'` to `'dsh-pet-session-bench'` (the `name` in `package.json`), per card `DSH-0.1.2-A1-26`.

### 3. Flat `useSession()` `nodes` snapshot
- **Location:** `src/client/index.ts`, line 14 — `const { nodes } = useSession()` and line 15 — `const first = nodes[0]` (`useSession` imported from `@deepseek-ai/dsh-client-ui-chat/client` at line 2)
- **Plane:** Web Client (UI-chat React hook consumer)
- **Upgrade card:** `DSH-0.1.2-A1-27` — the flat `nodes` array snapshot returned by `useSession()` changed shape on 0.1.2-alpha.2
- **Migration action:** adapt to the new snapshot shape defined by card `DSH-0.1.2-A1-27` (exact new shape not present in the fixture — unconfirmed); `nodes[0]` direct indexing is the code that must be updated.

### 4. Removed `ctx.connection.api` face
- **Location:** `src/client/index.ts`, line 13 — `ctx.connection.api.agentPresets.list().then(presets => { /* legacy connection.api face */ })`
- **Plane:** Web Client (ClientContext connection API face); depends on the `inject = ['slots', 'conversation']` declaration at line 7
- **Upgrade card:** `DSH-0.1.2-A1-30` — the `ctx.connection.api` face was removed
- **Migration action:** replace the `ctx.connection.api.agentPresets.list()` call with the successor access path defined by card `DSH-0.1.2-A1-30` (exact successor not present in the fixture — unconfirmed); this is a runtime break (property access throws/returns undefined), not just a type error.

## Non-breaking notes
- `src/client/Pet.tsx` (exported `Pet` component, imported at `index.ts` line 3) contains no runtime touchpoints; no cards apply.
- `package.json` `dsh.client.platform: "web"` and `private: true` match the current packaging conventions for a Web Client plugin; no collision found.

## Card-mapping provenance
Card IDs `DSH-0.1.2-A1-25`, `-26`, `-27`, `-30` are sourced from the fixture's own `README.md` touchpoint hints (maintainer reference included in the pack); each ID is corroborated by matching in-source evidence in `src/client/index.ts`. Per the closed-book constraint, the detailed migration steps inside each card (successor module names, new snapshot shape, replacement API face) are **unconfirmed** — the card texts themselves were not available in the fixture.

## Read-only discipline
No file under the fixture was modified, created, or deleted; no build, dependency install, reproduction environment, or network access was performed. This report is the only file written.
