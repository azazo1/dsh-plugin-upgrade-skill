# S3 — Snapshot read-surface migration assessment

**Target host:** dsh 0.1.2-alpha.2  
**Source baseline:** dsh 0.1.1-rc.1-style fixture  
**Scope:** read-only assessment; no fixture file was changed and no migration or installation was run.

## Evidence boundary

The authorized material contains the fixture only. A read-only scan of the container found no non-skill upgrade-card catalog, release notes, type declarations, or API reference containing `DSH-0.1.2-*`, `0.1.2-alpha.2`, or the replacement snapshot/read-surface names. The exact card suffixes and normative post-migration identifiers therefore cannot be established from the allowed evidence. They are intentionally not guessed below. This is a documentation blocker for requirements 2 and 3, not an assertion that the migration is optional.

## Inventory of affected surfaces

All affected surfaces are in `fixture/src/client/Pet.tsx`. The slot, locale registration, and Cordis ordering wiring in `fixture/src/client/index.ts:6-43` do not themselves read the snapshot and show no evidence of breaking from this snapshot-only migration.

| Location | Legacy surface that breaks | Required migration semantics | Projection decision | Upgrade card |
|---|---|---|---|---|
| `Pet.tsx:8` | `ConversationSnapshot` imported from `@deepseek-ai/dsh-client-runtime/client` | Replace the removed/changed legacy snapshot type with the 0.1.2-alpha.2 snapshot-read type exported by the runtime, and type selectors against that new read result. The exact exported identifier is not present in the authorized material. | Applies to every selector below; the legacy type cannot be retained as the contract. | **Not verifiable:** no authorized card catalog. |
| `Pet.tsx:13-15` | `isThinking(snapshot: ConversationSnapshot)` and `snapshot.partial?.blocks` | Read reasoning from the new streaming/partial-content read path. Preserve the predicate “any current block has `kind === 'reasoning'`”, but apply it to the new path’s current content/block collection. Do not assume `partial.blocks` survives under the old flat name. | **Immediate new read path.** Nested partial block detail is not safely reconstructible from a coarse compatibility projection; using one can miss reasoning transitions. | **Not verifiable:** no authorized card catalog. |
| `Pet.tsx:19` | `useSession(s => s.running)` | Keep the boolean meaning, but obtain it from the 0.1.2-alpha.2 read API (or its explicitly documented compatibility projection), not from a top-level legacy snapshot selector. The post form must be the documented new hook/read shape, whose name/path is absent here. | **Projection-safe first**, provided the host exposes the documented boolean running projection; it is a scalar aggregate with no historical or nested data. | **Not verifiable:** no authorized card catalog. |
| `Pet.tsx:21` | `useSession(s => s.runningCalls.length > 0)` | Keep the boolean meaning, but obtain active tool-call state from the new activity/call read path or the documented compatibility projection; then test whether the projected active-call collection is non-empty. The exact path/type is absent here. | **Projection-safe first** only if the compatibility projection guarantees the current active-call collection. It must not be projected from completed-call history. | **Not verifiable:** no authorized card catalog. |
| `Pet.tsx:23` | `useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)` | Read the most recent completed-turn end reason from the new turn/event/timeline read path. The required operation is “select the latest completed turn, then read its `reason`”; the replacement collection and hook/read method are absent here. | **Immediate new read path.** This is ordered historical data and cannot be faithfully supplied by a current-state compatibility projection. | **Not verifiable:** no authorized card catalog. |
| `Pet.tsx:20` | Passing `isThinking` directly to the old `useSession` selector surface | Update the selector callback to the new read hook’s callback/input type and new reasoning path. The callback must continue to return a boolean so the existing animation effect remains usable. | **Immediate new read path**, for the same reason as `partial.blocks`. | **Not verifiable:** no authorized card catalog. |

## Compatibility projection versus immediate cutover

The safe staged boundary, based on the data consumed by this fixture, is:

```text
compatibility projection first
  current running boolean
  current active tool-call presence/list

new read path immediately
  current reasoning blocks in the partial/streaming response
  latest completed turn and its end reason
```

The projection is suitable only as a temporary adapter for the two current-state aggregates. It must not be treated as a complete legacy `ConversationSnapshot`: doing so would silently fabricate or omit streaming block detail and turn history. The `isThinking` and `lastTurnEnd` selectors therefore need the new read surface before the host cutover; the `running` and active-call selectors can be staged behind the documented compatibility projection and then moved to the canonical path.

## Card-mapping blocker

Requirement 3 cannot be completed accurately from the allowed inputs. The only card-like identifier supplied by the prompt is the placeholder example `DSH-0.1.2-A1-xx`; it does not identify a real card. Assigning numeric suffixes or inventing replacement API names would make the migration assessment unreliable. The maintainer should supply or authorize the non-skill 0.1.2-alpha.2 upgrade-card/reference document before implementation begins.

## Read-only verification

- Fixture files inspected: `README.md`, `package.json`, `cordis.patch.yml`, `src/client/index.ts`, `src/client/Pet.tsx`, `src/client/locales.ts`.
- No fixture diff was present after inspection.
- No migration, package installation, publish, push, or external-service access was performed.
