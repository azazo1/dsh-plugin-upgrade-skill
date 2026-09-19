# S2 · Negative Scan Report — @demo/dsh-minimal-llm → dsh 0.1.2-alpha.2

- **Task**: read-only touchpoint scan (skill `plugin-upgrade`, Mode A · inspect)
- **Fixture** (static copy, read-only, never executed): `environment/fixture/` — `package.json`, `cordis.patch.yml`, `index.js`, `src/session-notes.js`, `README.md`
- **Corridor**: `dsh-v0.1.1-rc.2 → dsh-v0.1.2-alpha.1 → dsh-v0.1.2-alpha.2` (edges connected via the corridor index, not filename order)
- **Face**: Host-side ordinary Cordis plugin (no `dsh.client` in package.json, no browser/client code)

## 0. Configuration and dependency inventory

| Item | Value | Note |
|---|---|---|
| Plugin name / version | `@demo/dsh-minimal-llm` `0.1.0`, `private: true`, ESM | registry-track metadata, private test fixture |
| Entry | `main: index.js`; exports `. ` and `./cordis.patch.yml` | plain JS, no build step |
| DSH cohort | `dependencies: { "@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1" }` | **this package is deleted at 0.1.2-alpha.1** (DSH-0.1.2-A1-01) |
| Composition | `dsh.bundle.patch → ./cordis.patch.yml` (`insert` of `id: minimal-llm`) | profile-composition overlay, not a source patch (API-08 classification) |
| Manifest `dsh-plugin.json` | absent | not adopted; no action |
| Install track | static in-container copy; dsh not installed | scan-only, per brief |

## Touchpoint checkup (@demo/dsh-minimal-llm, 0.1.1-rc.2 → 0.1.2-alpha.2)

| Touchpoint | Hit | File/line | Applicable card | Confidence note |
|---|---:|---|---|---|
| #1 patch / monkey patch | **no** | — | — | `cordis.patch.yml` is profile composition (API-08: "a filename containing `patch` alone is not a hit"); no `patch-package`/`patchedDependencies`/monkey-patching |
| #2 events | **no** | — | — | no `ctx.on(`, `SessionEvent`, `subscribe(`, no event production/persistence |
| #3 services / Remote | **YES** | `index.js:2` `export const inject = ["apiProxy"]`; `index.js:9` `ctx.apiProxy.llm.providers()`; `package.json` dep `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` | **DSH-0.1.2-A1-01** (APIProxy removed; primary), **API-01 ledger** (plane-specific migration), **DSH-0.1.2-A2-03** (dependency graph: the dep package no longer exists), DSH-0.1.2-A2-02 (error handling pattern, secondary) | exact hit; old service key `apiProxy` matches rc.2 identifiers named in A1-01 |
| #4 host directory reads/writes | **no** | — | — | no fs calls, no `DSH_HOME`/`.dsh`/`homedir()`, no path construction |
| #5 UI / commands / tools | **no** | — | — | no `registerCommand`/`ctx.tools`/slots/`dsh-client-runtime`; no `dsh.client` manifest entry, so the client roster is not entered |
| #6 custom HTTP/WS/DOM channels | **no** | — | — | no server/socket/DOM/CSS; plugin only logs to stderr |
| #7 subprocess / output parsing | **no** | — | — | no child_process/spawn; `console.error` is its own stderr, not parsed output |

`src/session-notes.js` was inspected line by line: two pure string/array utility functions (`formatSessionNote`, `chunk`); the word "session" in the filename is historical naming only. Zero host-coupling surface — confirmed no-hit, not assumed.

## Hit mapping to change cards

### DSH-0.1.2-A1-01 · APIProxy removed (breaking, required-if-hit) — primary

The plugin is a **Host-plane** ordinary Cordis plugin (server-side `apply(ctx)`, no client manifest). Per the card's field note and the API-01 ledger:

- The `apiProxy` service and the entire `@deepseek-ai/dsh-host-apiproxy` package are **deleted at alpha.1**; `inject: ["apiProxy"]` makes the plugin stall forever at `pending (waiting for service: apiProxy)` (troubleshooting table symptom), and the install of the dependency itself fails/unresolves on the target cohort.
- **Correct Host-plane migration is NOT `ctx.remote`**: mechanically swapping `apiProxy` → `remote` hangs with `pending (waiting for service: remote)`, because `remote` exists only on the Client face. The Host must inject the owning domain service behind the old call.
- For the one call used here, `llm.providers`:
  - Host plane: `inject: ["llm"]` then `ctx.llm.listProviders()` (the ledger's verified Host pattern).
  - (Client plane, for contrast only — not applicable to this plugin: one old call splits into `ctx.remote.llm.listProviders()` + `listConfigurableProviders()`.)

### DSH-0.1.2-A2-03 · NPM dependency trimming (conditional) — dependency graph

The declared dependency `@deepseek-ai/dsh-host-apiproxy` no longer exists in the target cohort; it must be removed, and whatever package actually owns the consumed surface declared instead (for the Host `llm` service, the service injection comes from the host composition/bundle, not from this plugin's dependencies — confirm against the target tag's package exports). Per the rollup/alpha.2 rules, keep the DSH cohort exact and coherent; do not leave a mixed old/new peer tree.

### DSH-0.1.2-A2-02 · RemoteError vocabulary (secondary)

Only relevant if the call were kept on a Remote face; the current `try/catch` around `ctx.apiProxy.llm.providers()` logs `error.message` only, which is acceptable for diagnostics. After migrating to the Host `llm` service this card's `RemoteResult` branching does not apply (domain-service calls, not Remote calls). Listed for completeness; no required action for the Host-plane fix.

Non-hits with evidence: see the table above; every category was checked with the pre-flight patterns, not skipped.

## Q3: Do the six zero-hit categories prove compatibility with 0.1.2? — **No.**

**Judgment: this plugin is NOT compatible with 0.1.2-alpha.2 as-is, despite six of seven categories being zero-hit — and even the zero-hit result itself proves nothing.** Two independent grounds:

1. **A single hit is enough to break the plugin.** Category #3 is a hard hit: the injected service `apiProxy` and its package no longer exist. The plugin will never activate (pending forever) and its dependency cannot resolve. "Tiny and mostly zero-hit" does not soften a breaking deletion on the one surface it uses.
2. **Zero hits are heuristic non-detections, not compatibility evidence.** The pre-flight explicitly states: "This is a heuristic scan, not proof of compatibility. Zero hits across the seven classes only means 'not detected by the current patterns'; you must still check dependencies/configuration and run a build, a real mount, and functional smoke tests." Specifically, the scan cannot see:
   - **Dependency/configuration facts**: the #4–#7 zero-hit conclusion says nothing about `package.json` — and indeed the broken `dsh-host-apiproxy` dependency lives exactly there, invisible to source-pattern scanning. This fixture is the proof: the decisive incompatibility is a one-line dependency plus one `inject` entry.
   - **Runtime plane / composition facts**: whether the target profile actually provides the services the plugin will inject after migration (e.g. is an `llm` provider mounted in the composed profile), whether activation ends non-pending — only a real cold boot shows this.
   - **Cards are curated, not a complete diff**: "Host UI/performance changes without cards only mean the official material declares no plugin migration action; they do not prove the absence of API or behavior impact."

**What else is needed before concluding compatibility** (mandatory post-migration verification, per the brief recorded here, not executed in this task — fixture is static and non-executable):

1. **Static**: build/typecheck against the target cohort (trivial here — plain JS, no build — so at minimum a syntax/import resolution pass); confirm no `apiProxy`/`dsh-host-apiproxy` residue remains anywhere (source, composition, dependency).
2. **Dependency resolution**: install with the single package manager matching the lockfile; scan the full lockfile for the removed `@deepseek-ai/dsh-host-apiproxy` and any mixed old/new DSH peers.
3. **Enablement resolution**: verify the profile composition still resolves to `@demo/dsh-minimal-llm` (`--dump-config` shows no `pending (waiting for service: ...)` lines — the failure signature of both the old `apiProxy` inject and the wrong `remote` inject).
4. **Runtime**: isolated-profile cold boot of a real dsh 0.1.2-alpha.2 host; confirm entry activation and that required/provided services do not stay pending (skill's `verify-runtime.mjs` layer).
5. **Behavior**: execute the one core path — the migrated `ctx.llm.listProviders()` call — and check the plugin's stderr log shows the success line, plus one failure branch.

## Report per skill structure

- **pre-existing (baseline)**: not collected — fixture is a static copy; dsh not installed; no build/test suite exists to baseline.
- **Completed**: read-only scan of all fixture files; seven-category touchpoint table with evidence; card mapping (A1-01 primary, A2-03 dependency, A2-02 secondary); zero-hit limitation analysis.
- **Skipped**: client-plane migration patterns (API-10, A2-06 `$host`) — plugin has no client face (`dsh.client` absent); A2-01/A2-08 and other cards — touchpoints not hit; no executions, installs, or file modifications anywhere (fixture untouched).
- **Pending/residual risk**: exact Host `llm` service key/method at the target tag must be confirmed against the tag's declarations before implementing (the ledger's Host example shows `listProviders()`, but the card instructs item-by-item confirmation against the target tag — do not migrate from memory); composition availability of an `llm` provider in the target profile unverified.
- **Rollback**: nothing to roll back — this task was read-only; the fixture hash/content is unchanged.
- **Recommendations**: after migrating to `inject: ["llm"]` + `ctx.llm.listProviders()`, consider failing loud on a missing service rather than the current catch-and-log, and treat the stderr diagnostics as the smoke-test assertion point.
