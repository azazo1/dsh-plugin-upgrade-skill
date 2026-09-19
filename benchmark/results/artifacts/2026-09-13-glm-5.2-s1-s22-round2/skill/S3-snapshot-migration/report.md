# S3 · Snapshot Read-Surface Migration Assessment — bench-pet (read-only)

- **Plugin**: @demo/dsh-bench-pet v0.1.0 (private, Web Client-only plugin; pixel pet in the session header, animation driven by the live conversation snapshot)
- **Corridor**: dsh 0.1.1-rc.1 → 0.1.2-alpha.2 (edges rc.1→rc.2 → alpha.1 → alpha.2, connected by the from→to metadata in references/README.md)
- **Mode**: read-only assessment (plugin-upgrade skill, Mode A / Mode-C planning stage). Nothing inside the fixture was modified; no install, build, or migration was executed.
- **Evidence base**: fixture source (6 files), card sets DSH-0.1.1-R1, DSH-0.1.1-R2, DSH-0.1.2-A1, DSH-0.1.2-A2, and the interface ledger api-migration-0.1.2-alpha.2.md (API-10).

## Pre-existing state (baseline)

Not collected — read-only assessment; the fixture README declares the material “cannot be run”. One pre-existing deviation from the plugin's own claimed era is recorded below (F2).

---

## 1. Breaking surfaces, locations, target forms, and cards

### F1 · dsh-client-runtime still declared in the client manifest inject

- **Location**: package.json → client.inject: ["dsh-client-runtime", "dsh-client-ui-conversation", "dsh-client-locale"]
- **How it breaks**: @deepseek-ai/dsh-client-runtime was deleted in alpha.1. Keeping it in dsh.client.inject is a runtime phantom dependency: the assembly row stays pending forever / the plugin never enters the boot graph, “often without an explicit error”.
- **Card**: **DSH-0.1.2-A1-25** (plus API-10 “Type composition and dependency ownership” item 1)
- **Post-migration form**:

        "dsh.client": {
          "platform": "web",
          "inject": ["dsh-client-ui-conversation", "dsh-client-locale"]
        }

  Keep only packages that actually provide services the client half consumes (the conversation slot owner, the locale owner). Do not add dsh-client-ui-workspace or similar unless the bundle really imports them (per DSH-0.1.2-A1-32's note).

### F2 · Manifest key is "client", not dsh.client

- **Location**: package.json → top-level "client": { "platform": "web", "inject": [...] }
- **How it breaks**: client-modules enumerates packages **only** by the dsh.client declaration. A "client" (or legacy dshClient) key is ignored, so the client half silently never enters the browser plugin roster — no Node-half error at all. This deviation predates the corridor: the dshClient → dsh.client merge and the dsh.client-only scan were already effective in the rc.1 baseline the fixture claims to be written in, so it is a pre-existing latent bug the 0.1.2 migration must fix at the same time.
- **Cards**: **DSH-0.1.1-R1-02** (manifest field merged into dsh.client), **DSH-0.1.1-R1-03** (client-modules scans only dsh.client declarers); still the contract on 0.1.2-alpha.2 (cf. the A1-26 scan contract).
- **Post-migration form**: rename the key to dsh.client with the same value shape (platform "web" + cleaned inject, see F1). Verify the **packed** manifest carries dsh.client, not just the source package.json.

### F3 · ConversationSnapshot imported from the removed runtime package

- **Location**: src/client/Pet.tsx, line 6 — import type { ConversationSnapshot } from '@deepseek-ai/dsh-client-runtime/client'
- **How it breaks**: the package no longer exists; typecheck reports a nonexistent module. With skipLibCheck: true and stale devDependencies the import can instead silently degrade the selector parameter to any — “typecheck green” is not evidence here.
- **Cards**: **DSH-0.1.2-A1-25** (symbol/domain migration table), **DSH-0.1.2-A1-03** (snapshot surface split), API-10 exact mapping.
- **Post-migration form**: there is no same-shape ConversationSnapshot successor. The surface the pet consumes is the chat view snapshot owned by @deepseek-ai/dsh-client-ui-chat/client — ChatSnapshot with the keyed node store (order: string[] plus nodes: Map<id, node>), reached through the useChat selector, or transitionally the legacy projection (see F5). The helper's signature changes accordingly:

        import type { ChatSnapshot } from '@deepseek-ai/dsh-client-ui-chat/client'
        // staged compatibility: the legacy flat projection on the chat view
        function isThinking(chat: ChatSnapshot | undefined): boolean {
          return chat?.legacy.partial?.blocks.some(b => b.kind === 'reasoning') ?? false
        }

### F4 · ClientContext imported from the removed runtime package

- **Location**: src/client/index.ts, line 5 — import type { ClientContext } from '@deepseek-ai/dsh-client-runtime/client'
- **How it breaks**: same package removal as F3.
- **Card**: **DSH-0.1.2-A1-25**
- **Post-migration form**: import type { Context as ClientContext } from '@deepseek-ai/cordis', with the client facets (slots, conversation, locale) merged into Context via type-only imports of the owning packages — the fixture's existing "import type {} from '@deepseek-ai/dsh-client-locale/client'" / ".../dsh-client-ui-conversation/client" lines are exactly this pattern and remain correct. @deepseek-ai/cordis, dsh-client-ui-conversation, dsh-client-ui-slots, and (after F3/F5) dsh-client-ui-chat must be the plugin's **own direct dev/peer dependencies** — a published package's devDependencies are not transitively installed (DSH-0.1.2-A2-03 field note; API-10 dependency-ownership rules). Run one diagnostic typecheck with skipLibCheck: false to prove no declaration chain is missing.

### F5 · Flat snapshot fields read through useSession selectors

- **Location**: src/client/Pet.tsx, Pet() body —
  - useSession(s => s.running)
  - useSession(isThinking) reading snapshot.partial?.blocks
  - useSession(s => s.runningCalls.length > 0)
  - useSession(s => s.turnEnds[s.turnEnds.length - 1]?.reason)
- **How it breaks**: 0.1.2 no longer exposes the per-session flat ConversationSnapshot; the timeline became an internal projection of each view package. Selectors reading partial / runningCalls / turnEnds off the session snapshot stop receiving those fields (undefined → the pet freezes on “idle”), and nodes-shaped reads break outright.
- **Cards**: **DSH-0.1.2-A1-03** (with the dsh-ui-whale field note defining the legacy projection and the two-step migration), **DSH-0.1.2-A1-27** (session content reads rerouted — the principle behind the split), API-10 (useSession(session => session?.nodes) → useChat(chat => ...); keyed order + nodes.get(id)).
- **Post-migration forms** (two-step, per the verified field note: “migrate everything to legacy first, then migrate field-by-field to views/timeline once stable”):

  Step 1 — compatibility projection (the flat fields remain readable there):

        const thinking = useChat(c => c?.legacy.partial?.blocks.some(b => b.kind === 'reasoning') ?? false)
        const toolRunning = useChat(c => (c?.legacy.runningCalls.length ?? 0) > 0)
        const lastTurnEnd = useChat(c => {
          const ends = c?.legacy.turnEnds
          return ends === undefined ? undefined : ends[ends.length - 1]?.reason
        })

  Step 2 — final read paths:
  - node-ordered reads: useChat(chat => chat.order.flatMap(id => { const n = chat.nodes.get(id); return n ? [n] : [] })); an assistant step's final node narrows by type === 'assistant-step' then reads data.finalNode (API-10);
  - turnEnds → the timeline view of the owning view package (the whale note's “field-by-field to views/timeline”);
  - the exact field names for the partial/reasoning surface on the keyed ChatSnapshot are **not spelled out in the corridor cards** — pin them from the target tag's packages/client/ui-chat/src/client/contract/snapshot.ts before writing step 2 (pending, see §3).

### F6 · running is a lifecycle field — no projection coverage

- **Location**: src/client/Pet.tsx — const running = useSession(s => s.running)
- **How it breaks / differs**: per the A1-03 field note, lifecycle fields such as running are **not** part of the views.get('chat')?.legacy projection; they must go through the session seat. The fixture already reads running from the session seat, so the fix is to keep this read on the (surviving) session-seat selector while every other field moves — do not migrate running onto the chat view, and do not assume the legacy projection covers it.
- **Card**: **DSH-0.1.2-A1-03** (field note, dsh-ui-whale migration).

### F7 · Registration id ≠ package name (boot-manifest scan contract)

- **Location**: cordis.patch.yml — insert row { id: bench-pet, name: '@demo/dsh-bench-pet' }; the client bundle's registration id (the __ModuleLoader__.load id, usually injected by the build banner) is presumably "bench-pet" as well.
- **How it breaks**: 0.1.2 keys boot-manifest entries / modules / plugin registrations by package name. Startup assertion loaded without registering "<id>", or — more subtly — the pet silently disappears from the header, the boot graph lacks the plugin, and logs show no plugin-related errors.
- **Card**: **DSH-0.1.2-A1-26**
- **Post-migration form**: all three ids agree with package.json#name as the baseline:
  1. client bundle registration id == "@demo/dsh-bench-pet" (banner PLUGIN_ID);
  2. the assembly row uses the bare package name '@demo/dsh-bench-pet' (no file:/// literal-path + short-name id form);
  3. check with: dsh --profile <name> --dump-config (row names, no pending).
  Verification: window.__DSH_BOOT__.entries contains "id":"@demo/dsh-bench-pet"; the combo route /plugins/??@demo/dsh-bench-pet/client.js&rev=... serves a bundle containing __ModuleLoader__.load({ id: "@demo/dsh-bench-pet" (the scoped name needs URL quoting / curl -g).

### Non-hits (checked, no action)

| Surface | Card checked | Evidence of non-hit |
|---|---|---|
| APIProxy / ctx.connection.api calls | DSH-0.1.2-A1-01, A1-30, A2-02 | The plugin makes no Host calls at all; connection is not in inject. |
| Direct session-content reads (sessions.scope / getSnapshot().nodes) | DSH-0.1.2-A1-27 | Reads go through the slot's useSession seat, not the binding API. |
| Workspace navigation / directory picker / snapshot baselinesReady | DSH-0.1.2-A1-32 | No workspaces usage. |
| Persisted third-party SessionEvents / ignorable | DSH-0.1.2-A1-02, A2-01 | The plugin writes no session events. |
| rc.2 image / Files-API changes | DSH-0.1.1-R2-01…03 | No read_image, attachments, or LLM adapter usage. |
| PTC rename, headless output, auth/bootstrap tokens, settings, composer DOM, MarkdownText labels, user-questions | respective A1/A2 cards | No matching touchpoints (UI is a single header-slot div; no DOM manipulation outside the slot, no markdown rendering, no questions). |
| Slot name conversation.session.header.actions, PropsRuntime/PropsLocale, LocaleNamespaceMap | corridor cards | No card in rc.1→alpha.2 moves this slot or the ui-slots prop helpers (the conversation-slot relocation is a 0.1.5-alpha.2 change, outside this corridor). Keep the existing inject: ['slots', 'conversation', 'locale'] and the nested ctx.inject([...]) registration as-is. |

---

## 2. Compatibility projection vs immediate switch (requirement 4)

**Can run first through the views.get('chat')?.legacy compatibility projection** (flat fields remain readable there — staged migration keeps the pet animating before the field-by-field rework):

- snapshot.partial (the isThinking reasoning-block scan) — F5
- snapshot.runningCalls — F5
- snapshot.turnEnds (last turn-end reason → settle frame) — F5
- snapshot.nodes (not used by this plugin, but the same class) — F5

**Must switch to the new read path immediately — no projection exists:**

- s.running (lifecycle): not in the projection; must go through the session seat right away (F6).
- All import/packaging surfaces: the removed dsh-client-runtime in inject (F1), the ConversationSnapshot/ClientContext imports (F3/F4), the dsh.client manifest key (F2), and the registration-id alignment (F7). None has a compatibility shim; leaving any of them untouched keeps the plugin out of the boot graph or fails typecheck — the pet will not even load, regardless of how the selectors are written.

Recommended sequencing (matches the verified two-step field note): first land F1–F4 + F6–F7 plus legacy-projection selectors (F5 step 1) — the plugin loads and animates on alpha.2; then migrate F5 field-by-field to useChat + keyed store / timeline view once stable.

---

## 3. Pending / residual risk

- Exact keyed-ChatSnapshot field names for partial (reasoning blocks) and the timeline successor of turnEnds are not spelled out in the corridor cards; pin them from the target tag (packages/client/ui-chat/src/client/contract/snapshot.ts and the timeline view package) before writing step-2 code. Per the skill: when corridor edges or API coordinates are missing, mark them pending instead of coding from memory.
- Unpublished cohort: 0.1.2-alpha.x may not be fully installable from the registry; per R-01 in rollup-0.1.2.md, type dependencies may need link: to the official source checkout or tarball overrides, and the whole DSH cohort in package.json + lockfile must move coherently to the exact target.
- Fixture-only gaps: the fixture has no build config, so the banner PLUGIN_ID assumption in F7 and the dsh.client client-entry path must be confirmed against the real build setup; the fixture package.json also omits the client entry path entirely.
- Not verified at runtime (read-only task): boot graph, slot render, and animation behavior on a real alpha.2 host.

## 4. Validation plan (for the eventual migration PR)

1. Static: skipLibCheck: false typecheck (no implicit any in selectors); no dsh-client-runtime residue in imports or dsh.client.inject; direct dev/peer deps own every imported declaration.
2. Loader/config: isolated profile, dsh --profile <p> --dump-config — row name @demo/dsh-bench-pet, no pending rows.
3. Runtime (Web Client): per DSH-0.1.2-A1-19 — token URL → cookie, read window.__DSH_BOOT__.entries, fetch the host-advertised combo URL, prove __ModuleLoader__.load registration and a plugin-owned DOM marker (e.g. .pet with data-frame), not a bare HTTP 200.
4. Behavior: one message → tool call → response turn; assert the frame moves idle → thinking → working and the settle frame after turn end (the core plugin path).
5. Wrapper/artifact: pack and confirm the tarball manifest carries dsh.client, the plugin's own version, and the aligned registration id.

## 5. Rollback baseline (recorded, read-only)

Current state: fixture at @demo/dsh-bench-pet v0.1.0; files package.json, cordis.patch.yml, src/client/{index.ts, Pet.tsx, locales.ts}, README.md — all untouched by this assessment. A future migration should branch/worktree from this state; recovery = revert the branch (no configuration outside the plugin's own files is in scope).

## 6. Recommendations

- After the corridor migration lands, drop the legacy projection entirely (it is staged compatibility only, not a primary data surface for alpha.2-only plugins).
- Add a client test that builds the real ChatNodeStore shape (order + keyed get, missing-id tolerance) instead of old flat-array fixtures.
- Follow the dsh-community-standard manifest (dsh-plugin.json) if the plugin is ever published.
