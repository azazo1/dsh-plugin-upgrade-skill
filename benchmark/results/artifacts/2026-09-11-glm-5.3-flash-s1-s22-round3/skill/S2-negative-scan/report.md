
# Touchpoint checkup · @demo/dsh-minimal-llm → dsh 0.1.2-alpha.2

Mode: A/C hybrid per the plugin-upgrade skill — **read-only negative scan** of the static fixture at `environment/fixture/` (nothing under the fixture was modified, created, or deleted). No build, install, or migration was executed (the fixture is a static copy; dsh is not installed here — the brief says the required verifications only need to be written down).

## 0. Inventory (pre-flight step 0)

| Item | Value | Evidence |
|---|---|---|
| Plugin | `@demo/dsh-minimal-llm` v0.1.0, `private: true`, ESM | `package.json` |
| Face | Host-plane ordinary Cordis plugin (`main: index.js`, plain `apply(ctx)`, no `dsh.client` key) | `package.json`, `index.js` |
| DSH dependency cohort | `dependencies: { "@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1" }` — rc-era pin | `package.json` |
| Code self-identification | Comment: "0.1.1-rc.2 style: injects apiProxy, dot-domain calls" | `index.js` line 2 |
| Composition | `cordis.patch.yml`: a single `insert` row `{ id: minimal-llm, name: "@demo/dsh-minimal-llm" }` | `cordis.patch.yml` |
| Corridor | rc.2 → 0.1.2-alpha.1 (A1 cards) → 0.1.2-alpha.2 (A2 cards), joined by the `from → to` metadata, not by filename order | references/README.md, v0.1.2-alpha.1.md, v0.1.2-alpha.2.md |

Scan scope: every file in the fixture (`package.json`, `index.js`, `cordis.patch.yml`, `README.md`, `src/session-notes.js`). No generated artifacts, vendor, or node_modules present. Excluded-directories note: none needed.

## 1. Seven-class touchpoint scan — hit/no-hit with evidence

| # | Touchpoint | Hit | Evidence |
|---|---|---|---|
| 1 | Source patch / monkey patch | **No hit** | No `patchedDependencies`, `patch-package`, `DSH_HARNESS_SOURCE_ROOT`, or source-replacement intent anywhere. `cordis.patch.yml` contains only a composition `insert` row — per API-08 this is profile composition, not a source patch; a filename containing `patch` alone is not a hit for this class. |
| 2 | Internal event names / persistent events | **No hit** | No `ctx.on(`, `SessionEvent`, `session/event`, `subscribe(`, or internal event strings (`tool/code-dispatch`, `tools-code-mode`, `connection/reset`). `src/session-notes.js` is the decoy: its filename says "session" but the file is two pure utility functions (`formatSessionNote`, `chunk`) that touch no host coupling surface and produce no events. |
| 3 | Internal service probes / Remote | **HIT** | `index.js` line 4: `export const inject = ["apiProxy"]`; line 12: `await ctx.apiProxy.llm.providers()`; `package.json` dependency `@deepseek-ai/dsh-host-apiproxy` `0.0.1-rc.1`. This is exactly the rc.2-era Host APIProxy surface that alpha.1 deletes. |
| 4 | Direct host directory reads/writes | **No hit** | No `DSH_HOME`, `.dsh`, `profiles/`, `homedir(`, `readFile`, `writeFile`, `mkdir`, `openPath` in any file. |
| 5 | Internal UI / commands / tool registration | **No hit** | No `registerCommand`, `registerView`, `contributes`, `ctx.tools`, `ctx.slots`, `useSession`, `useChat`, `dsh-client-runtime`, `__ModuleLoader__`, `PLUGIN_ID`. No `dsh.client` key in `package.json` — the plugin is not on the Web Client roster, so all client-plane cards are inapplicable by face. |
| 6 | Custom HTTP / WS / RPC / DOM / CSS channels | **No hit** | No `createServer`, `WebSocket`, `router.*(`, `/api/`, `localhost`, `insertRule`, `MutationObserver`, `contenteditable`. The only `console.error(...)` calls in `index.js` are log output, not a channel and not stdout parsing. |
| 7 | Subprocess / stdout / stderr parsing | **No hit** | No `node:child_process`, `spawn`, `exec(Sync)`, `execa`, `--profile`, `headless`. |

## 2. Hit touchpoints mapped to change cards

**Touchpoint #3 → corridor net state, card by card:**

1. **DSH-0.1.2-A1-01 (breaking, required-if-hit, alpha.1) — APIProxy removed.** rc.2's service key `apiProxy` / package `@deepseek-ai/dsh-host-apiproxy` is deleted in alpha.1; `ctx.apiProxy.llm.providers()` will fail at injection/activation. The card's operation table maps `llm.providers` → `llm/listProviders` + `llm/listConfigurableProviders` (one call split into two). Critically, the card's field note pins the plane: this plugin is a **host-plane** consumer, and the correct migration is to **skip the gateway and inject the domain service directly** (`inject: ["llm"]`, then `ctx.llm.listProviders()` / `ctx.llm.listConfigurableProviders()`). Migrating to `ctx.remote.*` on the host plane produces `pending (waiting for service: remote)`; `ctx.remote.*` is only for browser-plane plugins, which this is not.
2. **DSH-0.1.2-A2-02 (breaking, alpha.2) — Remote failures become `RemoteError`.** Applicable **only if** any resulting call surface goes through Remote / `RemoteResult` error control flow. For the recommended host-plane direct-service injection this card is conditional, not required; it must be re-checked after the code shape is decided, not skipped silently.
3. **DSH-0.1.2-A2-03 (behavior, alpha.2) — peer dependency trimming.** Packaging surface: the plugin's direct dependency `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` points at a package that no longer exists in the target cohort. The dependency row must be removed/replaced, the direct dependency on whatever package now owns the consumed declarations must be added, and the DSH cohort kept exact and coherent in `package.json` and the lockfile (a successful install with mixed rc/alpha peers is not a migration).
4. **Corridor net-state note (A1-02 ⇄ A2-01):** alpha.1 removed `SessionEvent.ignorable` and alpha.2 restored it. Net effect for this plugin: **none**, because the plugin produces no session events (#2 no hit) — folded and closed, nothing to do.

No other card intersects the hit touchpoint and the plugin's actual face (Host, ordinary plugin): the Web Client cards (A1-25/A1-26/A1-28–A1-30/A1-32, A2-06), the ACP/headless/PTC cards (A1-04/A1-05/A1-06), and the preset/subagent cards (A1-20/A1-21/A1-31) are all non-hits by both touchpoint and face.

## 3. Do the zero-hit categories prove compatibility with 0.1.2-alpha.2? — **No.**

Judgment: the six no-hit categories give *weak negative evidence only* ("not detected by the current patterns"); they do **not** establish compatibility. Basis:

- The skill's pre-flight header states this verbatim: zero hits across the seven classes "only means 'not detected by the current patterns'; you must still check dependencies/configuration and run a build, a real mount, and functional smoke tests." This plugin is not even in the zero-hit case — it has a confirmed **breaking hit** (#3), so "should have no compatibility problems" is already falsified at the static level.
- The card sets are explicitly **curated lists, not a complete API diff**; a category can be zero-hit here yet still break via an edge the patterns do not cover. Where corridor edges or API coordinates are missing, they must be marked unsupported/pending rather than assumed fine.
- The dependency surface — which the touchpoint classes deliberately do not cover — is the second half of the risk: the pinned `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` cohort row cannot resolve on an alpha.2 host, and A2-03-style peer trimming can surface as implicit-`any` or runtime-missing packages that static greps never see.

### What is still required before concluding compatible (mandatory post-migration verification)

1. **Static:** implement the A1-01 host-plane migration (`inject: ["llm"]` → `ctx.llm.listProviders()` + `listConfigurableProviders()`), fix `package.json`/lockfile to a coherent alpha.2 cohort, then run build + typecheck against the target tag's declarations (one diagnostic pass with `skipLibCheck: false` if any selector turns `any`).
2. **Runtime enablement:** cold-boot a real, isolated `dsh` profile containing the plugin (`skills/plugin-upgrade/scripts/verify-runtime.mjs` does this end-to-end) and verify the entry activates with no service left pending — a successful install alone does not mean DSH enabled the plugin.
3. **Behavior:** one functional smoke through the migrated path — apply() runs and the provider list call succeeds (or fails with a correctly attributed error), i.e. at least one message → tool → response or equivalent dedicated flow.
4. **Residual risk to record:** A2-02 applicability after the code shape is decided; curated-card coverage gap (unsupported-gap check); Node 24.x loader note (A2-04) if `dsh web` is ever involved — currently not, since this is a Host-plane plugin.

Until those steps pass, the honest status is: **one confirmed breaking touchpoint (#3, DSH-0.1.2-A1-01) requiring source change; compatibility not established.**

## Report structure notes

- Pre-existing baseline failures: **not collected** (static fixture; no runnable dependency state — recorded per skill rules for non-Mode-C-baseline runs).
- Skipped (non-hits): categories #1, #2, #4, #5, #6, #7, with the grep-level evidence above; `src/session-notes.js` classified as a no-hit pure-utility decoy.
- Rollback: not applicable — nothing was modified; the fixture is untouched and the report is the only file written.
