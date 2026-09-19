# S2 · Negative Scan Report — `@demo/dsh-minimal-llm` → dsh 0.1.2-alpha.2

**Scan mode:** read-only static scan of the fixture source (5 files: `package.json`, `cordis.patch.yml`, `index.js`, `src/session-notes.js`, `README.md`). No file under the fixture was modified. This run had **no access to the plugin-upgrade skill**, so the "change cards" are referenced by the touchpoint category and the concrete API/package facts observed, not by canonical card IDs.

## 1. Touchpoint scan — hit / no-hit per category

The seven touchpoint categories scanned (as derived for this migration corridor):

| # | Category | Hit? | Evidence |
|---|----------|------|----------|
| 1 | Host/plugin lifecycle (`apply`, `ctx.effect`, inject declarations) | **No hit (clean usage)** | `index.js` uses `export function apply(ctx)` and wraps its work in `ctx.effect(async () => {...})` — the effect registration pattern itself is the current convention. No raw side effects outside `ctx.effect`, no manual disposers. |
| 2 | Service injection names (`inject: [...]`) | **Hit (shared surface with #3)** | `index.js`: `export const inject = ["apiProxy"]`. The plugin hard-declares the `apiProxy` service as a required dependency; if that service name is renamed/removed in 0.1.2-alpha.2, the plugin never activates (waits forever or fails at load). |
| 3 | Internal services / Remote RPC surface | **HIT (the only real hit)** | `index.js`: `await ctx.apiProxy.llm.providers()` — a 0.1.1-rc.2-style dot-domain Remote call into the host API proxy. Additionally `package.json` declares `"dependencies": { "@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1" }` — a pinned pre-release dependency from an older generation. |
| 4 | Events / `SessionEventMap` | **No hit** | No `ctx.on(...)`, no event names, no session-log writes anywhere in the source. |
| 5 | Client UI (Slots, React, client entry) | **No hit** | No `client.js`, no Slot registration, no React/`createElement` usage, no theme tokens. Host-only plugin. |
| 6 | Tool registration / model-visible surface | **No hit** | No `ctx.tool(...)` or tool-schema contributions; nothing model-visible, so no snapshot/session-log coupling. |
| 7 | Packaging / composition (`package.json`, `cordis.patch.yml`) | **Marginal hit — verify** | `cordis.patch.yml` is a minimal `insert:` of `id: minimal-llm` / `name: "@demo/dsh-minimal-llm"` — structurally fine, but patch-format semantics and the `dsh.bundle.patch` export path in `package.json` must be re-validated against the 0.1.2-alpha.2 bundle/patch loader. The stale `dsh-host-apiproxy@0.0.1-rc.1` dependency (see #3) also lives here. |

**Decoy correctly dispositioned:** `src/session-notes.js` — the filename suggests a session-surface touchpoint, but the file contains only two pure string/array utilities (`formatSessionNote`, `chunk`) with no host imports, no `ctx`, no events, no services. **Zero touchpoints.** Filename "session" is historical naming only.

## 2. Hit → change-card mapping

- **Category #3 (internal service / Remote) → the "legacy `apiProxy` dot-domain Remote → current RPC gateway" change card.** `ctx.apiProxy.llm.providers()` is exactly the legacy call shape; the migration card for internal-service/Remote access governs it. The remediation direction is to call the current LLM capability surface (Service Definition/Consumer) or the current RPC gateway instead of dot-domain `apiProxy` calls.
- **Category #7 → the "dependency/peer-range & bundle patch" change cards.** `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` is a pinned rc-era package; the dependency must be updated to the 0.1.2-alpha.2-compatible package/range (or removed if the service is provided by the host profile). The `cordis.patch.yml` insert must be rechecked against the current patch/bundle loader contract (and the resolver-manifest `dependencies` rule for bare/patch plugins).
- **Category #2 rides along with #3:** the `inject: ["apiProxy"]` declaration must match whatever service name the 0.1.2-alpha.2 surface actually exposes.

## 3. Does "no hits" in six of seven categories mean the plugin is compatible with 0.1.2?

**No. Zero hits ≠ compatible.** Judgment and basis:

1. **A static hit-scan is lexical, not semantic.** It detects *uses of names I searched for*. It cannot detect (a) services that changed contract under the same name, (b) implicit load-order/peer requirements, (c) packaging/loader behavior changes (patch format, manifest `dependencies` enforcement, peer ranges), which never appear as source-level "hits" but break at boot or install time. This fixture itself proves the point: the only substantive breakage (`apiProxy` Remote + stale pinned dependency) sits in the *one* hit category, while category #7's marginal risk (bundle/patch contract) produces almost no source text.
2. **One hit is enough to be incompatible.** The plugin is not "mostly compatible" — its sole runtime behavior depends on `ctx.apiProxy.llm.providers()` and on `dsh-host-apiproxy@0.0.1-rc.1` resolving. If either moved in 0.1.2-alpha.2, the plugin either fails to activate (inject never satisfied) or the call throws at startup. Compatibility is conjunctive, not averaged.
3. **The no-hit categories only support a weaker claim:** "no evidence of coupling to the changed surfaces in categories 1/4/5/6." That is absence of evidence from a name-based scan, not a proof of absence — e.g. a renamed event or a changed Slot contract would be invisible unless I knew the new names, which requires the 0.1.2-alpha.2 changelog/change-card corridor as ground truth.

**What is still needed before concluding compatibility (mandatory post-migration verification, not executed here because the fixture is a static, non-executable copy and dsh is not installed):**

1. **Build/typecheck** of the plugin against the 0.1.2-alpha.2 workspace/type surface (would catch `apiProxy` removal and dependency mismatch mechanically).
2. **Isolated-profile cold boot** — load the plugin in a disposable dsh 0.1.2-alpha.2 profile with nothing else enabled; confirm `apply()` runs, the inject requirement resolves, and no "service not found / waiting for dependency" state.
3. **Functional smoke test** — verify the migrated provider-listing call returns data (the current `console.error` logging in `index.js` is adequate as an observable probe).
4. **Dependency audit** — confirm `@deepseek-ai/dsh-host-apiproxy` is still the right package at a 0.1.2-alpha.2-compatible version, or drop/replace it per the internal-service change card; revalidate `cordis.patch.yml` against the current patch loader.

## Summary

| Question | Answer |
|---|---|
| Touchpoint hits | 1 real hit (#3 internal service/Remote: `apiProxy`), 1 shared (#2 inject name), 1 marginal (#7 packaging/deps); #1/#4/#5/#6 no hits; `src/session-notes.js` is a confirmed zero-hit decoy |
| Cards to apply | Legacy `apiProxy` dot-domain Remote → current service/RPC surface; dependency & bundle-patch/packaging update |
| "Tiny + mostly zero hits ⇒ compatible"? | **No.** Zero-hit categories are absence of evidence; the single hit already makes the plugin incompatible until migrated, and loader/dependency changes are invisible to a name scan. Real verification (build, cold boot, smoke) is required before any compatibility claim. |
