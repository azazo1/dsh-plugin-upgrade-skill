# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report (read-only)

Task: analyze the 0.1.1-rc.2-era Web Client plugin source in the fixture and list every touchpoint that breaks on dsh 0.1.2-alpha.2.

Scope/authorization: BENCHMARK-AUTH-v1 unattended run. The fixture was only read (never modified); no reproduction environment was built; no dependencies installed; nothing outside the designated output directory was written.

Fixture inspected (all files, read-only):

- `package.json`
- `README.md`
- `src/client/index.ts`
- `src/client/Pet.tsx`

## Summary

Four breaking touchpoints exist, all in `src/client/index.ts`, all on the **Web Client plane**. The mapping below is anchored to the fixture's own `README.md` ("Touchpoint hints (maintainer reference)"), which names each touchpoint together with its upgrade card ID; where a detail goes beyond that source it is marked **unconfirmed**.

## Touchpoints

### 1. Removed `@deepseek-ai/dsh-client-runtime/client` import

- **File/line:** `src/client/index.ts:1`
  ```ts
  import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
  ```
- **Plane:** Web Client (type import consumed by the plugin's client entry).
- **Card:** `DSH-0.1.2-A1-25` — `@deepseek-ai/dsh-client-runtime/client` package removal (source: fixture `README.md` touchpoint hint).
- **Migration action:** replace the `ClientContext` type import with the 0.1.2-alpha.2 client-context source (exact replacement module name: **unconfirmed** — not stated in the fixture). The `ClientContext` annotation on `apply(ctx: ClientContext)` at `src/client/index.ts:9` must move to the new import (or be dropped) together with line 1.

### 2. `__ModuleLoader__.load` registration id ≠ package name

- **File/line:** `src/client/index.ts:10`
  ```ts
  __ModuleLoader__.load('pet-legacy-bundle', () => { /* legacy bundle id, not package name */ })
  ```
- **Plane:** Web Client (module-loader registration inside the client entry).
- **Card:** `DSH-0.1.2-A1-26` — registration id must match the package.json name (source: fixture `README.md` touchpoint hint).
- **Migration action:** change the registration id from the legacy bundle id `'pet-legacy-bundle'` to the package name `'dsh-pet-session-bench'` from `package.json:2`, which is what 0.1.2-alpha.2 expects. Exact validation rule (error vs silent mismatch): **unconfirmed** — not stated in the fixture.

### 3. Flat `useSession()` `nodes` snapshot

- **File/lines:** `src/client/index.ts:12-13`
  ```ts
  const { nodes } = useSession()
  const first = nodes[0]
  ```
- **Plane:** Web Client (session-state hook usage; `useSession` imported from `@deepseek-ai/dsh-client-ui-chat/client` at `src/client/index.ts:2`).
- **Card:** `DSH-0.1.2-A1-27` — flat `useSession()` `nodes` snapshot change (source: fixture `README.md` touchpoint hint).
- **Migration action:** the flat `nodes` array destructuring no longer exists on 0.1.2-alpha.2; migrate to the new session-snapshot access (exact replacement API/shape: **unconfirmed** — not stated in the fixture).

### 4. Removed `ctx.connection.api` face

- **File/line:** `src/client/index.ts:11`
  ```ts
  ctx.connection.api.agentPresets.list().then(presets => { /* legacy connection.api face */ })
  ```
- **Plane:** Web Client (Host↔Client RPC face reached through the client context).
- **Card:** `DSH-0.1.2-A1-30` — `ctx.connection.api` face removal (source: fixture `README.md` touchpoint hint).
- **Migration action:** replace the `ctx.connection.api` call with the 0.1.2-alpha.2 replacement face (e.g. the package-private `host.call(...)` JSON-method channel; exact replacement name and `agentPresets.list` equivalent: **unconfirmed** — not stated in the fixture).

## Files with no breaking touchpoints

- `src/client/Pet.tsx` — empty component, no dsh APIs.
- `package.json` — `"dsh": { "client": { "platform": "web" } }` manifest block; no collision identified in the fixture sources (**unconfirmed** beyond the fixture's four listed touchpoints).

## Read-only discipline

- Fixture files: read only; no create/modify/delete/rename anywhere in the fixture or the benchmark repository.
- No builds, installs, network access, or reproduction environments.
- Only output written: this report under the designated benchmark-runs output directory.
