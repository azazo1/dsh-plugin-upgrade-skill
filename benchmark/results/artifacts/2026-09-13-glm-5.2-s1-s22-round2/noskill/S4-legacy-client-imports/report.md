# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report

**Task**: read-only scan of a dsh 0.1.1-rc.2-era Web Client plugin (`dsh-pet-session-bench`) ahead of migration to dsh 0.1.2-alpha.2.
**Fixture scanned** (unchanged, read-only): `fixture/package.json`, `fixture/src/client/index.ts`, `fixture/src/client/Pet.tsx`, `fixture/README.md`.
**Method**: static source inspection only. No build, no reproduction environment, no fixture modification.

## Touchpoints that break on 0.1.2-alpha.2

All breaking touchpoints are in the Web Client plane (`src/client/index.ts`); there is no Host-half source in the fixture.

### 1. Import from the removed `@deepseek-ai/dsh-client-runtime/client` package — DSH-0.1.2-A1-25

- **File/line**: `src/client/index.ts:1` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane**: Web Client (type import used by the plugin's `apply(ctx: ClientContext)` at `src/client/index.ts:9`)
- **Upgrade card**: `DSH-0.1.2-A1-25` — removal of the `@deepseek-ai/dsh-client-runtime/client` package (source: `fixture/README.md`, "Touchpoint hints")
- **Why it breaks**: the imported package no longer exists in 0.1.2-alpha.2, so the module (and its `ClientContext` type) cannot resolve.
- **Migration action**: replace the import with the 0.1.2-alpha.2 successor client-context module/package and update the `ClientContext` type reference accordingly. The exact successor import specifier is not present in the fixture and could not be verified closed-book — **unconfirmed (exact replacement specifier)**.

### 2. `__ModuleLoader__.load` registration id ≠ package.json name — DSH-0.1.2-A1-26

- **File/line**: `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', () => { ... })`
- **Plane**: Web Client (plugin module registration with the client module loader)
- **Upgrade card**: `DSH-0.1.2-A1-26` — loader registration id must match the package name (source: `fixture/README.md`)
- **Why it breaks**: the registration id `'pet-legacy-bundle'` does not equal the package name `dsh-pet-session-bench` declared in `package.json:2`; 0.1.2-alpha.2 enforces the match.
- **Migration action**: change the first argument of `__ModuleLoader__.load(...)` from `'pet-legacy-bundle'` to the exact package name `'dsh-pet-session-bench'` (keep the callback unchanged).

### 3. Flat `useSession()` `nodes` snapshot — DSH-0.1.2-A1-27

- **File/line**: `src/client/index.ts:12-13` — `const { nodes } = useSession()` then `const first = nodes[0]`
- **Plane**: Web Client (client-ui-chat session state consumed by the plugin)
- **Upgrade card**: `DSH-0.1.2-A1-27` — the flat `nodes` snapshot shape changed (source: `fixture/README.md`)
- **Why it breaks**: the fixture destructures a flat `nodes` array and indexes it directly; 0.1.2-alpha.2 no longer exposes the snapshot in that flat shape, so both the destructure and the `nodes[0]` access are stale.
- **Migration action**: port the consumer to the 0.1.2-alpha.2 session-snapshot shape from `@deepseek-ai/dsh-client-ui-chat/client` (restructured accessor for session nodes). The exact new accessor/shape is not in the fixture — **unconfirmed (exact new snapshot API)**.

### 4. Removed `ctx.connection.api` face — DSH-0.1.2-A1-30

- **File/line**: `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list().then(presets => { ... })`
- **Plane**: Web Client (Host↔Client RPC surface reached through the client context)
- **Upgrade card**: `DSH-0.1.2-A1-30` — removal of the `ctx.connection.api` face (source: `fixture/README.md`)
- **Why it breaks**: `ctx.connection.api` no longer exists on the 0.1.2-alpha.2 client context, so the `agentPresets.list()` call site fails.
- **Migration action**: replace the `ctx.connection.api.*` call with the 0.1.2-alpha.2 supported Host-call mechanism (per the DSH client plugin model, JSON methods via the package-private RPC channel, e.g. a `host.call(...)`-style invocation for `agentPresets.list`). Exact successor API name is not verifiable from the fixture — **unconfirmed (exact successor call signature)**.

## Non-breaking / supporting observations

- `src/client/index.ts:2` — `import { useSession } from '@deepseek-ai/dsh-client-ui-chat/client'`: the package itself is not flagged by any card in the fixture; only the consumed snapshot shape breaks (touchpoint 3).
- `src/client/index.ts:3` / `src/client/Pet.tsx` — local import and an empty exported component; no card in the fixture flags them.
- `src/client/index.ts:7` — `export const inject = ['slots', 'conversation']`: standard plugin inject declaration; not flagged by any fixture card. **Unconfirmed** whether 0.1.2-alpha.2 renamed either service — no evidence in fixture.
- `package.json` — `"dsh": { "client": { "platform": "web" } }`: not flagged by any fixture card.

## Source & confidence notes

- Card IDs and one-line semantics for all four touchpoints come from `fixture/README.md` ("Touchpoint hints (maintainer reference...)"), the only in-fixture authority; file/line mapping is my own static reading of `src/client/index.ts`.
- This is a closed-book brief: no change-card corpus was available outside the fixture, so the **exact migration code** (successor import specifier, new snapshot accessor, successor Host-call API) is marked **unconfirmed** above rather than guessed.
- Read-only discipline: no file under the fixture (or benchmark repo) was created, modified, deleted, or renamed; no build or reproduction environment was created.
