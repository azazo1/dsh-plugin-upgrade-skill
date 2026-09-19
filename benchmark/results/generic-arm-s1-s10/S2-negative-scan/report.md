# S2 Negative Scan Report — `@demo/dsh-minimal-llm` vs. dsh 0.1.2-alpha.2

**Date:** 2026-09-07
**Scope:** Read-only static scan of `/app/fixture/` (5 files, 43 lines total). No file under the fixture was modified; nothing was installed or executed.
**Method:** Framework-agnostic migration methodology (coupling-surface inventory → corridor mapping → layered verification plan). I do **not** have the dsh-specific changelog, the seven-category touchpoint taxonomy, or the change-card deck; where those are required for a precise answer, I say so explicitly instead of guessing.

---

## 0. What was scanned (basis for every "no hit" below)

Full content read of all five files:

| File | Role |
|---|---|
| `package.json` | Manifest, exports, `dsh.bundle` block, dependencies |
| `index.js` | Entry point (`main` / `exports["."]`) |
| `cordis.patch.yml` | Bundle patch / registration metadata (referenced by `dsh.bundle.patch`) |
| `src/session-notes.js` | Utility module |
| `README.md` | Documentation |

Pattern sweeps (read-only grep) over the whole tree for: host-context usage (`ctx.`, `inject`, imports/requires); process & I/O (`child_process`, `spawn`, `fs.`, sockets, `http`); UI contributions (`command`, `menu`, `view`, `panel`, `theme`, `keybinding`); persistence & configuration (`config`, `setting`, `schema`, `database`, `store`, `session`). Hits found are listed below; sweeps with zero output are the evidence behind the "no hit" rows.

**Taxonomy caveat:** the brief asks for conclusions per "the seven touchpoint categories." That seven-category list is a dsh-specific artifact I was not given. The only category label recoverable from the fixture itself is **#3 "internal service/Remote"** (named in `index.js:1` and `README.md:3`). Rather than invent the other six names, I report against my methodology's generic coupling checklist and map it onto the #3 label where the fixture permits. The mapping of generic categories → the official seven must be confirmed against the actual taxonomy document.

---

## 1. Hit / no-hit per touchpoint category

### Category #3 — Internal service / Remote: **HIT** (the only hit)

| Location | Evidence | What is coupled |
|---|---|---|
| `index.js:3` | `export const inject = ["apiProxy"]` | Declares a hard dependency on the host-provided `apiProxy` service; the host's injector must still recognize the service key `apiProxy`. |
| `index.js:7` | `ctx.effect(async () => { ... })` | Lifecycle/effect scope API on the plugin context. |
| `index.js:9` | `await ctx.apiProxy.llm.providers()` | Call-time use of the `apiProxy` service, dot-domain path `llm.providers()`. Return shape is consumed only via `JSON.stringify`, so the coupling to the payload shape is shallow, but the *existence* of `apiProxy.llm.providers` is load-bearing. |
| `package.json:17` | `"@deepseek-ai/dsh-host-apiproxy": "0.0.1-rc.1"` | A pinned package whose name mirrors the injected service. Whether this package *is* the service implementation, a client stub, or a type-only shim **cannot be determined from the given materials** — but a pinned `0.0.1-rc.1` prerelease dependency against a host moving to `0.1.2-alpha.2` is a classic duplicate-instance / version-skew risk that must be checked. |

Supporting context: `index.js:2` comments that this is "0.1.1-rc.2 style" — i.e. the plugin was written against an intermediate version *below* the 0.1.2-alpha.2 target. Whether `apiProxy` (the inject key, the dot-domain, or the method) survived the 0.1.1-rc.2 → 0.1.2-alpha.2 corridor unchanged **cannot be determined from the given materials**; it requires the upstream changelog / change cards for every version in that corridor.

### Remaining categories: **NO HIT** (with evidence and residual doubt)

| Generic category (official seven-category mapping TBD) | Result | Evidence | Residual doubt |
|---|---|---|---|
| Manifest / metadata & registration | No hit *beyond what is listed above* | `package.json:11-15` (`dsh.bundle.patch`), `exports` map, `cordis.patch.yml:1-3` (single `insert` with `id`/`name`). No compatibility-range field, no permission/capability declarations present at all. | Absence of a declared compatibility range is itself a finding: either the host infers compatibility, or the manifest schema in 0.1.2 requires a field this plugin omits. Cannot tell without the 0.1.2 manifest spec. The `cordis.patch.yml` `insert` schema (keys, required fields) likewise cannot be validated statically. |
| Host API imports (module-level) | No hit | `index.js` and `src/session-notes.js` contain **no `import`/`require` statements at all**; everything arrives via injection on `ctx`. | None for static imports. (Injection is covered under #3.) |
| Lifecycle & events | No hit beyond `ctx.effect` | No `on(...)`/`once(...)` event subscriptions, no dispose hooks; `ctx.effect` already counted under #3. | `ctx.effect` semantics (timing, error swallowing) could change behaviorally without a signature change — a behavioral-change risk, see §3. |
| Services & RPC exposed *by* the plugin | No hit | Plugin exposes no service, no RPC endpoint; it only consumes `apiProxy`. | None. |
| UI contributions | No hit | Sweep for `command|menu|view|panel|theme|keybinding`: zero hits in code. | None for this source tree. |
| Persistence | No hit | No `fs`, database, key-value store, or schema-version code anywhere. `src/session-notes.js` is pure string/array utilities despite the suggestive filename — confirmed by full read, not just the comment. | None for this source tree. No data-migration risk. |
| Process & I/O seams | No hit | Sweep for `child_process|spawn|exec|socket|net\.|http`: zero hits. No parsing of host logs/CLI output. | None. |
| Configuration | No hit | Sweep for `config|setting`: zero hits in code; no settings keys read or written, no documented defaults. | None for this source tree. |
| Dependencies | **Adjacent to the #3 hit** | Sole dependency is `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` (`package.json:17`). No lockfile in the fixture, so the actually-resolved tree cannot be inspected. | Pinned prerelease; duplicate-instance risk if the host also ships this package at a different version. Needs install-tree inspection post-migration. |

---

## 2. Mapping the hit to change cards

**I cannot give card IDs, and I will not invent them.** The change-card deck and the 0.1.1-rc.2 → 0.1.2-alpha.2 changelog were not part of my materials. What I can state precisely is *which* cards need to exist and be checked:

The single hit (touchpoint #3, `apiProxy`) must be mapped to every corridor card that touches any of:

1. the **injection key** `apiProxy` (renamed? removed? merged into another service?),
2. the **dot-domain** `ctx.apiProxy.llm` (restructured? renamed, possibly in two steps A→B→C, in which case the correct migration is straight A→C),
3. the **method** `providers()` (signature, return shape, sync/async),
4. the **`inject` declaration mechanism** itself (`export const inject = [...]` — still the supported contract in 0.1.2?),
5. the **`ctx.effect`** lifecycle API,
6. the **`@deepseek-ai/dsh-host-apiproxy` package** (bumped? deprecated? folded into the host?).

**Process I would follow to produce the exact mapping:** obtain the upstream changelog / release notes for every version in the corridor (start → target inclusive, not just the endpoints); read each change card and classify it as breaking / behavioral / additive / informational; build a net-state table so that a change introduced and reverted mid-corridor nets to zero and a two-step rename is applied directly; then intersect that table with the six coupling points above. Any card whose subject overlaps one of those six strings is a candidate mapping; each candidate is confirmed by reading the upstream source at the target tag rather than trusting a one-line changelog entry.

---

## 3. The key question: do the no-hit categories prove compatibility with 0.1.2?

**No. Zero hits in a static scan is evidence about *this source tree*, not proof about *the host's behavior*.** Basis:

1. **The scan is static; the risk is dynamic.** All six "no hit" conclusions rest on pattern sweeps and full reads of a 43-line source copy. They establish that this plugin *textually* does not touch those surfaces today. They say nothing about whether 0.1.2 changed the *behavior* of surfaces the plugin touches indirectly — e.g. manifest validation getting stricter (rejecting a manifest that omits a newly-required compatibility field), the `insert` schema of `cordis.patch.yml`, injector timing, or effect-scope error handling. Behavioral changes break plugins without any API the scanner could pattern-match.
2. **The one real hit is unverified.** The plugin's entire function depends on `apiProxy.llm.providers()` surviving the corridor, and that is exactly what I could not confirm without the changelog/cards. A single breaking card against `apiProxy` makes this plugin 0% compatible regardless of how many categories are clean. The comment "0.1.1-rc.2 style" in `index.js:2` flags that the code predates the target.
3. **The dependency pin is an unresolved risk outside the categories.** `@deepseek-ai/dsh-host-apiproxy@0.0.1-rc.1` pinned against a 0.1.2-alpha.2 host can produce a duplicate or stale instance of the service layer; a static scan of source cannot detect this — only inspecting the installed tree can.
4. **Unknown-unknowns in the taxonomy.** I could not even verify the official seven-category list, so there may be a category-specific check I structurally could not perform.
5. **Absence of fields is not the same as absence of coupling.** The manifest declares no compatibility range and no permissions. If 0.1.2 *requires* either, the plugin fails at install time — before any of the clean categories matter.

**What is needed before a compatibility conclusion is legitimate** (mandatory post-migration verification, per the layered-verification discipline — cheap layers first, each must pass before the next means anything):

1. **Corridor reading** (prerequisite, not optional): the changelog / change cards for every version from the plugin's baseline through 0.1.2-alpha.2, with the #3-hit mapping from §2 resolved card by card.
2. **Static:** install dependencies and run a build/typecheck/lint of the plugin against the 0.1.2-alpha.2 host types (currently impossible — dsh is not installed in this environment).
3. **Install-time:** the 0.1.2 host accepts `package.json` + `cordis.patch.yml` and loads the plugin with zero manifest warnings.
4. **Cold start (isolated profile):** boot a real 0.1.2 host with the plugin enabled in a throwaway profile/data directory; read logs for deprecation and fallback warnings, not just crashes. Confirm `[minimal-llm] ... 成功` appears, proving `inject` resolution and the `apiProxy.llm.providers()` call path end to end.
5. **Functional probe:** exercise the one feature (provider listing) and verify the output shape is sane — plus confirm nothing else regressed, since silent drift hides in the paths you did not migrate.
6. **Dependency alignment:** inspect the installed tree for duplicate copies of `@deepseek-ai/dsh-host-apiproxy`; align with the host's instance if duplicated.
7. **Rollback rehearsal:** keep the old install runnable side-by-side until the new one passes the layers above; confirm a restore path before touching real data (trivial here — no persistence — but the discipline still applies).

**Bottom-line judgment:** the scan result is "exactly one touchpoint hit (#3, `apiProxy`), everything else clean *as far as static analysis of this tree can tell*." That is a good starting position — the migration surface is genuinely tiny — but the honest answer to "is it compatible with 0.1.2?" is: **undetermined**. It hinges entirely on one unresolved question (did `apiProxy` / `inject` / `ctx.effect` / the apiproxy package survive the corridor?), and that question can only be answered by the changelog/change cards plus the layered runtime verification above — not by any amount of additional static scanning.
