# S5 · Naming Four-State Judgment (Read-Only, Mode A inspect)

**Target**: community plugin `acme/greet` (npm package `dsh-greet` v0.1.0, `private: true`)
**Inputs read**: `dsh-plugin.naming.json`, `package.json`, `README.md` under the fixture directory (unchanged; read-only).
**Registry status**: **no online registry query was performed** (closed-book brief; no network). Every "is this name free?" question is therefore reported as **unknown / not checked**. Nothing below claims "reserved" or "globally available".

## Verdict legend

- **Compatibility error** — the name violates a structural/naming rule; would fail or misresolve regardless of registry state.
- **Collision recommendation** — structurally valid, but the name is generic/unscoped enough that collisions are plausible; prefixing/scoping is recommended, not required.
- **Needs registry context** — verdict depends on who owns a namespace/channel; cannot be decided locally.
- **Unknown** — requires an online registry/coordinate lookup that was not performed.

## Per-surface judgment

| # | Surface | Declared value | Verdict | Reasoning |
|---|---|---|---|---|
| 1 | Plugin short name | `greet` | **Collision recommendation** (no compatibility error) | Short, syntactically valid, no reserved-word or format violation. But it is a generic unprefixed English word in a flat plugin-name space, so collision likelihood is high. A namespaced/prefixed form (the manifest already carries `acme/greet` and `acme-greet` elsewhere) is a recommendation, not an error. |
| 2 | Plugin coordinate | `acme/greet` | **Unknown** | Structural form `namespace/name` is valid, but whether `acme` (and the coordinate itself) is already registered can only be answered by the registry — not queried. |
| 3 | npm package name | `dsh-greet` | **Unknown** | Syntactically valid and does not impersonate the official `@deepseek-ai/dsh-*` scope (it is unscoped, not using the official scope). Availability on npm is unverified — no query performed. Note `package.json` sets `private: true`, which would block `npm publish` entirely; that is the fixture's stated "do not publish" discipline, and must be lifted deliberately before any real publish (observation only — no change made). |
| 4 | Loader id | `acme-greet` | **No finding (locally consistent)** | Matches the declared namespace + name; no unprefixed generic token. Local consistency only — global uniqueness of the loader id is not checkable offline, but no rule violation is visible. |
| 5 | Service name | `search` | **Collision recommendation (warning, not error)** | Unprefixed, highly generic service id in a shared service namespace. This is the classic collide-with-another-provider case (`search` is a name many plugins would pick). Recommend `acme-greet/search` or an `acme-` prefixed id. Per the naming policy this is a warning-tier finding, not a structural error. |
| 6 | Tool name | `acme_greet_hi` | **No finding (locally consistent)** | Namespaced with the plugin's own prefix; syntactically valid. |
| 7 | Command | `acme-greet-hi` | **No finding (locally consistent)** | Namespaced, consistent with the loader id prefix. |
| 8 | Skill name | `greet` | **Collision recommendation** | Same pattern as the plugin short name: valid but generic, in a flat skill-name space shared with the host catalog and other plugins. Recommend prefixing (`acme-greet` or `greet@acme` style per the community standard's skill naming). |
| 9 | Skill provider | `acme-greet-filesystem` | **No finding (locally consistent)** | Namespaced with the plugin's own prefix. |
| 10 | Event name | `web-search/ready` | **Needs registry context (shared channel — informational)** | The scoped channel `web-search/` is **not the plugin's own namespace** (`acme`). Either (a) it intends to emit into an existing shared `web-search` channel owned by another capability — then correctness depends on that channel's actual contract/owner, which is a registry/context question; or (b) it accidentally borrowed a foreign scope — then it should be `acme-greet/ready`. Locally we can only flag it; we cannot confirm which case holds without the channel registry (not consulted). Not a compatibility error on its face. |
| 11 | Settings namespace | `acme-greet` | **No finding (locally consistent)** | Namespaced; consistent with the loader id. |
| 12 | Route | `/api/plugins/acme-greet/hi` (exact) | **No finding (locally consistent)** | Sits under a plugin-namespaced path segment; no collision with a known host route pattern is visible offline. Absolute global uniqueness of HTTP routes cannot be certified without the registry — treated as locally consistent, not globally proven. |

## Negative findings exercised ("no findings ≠ no problems")

1. **Registry availability — unknown for all public coordinates.** Neither the `acme` namespace, the `acme/greet` coordinate, the npm name `dsh-greet`, nor any of the flat-space names (`greet`, `search`, `web-search`) was checked against a live registry. **No "reserved" or "available" claim is made anywhere in this report.** A pre-publish checklist must add an explicit registry/coordinate query step.
2. **Event channel ownership — needs registry context.** `web-search/ready` crosses out of the plugin's own namespace; this report does not assert it is wrong, only that the `web-search` channel's ownership and contract are unverified here.
3. **Consistency of the manifest is local evidence only.** Loader id, settings namespace, command, tool, and route prefixes agreeing with `acme` proves internal coherence, not external registrability.
4. **`private: true`** in `package.json` means a publish attempt would be rejected by npm as-is; per the fixture README this is intentional test discipline. Recorded as an observation; nothing was modified.

## Summary table (four-state counts)

- Compatibility error: **0**
- Collision recommendation: **3** (plugin short name `greet`; service `search`; skill `greet`)
- Needs registry context: **1** (event `web-search/ready` — shared/foreign channel scope)
- Unknown (registry not queried): **2** (coordinate `acme/greet`; npm package `dsh-greet`) — plus the implicit unknown that applies to *every* name's global availability
- Locally consistent / no local finding: loader id, tool, command, skill provider, settings namespace, route

## Skipped / not applicable

- No version-corridor migration cards were consulted: this is a naming judgment on an unpublished plugin, not a DSH host upgrade; the skill's reference corridor cards do not bear on name verdicts.
- No build, mount, install, or reproduction environment was created, per the brief.
- No files under the fixture (or anywhere in the benchmark repository) were modified; the only write is this report in the designated output directory.

## Pending / residual risk

- All "unknown" verdicts require an online registry query (plugin coordinate registry + npm) before publish; this environment is closed-book, so they remain open.
- The `web-search` channel ownership check requires the community channel/event registry or the owning capability's declarations — unavailable here.

## Rollback

No changes were made anywhere; nothing to roll back. (Read-only Mode A inspection.)
