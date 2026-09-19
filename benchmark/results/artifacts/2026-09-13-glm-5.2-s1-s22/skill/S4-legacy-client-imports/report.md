# S4 · Legacy Client Runtime Touchpoints — Migration Touchpoint Report (Read-Only)

**Task**: read-only touchpoint scan of a 0.1.1-rc.2-era Web Client plugin source against dsh **0.1.2-alpha.2**.
**Skill mode**: A · inspect (read-only; no files under the fixture were modified, no build/reproduction environment was created).
**Corridor**: `0.1.1-rc.2 → 0.1.2-alpha.1 → 0.1.2-alpha.2`, connected via the skill's `from → to` corridor index (rc.2→alpha.1 cards in `references/v0.1.2-alpha.1.md`; alpha.1→alpha.2 curated cards in `references/v0.1.2-alpha.2.md` plus `references/api-migration-0.1.2-alpha.2.md` API-10).

## 0 · Source identity and inventory

- Fixture: 4 files — `package.json`, `README.md`, `src/client/index.ts`, `src/client/Pet.tsx` (static copy; per README it is test material, `"private": true`, never executed).
- `package.json`: `name: "dsh-pet-session-bench"`, `version: 0.1.0`, `"type": "module"`, `dsh.client.platform: "web"`. No `peerDependencies`, no `engines`, no lockfile, no `dsh-plugin.json`, no `cordis.patch.yml` / `cordis.yml` composition file present in the fixture. The `dsh.client.inject` package list is absent — relevant to the A1-25 cleanup action below.
- Plane: **Web Client** plugin (client half only; no host source file present).
- Closed-book note: fixture line numbers below refer to the exact files read; no external/network sources were consulted. All card content is quoted from the skill's `references/` (v0.1.2-alpha.1.md, api-migration-0.1.2-alpha.2.md), which are the in-skill primary sources for this corridor.

## 1 · Breaking touchpoints (all four hits are in `src/client/index.ts`, 14 lines total)

| # | File / line | Code | Plane | Card | Migration action |
|---|---|---|---|---|---|
| 1 | `src/client/index.ts:1` | `import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'` | Web Client | **DSH-0.1.2-A1-25** | `@deepseek-ai/dsh-client-runtime` (incl. the `/client` entry) was removed in alpha.1; symbols split by domain. Replace the type import with `import type { Context as ClientContext } from '@deepseek-ai/cordis'` (verified mapping table in the card) and make the owning package a direct type/dev dependency. Symptom if untouched: typecheck reports a nonexistent module; at runtime the plugin does not enter the boot graph / its assembly row stays pending. |
| 2 | `src/client/index.ts:5,10` | `declare const __ModuleLoader__...` / `__ModuleLoader__.load('pet-legacy-bundle', ...)` — registration id `'pet-legacy-bundle'` ≠ `package.json` name `dsh-pet-session-bench` | Web Client | **DSH-0.1.2-A1-26** | 0.1.2's client-modules scan keys entries/modules/registrations by package name (`Entry name == package name`). Align the `__ModuleLoader__.load` id (normally injected via the tsdown banner `PLUGIN_ID`) to the exact `package.json` `name`; likewise the assembly-row `name` in the (absent here) composition file must use the bare package name, verified with `dsh --profile <name> --dump-config`. Symptom if untouched: startup assertion `loaded without registering "<id>"`, or the client half silently disappears from the boot graph. |
| 3 | `src/client/index.ts:2,12-13` | `import { useSession } from '@deepseek-ai/dsh-client-ui-chat/client'` … `const { nodes } = useSession()`; `nodes[0]` treats the snapshot as a flat `ConversationNode[]` | Web Client | **DSH-0.1.2-A1-27** (durable event window for session content) + **API-10** exact mapping in `references/api-migration-0.1.2-alpha.2.md` | On alpha.2 `ChatSnapshot.nodes` is a **keyed store**, not `ConversationNode[]`. Replace `useSession(session => session?.nodes)` with `useChat(chat => ...)`; iterate `snapshot.order` and call `snapshot.nodes.get(id)` per id (orderedNodes helper in API-10). For raw session-event content (e.g. user message text), go through the SessionBinding durable event window: `sessions.binding(id)` → `binding.eventSource.getSnapshot().entries`, types `SessionBinding`/`SessionEventLikeEntry` from `@deepseek-ai/dsh-api-session-controller/client`. Symptom if untouched: loads but `nodes` is undefined/empty and console reports factory errors. Note (source-level observation, beyond card scope): the fixture calls `useSession()` at module top level outside any React hook/component — the API-10 replacement `ctx.useChat` is also a hook-style call and must live in a component/hook context. |
| 4 | `src/client/index.ts:11` | `ctx.connection.api.agentPresets.list()` — the legacy `connection.api` face | Web Client | **DSH-0.1.2-A1-30** | alpha.1 removed the apiProxy mirror face on `ctx.connection` entirely; client calls throw (and a swallowed catch renders the UI "forever blank" instead of erroring). Branch by session origin: ordinary sessions move history reads to the `session/page` / `session/follow` Remotes (`ctx.remote.<namespace>.<method>` per API-10's one-page conclusion, declaring `remote` + the specific namespace injections); subagent-origin sessions have no usable host RPC for transcripts — serve them from the plugin's own host routes (`agent.session.events` live / `sessionPersistence.inspect` cold, with seed cutting + `afterSeq` deltas). After migration remove any `connection` entry from the client `inject` list — the fixture's `export const inject = ['slots', 'conversation']` (line 7) does not list `connection`, so no removal is needed here, but the dead `ctx.connection.api` call must go. |

## 2 · Non-hits and inapplicable items (with evidence)

- **A1-28 (composer textarea → contenteditable)**: no DOM manipulation, `contenteditable`, `setSelectionRange`, or `HTMLTextAreaElement` anywhere in the fixture (only 4 files; `Pet.tsx` is an empty function component).
- **A1-29 (MarkdownText labels)**: no `MarkdownText` / `ui-primitives` usage.
- **A1-32 / Workspace navigation**: no `ctx.workspaces`, `connectWorkspace`, `pickDirectory`, or workspace snapshot reads.
- **A1-24 (pi-ai duplicate instance)**: no `@earendil-works/pi-ai` dependency; `package.json` has no dependencies at all.
- **alpha.1→alpha.2 curated cards (5)**: persona prefix/suffix split, `SubprocessHandle.pid` removal, base-bundle `tool-str-replace-editor` row drop, launcher `runCli()`/`import.meta.main` gate, pi-ai `^0.84.2`→`^0.85.1` — none intersect this fixture's surfaces (Web Client, no persona/subprocess/launcher/LLM code). Confirmed inapplicable.
- **Classes #1 (source patch), #2 (session events), #4 (host filesystem), #6 (custom channels), #7 (subprocess/output)** of the pre-flight seven-class scan: zero hits across all 4 fixture files.
- `package.json` `dsh` field (`{ "client": { "platform": "web" } }`): kept as-is; A1-25's `dsh.client.inject` cleanup applies only if the plugin later declares that list — with the runtime package gone it must never appear there.

## 3 · Pending / residual risk

- The fixture is a static, partial copy (no composition file, no build config, no lockfile), so enablement-resolution and runtime layers cannot be verified here — unconfirmed by construction. Per the skill, before implementing: run `tsc --skipLibCheck false` once after adding the owning type dependencies to surface the missing declaration chain, then cold-boot a real profile and verify the boot graph contains the plugin with no pending rows and `window.__DSH_BOOT__.entries` carries `"id": "dsh-pet-session-bench"`.
- Whether `'pet-legacy-bundle'` is injected by a tsdown banner or hardcoded cannot be determined from the fixture alone (the `declare const` suggests an ambient global) — unconfirmed; the A1-26 fix must align whichever mechanism produces the id.

## 4 · Rollback

Not applicable — this was a read-only Mode-A inspection; nothing was changed. The fixture must remain untouched relative to git HEAD (per its README).

## 5 · Recommendation summary

All four breaking touchpoints live in `src/client/index.ts`; mapping: line 1 → DSH-0.1.2-A1-25, lines 5/10 → DSH-0.1.2-A1-26, lines 2/12-13 → DSH-0.1.2-A1-27 (+ API-10 exact mapping), line 11 → DSH-0.1.2-A1-30. Migration is confined to the Web Client plane; no Host-plane change is required.
