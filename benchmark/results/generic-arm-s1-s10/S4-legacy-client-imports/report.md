# Migration Touchpoint Report — S4 · Legacy Client Runtime Touchpoints

**Plugin:** `dsh-pet-session-bench` 0.1.0 (Web Client plugin, `dsh.client.platform: "web"`)
**Corridor:** dsh 0.1.1-rc.2 → dsh 0.1.2-alpha.2
**Mode:** read-only static analysis. No files under the fixture were modified; nothing was built, installed, or executed.

## Method

Following a framework-agnostic migration methodology: (1) inventory every coupling point between the plugin and the host (manifest, host-API imports, lifecycle, services, UI, persistence, config, dependencies), recording file/line and confidence; (2) map each inventory hit to a known upstream change; (3) mark every assertion with its source, and mark anything not verifiable from the given material as "unconfirmed".

**Scanned (complete file list of the fixture):**
- `README.md` (6 lines)
- `package.json` (7 lines)
- `src/client/index.ts` (14 lines)
- `src/client/Pet.tsx` (1 line)

The scan is exhaustive — the fixture contains only these four files, and all four were read in full.

**Source availability note:** This analysis was performed with a generic methodology manual only; the upstream dsh changelog / migration cards for the 0.1.2-alpha.x corridor were *not* available to me. The only document in scope that names specific breaking changes is the fixture's own `README.md`, which contains a maintainer reference list of four touchpoints with their upgrade card IDs. All card-ID mappings below cite that README as their source. The *existence and location* of each touchpoint in code is verified directly against the source files; the *card semantics and IDs* are sourced from the fixture README and should be re-confirmed against the upstream changelog before editing (see §Verification).

## Breaking touchpoints (will break on 0.1.2-alpha.2)

### T1 — Import from removed package `@deepseek-ai/dsh-client-runtime/client`

- **File/line:** `src/client/index.ts:1` — `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'`
- **Plane:** Web Client (client-runtime coupling). The type is consumed at the plugin boundary: `apply(ctx: ClientContext)` at `src/client/index.ts:9`.
- **Upgrade card:** `DSH-0.1.2-A1-25` — removal of the `@deepseek-ai/dsh-client-runtime/client` package. *(Source: fixture `README.md` line 6. Code occurrence verified at `index.ts:1`.)*
- **Migration action:** Stop importing from the removed package. Re-source `ClientContext` (or its replacement type) from whatever package the upstream changelog names as the successor for the client runtime API. The exact replacement module path cannot be determined from the given material — **unconfirmed**; must be looked up in the 0.1.2-alpha.2 changelog/card DSH-0.1.2-A1-25 before editing. Because the import is `import type`, it is erased at runtime, but the type it names anchors the whole `apply(ctx)` signature, so the replacement type's shape must be checked against every `ctx.*` usage (see T3/T4).

### T2 — `__ModuleLoader__.load` registration id does not match `package.json` name

- **File/line:** `src/client/index.ts:10` — `__ModuleLoader__.load('pet-legacy-bundle', () => { ... })`; the loader global is declared at `index.ts:5`. The package name is `dsh-pet-session-bench` (`package.json:2`), so the registration id `'pet-legacy-bundle'` mismatches it (the inline comment at `index.ts:10` itself flags "legacy bundle id, not package name").
- **Plane:** Web Client (module loading / plugin registration seam).
- **Upgrade card:** `DSH-0.1.2-A1-26` — `__ModuleLoader__.load` registration id must equal the `package.json` name. *(Source: fixture `README.md` line 6. Code occurrence verified at `index.ts:10`; package name verified at `package.json:2`.)*
- **Migration action:** Change the registration id to the package name: `__ModuleLoader__.load('dsh-pet-session-bench', ...)`. Whether the card additionally deprecates/replaces `__ModuleLoader__.load` itself cannot be determined from the given material — **unconfirmed**; verify against the card before assuming the API otherwise survives unchanged.

### T3 — `ctx.connection.api` face removed

- **File/line:** `src/client/index.ts:11` — `ctx.connection.api.agentPresets.list().then(...)`; the inline comment itself flags "legacy connection.api face".
- **Plane:** Web Client → Host services/RPC (plugin consuming a host-exposed API surface through the client context).
- **Upgrade card:** `DSH-0.1.2-A1-30` — the `ctx.connection.api` face was removed. *(Source: fixture `README.md` line 6. Code occurrence verified at `index.ts:11`.)*
- **Migration action:** Replace the call with the successor API for listing agent presets named by the changelog/card. The replacement path/shape (e.g., a service accessor, a different `ctx` property, or a request/response channel) cannot be determined from the given material — **unconfirmed**. Note the interaction with T1: the replacement must be typed against whatever replaces `ClientContext`, so T1 and T3 should be edited together and re-typechecked as one unit.

### T4 — Flat `useSession()` `nodes` snapshot removed/changed

- **File/line:** `src/client/index.ts:12–13` — `const { nodes } = useSession(); const first = nodes[0]`; the hook is imported at `index.ts:2` from `@deepseek-ai/dsh-client-ui-chat/client`.
- **Plane:** Web Client (UI/chat session-state consumption).
- **Upgrade card:** `DSH-0.1.2-A1-27` — the flat `nodes` snapshot returned by `useSession()` changed. *(Source: fixture `README.md` line 6. Code occurrence verified at `index.ts:2,12–13`.)*
- **Migration action:** Migrate off the flat `nodes` array to the replacement session-state shape named by the card (e.g., a tree, an ordered id list plus a lookup map, or a selector-based API — the actual shape is **unconfirmed** from the given material). All downstream uses of `nodes` must be updated together; here that is only `nodes[0]` at line 13, but the replacement's ordering/emptiness semantics for "first node" must be verified, since "first element of a flat array" does not automatically map to "root/first child" in a structured shape.

## Inventory items with no known breaking change (scanned, no hit)

Per methodology, a "no hit" is only meaningful with the scan scope stated. These items were found in the inventory but match none of the four changes listed in the fixture README. Absence from that list is **not** proof of safety — the full upstream changelog was not available, so each is marked accordingly:

- `package.json:6` — manifest block `"dsh": { "client": { "platform": "web" } }`. No compatibility-range field exists to bump; whether 0.1.2-alpha.2 requires new/changed manifest fields is **unconfirmed** (no source available).
- `src/client/index.ts:2` — the *package* `@deepseek-ai/dsh-client-ui-chat/client` itself. Only its `useSession()` return shape is flagged (T4); whether the package or this import path otherwise survives is **unconfirmed**.
- `src/client/index.ts:5` — the `__ModuleLoader__` global declaration. Only the id-mismatch rule is flagged (T2); the API's continued existence is **unconfirmed**.
- `src/client/index.ts:7` — `export const inject = ['slots', 'conversation']` (declared injection points / UI contribution coupling). No matching change in the available source; **unconfirmed**.
- `src/client/index.ts:9` — the `apply(ctx)` entry-point convention itself (lifecycle seam). Only the `ctx` type source (T1) and one `ctx` face (T3) are flagged; the entry-point signature convention is **unconfirmed**.
- `src/client/Pet.tsx:1` — `export function Pet() {}`. A stub with no host coupling; imports nothing. No touchpoint.
- Persistence, configuration keys, subprocess/I-O seams, keybindings/themes: **none present** in this plugin (verified by full-file reads of all four files).

## Suggested edit order (per methodology, dependency order)

1. T1 + T3 together (the `ClientContext` type and the `ctx.connection.api` face define each other's replacement).
2. T4 (session-state shape) — independent of T1/T3 but also a client-runtime-facing change.
3. T2 (registration id) — trivial one-token edit; do it before install-time verification since a mismatched id may block loading.
4. Manifest last-check: confirm no new required fields under `dsh.client` for 0.1.2-alpha.2 (**unconfirmed** — needs changelog).

## Verification plan (layered, cheap first — none executed, per the read-only brief)

1. **Static:** typecheck after edits; confirm zero remaining references to `@deepseek-ai/dsh-client-runtime`, `connection.api`, and the flat `nodes` destructure (`grep`-level sweep plus compiler).
2. **Install-time:** host accepts the manifest and registers the plugin under the corrected id (validates T2).
3. **Cold start:** boot the real host with the plugin enabled; watch logs for deprecation/fallback warnings, not just crashes.
4. **Functional probe:** exercise one real path per feature — the `agentPresets.list()` call path (T3) and the session-first-node read (T4) — including behaviors not migrated, to catch silent drift.
5. **Rollback:** keep the 0.1.1-rc.2-era copy installable until the new one passes layers 1–4.

## Honesty / provenance statement

- All four card IDs (`DSH-0.1.2-A1-25`, `-26`, `-27`, `-30`) are taken verbatim from the fixture `README.md` (line 6), the only in-scope document naming them. I did **not** have access to the upstream changelog or the cards themselves, so the *content* of each card beyond the README's one-line summary is **unconfirmed**.
- Before editing, each mapping above should be re-confirmed by: (a) fetching the upstream 0.1.2-alpha.x changelog and each named card; (b) reading the upstream source at the target tag where a card's one-line summary is ambiguous (per methodology: never guess shapes from a one-line changelog entry); (c) re-running this inventory against any additional corridor changes the changelog lists that the fixture README does not mention.
- No fixture file was modified, added, or deleted; no build, install, or execution was performed.
