# S2 · Negative Scan — Touchpoint Report for `@demo/dsh-minimal-llm`

**Task**: read-only compatibility scan for migration to dsh `0.1.2-alpha.2`.
**Fixture scanned** (static copy, read-only, never executed or modified): `fixture/` —
`package.json`, `cordis.patch.yml`, `index.js`, `src/session-notes.js`, `README.md`.
**Assumed corridor**: source is written in the 0.1.1-rc.2 style (`index.js` comment says
"0.1.1-rc.2 style: injects apiProxy"; dependency `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1`
matches the rc.2 service/package). Corridor: **0.1.1-rc.2 → 0.1.2-alpha.1 → 0.1.2-alpha.2**.
No lockfile is present in the fixture, so the "from" pin rests on code/dependency evidence only.

## 1. Seven touchpoint categories — hit / no-hit with evidence

| Touchpoint | Hit | Evidence | Note |
|---|---:|---|---|
| #1 source patch / monkey patch | **No** | The only "patch"-named file, `cordis.patch.yml`, is plain profile composition (`insert:` of the plugin id/name), not a host-source patch; no `patchedDependencies`, `patch-package`, `DSH_HARNESS_SOURCE_ROOT`, monkey-patching anywhere. Per API-08, a filename containing "patch" alone is not a hit. | |
| #2 internal event names / persisted events | **No** | No `ctx.on(`, `SessionEvent`, `subscribe(`, no event production or persistence anywhere in the four source files. | |
| #3 internal service probes / Remote | **YES** | `index.js`: `export const inject = ["apiProxy"]` and `await ctx.apiProxy.llm.providers()` inside `ctx.effect(...)`. Package dependency `@deepseek-ai/dsh-host-apiproxy`. | The only code-level hit; see §2. |
| #4 direct host directory reads/writes | **No** | No `DSH_HOME`, `.dsh`, `profiles/`, `homedir()`, `readFile`/`writeFile`/`mkdir` in any file. | |
| #5 internal UI / commands / tool registration | **No** | No `registerCommand`, `ctx.tools`, slots, `dsh-client-runtime`, client modules. This is a Host-plane (server-side) plugin only; no `dsh.client` in package.json. | |
| #6 custom HTTP / WS / RPC / DOM / CSS channel | **No** | No `createServer`, `WebSocket`, routers, loopback URLs, DOM/CSS. `console.error` logging only. | |
| #7 subprocess / stdout / stderr parsing | **No** | No `child_process`, `spawn`, `execa`; no invocation of `dsh`/`headless`/`--profile`. | |

Suspicious-looking file cleared: `src/session-notes.js` — despite the "session" name, it
contains two pure string/array utilities (`formatSessionNote`, `chunk`) with zero host
coupling and is not imported by `index.js` at all. **Zero hits, confirmed by reading, not
by name.**

## 2. Hit touchpoints → change cards

The plugin is a **Host-plane (ordinary server-side Cordis) plugin** — the face matters for
which card recipe applies.

- **DSH-0.1.2-A1-01 · "APIProxy removed, Host/Web Client calls moved to `@Remote`"** (rc.2→alpha.1, breaking, touchpoint #3, required-if-hit).
  - `@deepseek-ai/dsh-host-apiproxy` is **deleted in alpha.1**; the `apiProxy` service key no longer exists. The `inject: ["apiProxy"]` row will leave the plugin permanently pending (`waiting for service: apiProxy`) — exactly the `web boot: N entries did not activate` symptom in the troubleshooting table.
  - Face-correct recipe (per the A1-01 field note): the old `apiProxy` is the **host-plane** facade; a host-plane consumer must NOT switch to `inject: ["remote"]` (`ctx.remote` is the client-plane/browser facade — swapping names one-to-one hangs the plugin forever). Correct: **inject the owning domain service directly** — `inject: ["llm"]` and `ctx.llm.listProviders()`.
  - Note the operation split: old `llm.providers` maps to `llm/listProviders` **plus** `llm/listConfigurableProviders` (one call → two results) on the Remote plane; on the host plane verify what `ctx.llm` exposes in the target tag's generated declarations before choosing the second call.
- **Dependency/packaging consequence (A1-01 + DSH-0.1.2-A2-03 · "NPM packages trim unneeded peer dependencies")**: `package.json` still declares `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1`, a package that no longer exists in the target cohort. The dependency must be removed/replaced with the owning domain package, and the whole `@deepseek-ai/*` cohort kept exact and coherent (no mixed old/new peers). Scan the full resolved tree, not just top-level.
- **DSH-0.1.2-A2-02 · "Remote failures become `RemoteError`; error codes gain namespaces"** — *conditionally applicable only if* the migration instead goes through client-plane `ctx.remote`. This plugin is host-plane, so the A2-02 result-branch discipline applies only if the rewritten call returns a `RemoteResult`; the current `try/catch (error.message)` pattern in `index.js` is exactly the "parse `Error.message` / defensive catch" anti-pattern A2-02 warns about and should not be carried over to Remote-style results.
- Not mapped: A1-02/A2-01 (events) — no producer; API-10/A1-03 (client runtime/session-view) — no client face; A1-08 (channel auth) — no custom channel.

## 3. Do the six zero-hit categories prove compatibility with 0.1.2-alpha.2?

**No. Zero hits ≠ compatible.** Judgment and basis:

1. **This very fixture is the counterexample.** Six of seven categories are zero-hit, yet the
   plugin is definitively **incompatible** with 0.1.2-alpha.2: it injects a deleted service and
   depends on a deleted package (A1-01). The incompatibility is caught by category #3 here, but
   the general point stands — the scan is a *heuristic pattern match over source text*, and
   whole classes of breakage live outside those patterns:
   - **dependencies/configuration are checked separately** from the seven classes (pre-flight step 0): a removed peer, a renamed owning package, a lockfile pin, or a profile-composition change (`cordis.patch.yml` id/bundle-format drift) produces zero source hits;
   - **cards are a curated list, not a complete API diff** — absence of a hit only means "not detected by the current patterns", not "no change";
   - **runtime/activation failure is invisible statically**: a pending service, a wire-format change, or environment/Node-version issues (e.g. A2-04's Node 24.0–24.11.1 window) only appear on a real boot;
   - zero-hit categories still say nothing about the *hit* category's correctness after rewrite — the A1-01 ghost is that a mechanically "obvious" fix (`apiProxy`→`remote`) is wrong for the host plane.

2. **What the zero hits DO support** (weaker claim): the migration surface is narrow. No event,
   filesystem, UI, channel, or subprocess seams need card-by-card work, so the change plan can
   be scoped to #3 plus the dependency block, and the verification can focus on service
   activation + one functional path.

3. **What else is needed before concluding compatibility** (mandatory post-migration steps, per
   the brief not run here):
   - **baseline first**: record pre-existing build/typecheck/test failures before any change, so post-migration failures are attributable;
   - **build/typecheck** against the target cohort (and a one-shot `skipLibCheck: false` pass if any selector silently becomes `any` — A2-03);
   - **dependency-resolution check**: full lockfile/tree scan for the removed `dsh-host-apiproxy` and any stale `@deepseek-ai/*` rows; single package manager, frozen install in an isolated directory;
   - **enablement resolution**: the target profile's composition actually resolves to this package (the `cordis.patch.yml` `insert` row), no old/duplicate rows;
   - **isolated-profile cold boot** (`dsh --profile …`): plugin activates, `inject` resolves, no `waiting for service: …` pending state;
   - **functional smoke**: the rewritten providers-listing path succeeds (and a failure branch behaves sanely), plus teardown;
   - **ghost-host discipline** if verifying against a live host: pin the corridor's `from` to the actually running process generation, not the on-disk checkout.

## Summary

| Touchpoint | Hit | File/line | Applicable card | Confidence |
|---|---:|---|---|---|
| #1 patch | No | — | — | read all 4 source files + both configs |
| #2 events | No | — | — | no producers/observers |
| #3 services/Remote | **Yes** | `index.js` (inject + `ctx.apiProxy.llm.providers()`), `package.json` dep | **DSH-0.1.2-A1-01** (required), A2-03 (dep cohort), A2-02 (only if client-plane Remote) | high |
| #4 filesystem | No | — | — | |
| #5 UI/commands/tools | No | — | — | host-plane plugin, no client face |
| #6 custom channel | No | — | — | |
| #7 subprocess/output | No | — | — | |

**Verdict**: NOT compatible as-is despite "tiny and looks clean". One required breaking change
(A1-01: host-plane `apiProxy` → inject `llm` domain service, drop the deleted
`dsh-host-apiproxy` dependency). Zero-hit categories reduce scope but prove nothing; the
verification list above is mandatory before any compatibility claim.

*Fixture was only read; nothing under the fixture or benchmark repository was modified.*
