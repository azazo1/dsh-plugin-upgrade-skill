# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report

**Scope:** read-only analysis of `environment/fixture/` (dsh 0.1.1-rc.2-era Web Client plugin) against target **dsh 0.1.2-alpha.2**.
**Method:** closed-book. Sources used: the fixture's own files, including `fixture/README.md` (which is inside the fixture and states the four breaking-change cards). No network, no build, no reproduction environment. Fixture untouched.

## Files scanned (complete)

- `fixture/package.json` — name `dsh-pet-session-bench`, `dsh.client.platform = "web"`
- `fixture/README.md` — fixture description + maintainer touchpoint hints
- `fixture/src/client/index.ts` (14 lines) — the entire plugin client entry
- `fixture/src/client/Pet.tsx` — stub component, no upgrade-relevant touchpoints

## Touchpoints that break on 0.1.2-alpha.2

### 1. Import of removed `@deepseek-ai/dsh-client-runtime/client`

- **File/line:** `src/client/index.ts:1` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane:** Web Client (also blocks the plugin's typecheck/build)
- **Card:** `DSH-0.1.2-A1-25` — removal of the `@deepseek-ai/dsh-client-runtime/client` package (source: `fixture/README.md`, "Touchpoint hints")
- **Why it breaks:** the package no longer exists in 0.1.2-alpha.2, so the import (even type-only) fails to resolve.
- **Migration action:** replace the `ClientContext` import with the 0.1.2-alpha.2 client runtime's supported entry point and update the `apply(ctx: ClientContext)` signature accordingly. **Unconfirmed:** the exact replacement package/specifier path — not verifiable from the fixture (closed book).

### 2. `__ModuleLoader__.load` registration id ≠ package.json name

- **File/line:** `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', ...)`
- **Plane:** Web Client (plugin module registration)
- **Card:** `DSH-0.1.2-A1-26` — loader registration id must match the package name (source: `fixture/README.md`)
- **Why it breaks:** the registered id `'pet-legacy-bundle'` does not equal the package name `dsh-pet-session-bench` (`package.json:2`); 0.1.2-alpha.2 rejects the mismatch.
- **Migration action:** change the registration id to the package name: `__ModuleLoader__.load('dsh-pet-session-bench', ...)` (or derive it from the build, not a hardcoded literal).

### 3. Flat `useSession()` `nodes` snapshot

- **File/line:** `src/client/index.ts:12–13` — `const { nodes } = useSession()`; `const first = nodes[0]`
- **Plane:** Web Client (UI/session state consumption)
- **Card:** `DSH-0.1.2-A1-27` — the flat `nodes` snapshot shape changed (source: `fixture/README.md`)
- **Why it breaks:** the destructured flat `nodes` array shape is no longer the 0.1.2-alpha.2 session snapshot shape; `nodes[0]` reads a stale/removed structure.
- **Migration action:** migrate to the 0.1.2-alpha.2 session-snapshot API from `@deepseek-ai/dsh-client-ui-chat/client` (import at `index.ts:2` is itself unaffected per available sources). **Unconfirmed:** the exact new snapshot field names/structure — not verifiable from the fixture.

### 4. Removed `ctx.connection.api` face

- **File/line:** `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list().then(...)`
- **Plane:** Web Client (client→host RPC face)
- **Card:** `DSH-0.1.2-A1-30` — the `ctx.connection.api` face was removed (source: `fixture/README.md`)
- **Why it breaks:** `connection.api` no longer exists on the 0.1.2-alpha.2 ClientContext; the call throws at runtime and likely fails typecheck.
- **Migration action:** replace the `agentPresets.list()` call with the 0.1.2-alpha.2 client→host RPC mechanism (per the harness contract, Client halves call Host-exposed JSON methods). **Unconfirmed:** the exact replacement API name — not verifiable from the fixture.

## Items checked and found non-breaking (with caveat)

- `src/client/index.ts:2` — `@deepseek-ai/dsh-client-ui-chat/client` import and `useSession` symbol: no removal card listed in the fixture's hints; treated as unaffected. **Unconfirmed** for 0.1.2-alpha.2 behavioral changes beyond the `nodes` shape (card A1-27).
- `src/client/index.ts:7` — `export const inject = ['slots', 'conversation']`: no card in the fixture names inject-list changes; unaffected per available sources (unconfirmed beyond that).
- `src/client/Pet.tsx` — empty stub; no touchpoints.
- `package.json` — no dependency on `@deepseek-ai/dsh-client-runtime` is declared (only the type import references it), so no dependency entry needs removal; the `dsh.client.platform = "web"` field is not named by any card in the fixture.

## Card-ID source honesty note

All four card IDs (`DSH-0.1.2-A1-25/-26/-27/-30`) and their one-line descriptions come from `fixture/README.md:6` ("Touchpoint hints (maintainer reference, not part of the brief)"). The line-level mapping to `src/client/index.ts` is my own read of the source. Detailed replacement APIs are marked **unconfirmed** because this is a closed-book brief with no upgrade-card text available outside the fixture.

## Read-only discipline

No file under the fixture (or anywhere in the benchmark repository) was created, modified, deleted, or renamed. No builds, installs, or external services were used. Only this report file was written, in the designated output directory.
